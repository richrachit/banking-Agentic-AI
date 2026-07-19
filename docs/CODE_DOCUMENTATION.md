# Code Documentation

This is the code-level map for the current repository. The active runtime is a local reference implementation with JSON/SQLite persistence; `database/schema.sql` is a PostgreSQL target contract, not the repository currently used by the applications.

## Entry points

| Entry point | Command | Purpose |
| --- | --- | --- |
| Browser app | `python -m banking_agents.web_app` | Responsive role-based local UI on port 8000 |
| JSON API | `python -m uvicorn banking_agents.api_app:app --port 8001` | Versioned FastAPI endpoints and generated OpenAPI |
| Workflow CLI | `python -m banking_agents --help` | Seed/run/approve/list local workflow operations |
| Training data builder | `python scripts/build_training_database.py` | Catalog components and collect de-identified examples |
| Local model trainer | `python scripts/train_local_models.py` | Train registered advisory classifiers |
| Model status | `python scripts/model_status.py` | Print component/data/run registry |
| Advisory scoring | `python scripts/score_local_model.py --application-id ...` | Score without changing workflow state |
| Bureau demo seeder | `python scripts/seed_credit_bureau_demo.py` | Create fictional local credit-score fixtures |

## Application and interface modules

### `banking_agents/web_app.py`

- Implements the local `ThreadingHTTPServer` browser application.
- Renders home, signup/login, role dashboards, customer loan/dormant-account views, operations queues, approval views, admin/model status, and application progression.
- Uses `authenticate_local_user()` for the same local identity source as the API.
- Submits customer loans through `LoanOriginationService`, ensuring the bureau branch is shared with the API.
- Saves uploaded files under `data/uploads/`; production object storage/security is not implemented.

### `banking_agents/api_app.py`

- Defines `create_app(data_directory)` and the default FastAPI `app`.
- Publishes versioned routes under `/api/v1` and documentation at `/docs`, `/redoc`, and `/openapi.json`.
- Applies bearer-token authentication, role checks, customer ownership filters, response envelopes, validated request IDs, `no-store` API responses, redacted problem JSON for application/validation errors, and an environment-configured CORS allowlist.
- Exposes customer low-score reconsideration and applies authorised approval follow-on transitions for credit review, deviation, reactivation, transfer, and claims.
- Instantiates services against the configured local data directory on each operation.
- Keeps bearer tokens in process memory; there is no production session/token lifecycle.

See [API.md](API.md) for the endpoint matrix and payload behavior.

### `banking_agents/cli.py`, `banking_agents/__main__.py`

- Expose demo seed/reset, loan/dormancy/automation runs, approval decisions, transfers, claims, and event listing.
- Resolve paths relative to the current working directory; run from the repository root.

## Shared application services

### `banking_agents/loan_origination.py`

`LoanOriginationService.submit()` is the shared customer-submission sequence:

1. Persist the generated `LoanApplication`.
2. Call `CreditBureauDecisionAgent.assess()` with PAN, explicit-consent flag, and supported consent version.
3. If the score branch leaves the loan `HELD`, invoke `LoanExceptionAgent.run()`.
4. Route provider unavailability to Credit Manager review instead of rejection.
5. `continue_after_credit_review()` resumes exception checks only after an authorised approval or records a rejection.

### `banking_agents/auth_service.py`

- Defines the authenticated identity shape and local static development users.
- Maps registered users through `UserRegistry`.
- Associates the static customer with `CUST-1`; registered customers use their username as the local customer ID.

### `banking_agents/user_registry.py`

- Stores local registrations in `data/users.json`.
- Uses per-user random salts and PBKDF2-HMAC-SHA256 (310,000 iterations).
- Activates customers immediately and records staff signup as `PENDING_APPROVAL`.
- Has no staff-activation/admin workflow; replace with the bank IdP in production.

## Loan and credit modules

### `banking_agents/credit_bureau_agent.py`

