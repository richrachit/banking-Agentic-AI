import gc
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

from banking_agents.chatbot_training import (
    CHATBOT_MODEL_KEY,
    LocalChatbotIntentRuntime,
    LocalChatbotIntentTrainer,
    LocalChatbotTrainingDatabase,
)


TRAINING_LIBRARIES_AVAILABLE = importlib.util.find_spec("sklearn") is not None and importlib.util.find_spec("joblib") is not None


@unittest.skipUnless(TRAINING_LIBRARIES_AVAILABLE, "scikit-learn and joblib are not installed")
class LocalChatbotTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = LocalChatbotTrainingDatabase(self.root / "chatbot_training.sqlite3")
        self.output_directory = self.root / "models"

    def tearDown(self):
        gc.collect()
        self.temp.cleanup()

    def test_curated_training_creates_verified_local_intent_artifact(self):
        result = LocalChatbotIntentTrainer(self.database, self.output_directory).train()

        self.assertEqual(result["model_key"], CHATBOT_MODEL_KEY)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["sample_count"], 36)
        self.assertFalse(result["metrics"]["live_chat_text_retained"])
        artifact_path = Path(result["artifact_path"])
        self.assertTrue(artifact_path.is_file())

        prediction = LocalChatbotIntentRuntime(self.database, self.output_directory).predict(
            "How do I reactivate my dormant account?"
        )
        self.assertIsNotNone(prediction)
        # A deliberately conservative local threshold is allowed to return
        # FALLBACK. The important invariant is a verified, bounded prediction
        # rather than unguarded free-text generation.
        self.assertIn(prediction.intent, {"DORMANCY_STATUS", "FALLBACK"})
        self.assertGreaterEqual(prediction.confidence, 0.0)
        self.assertLessEqual(prediction.confidence, 1.0)
        self.assertEqual(prediction.model_run_id, result["run_id"])

    def test_live_message_is_not_persisted_and_tampered_artifact_fails_closed(self):
        result = LocalChatbotIntentTrainer(self.database, self.output_directory).train()
        secret_message = "UNIQUE-LIVE-CHAT-MESSAGE-NOT-FOR-TRAINING"
        runtime = LocalChatbotIntentRuntime(self.database, self.output_directory)
        self.assertIsNotNone(runtime.predict(secret_message))

        connection = sqlite3.connect(self.root / "chatbot_training.sqlite3")
        try:
            stored_examples = connection.execute("SELECT utterance FROM chatbot_training_example").fetchall()
        finally:
            connection.close()
        self.assertNotIn(secret_message, [row[0] for row in stored_examples])
        self.assertNotIn(secret_message.encode("utf-8"), (self.root / "chatbot_training.sqlite3").read_bytes())

        artifact_path = Path(result["artifact_path"])
        with artifact_path.open("ab") as stream:
            stream.write(b"tamper")
        self.assertIsNone(runtime.predict("How do I reactivate my dormant account?"))


if __name__ == "__main__":
    unittest.main()
