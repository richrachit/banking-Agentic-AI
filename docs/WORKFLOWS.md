# Current Workflow Reference

This document reflects the current local demo implementation in the repository, including the browser UI, loan exception handling, dormancy lifecycle management, and the automation supervisor.

## 1. End-to-end flow

1. A user signs in through the web UI and selects a role such as Customer, Loan Operations, Credit Manager, Compliance Officer, or Administrator.
2. A Customer submits a new loan application. The app creates a loan record, stores uploaded documents, and starts the workflow in the `HELD` state.
3. The loan agent evaluates the exception code:
   - `MISSING_DOCUMENT`: checks document completeness and requests the missing evidence.
   - `VERIFY_TRANSIENT_FAILURE`: retries verification and may recover after a second pass.
   - `INCOME_VARIANCE`: auto-resolves when within policy tolerance, or routes a deviation approval when it exceeds tolerance.
4. If a human approval is required, the repository creates an approval record and the workflow pauses until the designated role decides.
5. Once approved, the loan either returns to the main journey or remains pending for follow-up based on the decision.
6. The dormancy workflow processes active accounts, starts outreach, classifies dormant accounts, creates transfer approvals, executes approved transfers, and supports later claims.
7. The automation controller runs a cycle over both loan and account workflows, executes approved transfers/claims, and reports pending human actions.

## 2. Current loan state machine

`HELD -> AWAITING_CUSTOMER -> AWAITING_APPROVAL -> READY_FOR_MAIN_JOURNEY -> REJECTED/REOPENED`

### What happens in each state

- `HELD`: initial state for newly created customer loan requests.
- `AWAITING_CUSTOMER`: used when the agent needs more evidence or a customer response.
- `AWAITING_APPROVAL`: used when a policy deviation needs a credit decision.
- `READY_FOR_MAIN_JOURNEY`: used after successful resolution or after an approved deviation.
- `REJECTED`: used when an application is rejected by AI or operations review.
- `REOPENED`: used when a rejected or stalled application is reopened for resubmission or re-review.

### Current exception handling

| Exception code | Current behavior |
| --- | --- |
| `MISSING_DOCUMENT` | Verifies required documents for the product and requests any missing or invalid items. |
| `VERIFY_TRANSIENT_FAILURE` | Retries verification; if the second attempt succeeds, the loan is released. |
| `INCOME_VARIANCE` | Resolves automatically when within policy tolerance; otherwise creates a credit approval package. |
| Review action | Approve, reject, or reopen the loan directly from the dashboard queue. |

## 3. Current dormancy lifecycle

`ACTIVE -> OUTREACH -> DORMANT -> TRANSFER_PENDING -> TRANSFERRED -> CLAIM_PENDING -> CLAIM_PAID`

### Current behavior

1. The agent evaluates each account against the jurisdiction policy and the last customer activity date.
2. When the account is approaching the dormancy threshold, it marks the account as `OUTREACH` and records re-engagement activity.
3. When the inactivity threshold is reached, it marks the account as `DORMANT` and calculates a transfer due date.
4. Once the transfer due date is reached, it creates a compliance approval package for the transfer.
5. After an approved transfer, the account moves to `TRANSFERRED` and later supports a customer claim.
6. Claims are only accepted after the transfer exists and identity/entitlement validation is successful.

## 4. Approval routing in the current app

| Action | Current required role |
| --- | --- |
| Loan policy deviation | `credit.manager` |
| Unclaimed balance transfer | `compliance.officer` |
| Customer reclaim payment | `claims.officer` |

The approval queue is displayed in the dashboard and is persisted in the repository as part of the local workflow state.

## 5. Document verification flow

The current document verification model checks product-based document requirements:

| Product | Required documents |
| --- | --- |
| `PERSONAL` | PAN, Aadhaar, address proof, bank statement, income proof |
| `HOME` | Personal requirements plus property document |
| `BUSINESS` | PAN, Aadhaar, business registration, bank statement, financial statement |

