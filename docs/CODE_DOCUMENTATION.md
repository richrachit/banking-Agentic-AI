# Code Documentation

This is the code map for the current single-model reference implementation.
The browser and CLI use local JSON/SQLite persistence. `database/schema.sql` is
a target contract and is not the active application repository.

## Entry points

| Entry point | Command | Purpose |
| --- | --- | --- |
| Browser | `python -m banking_agents.web_app` | Role-based UI on port 8000 |
| API | `python -m uvicorn banking_agents.api_app:app --port 8001` | FastAPI and OpenAPI on port 8001 |
| CLI | `python -m banking_agents --help` | Seed and exercise deterministic workflows |
| Server initialization | `python scripts/initialize_server.py` | One-time demo-state and bureau-fixture initialization |
| Unified-model download | `python scripts/download_genai_model.py` | Download the one optional local base model |
| Dataset builder | `python scripts/build_genai_datasets.py` | Build curated SFT, preference, and evaluation JSONL |
| Unified-model trainer | `python scripts/train_unified_genai.py --method lora` | Fine-tune the one model |
| Bureau seeder | `python scripts/seed_credit_bureau_demo.py` | Create fictional bureau fixtures |

## Interfaces

### `banking_agents/web_app.py`

- Implements the local `ThreadingHTTPServer` browser application.
- Uses `BANKING_WEB_HOST` and `BANKING_WEB_PORT`.
- Provides customer, loan, credit, compliance, and administrator views.
- Applies role checks before workflow operations.
- Displays exactly one AI setting: `unified_generative_ai`.

### `banking_agents/api_app.py`

- Defines `create_app(data_directory)` and the default FastAPI `app`.
- Exposes `/api/v1`, `/docs`, `/redoc`, and `/openapi.json`.
- Applies bearer authentication, ownership filters, role checks, request IDs,
  CORS allowlisting, no-store headers, and redacted problem responses.
- Exposes unified-model status and bounded generative tasks.
- Keeps local tokens in memory; production requires an enterprise identity
  provider and proper token lifecycle.

### `banking_agents/cli.py`

- Seeds/resets demo state and exercises loan, dormancy, automation, approval,
  transfer, claim, and audit workflows.
- Must be run from the repository root.

## The single learned model

### `banking_agents/unified_genai.py`

`UnifiedGenerativeAI` is the repository's only learned-model contract. It:

- supports `local`, `hosted`, and `disabled` modes;
- allows per-request local/hosted switching through a server-side allowlist;
- supports customer support, loan exception, document/KYC, credit, dormancy,
  and compliance advisory tasks;
- enforces structured JSON output;
- forces `advisory_only=true` and `requires_human_review=true`;
- has no workflow mutation, approval, identity-verification, or money authority;
- limits serialized request context to 32 KB; and
- treats supplied context as untrusted data.

`LocalTransformersProvider` loads one local causal language model.
`HostedOpenAICompatibleProvider` calls an administrator-configured compatible
chat-completions endpoint. Hosted secrets are read from environment variables.

### Training files

| File | Purpose |
| --- | --- |
| `requirements-genai-training.txt` | PyTorch/Transformers plus Datasets, PEFT, TRL, and optional Linux bitsandbytes |
| `scripts/build_genai_datasets.py` | Curated non-PII SFT, refusal, DPO, and evaluation fixtures |
| `scripts/train_unified_genai.py` | LoRA, QLoRA, full SFT, and DPO entry point |
| `data/genai_training/*.jsonl` | Generated development datasets |

The included examples validate the pipeline only. Production training needs
approved de-identified data, independent evaluation, model-risk approval, and
privacy/security review.

## Deterministic workflow components

These are policy/orchestration controls, not additional AI models:

| Component | Responsibility |
| --- | --- |
| `loan_origination.py` | Shared submission, bureau routing, and exception handoff |
| `credit_bureau_agent.py` | Consent gate, fictional fixture lookup, deterministic score bands |
| `loan_agent.py` | Missing evidence, bounded retries, variance handling, approval packages |
| `document_verification.py` | Product document requirements and evidence states |
| `document_ai.py` | Deterministic file presence/extension safety baseline |
| `kyc_ai.py` | Consent/format/risk/external-evidence prerequisites |
| `dormancy_agent.py` | Outreach, dormancy, transfer, reactivation, and claim states |
| `automation_agent.py` | Bounded coordination of existing workflows |
| `chat_agent.py` | Deterministic role-scoped support fallback |
| `agent_settings.py` | Availability setting for the one unified model |

None of these deterministic components constitutes another learned model.

## Persistence

| Store | Purpose |
| --- | --- |
| `data/state.json` | Loans, accounts, approvals, and workflow state |
| `data/audit.jsonl` | Local append-only-style events |
| `data/users.json` | Local PBKDF2 password records |
| `data/credit_bureau.sqlite3` | Fictional HMAC-keyed bureau fixtures/checks |
| `data/loan_exception_cases.sqlite3` | Loan exception history |
| `data/dormancy_cases.sqlite3` | Dormancy/outreach/filing history |
| `data/agent_settings.json` | Unified-model enabled state |
| `data/uploads/` | Unencrypted development uploads |
| `data/unified_genai_adapter/` | Optional locally trained adapter/checkpoints |

The running application does not use PostgreSQL yet. Real deployment requires
transactional repositories, encrypted object storage, immutable audit storage,
secrets management, backup/restore, and reconciliation.

## Verification

```powershell
.\.venv-run\Scripts\python.exe -m compileall -q banking_agents scripts
.\.venv-run\Scripts\python.exe -m unittest discover -s tests -v
```

See [API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[UNIFIED_GENERATIVE_AI.md](UNIFIED_GENERATIVE_AI.md), and
[SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md).
