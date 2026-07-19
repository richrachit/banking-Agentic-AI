from __future__ import annotations

"""Local, privacy-safe training for the Banking Support Chatbot intent model.

Only curated support phrases are stored here. Live user chat text is never
written to this training store, audit record, or model artifact.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
from typing import Any
from uuid import uuid4


CHATBOT_MODEL_KEY = "banking_support_chatbot"

DEFAULT_INTENT_EXAMPLES: dict[str, tuple[str, ...]] = {
    "WELCOME": (
        "hello", "hi assistant", "help me", "what can you help with",
    ),
    "LOAN_STATUS": (
        "what is my loan status", "where is my application", "show my latest loan",
        "what is the next step for my application",
    ),
    "DOCUMENT_GUIDANCE": (
        "which documents do I need", "how do I upload a bank statement",
        "documents needed for a home loan", "is my aadhaar document required",
    ),
    "CREDIT_GUIDANCE": (
        "how does cibil work", "what is my credit score", "explain credit bureau review",
        "why is there a score review",
    ),
    "DORMANCY_STATUS": (
        "how do I reactivate a dormant account", "what is an inactive account",
        "tell me about dea fund", "unclaimed balance reactivation",
    ),
    "APPROVAL_QUEUE": (
        "how many approvals are pending", "show my review queue",
        "what decisions are waiting", "pending approval status",
    ),
    "AI_EXPLANATION": (
        "which ai agents are used", "how does the automation work",
        "show the ai model registry", "what can the ai agent do",
    ),
    "ACTION_BOUNDARY": (
        "can you approve my loan", "please reject this application",
        "can you transfer the money", "can you verify my kyc",
    ),
    "FALLBACK": (
        "what is the weather", "tell me a joke", "change my profile picture",
        "write a poem about banking",
    ),
}


@dataclass(frozen=True)
class ChatbotIntentPrediction:
    intent: str
    confidence: float
    model_run_id: str


class LocalChatbotTrainingDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chatbot_training_example (
                    example_key TEXT PRIMARY KEY,
                    utterance TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    source TEXT NOT NULL,
                    synthetic INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chatbot_training_run (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    intent_counts_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    artifact_path TEXT,
                    artifact_sha256 TEXT,
                    library_versions_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                """
            )

    def seed_curated_examples(self) -> int:
        count = 0
        now = self.now()
        with self._connect() as connection:
            for intent, phrases in DEFAULT_INTENT_EXAMPLES.items():
                for index, phrase in enumerate(phrases, start=1):
                    key = f"curated:{intent}:{index}"
                    connection.execute(
                        """
                        INSERT INTO chatbot_training_example(
                            example_key, utterance, intent, source, synthetic, created_at, updated_at
                        ) VALUES (?, ?, ?, 'CURATED_LOCAL_DEMO', 1, ?, ?)
                        ON CONFLICT(example_key) DO UPDATE SET
                            utterance=excluded.utterance, intent=excluded.intent, updated_at=excluded.updated_at
                        """,
                        (key, phrase, intent, now, now),
                    )
                    count += 1
        return count

    def examples(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT example_key, utterance, intent FROM chatbot_training_example ORDER BY example_key"
            ).fetchall()

    def start_run(self, run_id: str, examples: list[sqlite3.Row]) -> None:
        counts: dict[str, int] = {}
        for item in examples:
            counts[item["intent"]] = counts.get(item["intent"], 0) + 1
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chatbot_training_run(run_id, status, sample_count, intent_counts_json, started_at)
                VALUES (?, 'RUNNING', ?, ?, ?)
                """,
                (run_id, len(examples), json.dumps(counts, sort_keys=True), self.now()),
            )

    def complete_run(
        self,
        run_id: str,
        metrics: dict[str, Any],
        artifact_path: Path,
        artifact_sha256: str,
        versions: dict[str, str],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE chatbot_training_run
                SET status='SUCCEEDED', metrics_json=?, artifact_path=?, artifact_sha256=?,
                    library_versions_json=?, completed_at=?
                WHERE run_id=?
                """,
                (
                    json.dumps(metrics, sort_keys=True),
                    str(artifact_path.resolve()),
                    artifact_sha256,
                    json.dumps(versions, sort_keys=True),
                    self.now(),
                    run_id,
                ),
            )

    def fail_run(self, run_id: str, error: Exception) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE chatbot_training_run SET status='FAILED', error_message=?, completed_at=? WHERE run_id=?",
                (str(error)[:2000], self.now(), run_id),
            )

    def latest_successful_run(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM chatbot_training_run WHERE status='SUCCEEDED'
                ORDER BY completed_at DESC, started_at DESC LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["metrics"] = json.loads(result.pop("metrics_json"))
        result["intent_counts"] = json.loads(result.pop("intent_counts_json"))
        result["library_versions"] = json.loads(result.pop("library_versions_json"))
        return result

    def status_report(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM chatbot_training_example").fetchone()[0]
            intents = {
                row["intent"]: row["count"]
                for row in connection.execute(
                    "SELECT intent, COUNT(*) count FROM chatbot_training_example GROUP BY intent ORDER BY intent"
                ).fetchall()
            }
        return {
            "database": str(self.path.resolve()),
            "model_key": CHATBOT_MODEL_KEY,
            "sample_count": total,
            "intent_counts": intents,
            "latest_run": self.latest_successful_run(),
            "training_data_policy": "Curated local examples only; live customer messages are not used for training.",
        }


class LocalChatbotIntentTrainer:
    def __init__(self, database: LocalChatbotTrainingDatabase, output_directory: str | Path) -> None:
        self.database = database
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def train(self) -> dict[str, Any]:
        try:
            import joblib
            import sklearn
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import accuracy_score, balanced_accuracy_score
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import Pipeline
        except ImportError as error:
            raise RuntimeError("Install chatbot dependencies: python -m pip install -r requirements-training.txt") from error

        self.database.seed_curated_examples()
        examples = self.database.examples()
        if len(examples) < 18:
            raise ValueError("At least 18 curated chatbot examples are required.")
        texts = [item["utterance"] for item in examples]
        labels = [item["intent"] for item in examples]
        run_id = f"{CHATBOT_MODEL_KEY}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        self.database.start_run(run_id, examples)
        try:
            train_texts, test_texts, train_labels, test_labels = train_test_split(
                texts, labels, test_size=0.25, random_state=42, stratify=labels
            )
            evaluation = Pipeline(
                [
                    ("vectorizer", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                    ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
                ]
            )
            evaluation.fit(train_texts, train_labels)
            predicted = evaluation.predict(test_texts)
            metrics = {
                "accuracy": float(accuracy_score(test_labels, predicted)),
                "balanced_accuracy": float(balanced_accuracy_score(test_labels, predicted)),
                "train_count": len(train_texts),
                "test_count": len(test_texts),
                "evaluation_scope": "CURATED_LOCAL_DEMO_NOT_PRODUCTION_VALIDATION",
                "live_chat_text_retained": False,
            }
            pipeline = Pipeline(
                [
                    ("vectorizer", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                    ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
                ]
            )
            pipeline.fit(texts, labels)
            artifact_path = self.output_directory / f"{run_id}.joblib"
            artifact = {
                "artifact_schema_version": 1,
                "model_key": CHATBOT_MODEL_KEY,
                "run_id": run_id,
                "pipeline": pipeline,
                "minimum_confidence": 0.42,
                "live_chat_text_retained": False,
            }
            joblib.dump(artifact, artifact_path, compress=3)
            artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            versions = {
                "python": platform.python_version(),
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            }
            self.database.complete_run(run_id, metrics, artifact_path, artifact_hash, versions)
            return {**self.database.latest_successful_run(), "model_key": CHATBOT_MODEL_KEY}
        except Exception as error:
            self.database.fail_run(run_id, error)
            raise


class LocalChatbotIntentRuntime:
    def __init__(self, database: LocalChatbotTrainingDatabase, model_directory: str | Path) -> None:
        self.database = database
        self.model_directory = Path(model_directory).resolve()

    def predict(self, message: str) -> ChatbotIntentPrediction | None:
        run = self.database.latest_successful_run()
        if run is None:
            return None
        path = Path(run["artifact_path"]).resolve()
        if path.parent != self.model_directory or not path.exists():
            return None
        if hashlib.sha256(path.read_bytes()).hexdigest() != run["artifact_sha256"]:
            return None
        try:
            import joblib
        except ImportError:
            return None
        artifact = joblib.load(path)
        if artifact.get("model_key") != CHATBOT_MODEL_KEY or artifact.get("run_id") != run["run_id"]:
            return None
        probabilities = artifact["pipeline"].predict_proba([message])[0]
        labels = artifact["pipeline"].classes_
        index = int(probabilities.argmax())
        confidence = float(probabilities[index])
        intent = str(labels[index]) if confidence >= float(artifact.get("minimum_confidence", 0.42)) else "FALLBACK"
        return ChatbotIntentPrediction(intent, confidence, run["run_id"])
