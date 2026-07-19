from __future__ import annotations

"""SQLite persistence for local model governance and training feedback.

Only de-identified derived features belong in this database. Raw documents,
names, addresses, PAN/Aadhaar values, e-mail addresses, and phone numbers must
remain in approved source systems and are deliberately rejected here.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable


PROHIBITED_FEATURE_NAMES = {
    "aadhaar",
    "address",
    "applicant_name",
    "customer_name",
    "date_of_birth",
    "dob",
    "email",
    "extracted_text",
    "file_bytes",
    "name",
    "pan",
    "phone",
    "raw_document",
    "residential_address",
}


@dataclass(frozen=True)
class ModelComponent:
    model_key: str
    display_name: str
    component_type: str
    implementation: str
    training_supported: bool
    risk_tier: str
    positive_definition: str
    negative_definition: str
    authority_boundary: str
    feature_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrainingExample:
    example_key: str
    model_key: str
    entity_type: str
    entity_id_hash: str
    features: dict[str, float]
    label: int
    label_name: str
    label_source: str
    human_verified: bool = False
    synthetic: bool = False
    observed_at: str | None = None


class ModelTrainingDatabase:
    """Stores the model catalog, labelled examples, runs, and predictions."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_catalog (
                    model_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    component_type TEXT NOT NULL,
                    implementation TEXT NOT NULL,
                    training_supported INTEGER NOT NULL,
                    risk_tier TEXT NOT NULL,
                    positive_definition TEXT NOT NULL,
                    negative_definition TEXT NOT NULL,
                    authority_boundary TEXT NOT NULL,
                    feature_names_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS training_example (
                    example_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    example_key TEXT NOT NULL UNIQUE,
                    model_key TEXT NOT NULL REFERENCES model_catalog(model_key),
                    entity_type TEXT NOT NULL,
                    entity_id_hash TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    label INTEGER NOT NULL CHECK (label IN (0, 1)),
                    label_name TEXT NOT NULL,
                    label_source TEXT NOT NULL,
                    human_verified INTEGER NOT NULL DEFAULT 0,
                    synthetic INTEGER NOT NULL DEFAULT 0,
                    observed_at TEXT,
                    source_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS training_run (
                    run_id TEXT PRIMARY KEY,
                    model_key TEXT NOT NULL REFERENCES model_catalog(model_key),
                    status TEXT NOT NULL,
                    algorithm TEXT NOT NULL,
                    dataset_fingerprint TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    positive_count INTEGER NOT NULL,
                    negative_count INTEGER NOT NULL,
                    human_verified_count INTEGER NOT NULL,
                    synthetic_count INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    artifact_path TEXT,
                    artifact_sha256 TEXT,
                    library_versions_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS model_prediction (
                    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES training_run(run_id),
                    model_key TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id_hash TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    predicted_label INTEGER NOT NULL CHECK (predicted_label IN (0, 1)),
                    positive_probability REAL NOT NULL,
                    advisory_only INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ix_training_example_model
                    ON training_example(model_key, label, label_source);
                CREATE INDEX IF NOT EXISTS ix_training_run_model
                    ON training_run(model_key, status, started_at);
                CREATE INDEX IF NOT EXISTS ix_prediction_model
                    ON model_prediction(model_key, created_at);
                """
            )

    @staticmethod
    def utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def hash_identifier(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _validated_features(features: dict[str, float]) -> dict[str, float]:
        prohibited = sorted(name for name in features if name.lower() in PROHIBITED_FEATURE_NAMES)
        if prohibited:
            raise ValueError(f"PII/raw-data feature names are not allowed: {', '.join(prohibited)}")
        validated: dict[str, float] = {}
        for name, value in features.items():
            if not isinstance(name, str) or not name:
                raise ValueError("Feature names must be non-empty strings.")
            if not isinstance(value, (int, float)):
                raise ValueError(f"Feature {name!r} must be numeric.")
            validated[name] = float(value)
        return validated

    def sync_catalog(self, components: Iterable[ModelComponent]) -> None:
        now = self.utc_now()
        with self._connect() as connection:
            for component in components:
                connection.execute(
                    """
                    INSERT INTO model_catalog(
                        model_key, display_name, component_type, implementation,
                        training_supported, risk_tier, positive_definition,
                        negative_definition, authority_boundary, feature_names_json,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(model_key) DO UPDATE SET
                        display_name=excluded.display_name,
                        component_type=excluded.component_type,
                        implementation=excluded.implementation,
                        training_supported=excluded.training_supported,
                        risk_tier=excluded.risk_tier,
                        positive_definition=excluded.positive_definition,
                        negative_definition=excluded.negative_definition,
                        authority_boundary=excluded.authority_boundary,
                        feature_names_json=excluded.feature_names_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        component.model_key,
                        component.display_name,
                        component.component_type,
                        component.implementation,
                        int(component.training_supported),
                        component.risk_tier,
                        component.positive_definition,
                        component.negative_definition,
                        component.authority_boundary,
                        json.dumps(component.feature_names),
                        now,
                    ),
                )

    def upsert_example(self, example: TrainingExample) -> None:
        features = self._validated_features(example.features)
        features_json = json.dumps(features, sort_keys=True, separators=(",", ":"))
        source_material = json.dumps(
            {
                "model_key": example.model_key,
                "entity_id_hash": example.entity_id_hash,
                "features": features,
                "label": example.label,
                "label_source": example.label_source,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        source_hash = hashlib.sha256(source_material.encode("utf-8")).hexdigest()
        now = self.utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO training_example(
                    example_key, model_key, entity_type, entity_id_hash,
                    features_json, label, label_name, label_source,
                    human_verified, synthetic, observed_at, source_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(example_key) DO UPDATE SET
                    features_json=excluded.features_json,
                    label=excluded.label,
                    label_name=excluded.label_name,
                    label_source=excluded.label_source,
                    human_verified=excluded.human_verified,
                    synthetic=excluded.synthetic,
                    observed_at=excluded.observed_at,
                    source_hash=excluded.source_hash,
                    updated_at=excluded.updated_at
                """,
                (
                    example.example_key,
                    example.model_key,
                    example.entity_type,
                    example.entity_id_hash,
                    features_json,
                    example.label,
                    example.label_name,
                    example.label_source,
                    int(example.human_verified),
                    int(example.synthetic),
                    example.observed_at,
                    source_hash,
                    now,
                    now,
                ),
            )

    def load_examples(self, model_key: str) -> list[TrainingExample]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT example_key, model_key, entity_type, entity_id_hash,
                       features_json, label, label_name, label_source,
                       human_verified, synthetic, observed_at
                FROM training_example
                WHERE model_key = ?
                ORDER BY example_key
                """,
                (model_key,),
            ).fetchall()
        return [
            TrainingExample(
                example_key=row["example_key"],
                model_key=row["model_key"],
                entity_type=row["entity_type"],
                entity_id_hash=row["entity_id_hash"],
                features=json.loads(row["features_json"]),
                label=int(row["label"]),
                label_name=row["label_name"],
                label_source=row["label_source"],
                human_verified=bool(row["human_verified"]),
                synthetic=bool(row["synthetic"]),
                observed_at=row["observed_at"],
            )
            for row in rows
        ]

    def dataset_fingerprint(self, model_key: str) -> str:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT example_key, source_hash FROM training_example WHERE model_key = ? ORDER BY example_key",
                (model_key,),
            ).fetchall()
        material = "\n".join(f"{row['example_key']}:{row['source_hash']}" for row in rows)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def start_run(
        self,
        run_id: str,
        model_key: str,
        algorithm: str,
        dataset_fingerprint: str,
        examples: list[TrainingExample],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO training_run(
                    run_id, model_key, status, algorithm, dataset_fingerprint,
                    sample_count, positive_count, negative_count,
                    human_verified_count, synthetic_count, started_at
                ) VALUES (?, ?, 'RUNNING', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    model_key,
                    algorithm,
                    dataset_fingerprint,
                    len(examples),
                    sum(item.label == 1 for item in examples),
                    sum(item.label == 0 for item in examples),
                    sum(item.human_verified for item in examples),
                    sum(item.synthetic for item in examples),
                    self.utc_now(),
                ),
            )

    def complete_run(
        self,
        run_id: str,
        metrics: dict[str, Any],
        artifact_path: Path,
        artifact_sha256: str,
        library_versions: dict[str, str],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE training_run
                SET status='SUCCEEDED', metrics_json=?, artifact_path=?,
                    artifact_sha256=?, library_versions_json=?, completed_at=?
                WHERE run_id=?
                """,
                (
                    json.dumps(metrics, sort_keys=True),
                    str(artifact_path.resolve()),
                    artifact_sha256,
                    json.dumps(library_versions, sort_keys=True),
                    self.utc_now(),
                    run_id,
                ),
            )

    def fail_run(self, run_id: str, error_message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE training_run SET status='FAILED', error_message=?, completed_at=? WHERE run_id=?",
                (error_message[:2000], self.utc_now(), run_id),
            )

    def latest_successful_run(self, model_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM training_run
                WHERE model_key=? AND status='SUCCEEDED'
                ORDER BY completed_at DESC, started_at DESC
                LIMIT 1
                """,
                (model_key,),
            ).fetchone()
        return dict(row) if row else None

    def record_prediction(
        self,
        run_id: str,
        model_key: str,
        entity_type: str,
        entity_id: str,
        features: dict[str, float],
        predicted_label: int,
        positive_probability: float,
    ) -> None:
        validated = self._validated_features(features)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO model_prediction(
                    run_id, model_key, entity_type, entity_id_hash,
                    features_json, predicted_label, positive_probability,
                    advisory_only, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    run_id,
                    model_key,
                    entity_type,
                    self.hash_identifier(entity_id),
                    json.dumps(validated, sort_keys=True),
                    predicted_label,
                    positive_probability,
                    self.utc_now(),
                ),
            )

    def status_report(self) -> dict[str, Any]:
        with self._connect() as connection:
            catalog_rows = connection.execute("SELECT * FROM model_catalog ORDER BY model_key").fetchall()
            counts = {
                row["model_key"]: {
                    "total": row["total"],
                    "positive": row["positive"],
                    "negative": row["negative"],
                    "human_verified": row["human_verified"],
                    "synthetic": row["synthetic"],
                }
                for row in connection.execute(
                    """
                    SELECT model_key, COUNT(*) total, SUM(label=1) positive,
                           SUM(label=0) negative, SUM(human_verified) human_verified,
                           SUM(synthetic) synthetic
                    FROM training_example GROUP BY model_key
                    """
                ).fetchall()
            }
            run_rows = connection.execute(
                "SELECT * FROM training_run ORDER BY started_at DESC"
            ).fetchall()

        latest_by_model: dict[str, dict[str, Any]] = {}
        for row in run_rows:
            if row["model_key"] in latest_by_model:
                continue
            run = dict(row)
            run["metrics"] = json.loads(run.pop("metrics_json"))
            run["library_versions"] = json.loads(run.pop("library_versions_json"))
            latest_by_model[row["model_key"]] = run

        components = []
        for row in catalog_rows:
            item = dict(row)
            item["training_supported"] = bool(item["training_supported"])
            item["feature_names"] = json.loads(item.pop("feature_names_json"))
            item["examples"] = counts.get(item["model_key"], {"total": 0, "positive": 0, "negative": 0, "human_verified": 0, "synthetic": 0})
            item["latest_run"] = latest_by_model.get(item["model_key"])
            components.append(item)
        return {"database": str(self.db_path.resolve()), "components": components}

    def export_example(self, example: TrainingExample) -> dict[str, Any]:
        """Returns an audit-friendly representation without the source identifier."""
        output = asdict(example)
        output.pop("entity_id_hash", None)
        return output
