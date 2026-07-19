# Local Model Registry and Training

This project contains a governed local training pipeline for two advisory classifiers. It also catalogs deterministic agents, policy controls, and the optional pretrained document-vision provider so operators can see which components are learned and which are not.

The local classifiers are routing aids only. They do not mutate workflow state, approve/reject a loan, establish KYC, authenticate a document, change statutory clocks, or move money. The active loan/CIBIL/dormancy workflows remain deterministic and human-gated. The FastAPI application exposes registry status through `GET /api/v1/ai/models`; it does not use these advisory classifiers to make origination decisions.

## Component catalog

`banking_agents/local_models.py` registers ten components:

| Model key | Type | Locally trained | Authority boundary |
| --- | --- | --- | --- |
| `loan_exception_resolution_advisory` | scikit-learn advisory classifier | Yes | Routing explanation only; policy and approval state are authoritative |
| `document_review_advisory` | scikit-learn advisory classifier | Yes | Readability/review pattern only; not authenticity, identity, or loan approval |
| `qwen_document_vision` | Optional pretrained foundation model | No | Visual triage suggestion remains pending for review |
| `baseline_document_provider` | Deterministic validator | No | File safety/routing check only |
| `document_verification_rules` | Deterministic policy | No | Product document completeness/status rules |
| `india_kyc_agent` | Deterministic control agent | No | Requires approved issuer/CKYCR/OVD/V-CIP evidence and human controls |
| `credit_bureau_decision_agent` | Deterministic policy agent | No | Consumes an external score; does not recreate CIBIL or approve/disburse |
| `loan_exception_agent` | Deterministic orchestrator | No | Cannot override credit policy or disburse |
| `dormancy_agent` | Deterministic orchestrator | No | Statutory clocks and money movement must not be learned decisions |
| `operations_automation_agent` | Deterministic supervisor | No | Cannot bypass approval gates |

“Positive” and “negative” describe the model-specific target, not customer sentiment or a final credit decision:

- Loan positive: a derived pattern resembles an exception resolved under the existing controls.
- Loan negative: a pattern resembles evidence/rework or authorised review being required.
- Document positive: derived signals resemble a readable item suitable for the next review step.
- Document negative: derived signals resemble replacement or human investigation being required.

## Local data stores

| Path | Contents |
| --- | --- |
| `data/model_training.sqlite3` | Catalog, de-identified feature rows, labels/provenance, runs, metrics, artifact hashes, predictions |
| `data/models/*.joblib` | Locally produced scikit-learn artifacts |
| `data/state.json` | Source workflow states used by the collector |
| `data/loan_exception_cases.sqlite3` | Optional weak-rule document observations used by the collector |

The matching PostgreSQL target tables are `ai_model_catalog`, `ai_training_example`, `ai_training_run`, and `ai_model_prediction` in `database/schema.sql`. The runtime has not been switched to those tables.

## Feature governance

Only numeric, derived features are accepted. `ModelTrainingDatabase` rejects feature names associated with raw documents or direct identifiers, including PAN, Aadhaar, names, dates of birth, e-mail, phone, addresses, extracted text, and file bytes. Entity identifiers are stored as SHA-256 hashes. This name-based control is a guardrail, not a complete privacy classifier; a production ingestion pipeline still needs data classification, minimization, lineage, retention, access controls, and privacy review.

### Loan feature schema

The loan classifier uses one-hot exception/product flags, product-required/received document counts, evidence-state ratios, income-variance ratio, verification attempts, and requested-amount-to-annual-income. Missing/zero values are normalized conservatively in `loan_features()`.

### Document feature schema

The document classifier uses quality score, issue count, extracted-text length, missing-page/signature/illegibility/empty signals, and whether the filename extension is supported. It does not store extracted text or file content.

The credit bureau score is intentionally not a feature in either demo classifier. `CreditBureauDecisionAgent` consumes an authorised external signal through deterministic, versionable policy. A bank must not train a local model to imitate a bureau score or use approve/reject history as a substitute for repayment-outcome validation.

## Label sources

`LocalTrainingDataCollector` can collect:

| Source | Model | Label quality |
| --- | --- | --- |
| `READY_FOR_MAIN_JOURNEY` / `REJECTED` workflow status | Loan | Operational/weak label; `human_verified=False` |
| Decided `LOAN_DEVIATION` approval | Loan | Human decision; `human_verified=True` |
| `requires_human_review` in document case rows | Document | Rule-derived weak label; `human_verified=False` |
| Generated examples with `--include-synthetic-demo` | Both | Synthetic pipeline fixture; never production evidence |

