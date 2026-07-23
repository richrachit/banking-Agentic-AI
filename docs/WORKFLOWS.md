# Workflow Reference

This document describes the workflows that the current code executes, including their human-control boundaries and known local-demo gaps.

## 1. Personas and responsibilities

| Persona | Starts/owns | Can decide | Cannot do |
| --- | --- | --- | --- |
| Customer | Own loan application, document upload, own-account reactivation request | Consent to bureau lookup; supply requested evidence | Run staff agents, see another customer's data, approve/release funds |
| Loan Operations | Exception investigation, evidence update, agent run, automation cycle | Operational reject/reopen actions in the browser workflow | Approve credit deviations or compliance transfers |
| Credit Manager | Credit-score review and loan-deviation queue | Matching `credit.manager` approvals | Transfer unclaimed balances or disburse a loan |
| Compliance Officer | Dormancy assessment, transfer/reactivation queue, automation cycle | Matching `compliance.officer` approvals | Approve credit deviations |
| Claims Officer | Claim review in the domain/CLI workflow | Matching `claims.officer` approval | Other approval types |
| Administrator | Local cross-system/model view, AI-agent availability controls, and demo automation | Current API permits any approval and may enable/disable registered components | Must not retain business-approval bypass or ungoverned production change control |

## 2. Loan application and AI start point

```text
Customer
  1. Authenticates and submits applicant, financial, product and consent facts
  2. Does not supply an application ID or credit score
       |
Repository
  3. Generates application ID and stores HELD application
       |
AI/automation begins
  4. Credit Bureau Agent obtains a consent-gated provider result
  5. Score policy routes to reject, human review, or continued checks
  6. Document/exception agent diagnoses evidence and verification state
       |
Human-controlled boundary
  7. Customer supplies evidence, or Credit Manager decides a package
       |
Normal lending systems (future integration)
  8. Affordability/fraud/underwriting, offer, eSign, operations and disbursement
```

`banking_agents/progression.py` exposes eight user-facing stages. The first AI-active stage is **Consent and credit-bureau assessment**, immediately after application submission. The progression is explanatory; persisted loan status and approval records are the source of truth.

The browser loan form checks required fields before submission and shows a visible error modal when information is missing. That client-side feedback does not replace server validation: the API still validates the full request and returns a redacted field-violation response if a malformed request reaches it.

## 3. Consent and CIBIL-style score workflow

### Current local sequence

1. The customer sends `credit_bureau_consent=true` and a PAN-shaped lookup value.
2. `LoanOriginationService` persists the loan before requesting the score.
3. `LocalCreditBureauProvider` refuses the lookup without consent.
4. The provider validates PAN format, converts it to an HMAC-SHA256 subject key, and reads a fictional fixture from `data/credit_bureau.sqlite3`.
5. The agent records the supported consent version, fixed purpose, and UTC time on the loan and in the audit log.
6. The provider records application ID, hashed subject, result, provider reference, consent boolean, version, purpose, and timestamp. Raw PAN is not stored in that SQLite database.
7. `CreditBureauDecisionAgent` writes score/band/provider/reference/timestamp/decision metadata to the loan, appends an audit event, and applies the policy matrix.

Run the fictional fixture seed once for a clean local environment:

```powershell
.\.venv\Scripts\python.exe scripts\seed_credit_bureau_demo.py
```

### Current policy matrix

| Provider result | Band | Loan status | Next owner |
| --- | --- | --- | --- |
| `300–649` | `LOW` | `REJECTED` when the local demo auto-reject flag is enabled | Customer may create `CREDIT_RECONSIDERATION`; full dispute/grievance integration remains external |
| `650–749` | `REVIEW` | `AWAITING_APPROVAL` | `credit.manager` via `CREDIT_SCORE_REVIEW` |
| `750–900` | `HIGH` | Temporarily `HELD`, then exception workflow runs | AI/document workflow; this is not approval |
| No score returned | `NO_HISTORY` | `AWAITING_APPROVAL` | `credit.manager`; no-history is not converted to zero |
| Provider/fixture missing | n/a | `AWAITING_APPROVAL` and `CREDIT_BUREAU_UNAVAILABLE` | Credit Manager coordinates manual retrieval/retry; never auto-reject |

