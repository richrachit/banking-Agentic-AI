# Architecture

```text
Browser UI                    API clients
    |                              |
    +---------- FastAPI v2 --------+
                     |
        +------------+-------------+
        |                          |
BankStatementAnalysisAgent    DormancyAgent
 cleansing/category/metrics   rules/outreach/clocks
 cross-validation/risk        approvals/transfer/reclaim
        |                          |
BankStatementDatabase         LocalRepository + DormancyCaseDatabase
        +------------+-------------+
                     |
               AuditLog hash chain
```

The local UI is HTML/CSS/JavaScript served by Python. FastAPI owns authentication, authorization, validation and workflow endpoints. SQLite stores financial-analysis and dormant-case detail; JSON retains local dormant state/approvals. PostgreSQL schema is the production target, not the active adapter.

External trust boundaries: OCR, AA, ITR/GST, CBS, GL, communications, KYC/V-CIP, regulator submission and payment. All require idempotency, retries, reconciliation, signed evidence, secrets, monitoring and contractual authorization.