The form accepts evidence entries in the form `DOCUMENT:STATUS`, such as `PAN:VALID,AADHAAR:EXPIRED`. Accepted statuses are `VALID`, `PENDING`, `INVALID`, `EXPIRED`, and `UNREADABLE`.

## 6. Automation cycle

The automation supervisor runs the workflow in a safe, human-gated loop:

- it processes held loans,
- applies approved loan deviations,
- evaluates dormancy status,
- executes approved transfers and claims,
- and reports pending human approvals.

The automation agent does not bypass the approval gate for deviations or money movement.

## 7. Customer-to-disbursement progression

1. Customer submits a loan request and product-specific documents.
2. **AI starts:** mandatory-data validation, document classification/extraction, integrity checks, and evidence requests.
3. **AI continues:** affordability, credit/fraud adapter signals, and an explainable policy recommendation.
4. Human review is mandatory for deviations, medium confidence, fraud signals, high-value loans, and every financial action.
5. Customer eSigns; Operations disburses only after all controls and approvals pass.

The application-detail screen shows this progression and marks the AI-owned stages.

## 8. AI-agent execution sequence

### Loan exception sequence

1. **Loan Exception Agent** reads the held application's exception code.
2. **Document Verification Model** calculates required evidence for the product.
3. **Document AI Pipeline** may provide OCR/classification/tamper-review signals; its default result remains pending.
4. **India KYC AI Agent** requests approved issuer PAN, Aadhaar/OVD, CKYCR, sanctions, or V-CIP verification when required.
5. The Loan Exception Agent resolves permitted conditions, requests evidence, retries transient checks, or creates a Credit Manager package.
6. **Operations Automation Agent** runs the cycle when new evidence or approval is available.

### Dormant-account sequence

1. **Dormancy Agent** evaluates inactivity against the jurisdiction policy.
2. It records outreach and calculates the dormancy/transfer clock.
3. On the due date it creates a Compliance Officer package; it does not transfer money yet.
4. After approval, it executes the transfer and retains claim information.
5. **Operations Automation Agent** coordinates scheduled runs and reports unresolved human tasks.

## 9. AI outcome meanings

| Outcome | Meaning | Next step |
| --- | --- | --- |
| `READY_FOR_MAIN_JOURNEY` | An in-policy condition is resolved. | Continue normal LOS journey. |
| `AWAITING_CUSTOMER` | Evidence, consent, or customer action is missing. | Send a precise request. |
| `AWAITING_APPROVAL` | Policy or compliance authority is required. | Route to the named role. |
| `PENDING_EXTERNAL_VERIFICATION` | KYC needs an approved integration. | Run issuer/CKYCR/V-CIP verification. |
| `MANUAL_REVIEW` | Fraud, KYC, low confidence, or conflict requires review. | Escalate to the authorised team. |

AI recommendations are workflow inputs, not final KYC, regulatory, credit, or payment decisions.

## 10. Role-by-role browser workflow

### Customer

1. Opens the responsive home page, signs up or signs in, and lands on a customer dashboard.
2. Completes the loan form and supplies product-specific document uploads in separate fields.
3. On submission, the application ID is generated by the repository and the loan starts in `HELD`.
4. The dashboard shows the application, current state, diagnosis, and a link to the progression screen.
5. If evidence is missing, the application is `AWAITING_CUSTOMER`; the customer supplies the requested information through the customer workflow.
6. For an inactive/dormant account, the customer submits a reactivation request and confirms KYC currency. The request is audited and routed for compliance review; it does not reactivate the account automatically.

### Loan Operations

1. Opens the operations dashboard and views exception, pending, and reopen queues.
2. Supplies application facts, document evidence, and the selected exception code where an upstream LOS has raised a hold.
3. The Loan Exception Agent diagnoses the case and either requests evidence, retries a transient verification, resolves an in-policy condition, or creates an approval package.
4. The operator can use the review/reopen queue while preserving the reason and audit trail.

