# AI Agents: Technical Reference

This reference describes what the code currently implements. It is a local, policy-driven workflow demo: the agents recommend, route, and perform constrained state changes. They are not autonomous KYC authorities, credit approvers, payment systems, or regulatory filing services.

## 1. Runtime topology

```text
Browser / responsive web UI (`web_app.py`)
        |
        +-- LoanExceptionAgent -------- DocumentVerificationModel
        |          |                    DocumentAIPipeline (optional provider)
        |          |                    IndiaKycAIAgent (orchestration/control)
        |
        +-- DormancyAgent ------------- jurisdiction policy and lifecycle clocks
        |
        +-- OperationsAutomationAgent - safe scheduled/cycle supervisor
                    |
                    +-- LocalRepository + AuditLog + case SQLite stores
```

The browser server is intentionally lightweight (`ThreadingHTTPServer` on `127.0.0.1:8000`). Role-aware forms call the workflow agents, then refresh the dashboard from persisted state. The UI includes responsive viewport metadata and breakpoints for desktop, tablet, and phone layouts; forms and metrics stack, and wide case tables scroll horizontally on phones.

## 2. Agent catalog

| Component | Code | Trigger | Result | Mandatory human boundary |
| --- | --- | --- | --- | --- |
| Loan Exception Agent | `banking_agents/loan_agent.py` | Held loan / exception submission / automation cycle | Evidence request, verification retry, in-policy resolution, or approval package | Credit decision for policy deviation; no disbursement |
| Dormancy Agent | `banking_agents/dormancy_agent.py` | Account lifecycle run / automation cycle | Outreach, dormant classification, transfer package, approved transfer or claim step | Compliance approval before transfer; claim validation |
| Operations Automation Agent | `banking_agents/automation_agent.py` | User-selected automated cycle | Coordinates open loans/accounts and reports queues | Never bypasses an approval gate |
| Document Verification Model | `banking_agents/document_verification.py` | Loan document review | Required-document and evidence-status result | Completeness is not authenticity or identity proof |
| Document AI Pipeline | `banking_agents/document_ai.py` | Optional image/PDF triage | OCR/classification/extraction/tamper-risk suggestion | Default response is pending review; no approval authority |
| Qwen vision provider | `QwenVisionDocumentAIProvider` in `document_ai.py` | Optional locally downloaded vision model | Local visual document triage | Output stays a review suggestion |
| India KYC AI Agent | `banking_agents/kyc_ai.py` | KYC assessment with consent and evidence | Verification prerequisite / manual-review / rejection recommendation | Approved issuer, CKYCR/OVD, sanctions and V-CIP integrations are still required |
| Progression presenter | `banking_agents/progression.py` | Loan detail screen | Shows stage ownership and where AI begins | Display-only; does not decide |

## 3. Loan exception agent

`LoanExceptionAgent` receives a `LoanApplication`, its exception code, document evidence, and `PolicyConfig`. It writes the updated application through the repository, emits audit events, and optionally persists a separate exception-case history in `data/loan_exception_cases.sqlite3`.

| Exception | Deterministic processing path |
| --- | --- |
| `MISSING_DOCUMENT` | Selects product requirements; compares received evidence; records missing, pending, invalid, expired, or unreadable evidence; moves to `AWAITING_CUSTOMER`. |
| `VERIFY_TRANSIENT_FAILURE` | Performs the permitted retry path. A recovered check may move the application to `READY_FOR_MAIN_JOURNEY`; otherwise the case remains actionable. |
| `INCOME_VARIANCE` | Compares declared and verified income using the configured tolerance. An in-policy variance is resolved; an out-of-policy variance produces a `LOAN_DEVIATION` approval for `credit.manager`. |

The agent is idempotency-aware at the case-store layer: repeated processing of the same application does not create an additional exception case record. It must still be backed by transaction/idempotency keys at real LOS integration boundaries.

## 4. Document and KYC controls

### 4.1 Required documents

`DocumentVerificationModel` uses product requirements:

| Product | Required evidence |
| --- | --- |
| `PERSONAL` | PAN, Aadhaar, address proof, bank statement, income proof |
| `HOME` | Personal set plus property document |
| `BUSINESS` | PAN, Aadhaar, business registration, bank statement, financial statement |

Permitted evidence states are `VALID`, `PENDING`, `INVALID`, `EXPIRED`, and `UNREADABLE`. The web form collects separate upload fields, while the local workflow stores evidence metadata and state rather than treating a file upload as conclusive verification.