The `<650` and `>=750` values are illustrative `PolicyConfig` values. CIBIL supplies a risk signal, while the lender owns its credit policy and final decision. CIBIL describes scores in the 300–900 range and higher values as lower risk; the [CIBIL FAQ](https://www.cibil.com/faq/understand-your-credit-score-and-report) and [Consumer Credit Risk Assessment product page](https://apimarketplace.transunioncibil.com/products/credit-data/consumer-credit-risk-assessment) should be read alongside the bank's approved policy.

### Consent/adverse-action controls and remaining gaps

RBI's [Digital Lending Directions, 2025](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0) call for need-based data collection with prior explicit consent and an audit trail, purpose disclosure, and consent choices. The local form/API enforces consent and stores its supported version, fixed purpose, and time with the loan/audit/check. It does not yet implement a separately signed/hashed consent-evidence object, denial/revocation/deletion lifecycle, or immutable retention. The PostgreSQL target has the required data shape; its repository is not implemented.

For a customer-owned low-score rejection, `POST /loan-applications/{id}/credit-review-requests` creates a `CREDIT_RECONSIDERATION` package containing the customer's reason and optional bureau dispute reference. It does not reverse the decision without Credit Manager approval. This local route is only part of the required production process, which also needs approved reason codes, bureau-data correction/dispute guidance, complaint handling, and non-retaliatory processing.

The approval endpoint now applies credit follow-on state: approved `CREDIT_SCORE_REVIEW`, `CREDIT_BUREAU_UNAVAILABLE`, or `CREDIT_RECONSIDERATION` cases re-enter the document/exception workflow; rejected cases retain an adverse state and decision note. The local follow-on is synchronous. Production needs idempotent asynchronous execution, retry/reconciliation, and explicit provider-retry behavior.

## 4. Loan document workflow

### Product requirements

| Product | Required evidence |
| --- | --- |
| `PERSONAL` | PAN, Aadhaar, address proof, bank statement, income proof |
| `HOME` | Personal set plus property document |
| `BUSINESS` | PAN, Aadhaar, business registration, bank statement, financial statement |

Evidence status is one of `VALID`, `PENDING`, `INVALID`, `EXPIRED`, or `UNREADABLE`.

### Upload and review sequence

1. During application creation, `uploaded_document_types` creates `PENDING` metadata only.
2. A customer/Loan Operations/Admin uploads each file separately through the web form or multipart API.
3. The local adapter accepts PDF/PNG/JPG up to 10 MiB and saves it in `data/uploads/<application-id>/`.
4. `DocumentVerificationModel` compares product requirements to evidence metadata.
5. Missing or non-valid evidence produces an exact customer request and `AWAITING_CUSTOMER`.
6. An optional document-AI provider can add classification/extraction/quality/tamper-review observations, but cannot set authenticity or approve the loan.
7. KYC requires approved external verification; local format/checksum or face-match signals alone are insufficient.

Local file upload checks the type allowlist and PDF/PNG/JPEG magic bytes against the extension. It still does not include malware scanning, full MIME/container validation, encryption, OCR, issuer verification, or authenticity detection. Do not upload real documents.

## 5. Loan exception state machine

```text
HELD
  +-- missing/non-valid evidence ------> AWAITING_CUSTOMER
  |                                         |
  |                              evidence supplied + reassess
  |
  +-- out-of-policy variance ----------> AWAITING_APPROVAL
  |                                         |
  |                              Credit Manager decision
  |
  +-- recovered/in-policy condition ---> READY_FOR_MAIN_JOURNEY

Any authorised adverse review ----------> REJECTED
Rejected/stalled browser case ----------> REOPENED -> reassess
```

`READY_FOR_MAIN_JOURNEY` only means the demonstrated exception is resolved. It does not mean underwriting approval, eSign, sanction, account creation, or disbursement has occurred.

### Exception behavior

| Exception code | Agent diagnosis/action | Human boundary |
| --- | --- | --- |
| `MISSING_DOCUMENT` | Calculates product requirements and requests missing/pending/invalid/expired/unreadable evidence | Customer supplies new evidence; authenticity/KYC review remains external/human |
| `VERIFY_TRANSIENT_FAILURE` | Performs the permitted retry path and releases a recovered check | Persistent/provider errors require operations/integration handling |
| `INCOME_VARIANCE` | Compares declared and verified income to 10% illustrative tolerance | Outside tolerance creates `LOAN_DEVIATION` for `credit.manager` |
| Unsupported condition | Leaves a diagnosable unresolved case | Authorised operations/policy owner handles it |

Loan exception cases are persisted separately for local history/idempotency support. Real LOS updates need transaction/outbox semantics and idempotency keys.

## 6. Loan approval workflow

1. The agent creates an `Approval` containing type, loan ID, required role, and evidence package.
2. The loan becomes `AWAITING_APPROVAL`.
3. Credit Manager sees only `credit.manager` work through the API's role filter.
4. The decision endpoint validates `APPROVED`/`REJECTED`, required role, pending state, actor, and rejection note, then writes the approval/audit event.
5. A score-review/reconsideration approval resumes document/exception checks; a loan-deviation approval returns the loan to its permitted journey. Rejection records the adverse outcome.
6. `LoanExceptionAgent.approve_application()` refuses to bypass an awaiting/rejected bureau or Credit Manager decision, even if Loan Operations calls it directly.

There is no implemented disbursement endpoint. Operations, agreement, eSign, sanction, and repayment are future adapters.

## 7. Dormant-account lifecycle

```text
ACTIVE
  -> OUTREACH
  -> DORMANT
  -> TRANSFER_PENDING
  -> TRANSFERRED
  -> CLAIM_PENDING
  -> CLAIM_PAID
```

### Scheduled lifecycle

1. Compliance/API/automation supplies an account's jurisdiction, balance, last customer activity, and as-of date.
2. `DormancyAgent` compares inactivity to the configured jurisdiction clock.
3. Within the outreach lead window it records re-engagement and moves the account to `OUTREACH`.
4. At the dormancy threshold it marks `DORMANT` and calculates `transfer_due_on`.
5. When due, it creates an `UNCLAIMED_TRANSFER` package and moves to `TRANSFER_PENDING`.
6. A `compliance.officer` decision is required.
7. The approved local path records transfer state/amount. No external payment, filing, or regulator acknowledgement occurs.
8. A later claim requires validated entitlement and `claims.officer` approval before local `CLAIM_PAID` state.

Jurisdiction differences and effective-date changes must be represented as compliance-approved, versioned policy. The included `IN-RBI-DEA` configuration is illustrative and must not be treated as legal advice or a current filing rule.

### Customer reactivation

1. The authenticated customer lists only accounts matching their `customer_id`.
2. The customer selects an account and confirms current KYC.
3. The API rejects another customer's account as `404` and rejects `kyc_confirmed=false` as `422`.
4. A valid request creates `ACCOUNT_REACTIVATION` for `compliance.officer` and appends an audit event.
5. Compliance approval moves the local account to `ACTIVE`, clears dormancy/transfer dates, refreshes last activity, and rejects any pending transfer package. Approved KYC/core-banking execution remains a production integration.

## 8. Automation cycle

`OperationsAutomationAgent` is a bounded supervisor:

1. Iterate eligible held/open loan cases.
2. Delegate each to `LoanExceptionAgent`.
3. Apply only already-approved deviation actions.
4. Evaluate dormant accounts at the supplied as-of date.
5. Execute only already-approved transfer/claim states.
6. Return a run summary and pending human actions.

It is callable by `LOAN`, `COMPLIANCE`, and `ADMIN` through the API. The caller's ability to start a cycle does not grant authority to create an approval outcome.

## 9. Support-chatbot and AI-control workflow

```text
Authenticated browser user
  -> submits a 1–1000 character support question
  -> role/entity scope is applied before any workflow fact is read
  -> optional verified local intent artifact classifies a bounded support intent
       otherwise deterministic retrieval classifies the same bounded topic set
  -> assistant returns explanation, safe navigation hints, and its read-only boundary
  -> audit records intent/source only; message/reply are not stored for training
```

The chatbot can explain application status, required documents, bureau routing, approved-role queues, agent boundaries, and dormant-account reactivation. It cannot submit or amend an application, make/override a decision, verify KYC, disburse, transfer or pay money, or mutate an account. A customer sees only their own loans/accounts; Compliance cannot retrieve loan information; internal approval summaries are limited to each role's queue.

The support assistant has a deterministic role-scoped fallback. All learned advisory generation uses the single `UnifiedGenerativeAI` contract; there is no separately trained intent classifier.

An Administrator can list all registered component controls and change an enabled flag in the browser AI settings dashboard or via the API. A registered component is enabled by default. For components that protect active routes, disabled means the dependent action returns `503`; the system must not work around a disabled control. The local settings file records the last Administrator actor/time but is not an enterprise change-management or emergency-kill-switch system.

## 10. API-to-workflow mapping

| User intent | Endpoint | Workflow effect |
| --- | --- | --- |
| Apply for loan | `POST /api/v1/loan-applications` | ID → consent/bureau → score branch → exception agent when high |
| Track application | `GET /api/v1/loan-applications/{id}` | Returns state plus eight-stage progression |
| Request low-score reconsideration | `POST /api/v1/loan-applications/{id}/credit-review-requests` | Creates `CREDIT_RECONSIDERATION` for Credit Manager |
| Supply document | `POST /api/v1/loan-applications/{id}/documents` | Local file + `PENDING` evidence; no automatic re-run |
| Re-run exception work | `POST /api/v1/loan-applications/{id}/run-exception-agent` | Loan Ops/Admin diagnosis and state update |
| Review approvals | `GET /api/v1/approvals` | Role-scoped queue |
| Decide approval | `POST /api/v1/approvals/{id}/decision` | Records authority result and applies the matching local credit/loan/reactivation/transfer/claim transition |
| View owned accounts | `GET /api/v1/accounts` | Customer ownership filter or staff view |
| Request reactivation | `POST /api/v1/accounts/{id}/reactivation-requests` | Compliance package; no immediate reactivation |
| Run dormancy | `POST /api/v1/dormancy/cycles` | Save/evaluate supplied account facts |
| Run supervisor | `POST /api/v1/automation/cycles` | Bounded cross-workflow cycle |
| Ask support assistant | `POST /api/v1/chat/messages` | Read-only, role-scoped workflow explanation and safe navigation hints |
| Inspect AI controls | `GET /api/v1/ai/agents` | Administrator sees registered settings and chatbot-training aggregate status |
| Change AI availability | `POST /api/v1/ai/agents/{model_key}/settings` | Administrator enables/disables a component; wired dependent routes fail closed |

## 11. Data and audit sequence

Each current operation can write one or more local stores:

| Workflow concern | Local source of truth/history | PostgreSQL target |
| --- | --- | --- |
| Loan/account/approval state | `data/state.json` | `loan_application`, `dormant_account_case`, `approval_case` |
| Bureau fixture and check | `data/credit_bureau.sqlite3` | `credit_bureau_consent`, `credit_bureau_enquiry`, `credit_policy_decision` |
| Exception/document cases | `data/loan_exception_cases.sqlite3` | `loan_document`, `workflow_step` |
| Dormancy/outreach/filing | `data/dormancy_cases.sqlite3` | `outreach_attempt`, `workflow_step` |
| Actor/action trail | `data/audit.jsonl` | `immutable_audit_event` plus WORM store |
| Unified GenAI lifecycle | Provider configuration and approved external/local model storage | One switchable advisory-model contract |
| Agent availability | `data/agent_settings.json` | `ai_agent_setting`, audited change-control event |

The local writes are not one atomic transaction. Production needs transactional state/outbox, retries, reconciliation, and duplicate protection across every external side effect.

## 12. Outcome meanings

| Outcome/state | Exact meaning |
| --- | --- |
| `HELD` | Application is persisted and an automated/operational check remains |
| `AWAITING_CUSTOMER` | Specific evidence or action is required from the customer |
| `AWAITING_APPROVAL` | Named human authority is required |
| `READY_FOR_MAIN_JOURNEY` | Demonstrated exception resolved; continue normal LOS controls |
| `REJECTED` | Current local policy/reviewer stopped the application; no funds released |
| `PENDING_EXTERNAL_VERIFICATION` | KYC needs an approved external provider/process |
| `MANUAL_REVIEW` | Risk/conflict/low-confidence condition needs authorised review |

For API fields and security behavior, see [API.md](API.md). For model configuration, see [UNIFIED_GENERATIVE_AI.md](UNIFIED_GENERATIVE_AI.md). For local stores and the PostgreSQL target, see [DATABASE.md](DATABASE.md).
