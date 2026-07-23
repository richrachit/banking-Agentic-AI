# Banking Operations Agentic AI Platform

A local reference application for two expensive, exception-heavy banking operations workflows:

1. **Loan-processing exception resolution.** Applications often stop because evidence is missing or inconsistent, verification fails, or a requested decision falls outside policy. The platform diagnoses the hold, requests specific evidence, retries permitted checks, routes deviations to the correct human authority, and returns resolved cases to the main loan journey.
2. **Dormant accounts and unclaimed balances.** Outreach, inactivity clocks, classification, transfer preparation, compliance approval, and later customer claims are coordinated through a jurisdiction-aware, auditable workflow.

The repository combines a responsive multi-persona browser app, a versioned FastAPI backend, command-line workflow tools, explainable deterministic agents, and one switchable local/hosted generative-AI advisory model.

> **Reference implementation only.** This code does not connect to TransUnion CIBIL, RBI/DEA filing, UIDAI, CKYCR, a loan origination system, core banking, payments, eSign, sanctions screening, or a production identity provider. It must not be used to make live credit, KYC, regulatory, or customer-money decisions without approved integrations, legal/compliance validation, model-risk governance, security controls, and maker-checker authorization.

## What the project implements

| Capability | Current implementation | Production boundary |
| --- | --- | --- |
| Customer loan application | Server-generated application ID, applicant/financial fields, product document metadata, separate uploads | LOS/customer master integration, field validation, privacy/retention controls |
| Credit-bureau step | Explicit-consent gate plus fictional local CIBIL-style fixture provider | Authorised bureau membership/API, consent evidence, idempotency, reconciliation |
| Score routing | `<650` local demo rejection with reconsideration, `650–749`/no-history/unavailable Credit Manager review, `>=750` continues workflow | Bank-approved/versioned policy; explainability, review and dispute path |
| Loan exception agent | Missing-document diagnosis, transient retry, income-variance resolution/approval package | LOS, DMS/OCR, KYC, fraud, affordability and notification adapters |
| Document review | Product requirement rules, upload status, baseline provider, optional Qwen visual triage | Malware scan, authenticity/fraud models, issuer verification, human QA |
| KYC orchestration | Consent/format/risk/prerequisite checks in `IndiaKycAIAgent` | Approved PAN/Aadhaar/OVD/CKYCR/V-CIP/sanctions integrations |
| Dormant-account lifecycle | Outreach, dormancy clocks, transfer package/approval, transfer/claim state machine | Current jurisdiction rules, actual communications, filing, ledger and reconciliation adapters |
| Human approvals | Credit, compliance and claims approval records with audit events | Enterprise workflow, segregation of duties, delegated authority, immutable evidence |
| Unified GenAI | One local/hosted provider contract for all advisory tasks | Independently validated model governance and production serving |
| Support chatbot | Role-scoped, read-only deterministic fallback plus the unified GenAI task | Approved conversational design, prompt-injection testing, monitoring, retention controls, and enterprise knowledge retrieval |
| AI agent controls | Administrator can enable/disable each registered component; dependent routes fail closed when disabled | Change management, approval, separation of duties, monitoring, and a central feature-control service |
| Persistence | JSON state/audit plus capability-specific SQLite stores | PostgreSQL repositories, encrypted object storage, WORM audit store |

## Personas

- **Customer:** signs up/signs in, submits a loan and consent, uploads product-specific documents, follows application progression, views owned accounts, and requests dormant-account reactivation.
- **Loan Operations:** reviews loan exceptions, supplies evidence, runs the exception agent, and monitors unresolved work.
- **Credit Manager:** reviews credit-score and policy-deviation packages and records an authorised decision.
- **Compliance Officer:** manages dormant-account lifecycle cases, transfer approvals, and reactivation/claim controls.
- **Administrator:** sees cross-system status and local model governance, including the AI-agent availability controls. Production administration must not bypass business approval roles or change controls without governed change management.

## End-to-end loan flow

