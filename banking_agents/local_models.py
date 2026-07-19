from __future__ import annotations

"""Local advisory model training and verified inference.

The trained classifiers in this module are routing aids only. They never
mutate a loan/account, establish KYC, approve a deviation, or move money.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
from typing import Any
from uuid import uuid4

from .document_verification import DocumentVerificationModel
from .models import LoanApplication, LoanStatus
from .repository import LocalRepository
from .training_store import ModelComponent, ModelTrainingDatabase, TrainingExample


LOAN_MODEL_KEY = "loan_exception_resolution_advisory"
DOCUMENT_MODEL_KEY = "document_review_advisory"

LOAN_FEATURES = (
    "exception_missing_document",
    "exception_transient_failure",
    "exception_income_variance",
    "exception_unsupported",
    "product_personal",
    "product_home",
    "product_business",
    "required_document_count",
    "received_document_count",
    "valid_document_ratio",
    "missing_document_ratio",
    "invalid_document_ratio",
    "pending_document_ratio",
    "income_variance_ratio",
    "verification_attempts",
    "requested_amount_to_annual_income",
)

DOCUMENT_FEATURES = (
    "quality_score",
    "issue_count",
    "text_length",
    "missing_page_signal",
    "signature_issue_signal",
    "illegible_signal",
    "empty_signal",
    "supported_extension",
)


MODEL_COMPONENTS = (
    ModelComponent(
        LOAN_MODEL_KEY,
        "Loan exception resolution advisory",
        "TRAINABLE_ADVISORY",
        "scikit-learn LogisticRegression",
        True,
        "HIGH",
        "Pattern resembles an exception that can be resolved under existing deterministic controls.",
        "Pattern resembles a case requiring customer evidence or authorised human review.",
        "Prediction is explanatory routing only; policy and approval state machines remain authoritative.",
        LOAN_FEATURES,
    ),
    ModelComponent(
        DOCUMENT_MODEL_KEY,
        "Document review advisory",
        "TRAINABLE_ADVISORY",
        "scikit-learn LogisticRegression",
        True,
        "HIGH",
        "Derived quality signals resemble a readable document suitable for the next review step.",
        "Derived signals resemble a document that needs replacement or human investigation.",
        "Cannot authenticate a document, establish identity, or approve a loan.",
        DOCUMENT_FEATURES,
    ),
    ModelComponent(
        "qwen_document_vision",
        "Qwen2.5-VL document vision provider",
        "PRETRAINED_FOUNDATION_MODEL",
        "Qwen/Qwen2.5-VL-3B-Instruct through transformers",
        False,
        "HIGH",
        "Produces readable classification/extraction observations for review.",
        "Produces uncertainty, quality, mismatch, or tamper concerns for review.",
        "Inference remains PENDING; no local fine-tuning corpus or approval authority is present.",
    ),
    ModelComponent(
        "baseline_document_provider",
        "Baseline document provider",
        "DETERMINISTIC_VALIDATOR",
        "BaselineDocumentAIProvider",
        False,
        "HIGH",
        "Supported non-empty file is routed as PENDING.",
        "Missing, empty, or unsupported file is marked INVALID.",
        "File safety check only; not a learned model or authenticity check.",
    ),
    ModelComponent(
        "document_verification_rules",
        "Product document verification rules",
        "DETERMINISTIC_POLICY",
        "DocumentVerificationModel",
        False,
        "HIGH",
        "Every product-required document has VALID evidence.",
        "Evidence is missing, pending, invalid, expired, or unreadable.",
        "Requirements must be policy-controlled and cannot be replaced by a learned prediction.",
    ),
    ModelComponent(
        "india_kyc_agent",
        "India KYC control agent",
        "DETERMINISTIC_CONTROL",
        "IndiaKycAIAgent",
        False,
        "CRITICAL",
        "Consent and every approved-provider KYC prerequisite are satisfied.",
        "Consent, format, sanctions, document risk, face match, or external verification needs review.",
        "AI cannot establish identity; issuer/CKYCR/OVD/V-CIP and authorised human controls are required.",
    ),
    ModelComponent(
        "credit_bureau_decision_agent",
        "Credit-bureau policy agent",
        "DETERMINISTIC_CONTROL",
        "CreditBureauDecisionAgent",
        False,
        "CRITICAL",
        "A high external bureau score continues to document, KYC, affordability, and fraud checks.",
        "A low score follows the versioned adverse-decision path; no-hit/intermediate scores require human review.",
        "Consumes an authorised external signal; it does not recreate CIBIL, and a score alone cannot approve/disburse a loan.",
    ),
    ModelComponent(
        "loan_exception_agent",
        "Loan exception workflow agent",
        "DETERMINISTIC_ORCHESTRATOR",
        "LoanExceptionAgent",
        False,
        "HIGH",
        "In-policy evidence/retry/variance path returns the case to the main journey.",
        "Missing evidence, unsupported conditions, or deviations create a customer/human task.",
        "Cannot override credit policy or disburse funds.",
    ),
    ModelComponent(
        "dormancy_agent",
        "Dormancy and unclaimed-balance agent",
        "DETERMINISTIC_ORCHESTRATOR",
        "DormancyAgent",
        False,
        "CRITICAL",
        "Account follows the configured outreach, dormancy, transfer, and claim sequence.",
        "An action is blocked when its clock, evidence, identity, or approval prerequisite is absent.",
        "Statutory clocks, compliance approval, transfers, and claims must never be learned decisions.",
    ),
    ModelComponent(
        "operations_automation_agent",
        "Operations automation supervisor",
        "DETERMINISTIC_ORCHESTRATOR",
        "OperationsAutomationAgent",
        False,
        "CRITICAL",
        "Delegates eligible work and reports pending human actions.",
        "Leaves blocked or unapproved actions pending without bypassing controls.",
        "Cannot approve deviations, KYC, transfers, claims, or disbursement.",
    ),
)


@dataclass(frozen=True)
class AdvisoryPrediction:
    model_key: str
    run_id: str
    predicted_label: int
    label_name: str
    positive_probability: float
    advisory_only: bool = True


def loan_features(loan: LoanApplication) -> dict[str, float]:
    """Creates de-identified, status-independent loan features."""
    product = loan.loan_product.upper().strip()
    exception = loan.exception_code.upper().strip()
    requirements = set(DocumentVerificationModel().requirements_for(product))
    requirements.update(item.upper().strip() for item in loan.requested_documents)
    evidence = {item.upper().strip(): "VALID" for item in loan.documents}
    evidence.update({name.upper().strip(): status.upper().strip() for name, status in loan.document_evidence.items()})
    received = set(evidence)
    denominator = max(1, len(requirements))
    valid = sum(evidence.get(name) == "VALID" for name in requirements)
    invalid = sum(evidence.get(name) in {"INVALID", "EXPIRED", "UNREADABLE"} for name in requirements)
    pending = sum(evidence.get(name) == "PENDING" for name in requirements)
    missing = sum(name not in received for name in requirements)
    if loan.declared_income > 0:
        income_variance = min(5.0, abs(loan.declared_income - loan.verified_income) / loan.declared_income)
    elif exception == "INCOME_VARIANCE":
        income_variance = 5.0
    else:
        income_variance = 0.0
    annual_income = loan.monthly_income * 12
    amount_ratio = min(20.0, loan.requested_amount / annual_income) if annual_income > 0 else 0.0
    return {
        "exception_missing_document": float(exception == "MISSING_DOCUMENT"),
        "exception_transient_failure": float(exception == "VERIFY_TRANSIENT_FAILURE"),
        "exception_income_variance": float(exception == "INCOME_VARIANCE"),
        "exception_unsupported": float(exception not in {"MISSING_DOCUMENT", "VERIFY_TRANSIENT_FAILURE", "INCOME_VARIANCE"}),
        "product_personal": float(product == "PERSONAL"),
        "product_home": float(product == "HOME"),
        "product_business": float(product == "BUSINESS"),
        "required_document_count": float(len(requirements)),
        "received_document_count": float(len(received)),
        "valid_document_ratio": valid / denominator,
        "missing_document_ratio": missing / denominator,
        "invalid_document_ratio": invalid / denominator,
        "pending_document_ratio": pending / denominator,
        "income_variance_ratio": income_variance,
        "verification_attempts": float(min(5, max(0, loan.verification_attempts))),
        "requested_amount_to_annual_income": amount_ratio,
    }


def document_features(
    quality_score: float,
    issues: list[str],
    extracted_text_length: int,
    file_name: str,
) -> dict[str, float]:
    normalized_issues = " ".join(issues).lower()
    suffix = Path(file_name).suffix.lower()
    return {
        "quality_score": max(0.0, min(1.0, float(quality_score) / 100.0)),
        "issue_count": float(min(20, len(issues))),
        "text_length": min(10.0, max(0, extracted_text_length) / 1000.0),
        "missing_page_signal": float("missing page" in normalized_issues),
        "signature_issue_signal": float("signature" in normalized_issues),
        "illegible_signal": float("illegible" in normalized_issues or "blur" in normalized_issues),
        "empty_signal": float("empty" in normalized_issues),
        "supported_extension": float(suffix in {".pdf", ".png", ".jpg", ".jpeg"}),
    }


class LocalTrainingDataCollector:
    """Builds a de-identified local data set and clearly marks label quality."""

    def __init__(
        self,
        repository: LocalRepository,
        database: ModelTrainingDatabase,
        exception_db_path: str | Path | None = None,
    ) -> None:
        self.repository = repository
        self.database = database
        self.exception_db_path = Path(exception_db_path) if exception_db_path else None

    def collect(self, include_synthetic_demo: bool = False) -> dict[str, Any]:
        self.database.sync_catalog(MODEL_COMPONENTS)
        added = {LOAN_MODEL_KEY: 0, DOCUMENT_MODEL_KEY: 0}
        real = 0
        synthetic = 0

        loans = {loan.application_id: loan for loan in self.repository.list_loans()}
        for loan in loans.values():
            label: int | None = None
            label_name = ""
            if loan.status == LoanStatus.READY_FOR_MAIN_JOURNEY.value:
                label, label_name = 1, "POSITIVE_RESOLVED"
            elif loan.status == LoanStatus.REJECTED.value:
                label, label_name = 0, "NEGATIVE_REVIEW_OR_REWORK"
            if label is not None:
                self._save_loan_example(
                    f"local-loan-status:{loan.application_id}",
                    loan,
                    label,
                    label_name,
                    "WORKFLOW_TERMINAL_STATUS",
                    human_verified=False,
                )
                added[LOAN_MODEL_KEY] += 1
                real += 1

        for approval in self.repository.list_approvals():
            if approval.kind != "LOAN_DEVIATION" or approval.status not in {"APPROVED", "REJECTED"}:
                continue
            loan = loans.get(approval.entity_id)
            if loan is None:
                continue
            label = int(approval.status == "APPROVED")
            self._save_loan_example(
                f"local-loan-approval:{approval.approval_id}",
                loan,
                label,
                "POSITIVE_HUMAN_APPROVED" if label else "NEGATIVE_HUMAN_REJECTED",
                "HUMAN_APPROVAL",
                human_verified=True,
            )
            added[LOAN_MODEL_KEY] += 1
            real += 1

        document_count = self._collect_document_rows()
        added[DOCUMENT_MODEL_KEY] += document_count
        real += document_count

        if include_synthetic_demo:
            loan_count, document_count = self._seed_synthetic_examples()
            added[LOAN_MODEL_KEY] += loan_count
            added[DOCUMENT_MODEL_KEY] += document_count
            synthetic += loan_count + document_count

        return {
            "catalogued_components": len(MODEL_COMPONENTS),
            "examples_processed_by_model": added,
            "real_or_weak_label_examples_processed": real,
            "synthetic_demo_examples_processed": synthetic,
            "production_training_ready": self._production_training_ready(),
            "note": "Synthetic and rule-derived labels validate the pipeline only; they are not production evidence.",
        }

    def _save_loan_example(
        self,
        example_key: str,
        loan: LoanApplication,
        label: int,
        label_name: str,
        label_source: str,
        human_verified: bool,
        synthetic: bool = False,
    ) -> None:
        self.database.upsert_example(
            TrainingExample(
                example_key=example_key,
                model_key=LOAN_MODEL_KEY,
                entity_type="LOAN_APPLICATION",
                entity_id_hash=self.database.hash_identifier(loan.application_id),
                features=loan_features(loan),
                label=label,
                label_name=label_name,
                label_source=label_source,
                human_verified=human_verified,
                synthetic=synthetic,
            )
        )

    def _collect_document_rows(self) -> int:
        if self.exception_db_path is None or not self.exception_db_path.exists():
            return 0
        connection = sqlite3.connect(self.exception_db_path)
        connection.row_factory = sqlite3.Row
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='loan_exception_documents'"
            ).fetchone()
            if not table:
                return 0
            rows = connection.execute(
                """
                SELECT id, file_name, extracted_text, quality_score, issues,
                       requires_human_review
                FROM loan_exception_documents
                ORDER BY id
                """
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            issues = [item for item in (row["issues"] or "").split("|") if item]
            label = int(not bool(row["requires_human_review"]))
            self.database.upsert_example(
                TrainingExample(
                    example_key=f"local-document-row:{row['id']}",
                    model_key=DOCUMENT_MODEL_KEY,
                    entity_type="LOAN_DOCUMENT",
                    entity_id_hash=self.database.hash_identifier(f"document-row-{row['id']}"),
                    features=document_features(
                        row["quality_score"] or 0,
                        issues,
                        len(row["extracted_text"] or ""),
                        row["file_name"] or "",
                    ),
                    label=label,
                    label_name="POSITIVE_USABLE_PATTERN" if label else "NEGATIVE_REVIEW_PATTERN",
                    label_source="WEAK_RULE_DERIVED",
                    human_verified=False,
                    synthetic=False,
                )
            )
        return len(rows)

    def _seed_synthetic_examples(self) -> tuple[int, int]:
        loan_count = 0
        for product in ("PERSONAL", "HOME", "BUSINESS"):
            requirements = DocumentVerificationModel().requirements_for(product)
            for variant in range(4):
                evidence = {name: "VALID" for name in requirements}
                positive = LoanApplication(
                    f"SYN-LOAN-DOC-P-{product}-{variant}",
                    "MISSING_DOCUMENT",
                    loan_product=product,
                    document_evidence=evidence,
                    monthly_income=50000 + variant * 5000,
                    requested_amount=300000 + variant * 25000,
                )
                self._save_loan_example(
                    f"synthetic-loan-doc-positive:{product}:{variant}",
                    positive,
                    1,
                    "POSITIVE_RESOLVED",
                    "SYNTHETIC_DEMO",
                    False,
                    True,
                )
                loan_count += 1
                negative_evidence = evidence.copy()
                negative_evidence[requirements[variant % len(requirements)]] = ("EXPIRED" if variant % 2 else "UNREADABLE")
                negative = LoanApplication(
                    f"SYN-LOAN-DOC-N-{product}-{variant}",
                    "MISSING_DOCUMENT",
                    loan_product=product,
                    document_evidence=negative_evidence,
                    monthly_income=50000,
                    requested_amount=500000,
                )
                self._save_loan_example(
                    f"synthetic-loan-doc-negative:{product}:{variant}",
                    negative,
                    0,
                    "NEGATIVE_REVIEW_OR_REWORK",
                    "SYNTHETIC_DEMO",
                    False,
                    True,
                )
                loan_count += 1

        for attempt in range(6):
            label = int(attempt >= 2)
            loan = LoanApplication(
                f"SYN-LOAN-RETRY-{attempt}",
                "VERIFY_TRANSIENT_FAILURE",
                verification_attempts=attempt,
            )
            self._save_loan_example(
                f"synthetic-loan-retry:{attempt}",
                loan,
                label,
                "POSITIVE_RESOLVED" if label else "NEGATIVE_REVIEW_OR_REWORK",
                "SYNTHETIC_DEMO",
                False,
                True,
            )
            loan_count += 1

        for index, ratio in enumerate((0.0, 0.02, 0.05, 0.08, 0.10, 0.11, 0.15, 0.25, 0.40, 0.70)):
            label = int(ratio <= 0.10)
            declared = 100000.0
            loan = LoanApplication(
                f"SYN-LOAN-INCOME-{index}",
                "INCOME_VARIANCE",
                declared_income=declared,
                verified_income=declared * (1 - ratio),
                monthly_income=declared / 12,
                requested_amount=300000,
            )
            self._save_loan_example(
                f"synthetic-loan-income:{index}",
                loan,
                label,
                "POSITIVE_RESOLVED" if label else "NEGATIVE_REVIEW_OR_REWORK",
                "SYNTHETIC_DEMO",
                False,
                True,
            )
            loan_count += 1

        positive_documents = [
            (100, [], 1600, "pan.pdf"),
            (96, [], 1300, "aadhaar.png"),
            (92, [], 2100, "statement.pdf"),
            (88, [], 900, "salary.jpg"),
            (84, [], 700, "address.jpeg"),
            (80, [], 500, "tax.pdf"),
        ]
        negative_documents = [
            (65, ["missing page"], 600, "statement.pdf"),
            (55, ["signature incomplete"], 800, "form.pdf"),
            (45, ["blurred or illegible content"], 200, "aadhaar.jpg"),
            (20, ["empty document"], 0, "pan.pdf"),
            (70, ["unsupported extension"], 900, "statement.txt"),
            (30, ["missing page", "signature incomplete", "blurred content"], 150, "form.png"),
        ]
        document_count = 0
        for repetition in range(4):
            for index, values in enumerate(positive_documents):
                self._save_document_synthetic(f"synthetic-document-positive:{repetition}:{index}", values, 1)
                document_count += 1
            for index, values in enumerate(negative_documents):
                self._save_document_synthetic(f"synthetic-document-negative:{repetition}:{index}", values, 0)
                document_count += 1
        return loan_count, document_count

    def _save_document_synthetic(
        self,
        example_key: str,
        values: tuple[int, list[str], int, str],
        label: int,
    ) -> None:
        quality, issues, text_length, file_name = values
        self.database.upsert_example(
            TrainingExample(
                example_key=example_key,
                model_key=DOCUMENT_MODEL_KEY,
                entity_type="LOAN_DOCUMENT",
                entity_id_hash=self.database.hash_identifier(example_key),
                features=document_features(quality, issues, text_length, file_name),
                label=label,
                label_name="POSITIVE_USABLE_PATTERN" if label else "NEGATIVE_REVIEW_PATTERN",
                label_source="SYNTHETIC_DEMO",
                human_verified=False,
                synthetic=True,
            )
        )

    def _production_training_ready(self) -> bool:
        for model_key in (LOAN_MODEL_KEY, DOCUMENT_MODEL_KEY):
            examples = self.database.load_examples(model_key)
            verified_positive = sum(item.human_verified and item.label == 1 for item in examples)
            verified_negative = sum(item.human_verified and item.label == 0 for item in examples)
            if verified_positive < 20 or verified_negative < 20:
                return False
        return True


class LocalAdvisoryModelTrainer:
    """Trains reproducible demo classifiers and persists governance metadata."""

    def __init__(self, database: ModelTrainingDatabase, model_directory: str | Path) -> None:
        self.database = database
        self.model_directory = Path(model_directory)
        self.model_directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _dependencies() -> tuple[Any, ...]:
        try:
            import joblib
            import sklearn
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
        except ImportError as error:
            raise RuntimeError("Install local training dependencies: python -m pip install -r requirements-training.txt") from error
        return (
            joblib,
            sklearn,
            LogisticRegression,
            accuracy_score,
            balanced_accuracy_score,
            confusion_matrix,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
            train_test_split,
            Pipeline,
            StandardScaler,
        )

    def train_all(self, allow_synthetic_demo: bool = False) -> list[dict[str, Any]]:
        results = []
        for component in MODEL_COMPONENTS:
            if component.training_supported:
                results.append(self.train(component.model_key, allow_synthetic_demo=allow_synthetic_demo))
        return results

    def train(self, model_key: str, allow_synthetic_demo: bool = False) -> dict[str, Any]:
        component = next((item for item in MODEL_COMPONENTS if item.model_key == model_key), None)
        if component is None:
            raise KeyError(f"Unknown model: {model_key}")
        if not component.training_supported:
            raise ValueError(f"{model_key} is a deterministic/pretrained component and is not trained by this pipeline.")
        examples = self.database.load_examples(model_key)
        positives = sum(item.label == 1 for item in examples)
        negatives = sum(item.label == 0 for item in examples)
        human_positives = sum(item.human_verified and item.label == 1 for item in examples)
        human_negatives = sum(item.human_verified and item.label == 0 for item in examples)
        if not allow_synthetic_demo and (human_positives < 20 or human_negatives < 20):
            raise ValueError(
                f"Insufficient human-verified data for {model_key}: "
                f"need at least 20 positive and 20 negative labels; found {human_positives}/{human_negatives}. "
                "Use --allow-synthetic-demo only to validate the local pipeline."
            )
        if positives < 5 or negatives < 5:
            raise ValueError(f"At least five positive and five negative examples are required; found {positives}/{negatives}.")

        (
            joblib,
            sklearn,
            LogisticRegression,
            accuracy_score,
            balanced_accuracy_score,
            confusion_matrix,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
            train_test_split,
            Pipeline,
            StandardScaler,
        ) = self._dependencies()

        feature_names = component.feature_names
        matrix = [[item.features[name] for name in feature_names] for item in examples]
        labels = [item.label for item in examples]
        run_id = f"{model_key}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        algorithm = "StandardScaler+LogisticRegression(class_weight=balanced)"
        fingerprint = self.database.dataset_fingerprint(model_key)
        self.database.start_run(run_id, model_key, algorithm, fingerprint, examples)
        try:
            x_train, x_test, y_train, y_test = train_test_split(
                matrix,
                labels,
                test_size=0.25,
                random_state=42,
                stratify=labels,
            )
            evaluation_model = Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
                ]
            )
            evaluation_model.fit(x_train, y_train)
            predicted = evaluation_model.predict(x_test)
            probability = evaluation_model.predict_proba(x_test)[:, 1]
            metrics = {
                "accuracy": float(accuracy_score(y_test, predicted)),
                "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
                "precision_positive": float(precision_score(y_test, predicted, zero_division=0)),
                "recall_positive": float(recall_score(y_test, predicted, zero_division=0)),
                "f1_positive": float(f1_score(y_test, predicted, zero_division=0)),
                "roc_auc": float(roc_auc_score(y_test, probability)),
                "confusion_matrix_labels_0_1": confusion_matrix(y_test, predicted, labels=[0, 1]).tolist(),
                "train_count": len(x_train),
                "test_count": len(x_test),
                "evaluation_scope": "SYNTHETIC_DEMO_NOT_PRODUCTION_VALIDATION" if any(item.synthetic for item in examples) else "LOCAL_LABELLED_DATA",
                "threshold": 0.5,
                "advisory_only": True,
            }
            final_model = Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
                ]
            )
            final_model.fit(matrix, labels)
            artifact_path = self.model_directory / f"{run_id}.joblib"
            artifact = {
                "artifact_schema_version": 1,
                "model_key": model_key,
                "run_id": run_id,
                "dataset_fingerprint": fingerprint,
                "feature_names": feature_names,
                "positive_label": 1,
                "negative_label": 0,
                "advisory_only": True,
                "pipeline": final_model,
            }
            joblib.dump(artifact, artifact_path, compress=3)
            artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            versions = {
                "python": platform.python_version(),
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            }
            self.database.complete_run(run_id, metrics, artifact_path, artifact_hash, versions)
            return {
                "run_id": run_id,
                "model_key": model_key,
                "status": "SUCCEEDED",
                "sample_count": len(examples),
                "positive_count": positives,
                "negative_count": negatives,
                "human_verified_count": sum(item.human_verified for item in examples),
                "synthetic_count": sum(item.synthetic for item in examples),
                "metrics": metrics,
                "artifact_path": str(artifact_path.resolve()),
                "artifact_sha256": artifact_hash,
                "production_ready": not any(item.synthetic for item in examples) and human_positives >= 20 and human_negatives >= 20,
            }
        except Exception as error:
            self.database.fail_run(run_id, str(error))
            raise


class LocalAdvisoryModelRuntime:
    """Loads only locally trained, hash-verified artifacts from the model folder."""

    def __init__(self, database: ModelTrainingDatabase, model_directory: str | Path) -> None:
        self.database = database
        self.model_directory = Path(model_directory).resolve()

    def predict(
        self,
        model_key: str,
        features: dict[str, float],
        entity_type: str,
        entity_id: str,
    ) -> AdvisoryPrediction:
        component = next((item for item in MODEL_COMPONENTS if item.model_key == model_key), None)
        if component is None or not component.training_supported:
            raise ValueError(f"No local advisory runtime is configured for {model_key}.")
        if set(features) != set(component.feature_names):
            missing = sorted(set(component.feature_names) - set(features))
            unexpected = sorted(set(features) - set(component.feature_names))
            raise ValueError(f"Feature schema mismatch; missing={missing}, unexpected={unexpected}")
        run = self.database.latest_successful_run(model_key)
        if run is None:
            raise RuntimeError(f"No successful local training run exists for {model_key}.")
        artifact_path = Path(run["artifact_path"]).resolve()
        if artifact_path.parent != self.model_directory:
            raise RuntimeError("Registered artifact is outside the approved local model directory.")
        if not artifact_path.exists():
            raise RuntimeError("Registered model artifact does not exist.")
        actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_hash != run["artifact_sha256"]:
            raise RuntimeError("Model artifact checksum validation failed.")
        try:
            import joblib
        except ImportError as error:
            raise RuntimeError("Install local training dependencies: python -m pip install -r requirements-training.txt") from error
        # joblib is pickle-based; only this locally produced and hash-verified path is loaded.
        artifact = joblib.load(artifact_path)
        if artifact.get("model_key") != model_key or artifact.get("run_id") != run["run_id"]:
            raise RuntimeError("Model artifact metadata does not match the registry.")
        vector = [[features[name] for name in component.feature_names]]
        probability = float(artifact["pipeline"].predict_proba(vector)[0][1])
        label = int(probability >= 0.5)
        result = AdvisoryPrediction(
            model_key=model_key,
            run_id=run["run_id"],
            predicted_label=label,
            label_name="POSITIVE_PATTERN" if label else "NEGATIVE_REVIEW_PATTERN",
            positive_probability=probability,
        )
        self.database.record_prediction(run["run_id"], model_key, entity_type, entity_id, features, label, probability)
        return result

    def score_loan(self, loan: LoanApplication) -> AdvisoryPrediction:
        return self.predict(LOAN_MODEL_KEY, loan_features(loan), "LOAN_APPLICATION", loan.application_id)

    def score_document(
        self,
        entity_id: str,
        quality_score: float,
        issues: list[str],
        extracted_text_length: int,
        file_name: str,
    ) -> AdvisoryPrediction:
        return self.predict(
            DOCUMENT_MODEL_KEY,
            document_features(quality_score, issues, extracted_text_length, file_name),
            "LOAN_DOCUMENT",
            entity_id,
        )

    @staticmethod
    def as_dict(prediction: AdvisoryPrediction) -> dict[str, Any]:
        return asdict(prediction)
