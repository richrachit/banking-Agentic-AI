# Database Reference

## Active local stores

| Store | Content |
|---|---|
| `data/state.json` | Dormant accounts and approvals |
| `data/audit.jsonl` | Timestamped, actor-attributed hash-chain events |
| `data/dormancy_cases.sqlite3` | Dormancy cases, outreach, trace and filing evidence |
| `data/bank_statement_analysis.sqlite3` | Uploaded document metadata, analyses and normalized transactions |
| `data/users.json` | Local-demo registered users |
| `data/jurisdiction_rule_packs.json` | Lifecycle configuration |
| `data/uploads/` | Local uploaded documents; not production-secure storage |

The pre-refactor demo databases and state were moved, not destroyed, to `data/legacy-backup-20260821/`. They are not read by the focused runtime and can be recovered manually if historical inspection is required.

## Target PostgreSQL contract

`database/schema.sql` contains only retained-scope tables: users, financial documents, verification consent, analyses, transactions, cross-validation, risk indicators, dormant cases, outreach, approvals, transfers, claims and immutable audit events.

Production requires migrations, tenant row isolation, encrypted object storage, KMS, tokenized account identifiers, backup/restore, retention/deletion/legal hold, WORM audit and reconciliation.
