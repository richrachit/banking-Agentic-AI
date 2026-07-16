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