### Credit Manager

1. Receives `LOAN_DEVIATION` cases whose calculated variance exceeds policy tolerance.
2. Opens the application progression/evidence context, records `APPROVED` or `REJECTED`, and adds a decision note.
3. An approved deviation returns the application to the main journey; rejected/reopened cases remain visible for follow-up.

### Compliance Officer

1. Runs a dormancy lifecycle assessment using account, jurisdiction, balance, last activity, and as-of date.
2. Reviews outreach/dormancy cases and transfer packages when their statutory/policy due date arrives.
3. Approves or rejects the transfer package. The transfer is not executed before that approval.
4. Reviews customer reactivation requests and later claim workflows using the recorded evidence.

### Administrator

The Administrator can view the cross-role dashboard and operational queues. In a production deployment this role should administer access, policies, model versions, and monitoring—not become an implicit approval bypass.

## 11. Detailed loan workflow and decision points

```text
Customer application / LOS exception
    -> application persisted as HELD
    -> AI data + document validation begins
    -> document/KYC/verification evidence assessed
    -> in-policy resolution -> READY_FOR_MAIN_JOURNEY
       missing evidence -> AWAITING_CUSTOMER -> resubmission -> reassess
       policy variance -> AWAITING_APPROVAL -> Credit decision
       adverse/rejected -> REJECTED -> optional REOPENED -> reassess
    -> normal LOS journey, eSign, operations disbursement (future adapter boundary)
```

The AI begins after a loan is created, at data/document validation. It can create specific customer work requests and explain the workflow state, but it cannot complete eKYC, approve a deviation, sign an agreement, or release funds. The application-detail page exposes this sequence and marks AI-owned stages.

## 12. Detailed dormant-account workflow and decision points

```text
Scheduled assessment / compliance submission
    -> compare last customer activity with jurisdiction policy
    -> approaching threshold: OUTREACH + recorded channel attempt
    -> threshold reached: DORMANT + transfer clock
    -> due date: TRANSFER_PENDING + compliance package
    -> compliance approval: TRANSFERRED
    -> customer claim: CLAIM_PENDING -> validated entitlement -> CLAIM_PAID
```

The workflow is jurisdiction-policy driven. The code is a controlled reference for the lifecycle and does not file directly with RBI/DEA, send real messages, or move money. Real filing, payment, and customer-contact integrations need bank-approved adapters, reconciliation, and maker-checker controls.

## 13. Data writes and audit trail

Each workflow action writes state through `LocalRepository` and appends an audit event through `AuditLog`. The active local demo uses `data/state.json`, `data/audit.jsonl`, user data in `data/users.json`, and SQLite case stores for exception/dormancy history. The PostgreSQL production target is defined in `database/schema.sql`.

| Workflow event | Active state written | Target PostgreSQL records |
| --- | --- | --- |
| Loan submitted/updated | Loan record and evidence | `loan_application`, `loan_document`, `workflow_step`, `immutable_audit_event` |
| Loan exception/approval | Loan status and approval | `approval_case`, `workflow_step`, `immutable_audit_event` |
| Dormancy/outreach | Account status and lifecycle evidence | `dormant_account_case`, `outreach_attempt`, `workflow_step` |
| Transfer/claim decision | Approval and account state | `approval_case`, `dormant_account_case`, `immutable_audit_event` |

## 14. UI progression and responsive behavior

The landing page, authentication screens, dashboards, loan form, dormant-account service, and loan-detail page are designed for desktop, tablet, and mobile widths. Tablet layouts reduce multi-column panels; phone layouts stack form fields and dashboard metrics, make sign-out full width, and preserve data-table access through horizontal scrolling. The displayed workflow progression is explanatory; the persisted state and approval records remain the source of truth.

For code-level agent inputs, model boundaries, local storage, and the PostgreSQL target contract, see [AI_AGENTS_TECHNICAL.md](AI_AGENTS_TECHNICAL.md).