```text
Customer submits application and explicit bureau consent
  -> repository generates application ID
  -> Credit Bureau Agent fetches authorised/local-fixture signal
       low demo band -> explainable rejection + review/dispute wording
       intermediate/no history -> Credit Manager approval queue
       provider unavailable -> Credit Manager retrieval/retry queue (not rejection)
       high band -> continue (not an approval)
  -> document/data validation and exception diagnosis
       missing/invalid evidence -> customer request
       transient verification -> permitted retry
       in-policy variance -> return to normal journey
       policy deviation -> Credit Manager package
  -> normal LOS/eSign/disbursement boundary (not implemented)
```

The score band does not approve a loan. It is one input before document, KYC, affordability, fraud, policy, and human-authority controls. The configured cutoffs are illustrative bank policy, not CIBIL or RBI thresholds. CIBIL describes a 300–900 score range and higher scores as lower credit risk; see the [CIBIL score FAQ](https://www.cibil.com/faq/understand-your-credit-score-and-report). RBI's [Digital Lending Directions, 2025](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0) require need-based data collection with prior explicit consent and an audit trail, among other controls.

A customer can request Credit Manager reconsideration of a local low-score rejection. Approved intermediate/no-history/unavailable or reconsideration cases resume document/exception checks; Loan Operations cannot bypass the required credit decision.

## End-to-end dormant-account flow

```text
Scheduled assessment
  -> approaching inactivity threshold: recorded multi-channel outreach
  -> policy threshold: dormant classification and transfer clock
  -> due date: unclaimed-balance/DEA-style package
  -> Compliance Officer approval
  -> transfer adapter and reconciliation boundary
  -> claim-ready record
  -> validated later customer claim with approval
```

The included `IN-RBI-DEA` dates are illustrative configuration. Compliance must verify and version the applicable rule before use.

## Architecture at a glance

```text
Responsive browser UI          JSON clients
`web_app.py`                   FastAPI `/api/v1`
          \                      /
           \-- application services --/
                 |
                 +-- CreditBureauDecisionAgent
                 +-- LoanExceptionAgent -- document/KYC providers
                 +-- DormancyAgent
                 +-- OperationsAutomationAgent
                 +-- BankingSupportChatAgent (read-only)
                 |
                 +-- LocalRepository + AuditLog + SQLite workflow stores
                 +-- AgentSettingsStore (fail-closed local controls)
                                      |
                                      +-- PostgreSQL target schema (not active)
```

Important modules:

- `banking_agents/api_app.py` — role-secured FastAPI surface and generated OpenAPI.
- `banking_agents/web_app.py` — responsive multi-persona local browser application.
- `banking_agents/loan_origination.py` — shared application submission, bureau assessment, and exception-workflow handoff.
- `banking_agents/credit_bureau_agent.py` — provider contract, fictional local fixture database, and score policy routing.
- `banking_agents/loan_agent.py` — loan exception resolution and credit-deviation approvals.
- `banking_agents/dormancy_agent.py` — dormancy, transfer, reactivation, and claim lifecycle.
- `banking_agents/document_verification.py`, `document_ai.py`, `kyc_ai.py` — document/KYC control layers.
- `banking_agents/unified_genai.py` — the single switchable local/hosted generative-AI contract.
- `banking_agents/chat_agent.py` — deterministic role-scoped support fallback.
- `banking_agents/agent_settings.py` — persisted, fail-closed availability settings for the registered components.
- `database/schema.sql` — PostgreSQL target contract; the running demo does not use it yet.

## Requirements

- Python 3.11 or newer.
- PowerShell examples below assume Windows.
- Docker Desktop is optional and used only to inspect the PostgreSQL target schema.
- The browser/CLI workflow uses the Python standard library. FastAPI, PostgreSQL, and the optional local unified model have separate requirements files.

## Local setup

From `D:\Agentic Ai`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m banking_agents seed-demo
.\.venv\Scripts\python.exe scripts\seed_credit_bureau_demo.py
```

Generated local state is written under `data/` and is excluded from new Git tracking. Do not use real customer identifiers or documents in the demo.

## Run the applications

For a Linux server/container deployment that installs the API,
PostgreSQL client, and optional unified-model dependencies, see
[Server deployment](docs/SERVER_DEPLOYMENT.md).

The optional single-model advisory layer can switch between local and hosted
inference; see [Unified generative AI](docs/UNIFIED_GENERATIVE_AI.md).

### Browser application

```powershell
.\.venv\Scripts\python.exe -m banking_agents.web_app
```

Open `http://127.0.0.1:8000`.

### JSON API

In another terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn banking_agents.api_app:app --host 127.0.0.1 --port 8001 --reload
```

Open `http://127.0.0.1:8001/docs`. See [docs/API.md](docs/API.md) for endpoint roles, payloads, response/error envelopes, CIBIL-style routing, and production gaps.

## Run the command-line workflows

```powershell
.\.venv\Scripts\python.exe -m banking_agents --help
.\.venv\Scripts\python.exe -m banking_agents run-loan --application-id LN-1001
.\.venv\Scripts\python.exe -m banking_agents run-automation --as-of 2026-07-20
.\.venv\Scripts\python.exe -m banking_agents list-approvals
.\.venv\Scripts\python.exe -m banking_agents list-events
```

`seed-demo` and `reset-demo` both replace the local demo loan/account state and clear the local audit file. Do not use those commands against data you intend to retain.

## One unified generative AI

The repository now has exactly one learned-model contract:
`UnifiedGenerativeAI`. It handles customer-support, loan, document/KYC, credit,
dormancy, and compliance advisory tasks and can switch between an approved local
or hosted provider. Deterministic policy and human approvals remain
authoritative. See [Unified generative AI](docs/UNIFIED_GENERATIVE_AI.md).

## PostgreSQL target schema

The active demo uses local files. `database/schema.sql` is a migration/design baseline for application, document, bureau consent/enquiry/decision, workflow, approval, dormant account, outreach, audit, and AI governance records.

```powershell
docker compose up -d postgres
.\.venv\Scripts\python.exe -m pip install -r requirements-postgres.txt
```

Starting PostgreSQL does not switch the application repository. A PostgreSQL repository/transaction adapter still needs to be implemented. Change the Compose password before any environment beyond an isolated workstation.

## Tests and debugger

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run tests as a module from the project root. Directly running `python tests\test_workflows.py` changes the import root and can produce `ModuleNotFoundError: banking_agents`. VS Code launch settings are under `.vscode/launch.json`; select the project-root workflow test configuration and ensure the `.venv` interpreter is active.

## Current local persistence

| Store | Purpose |
| --- | --- |
| `data/state.json` | Loan, account, approval, and workflow state |
| `data/audit.jsonl` | Append-only-style local workflow events |
| `data/users.json` | PBKDF2-hashed local registrations |
| `data/credit_bureau.sqlite3` | Fictional HMAC-keyed score fixtures and lookup audit |
| `data/loan_exception_cases.sqlite3` | Loan exception/document case history |
| `data/dormancy_cases.sqlite3` | Dormancy/outreach/filing case history |
| `data/agent_settings.json` | Administrator enable/disable setting for the unified generative model |
| `data/uploads/` | Unencrypted local uploaded files; development only |

## Documentation

- [API reference](docs/API.md)
- [OpenAPI 3.1 snapshot](docs/openapi.json)
- [Workflow reference](docs/WORKFLOWS.md)
- [Architecture and coding standards](docs/ARCHITECTURE.md)
- [AI agent technical reference](docs/AI_AGENTS_TECHNICAL.md)
- [Unified generative AI](docs/UNIFIED_GENERATIVE_AI.md)
- [Database design and local-data boundaries](docs/DATABASE.md)
- [Code/module map](docs/CODE_DOCUMENTATION.md)
- [Research notes](docs/RESEARCH.md)

## Non-negotiable production controls

- Purpose-specific, revocable customer consent and a defensible audit trail for bureau/KYC data access.
- Enterprise identity, MFA, least privilege, row/entity authorization, and maker-checker segregation.
- Encryption in transit/at rest, approved secrets management, PII minimization, retention/deletion, and India data-location review.
- Versioned policy/model/provider configuration, reproducible decision evidence, independent validation, monitoring, and rollback.
- Idempotent, reconciled LOS/core/payment/regulatory integrations with retry, timeout, dead-letter, and human fallback.
- Explainable adverse decisions plus authorised reconsideration, data-correction, complaint, and dispute handling.
- No autonomous disbursement, unclaimed-balance transfer, customer claim payment, KYC verification, or regulatory sign-off.