On a clean database the synthetic generator adds 40 loan examples and 48 document examples. These examples deliberately cover positive and negative branches, but any resulting metric measures a small generated fixture—not real-world model quality.

There is currently no approved import job for human-reviewed document outcomes. Consequently, production training of the document classifier will fail closed until such a governed source supplies sufficient labels.

## Install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt
```

`requirements-training.txt` installs scikit-learn and joblib; NumPy and SciPy arrive as transitive dependencies. The optional Qwen document provider is separate:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
.\.venv\Scripts\python.exe scripts\download_document_model.py
```

The Qwen download can require substantial disk/RAM and benefits from a compatible GPU. Review the model card, licence, model supply chain, data residency, and customer-data controls before download or use. Qwen is not fine-tuned by this repository.

## Build the registry and dataset

Production-intent collection (no synthetic rows):

```powershell
.\.venv\Scripts\python.exe scripts\build_training_database.py
```

Local pipeline demonstration:

```powershell
.\.venv\Scripts\python.exe scripts\build_training_database.py --include-synthetic-demo
```

Collection is implemented as upserts keyed by `example_key`, so repeating it updates the same logical examples rather than intentionally multiplying them.

Inspect the catalog, counts, and latest run:

```powershell
.\.venv\Scripts\python.exe scripts\model_status.py
```

## Training gates and algorithm

Without `--allow-synthetic-demo`, each trainable model requires at least:

- 20 human-verified positive examples, and
- 20 human-verified negative examples.

All runs also require at least five examples of each class. If the human-label threshold is not met, training fails closed with an explanatory error.

The demonstration trainer uses:

1. Feature order from the registered model schema.
2. A stratified 75/25 split with `random_state=42`.
3. `StandardScaler` plus `LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)`.
4. Accuracy, balanced accuracy, positive precision/recall/F1, ROC AUC, and a `[0,1]` confusion matrix.
5. A second fit over the complete dataset for the persisted artifact.
6. A default advisory classification threshold of `0.5`.

Train only when the production label gate is met:

```powershell
.\.venv\Scripts\python.exe scripts\train_local_models.py
```

Exercise the synthetic demonstration pipeline explicitly:

```powershell
.\.venv\Scripts\python.exe scripts\train_local_models.py --allow-synthetic-demo
```

Every run records the dataset fingerprint, label counts and provenance, metrics, Python/scikit-learn/joblib versions, artifact path, and SHA-256. If any synthetic row is present, the evaluation scope is `SYNTHETIC_DEMO_NOT_PRODUCTION_VALIDATION` and `production_ready` is false.

## Advisory inference

Score an existing local loan:

```powershell
.\.venv\Scripts\python.exe scripts\score_local_model.py --application-id LN-1002
```

`LocalAdvisoryModelRuntime`:

- accepts only the exact registered feature schema;
- loads the latest successful run;
- requires the artifact to be directly inside the configured local model directory;
- verifies its SHA-256 against the registry before deserialization;
- checks the embedded model key and run ID; and
- records the prediction with a hashed entity ID and `advisory_only=True`.

The runtime does not update the source `LoanApplication`. Tests assert that workflow state remains unchanged after scoring.

## Artifact security

Joblib uses a pickle-based format. Hash and path checks protect against accidental replacement and unregistered artifacts, but they do not make an untrusted pickle safe. Only load artifacts produced by this controlled pipeline and protected by filesystem access controls. Scikit-learn's [model persistence guide](https://scikit-learn.org/stable/model_persistence.html) documents the arbitrary-code risk and the need to keep serving dependencies compatible with the training environment.

For production, use signed artifacts in an immutable registry, build provenance/SBOMs, vulnerability scanning, isolated loading, promotion approvals, rollback, and environment pinning. Consider a safer serving format where model compatibility permits.

## Validation required before production

The minimum code gate is not a claim of statistical adequacy. A production model also needs:

- a documented target tied to a legitimate operational outcome;
- representative, time-separated development/validation/holdout datasets;
- leakage, bias/fairness, class imbalance, calibration, stability, and subgroup testing;
- error-cost thresholds approved by Risk/Compliance/Operations;
- challenger and deterministic-baseline comparison;
- explainability and reason-code mapping appropriate to the decision;
- independent model validation and model-risk approval;
- monitoring for drift, overrides, false positives/negatives, latency, and data quality;
- retraining/promotion/rollback controls; and
- customer review/grievance paths for any workflow influenced by a model.

Do not quote synthetic test metrics as expected production accuracy.

## Tests

`tests/test_local_model_training.py` verifies catalog classification, PII-name rejection, the fail-closed human-label gate, synthetic training/advisory inference, no source-state mutation, and rejection of a tampered artifact.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_local_model_training -v
```

