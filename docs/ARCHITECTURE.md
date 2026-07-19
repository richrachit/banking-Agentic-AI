# Architecture and Coding Standards

## 1. Scope and design intent

The repository is a local reference architecture for loan-exception resolution and dormant-account/unclaimed-balance operations. Its central design principle is **bounded agency**: software can gather facts, classify work, execute explicitly permitted steps, and package evidence, while named human authorities retain policy deviations, regulatory sign-off, identity decisions, and customer-money movement.

The current applications run against local JSON/SQLite adapters. `database/schema.sql` defines a PostgreSQL production target, but no active PostgreSQL repository is implemented.

## 2. Runtime context

```text
Customer / Loan Ops / Credit / Compliance / Admin
              |
       +------+-------------------+
       |                          |
Responsive browser app       FastAPI `/api/v1`
`web_app.py`                 `api_app.py`
       |                          |
       +------ application services ------+
                       |
             LoanOriginationService
                       |
       +---------------+-------------------+
       |               |                   |
Credit Bureau       Loan Exception      Dormancy
Decision Agent      Agent               Agent
       |               |                   |
Provider contract   Document/KYC        Jurisdiction policy
       |             providers               |
       +---------------+-------------------+
                       |
          OperationsAutomationAgent
                       |
     Local repository / audit / case / model stores
                       |
        PostgreSQL + object/WORM storage target
```

The CLI calls the same workflow agents for development and tests. The browser app uses a standard-library HTTP server on port 8000; FastAPI runs separately on port 8001 by convention and supplies generated OpenAPI for clients.

## 3. Layer boundaries

| Layer | Responsibility | Modules |
| --- | --- | --- |
| Interfaces | Parse browser/API/CLI input, authenticate, authorize, shape output | `web_app.py`, `api_app.py`, `cli.py` |
| Application service | Coordinate a user intent across agents without duplicating business flow | `loan_origination.py` |
| Orchestration agents | Diagnose work, perform constrained transitions, create human tasks | `credit_bureau_agent.py`, `loan_agent.py`, `dormancy_agent.py`, `automation_agent.py` |
| Verification/providers | Evaluate documents/KYC or obtain an external normalized fact | `document_verification.py`, `document_ai.py`, `kyc_ai.py`, `CreditBureauProvider` |
| Policy/domain | Define thresholds, statuses, applications, accounts, approvals | `policy.py`, `models.py` |
| Persistence/audit | Store active state, case history, user registry, model governance, events | `repository.py`, `audit.py`, `*_platform.py`, `training_store.py` |
| Model lifecycle | Build derived features, collect labels, train/load advisory artifacts | `local_models.py`, `scripts/*model*.py` |

Rules and orchestration must not depend on a specific external vendor. A real CIBIL, LOS, KYC, document, notification, filing, or payment connection should implement a narrow adapter and return normalized facts to the domain layer.

## 4. Loan transaction sequence

```text
POST/form application
  -> interface authenticates CUSTOMER and validates input
  -> repository generates application ID
  -> LoanOriginationService persists HELD application
  -> CreditBureauDecisionAgent asks provider (explicit consent required)
       LOW + enabled demo rule -> REJECTED
       REVIEW / NO_HISTORY -> CREDIT_SCORE_REVIEW approval
       HIGH -> retain HELD and continue
  -> LoanExceptionAgent diagnoses documents/verification/variance
  -> repository state + case history + audit event
  -> role-scoped response/progression
```

The `HIGH` branch means “continue checks,” never “approve.” The local low-score auto-rejection exists to demonstrate the requested workflow and is controlled by `PolicyConfig.auto_reject_low_credit_score`. Production should default this off until policy, legal, compliance, fairness, reason-code, and grievance controls are approved.

The local bureau adapter is deliberately fictional. It HMAC-hashes PAN for fixture lookup and stores the result/reference, but the default key is unsafe and the request's `consent_version` is not yet persisted in a dedicated record. The target schema corrects the data shape with consent, enquiry, and policy-decision entities; an implementation is still required.

## 5. Dormant-account transaction sequence

```text
Scheduled/API assessment
  -> normalize account/jurisdiction/as-of facts
  -> apply versioned inactivity/outreach/transfer policy
  -> write lifecycle and outreach evidence
  -> create compliance approval when due
  -> only approved path reaches transfer adapter boundary
  -> retain claim-ready evidence
  -> validated/approved customer claim reaches payment boundary
```

