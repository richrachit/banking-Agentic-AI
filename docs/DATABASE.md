# Database Reference

## Purpose and runtime status

The application currently runs with local JSON and SQLite adapters so that the complete demo can start on one workstation. PostgreSQL is the target production data contract in [`database/schema.sql`](../database/schema.sql); starting the bundled PostgreSQL container does **not** switch the Python repository to PostgreSQL.

Do not place real customer information, PAN, Aadhaar, account balances, documents, or production credentials in the local stores.

## Local development stores

| Path | Owner | Data held | Important boundary |
| --- | --- | --- | --- |
| `data/state.json` | `LocalRepository` | Loan applications, accounts, approval state | Not transactional or safe for multiple application instances |
| `data/audit.jsonl` | `AuditLog` | Local actor/action/outcome events | Append-only-style only; not WORM/immutable storage |
| `data/users.json` | `UserRegistry` | Local PBKDF2 password hashes and registrations | Not an enterprise identity service |
| `data/credit_bureau.sqlite3` | Local bureau adapter | Fictional HMAC-keyed fixtures and lookup metadata | Does not store raw PAN; not a real bureau integration |
| `data/loan_exception_cases.sqlite3` | Loan case platform | Exception and document review history | Local idempotency aid only |
| `data/dormancy_cases.sqlite3` | Dormancy case platform | Outreach, filing, transfer, and claim history | Jurisdiction rules are illustrative |
| `data/model_training.sqlite3` | `ModelTrainingDatabase` | Derived model features, labels, runs, prediction metadata | No raw identity or document data is accepted by the store |
| `data/chatbot_training.sqlite3` | `LocalChatbotTrainingDatabase` | Reviewed/curated support phrases and training runs | Never stores live user messages or assistant replies |
| `data/agent_settings.json` | `AgentSettingsStore` | AI component enabled state and latest Administrator change | Local control only; protected routes fail closed when disabled |
| `data/models/*.joblib` | Local trainers | SHA-256-recorded local artifacts | Treat artifacts as trusted-only pickle/joblib inputs |

All paths above are excluded from new Git tracking. Back up only approved, sanitized development data.

## PostgreSQL target

`database/schema.sql` defines a clean-install PostgreSQL 16 baseline. It contains:

| Domain | Tables |
| --- | --- |
| Identity | `app_user` |
| Loan origination and documents | `loan_application`, `loan_document` |
| Bureau consent and decisions | `credit_bureau_consent`, `credit_bureau_enquiry`, `credit_policy_decision` |
| Workflow, authority, and audit | `workflow_step`, `approval_case`, `immutable_audit_event` |
| Dormancy lifecycle | `dormant_account_case`, `outreach_attempt` |
| General AI model governance | `ai_model_catalog`, `ai_training_example`, `ai_training_run`, `ai_model_prediction` |
| AI availability and chatbot governance | `ai_agent_setting`, `chatbot_training_example`, `chatbot_training_run`, `chat_assistant_event` |

`chat_assistant_event` intentionally contains metadata only: actor, role, intent, retrieval source/mode, read-only flag, correlation ID, and time. It has no message or response column. `chatbot_training_example` is for approved curated phrases, not a transcript import table.

The schema uses UUID primary keys, foreign keys, JSONB for versioned evidence/metadata, timestamps, role checks, and operational indexes. It is a target contract, not a complete live migration history. A production repository must add transaction boundaries, idempotency keys, optimistic concurrency, an outbox/inbox, row-level authorization, encrypted/tokenized PII, immutable evidence retention, backups/restore testing, monitoring, and controlled migrations.

## Start a disposable PostgreSQL target

The supplied Compose file initializes a fresh container with `database/schema.sql`:

```powershell
docker compose up -d postgres
```

The schema initialization hook runs only when the named Docker volume is first created. For a disposable local reset, stop the container and remove the `postgres_data` volume only after confirming that no data needs to be retained. Never use the supplied default password outside an isolated development machine.

Verify the expected tables after startup:

```powershell
docker compose exec postgres psql -U banking_ai -d banking_ai -c "\dt"
```

Again, this validates the schema only. The application keeps using its local JSON/SQLite adapters until a PostgreSQL repository and migration/transaction implementation is introduced.

## Data protection and retention rules

- Raw documents belong in approved encrypted object storage; store only object keys, content hashes, scan results, retention class, and decision references in PostgreSQL.
- Never use local chat transcripts as implicit training data. A governed ingestion process needs explicit source approval, minimization, retention, and model-risk review.
- Keep bureau consent, provider references, policy version, and decision reasons together with an auditable time and actor.
- Preserve maker-checker events and financial-transfer reconciliation evidence in immutable, access-controlled systems.
- Apply retention/deletion rules and legal holds based on the bank's approved jurisdictional policy rather than demo defaults.