### 4.2 AI provider contract

`DocumentAIPipeline` separates the agent logic from the model vendor. `BaselineDocumentAIProvider` returns a conservative pending result. The optional Qwen provider is installed/downloaded through `scripts/download_document_model.py` and requires the optional AI dependencies. It can assist with classification and extraction but must not be used to auto-accept a document, establish identity, or make an adverse credit decision.

### 4.3 India KYC agent

`IndiaKycAIAgent` combines consent, format validation, document-risk results, face-match threshold, and external-verification prerequisites. PAN and Aadhaar checks in code are local format/checksum checks only. A result can be `PENDING_EXTERNAL_VERIFICATION`, `MANUAL_REVIEW`, `REJECTED`, or `VERIFIED`; the latter requires authorised external evidence such as issuer PAN verification and an Aadhaar/OVD/CKYCR or V-CIP route. There are deliberately no direct UIDAI, CKYCR, PAN issuer, sanctions, or V-CIP network calls in this repository.

## 5. Dormancy and unclaimed-balance agent

`DormancyAgent` applies the current jurisdiction policy to the last customer-activity date and account balance. It persists the lifecycle through the repository and writes case, outreach, and filing history to `data/dormancy_cases.sqlite3`.

```text
ACTIVE -> OUTREACH -> DORMANT -> TRANSFER_PENDING
       -> TRANSFERRED -> CLAIM_PENDING -> CLAIM_PAID
```

It records customer outreach, calculates a transfer due date, creates the regulatory/DEA package, and waits for the `compliance.officer` approval. Only the approved path can execute a transfer. A later customer claim remains an auditable workflow, not an automatic payment.

## 6. State, audit, and database design

### Current local runtime stores

| Store | Contents | Purpose |
| --- | --- | --- |
| `data/state.json` | Loans, accounts, approvals, and workflow state | Local demo repository |
| `data/audit.jsonl` | Append-only application audit events | Trace actions and outcomes |
| `data/users.json` | Local user registry and salted password hashes | Demo authentication |
| `data/loan_exception_cases.sqlite3` | Exception case history | Operational case view / idempotency support |
| `data/dormancy_cases.sqlite3` | Dormancy cases, outreach, and filing history | Lifecycle case register |

### PostgreSQL target contract

`database/schema.sql` defines the migration baseline. The main tables are:

| Table | Key fields / responsibility |
| --- | --- |
| `app_user` | User identity, role, password hash, access status |
| `loan_application` | Application status, exception code, applicant/financial JSON, AI decision payload |
| `loan_document` | Object-store key, SHA-256, verification state, AI result JSON; document bytes stay outside PostgreSQL |
| `workflow_step` | Stage ownership, actor, outcome, and structured detail |
| `approval_case` | Approval package, required role, decision and evidence |
| `dormant_account_case` | Jurisdiction, balance, lifecycle status, transfer due date, filing data |
| `outreach_attempt` | Channel, result, evidence, and timestamp |
| `immutable_audit_event` | Correlated actor/action/outcome audit trail |

The schema supplies UUID primary keys, `jsonb` payloads, timestamps, status indexes, and a workflow-entity index. Production deployment should use transactional writes, row-level authorization, encryption, object-storage retention controls, database migrations, and an immutable/WORM audit destination. The current browser demo has not yet switched its active repository from JSON/SQLite to PostgreSQL.

## 7. Security and operational controls

- Passwords are salted PBKDF2 hashes in the local registry; replace this with enterprise identity, MFA, and role provisioning in production.
- Do not put document bytes, PAN/Aadhaar numbers, secrets, or raw KYC artifacts in source control or audit JSON.
- Store document blobs encrypted in approved object storage; persist hash, object key, retention class, and review output in `loan_document`.
- Version policies, prompts, models, and provider configurations with every material decision.
- Capture model confidence, evidence references, human decision, and override rationale in `workflow_step`/`immutable_audit_event`.
- Monitor false positives, manual overturn rate, missing-document rate, transfer lateness, and approval SLA separately from model accuracy.

## 8. Production integration boundary

The next implementation layer is adapter-based: LOS, document-management, core banking/payment, CRM/notification, bureau, approved KYC, sanctions, V-CIP, eSign, and regulator-filing adapters. Each must have authenticated service identities, retries with idempotency keys, reconciliation, dead-letter handling, and human fallback. The agents should receive normalized facts from these adapters, not direct ungoverned access to customer money or identity systems.
