# Deployment Plan

## Local

Run API on 8001 and UI on 8000. Local JSON/SQLite/uploads and demo tokens are single-workstation only.

## Production phases

1. Package API/UI, pin dependencies, generate SBOM, scan and sign artifacts.
2. Replace local identity with SSO/MFA and tenant-aware RBAC.
3. Implement PostgreSQL migrations, encrypted object storage, KMS and WORM audit.
4. Add queue/scheduler, observability, alerting, backup/restore and disaster recovery.
5. Integrate approved OCR, AA, tax, communication, CBS, GL, KYC/V-CIP, e-Kuber, UDGAM and payment adapters with idempotency/reconciliation.
6. Validate rules, interest, filing schemas, security/privacy, accessibility and operational runbooks.
7. Shadow run, reconcile against manual samples, pilot with dual control, then roll out gradually.

Rollback must preserve database/audit evidence and stop outbound connector execution. Account-level pause is not a replacement for a platform incident kill switch.