Jurisdiction rules are configuration, not learned predictions. The local values are illustrative and must not be treated as current law. A production rules service needs effective dates, source references, approval, regression tests, controlled rollout, and historical replay.

## 6. Authorization model

The interface layer must enforce role and entity scope before calling an agent:

- Customers can see only loans whose `submitted_by` matches their username and accounts whose `customer_id` matches their identity.
- Loan Operations can run loan exception work but cannot decide credit/compliance approvals.
- Credit Managers can decide only `credit.manager` approval packages.
- Compliance Officers can decide only `compliance.officer` packages and run dormant-account controls.
- The local API permits `ADMIN` to decide any approval. That convenience must be removed in production to preserve segregation of duties.

The local token map, static development users, and file-based registration are not an enterprise authorization system. Production authorization must be rechecked in the service/repository tier—not trusted from a client-supplied role.

## 7. AI and deterministic control architecture

The term “agent” does not imply every component is a trained model.

| Category | Components | Why |
| --- | --- | --- |
| Deterministic orchestrators | Loan Exception, Dormancy, Operations Automation | Auditable state transitions and approval boundaries |
| Deterministic controls | Credit Bureau Decision, India KYC, product document rules | Policy/consent/prerequisites must remain explicit and versionable |
| Optional pretrained model | Qwen2.5-VL document provider | Visual extraction/triage suggestion only |
| Locally trainable advisory | Loan exception and document review classifiers | Optional routing signal; never state-changing authority |

The advisory classifiers are not currently invoked by the web/API origination flow. Their registry and artifacts are a separate governance demonstration. This separation prevents a synthetic demonstration model from silently becoming a credit decision engine.

## 8. Active local data architecture

| Store | Writer | Contents and limitations |
| --- | --- | --- |
| `data/state.json` | `LocalRepository` | Loans, accounts, approvals; no transactions/locking/multi-instance safety |
| `data/audit.jsonl` | `AuditLog` | Append-only-style events; not immutable/WORM |
| `data/users.json` | `UserRegistry` | Salted PBKDF2 password hashes; no enterprise identity lifecycle |
| `data/credit_bureau.sqlite3` | Local bureau database | Fictional HMAC-keyed fixtures/checks; not CIBIL |
| `data/loan_exception_cases.sqlite3` | Loan case platform | Exception/document history |
| `data/dormancy_cases.sqlite3` | Dormancy case platform | Case/outreach/filing history |
| `data/model_training.sqlite3` | Model training database | Catalog, derived features, labels, runs, predictions |
| `data/models/` | Local trainer | Joblib artifacts with registered SHA-256 |
| `data/uploads/` | Web/API interface | Plain local files; no malware scan/encryption/retention guarantees |

Local JSON and SQLite stores can diverge if a process fails between writes. Production workflows require one transaction/outbox strategy across authoritative state and emitted events, plus idempotent external operations.

## 9. PostgreSQL target contract

`database/schema.sql` groups the production data contract into:

- identity: `app_user`;
- origination/documents: `loan_application`, `loan_document`;
- bureau governance: `credit_bureau_consent`, `credit_bureau_enquiry`, `credit_policy_decision`;
- workflow/authority: `workflow_step`, `approval_case`, `immutable_audit_event`;
- dormant accounts: `dormant_account_case`, `outreach_attempt`;
- model governance: `ai_model_catalog`, `ai_training_example`, `ai_training_run`, `ai_model_prediction`.

The schema uses UUIDs, JSONB payloads, timestamps, constraints, and operational indexes as a baseline. It is not a complete migration set. A production implementation also needs:

- normalized user/role/entitlement mapping and row/entity authorization;
- policy/model/provider version references on every material decision;
- optimistic version columns or locking strategy;
- unique idempotency constraints for submissions, enquiries, approvals, transfers, filings, and claims;
- outbox/inbox tables for reliable integration events;
- encrypted/tokenized identity fields and key management;
- partitioning/retention/archive controls and immutable audit export;
- migration tooling, backups, restore tests, high availability, and monitoring.

Document bytes belong in encrypted object storage. PostgreSQL should retain the object key, cryptographic hash, content/scan metadata, retention class, and decision evidence—not raw files in JSONB.

