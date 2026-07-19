import importlib.util
import tempfile
import unittest
from pathlib import Path

from banking_agents.local_models import (
    DOCUMENT_MODEL_KEY,
    LOAN_MODEL_KEY,
    LocalAdvisoryModelRuntime,
    LocalAdvisoryModelTrainer,
    LocalTrainingDataCollector,
)
from banking_agents.models import LoanApplication
from banking_agents.repository import LocalRepository
from banking_agents.training_store import ModelTrainingDatabase, TrainingExample


TRAINING_LIBRARIES_AVAILABLE = importlib.util.find_spec("sklearn") is not None


class LocalModelTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = LocalRepository(self.root / "state.json")
        self.repo.seed([LoanApplication("L-PENDING", "INCOME_VARIANCE", declared_income=100, verified_income=70)], [])
        self.database = ModelTrainingDatabase(self.root / "model_training.sqlite3")
        self.collector = LocalTrainingDataCollector(self.repo, self.database, self.root / "missing-exceptions.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_includes_trainable_and_control_components(self):
        result = self.collector.collect(include_synthetic_demo=False)
        report = self.database.status_report()
        by_key = {item["model_key"]: item for item in report["components"]}
        self.assertGreaterEqual(result["catalogued_components"], 8)
        self.assertTrue(by_key[LOAN_MODEL_KEY]["training_supported"])
        self.assertTrue(by_key[DOCUMENT_MODEL_KEY]["training_supported"])
        self.assertFalse(by_key["qwen_document_vision"]["training_supported"])
        self.assertFalse(by_key["india_kyc_agent"]["training_supported"])

    def test_training_store_rejects_pii_feature_names(self):
        self.collector.collect(include_synthetic_demo=False)
        with self.assertRaisesRegex(ValueError, "PII/raw-data"):
            self.database.upsert_example(
                TrainingExample(
                    "unsafe-example",
                    LOAN_MODEL_KEY,
                    "LOAN_APPLICATION",
                    self.database.hash_identifier("L-1"),
                    {"pan": 123.0},
                    1,
                    "POSITIVE",
                    "TEST",
                )
            )

    def test_production_training_fails_closed_without_human_labels(self):
        self.collector.collect(include_synthetic_demo=True)
        trainer = LocalAdvisoryModelTrainer(self.database, self.root / "models")
        with self.assertRaisesRegex(ValueError, "Insufficient human-verified data"):
            trainer.train(LOAN_MODEL_KEY, allow_synthetic_demo=False)

    @unittest.skipUnless(TRAINING_LIBRARIES_AVAILABLE, "scikit-learn is not installed")
    def test_synthetic_demo_training_and_advisory_inference(self):
        result = self.collector.collect(include_synthetic_demo=True)
        self.assertFalse(result["production_training_ready"])
        runs = LocalAdvisoryModelTrainer(self.database, self.root / "models").train_all(allow_synthetic_demo=True)
        self.assertEqual({item["model_key"] for item in runs}, {LOAN_MODEL_KEY, DOCUMENT_MODEL_KEY})
        self.assertTrue(all(item["status"] == "SUCCEEDED" for item in runs))
        self.assertTrue(all(not item["production_ready"] for item in runs))
        runtime = LocalAdvisoryModelRuntime(self.database, self.root / "models")
        prediction = runtime.score_loan(self.repo.get_loan("L-PENDING"))
        self.assertTrue(prediction.advisory_only)
        self.assertGreaterEqual(prediction.positive_probability, 0.0)
        self.assertLessEqual(prediction.positive_probability, 1.0)
        self.assertEqual(self.repo.get_loan("L-PENDING").status, "HELD")

    @unittest.skipUnless(TRAINING_LIBRARIES_AVAILABLE, "scikit-learn is not installed")
    def test_runtime_rejects_tampered_artifact(self):
        self.collector.collect(include_synthetic_demo=True)
        trainer = LocalAdvisoryModelTrainer(self.database, self.root / "models")
        run = trainer.train(LOAN_MODEL_KEY, allow_synthetic_demo=True)
        artifact = Path(run["artifact_path"])
        with artifact.open("ab") as stream:
            stream.write(b"tamper")
        runtime = LocalAdvisoryModelRuntime(self.database, self.root / "models")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            runtime.score_loan(self.repo.get_loan("L-PENDING"))


if __name__ == "__main__":
    unittest.main()