- Defines the `CreditBureauProvider` protocol and normalized `CreditScoreResult`.
- `LocalCreditBureauDatabase` stores fictional fixtures and lookup history in SQLite.
- Validates PAN format, derives an HMAC-SHA256 subject key, and avoids persisting raw PAN.
- `LocalCreditBureauProvider` requires explicit consent and records version/purpose with the check while mapping scores to `LOW`, `REVIEW`, `HIGH`, or `NO_HISTORY` using `PolicyConfig`.
- `CreditBureauDecisionAgent` records consent/score metadata and routes to local rejection, Credit Manager review, provider-unavailable review, or continued workflow.
- Does not implement a real TransUnion CIBIL connection.

### `banking_agents/loan_agent.py`

- Diagnoses `MISSING_DOCUMENT`, `VERIFY_TRANSIENT_FAILURE`, and `INCOME_VARIANCE` holds.
- Requests exact customer evidence, retries permitted checks, resolves within tolerance, or creates a `LOAN_DEVIATION` approval.
- Applies approved deviations and provides reviewed reject/reopen actions.
- Writes repository state, audit events, and optional loan-exception case history.
- Cannot disburse funds; its direct approve action rejects attempts to bypass an awaiting/rejected bureau or Credit Manager decision.

### `banking_agents/document_verification.py`

- Holds product-to-required-document policy for `PERSONAL`, `HOME`, and `BUSINESS` loans.
- Evaluates `VALID`, `PENDING`, `INVALID`, `EXPIRED`, and `UNREADABLE` evidence states.
- Produces explainable completeness/status results; it does not prove authenticity.

### `banking_agents/document_ai.py`

- Defines the provider abstraction for classification, OCR/extraction observations, quality, and risk flags.
- `BaselineDocumentAIProvider` fails conservatively to `PENDING` or invalid file status.
- `QwenVisionDocumentAIProvider` is an optional locally downloaded Qwen2.5-VL inference adapter.
- Provider output is review guidance and has no approval authority.

### `banking_agents/kyc_ai.py`

- Orchestrates consent, local format/checksum validation, document risk, face-match threshold, sanctions result, and external-verification prerequisites.
- Does not call UIDAI, PAN issuer, CKYCR, sanctions, OVD, or V-CIP services.
- A `VERIFIED` outcome requires approved external evidence; local PAN/Aadhaar checks alone are insufficient.

### `banking_agents/progression.py`

- Returns eight display stages from application submission through disbursement.
- Marks AI-active stages, beginning with consent/credit-bureau assessment.
- Is presentation logic only; the repository status and approval records remain authoritative.

## Dormancy modules

### `banking_agents/dormancy_agent.py`

- Evaluates inactivity against jurisdiction configuration.
- Records outreach, dormancy classification, transfer due date, approval package, approved transfer, and claim progression.
- Requires `compliance.officer` for transfer and `claims.officer` for claim approval.
- Does not contact customers, file with a regulator, post a ledger transaction, or reconcile money externally.

### `banking_agents/dormancy_escheatment_platform.py`

- Provides the SQLite case/outreach/filing history used by the dormancy agent.
- Supports the local lifecycle record; it is not a regulator system of record.

### `banking_agents/automation_agent.py`

- Supervises bounded loan and dormant-account work in one run.
- Delegates to specialist agents, applies already-authorised actions, and returns pending human queues.
- Never changes who has authority to approve a deviation, transfer, or claim.

## Domain, policy, and persistence modules

### `banking_agents/models.py`

Defines dataclasses and status enums:

- `LoanApplication` includes application/financial/document fields, submitter ownership, diagnosis, bureau consent metadata, and credit-score routing metadata.
- `Account` holds jurisdiction, balance, inactivity, transfer, and claim state.
- `Approval` holds kind, target entity, required role, package, status, and decision evidence.
- `LoanStatus` and `DormancyStatus` define the persisted state vocabulary.

### `banking_agents/policy.py`

`PolicyConfig` centralizes the illustrative income tolerance, outreach lead, jurisdiction timelines, bureau cutoffs, and local low-score auto-reject switch. Defaults are code configuration, not approved production policy. Version and persist policy decisions in production.