## 10. Trust boundaries and production adapters

| Boundary | Required controls |
| --- | --- |
| Mobile/browser ↔ API | TLS, approved origins, API gateway/WAF, rate limits, schema validation, short-lived tokens, device/session controls |
| API ↔ identity provider | OIDC/OAuth, MFA/step-up, group/role mapping, revocation, service identities |
| Workflow ↔ CIBIL/CIC | Authorised access, purpose-specific consent, mTLS/OAuth, idempotency, signed/hashed evidence, error/no-hit semantics, reconciliation |
| Workflow ↔ LOS/core banking | Transaction IDs, idempotency, maker-checker, limits, reconciliation, compensating actions |
| Document/KYC providers | Malware scan, MIME validation, encrypted storage, issuer verification, confidence/reason codes, human fallback |
| Notifications | Template/version approval, consent/preference handling, delivery receipts, PII minimization |
| Regulator/DEA filing | Current rules, maker-checker sign-off, acknowledgement, batch/ledger reconciliation, evidence retention |
| Model registry/serving | Signed artifacts, SBOM/provenance, isolated load, validation approval, monitoring, rollback |

## 11. Audit and observability

Every material action should correlate:

- request/correlation ID;
- authenticated actor and delegated service identity;
- entity, action, before/after state, and outcome;
- policy/model/provider version;
- evidence/reference hashes rather than unnecessary PII;
- approval role, decision, reason, and override rationale;
- external idempotency/reference/acknowledgement IDs.

Operational monitoring should separate workflow quality from model quality. Examples include exception aging, customer evidence turnaround, approval SLA, outreach delivery, transfer lateness, reconciliation breaks, model drift, false-positive/override rate, and provider failures.

## 12. Security and privacy decisions

- Fail closed when consent, identity, evidence, provider response, authority, or artifact provenance is absent.
- Do not log raw PAN/Aadhaar, access tokens, document text/bytes, passwords, or provider payloads.
- Collect only purpose-required data; support consent denial/revocation, retention, correction, and deletion where applicable.
- Encrypt in transit and at rest; rotate keys/secrets and separate environments/accounts.
- Apply deny-by-default RBAC/ABAC and enforce maker-checker separation for adverse/deviation, transfer, claim, and disbursement actions.
- Use approved customer explanations and grievance/dispute paths for adverse outcomes.
- Threat-model prompt injection, malicious documents, model supply chain, data exfiltration, insecure deserialization, and agent tool abuse.

RBI's [Digital Lending Directions, 2025](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0) describe need-based collection with prior explicit consent and an audit trail, purpose disclosure, and consent choices. They and other applicable requirements must be interpreted by the bank's legal/compliance teams for the actual deployment.

## 13. Coding standards

- Target Python 3.11+ and use type hints on public/service boundaries.
- Keep interface parsing, application orchestration, deterministic policy, provider adapters, and persistence separate.
- Model business data with dataclasses/enums and explicit state transitions.
- Centralize approved thresholds/rules; attach version/effective date/source in production.
- Return normalized provider results and map provider-specific errors at the adapter boundary.
- Make external actions idempotent and safe to retry; persist intent before side effects and reconcile completion.
- Never infer authority from model confidence. Require the correct human role when policy says so.
- Store derived, minimized features for training; retain label source and human/synthetic provenance.
- Never load an untrusted joblib/pickle artifact; validate registry, path, hash, and environment.
- Preserve backward-compatible `/api/v1` contracts or introduce a new version with migration guidance.
- Add tests for authorization/ownership, consent, no-hit/error, success/review/reject, duplicate/retry, partial failure, approval boundaries, and artifact tampering.
- Keep generated data, documents, credentials, databases, and artifacts out of source control.

## 14. Verification commands

```powershell
# Full unit/API suite
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# API schema and interactive documentation
.\.venv\Scripts\python.exe -m uvicorn banking_agents.api_app:app --port 8001
# Open http://127.0.0.1:8001/docs

# Model governance state
.\.venv\Scripts\python.exe scripts\model_status.py
```

See [API.md](API.md), [WORKFLOWS.md](WORKFLOWS.md), [AI_AGENTS_TECHNICAL.md](AI_AGENTS_TECHNICAL.md), and [MODEL_TRAINING.md](MODEL_TRAINING.md) for detailed contracts.

