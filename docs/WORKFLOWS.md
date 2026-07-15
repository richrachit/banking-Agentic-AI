# Workflow Details

## Loan resolution state machine

`HELD -> INVESTIGATING -> AWAITING_CUSTOMER | AWAITING_APPROVAL | READY_FOR_MAIN_JOURNEY`

1. Receive an LOS hold event with application ID, exception code, and correlation ID.
2. Read relevant LOS, document, and verification evidence through authorized adapters.
3. Classify the exception and record diagnosis.
4. For a missing document, create one CRM task and wait for document arrival.
5. For a transient verification failure, retry through the verifier; record the result.
6. For an income variance, compare to tolerance. Resolve in-policy variances; package larger variances for the configured credit approver.
7. On approved deviation, update LOS state and publish a return-to-journey event. On rejection, retain the hold and notify stakeholders.

## Dormancy lifecycle state machine

`ACTIVE -> OUTREACH -> DORMANT -> TRANSFER_PENDING -> TRANSFERRED -> CLAIM_PENDING -> CLAIM_PAID`

1. Daily scheduler selects active accounts at outreach lead time and creates a non-duplicated multi-channel contact sequence.
2. At the jurisdictional dormancy threshold, classify accounts as dormant and calculate the transfer due date.
3. At due date, freeze the balance snapshot in a transfer package and submit it to compliance.
4. After compliance approval, perform an idempotent transfer instruction and retain a claim-ready record.
5. For a later claimant, perform identity/entitlement checks through external adapters, then route payment to an authorized approver.

## Approval requirements

| Action | Required role |
| --- | --- |
| Loan policy deviation | `credit.manager` |
| Unclaimed balance transfer | `compliance.officer` |
| Customer reclaim payment | `claims.officer` |