### `banking_agents/repository.py`

- Serializes loans, accounts, and approvals to `data/state.json`.
- Generates application IDs and approval records.
- Is suitable only for single-workstation demonstration; it does not provide database transactions, locking, row-level authorization, or multi-instance concurrency.

### `banking_agents/audit.py`

- Appends actor/action/entity/outcome/detail events to `data/audit.jsonl`.
- Provides traceability for the local demo, not tamper-proof/WORM guarantees.

### `banking_agents/loan_exception_platform.py`

- Stores loan exception/document case history in `data/loan_exception_cases.sqlite3`.
- Supplies case persistence/idempotency support to `LoanExceptionAgent`.

## Local model modules

### `banking_agents/training_store.py`

- Creates and manages the local SQLite model catalog, training examples, runs, and predictions.
- Validates numeric derived features and blocks common direct-PII/raw-data feature names.
- Records label provenance, synthetic/human flags, dataset fingerprints, metrics, package versions, artifact SHA-256, and advisory predictions.

### `banking_agents/local_models.py`

- Catalogs ten learned/deterministic/pretrained components.
- Implements loan/document derived feature builders.
- Collects workflow, approval, document-rule, and optional synthetic labels.
- Trains two `StandardScaler + LogisticRegression` advisory pipelines.
- Requires a human-label gate for normal training and marks synthetic runs non-production.
- Loads only the latest registered artifact inside the configured model directory after SHA-256 verification.

See [MODEL_TRAINING.md](MODEL_TRAINING.md) for features, labels, commands, artifact risk, and validation requirements.

## Feature-to-module map

| Feature | Main modules |
| --- | --- |
| Login/signup and role identity | `auth_service.py`, `user_registry.py`, `web_app.py`, `api_app.py` |
| Customer loan creation | `web_app.py`, `api_app.py`, `loan_origination.py`, `repository.py` |
| Consent-based bureau assessment | `credit_bureau_agent.py`, `policy.py`, `loan_origination.py` |
| Document upload/requirements/review | `api_app.py`, `web_app.py`, `document_verification.py`, `document_ai.py` |
| KYC control orchestration | `kyc_ai.py` |
| Loan exception diagnosis and routing | `loan_agent.py`, `loan_exception_platform.py` |
| Credit/compliance approval | `loan_agent.py`, `dormancy_agent.py`, `repository.py`, interface modules |
| Dormancy/transfer/claim workflow | `dormancy_agent.py`, `dormancy_escheatment_platform.py` |
| Cross-workflow automation | `automation_agent.py` |
| Application progression | `progression.py`, interface modules |
| Local model governance/training | `local_models.py`, `training_store.py`, `scripts/*model*.py` |
| PostgreSQL target | `database/schema.sql`, `docker-compose.yml` |

## Data writes

| Action | Active local write | PostgreSQL target |
| --- | --- | --- |
| Loan submission/state | `state.json` | `loan_application`, `workflow_step` |
| Bureau fixture/check | `credit_bureau.sqlite3` | `credit_bureau_consent`, `credit_bureau_enquiry`, `credit_policy_decision` |
| Document bytes/status | `uploads/`, `state.json` | Object storage plus `loan_document` |
| Approval | `state.json` | `approval_case` |
| Dormancy case/outreach | `state.json`, `dormancy_cases.sqlite3` | `dormant_account_case`, `outreach_attempt` |
| Audit | `audit.jsonl` | `immutable_audit_event` plus WORM sink |
| Model governance | `model_training.sqlite3`, `models/` | `ai_model_*`, `ai_training_*`, signed artifact registry |

## Coding and test conventions

- Use type hints/dataclasses for business boundaries and explicit enum/string states.
- Keep provider adapters separate from deterministic policy and orchestration.
- Fail closed when consent, evidence, policy, role authority, model provenance, or external verification is absent.
- Avoid logging or training on direct identifiers/raw document content.
- Make retries and external writes idempotent before adding real adapters.
- Test success, missing/no-hit, rejection, review, approval, ownership, duplicate-run, and tamper cases.
- Run the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
