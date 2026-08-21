# Technology Stack

## 1. Overview

Banking Operations AI is a Python-based reference application for governed loan-origination, loan-exception, credit-bureau, dormant-account, document-review, and support-chat workflows. It provides a local browser interface, a versioned REST API, command-line utilities, rule-based agents, and optional locally trained advisory models.

The running demonstration uses local JSON and SQLite storage. PostgreSQL is included as a target data model for future production integration, but the application does not currently use PostgreSQL as its runtime repository.

## 2. Stack summary

| Area | Technology | Use in this project |
| --- | --- | --- |
| Language | Python 3.11+ | Application, agents, API, browser server, scripts, and tests |
| REST API | FastAPI | Versioned `/api/v1` endpoints, authentication dependencies, validation, middleware, and OpenAPI generation |
| API server | Uvicorn | ASGI server for the FastAPI application on port 8001 |
| Validation | Pydantic | Strict API request schemas, field constraints, and typed payloads |
| Local web UI | Python `http.server` | Server-rendered, dependency-light browser application on port 8000 |
| Local persistence | JSON, JSON Lines, SQLite | Demo workflow state, users, audit events, cases, credit fixtures, agent settings, and model metadata |
| Target database | PostgreSQL 16 | Production-oriented schema contract and optional Docker service; not connected to the running demo |
| Classical ML | scikit-learn | Local advisory-model and intent-classification training |
| Model artifacts | joblib | Serialization and loading of verified local scikit-learn artifacts |
| Numerical runtime | NumPy, SciPy | Transitive numerical dependencies used by scikit-learn |
| Document AI | PyTorch, Transformers, Accelerate, Pillow | Optional local vision-language document-review provider |
| Model distribution | Hugging Face Hub | Optional download/cache support for the configured document model |
| PostgreSQL client | Psycopg 3 | Driver available for future PostgreSQL adapter implementation |
| API testing | `httpx2` via FastAPI `TestClient` | In-process HTTP tests for API behavior and authorization |
| Test framework | `unittest` | Unit, integration, workflow, database, model, API, and authorization tests |
| Containers | Docker Compose | Optional local PostgreSQL 16 schema environment |

## 3. Application interfaces

### Browser application

`banking_agents/web_app.py` uses Python's standard-library HTTP server. It renders the local multi-role interface and invokes the same application services and workflow agents used by the API and CLI. It runs at `http://127.0.0.1:8000` by default.

No Node.js, npm package, JavaScript framework, or separate frontend build pipeline is required.

### REST API

`banking_agents/api_app.py` defines the FastAPI application. Its main capabilities include:

- versioned routes under `/api/v1`;
- Pydantic request validation with unknown fields rejected;
- bearer-token authentication for the local demo;
- role and customer-ownership authorization;
- exact-origin CORS configuration;
- multipart document upload support;
- RFC-style problem JSON error responses;
- request correlation IDs and `Cache-Control: no-store` on API responses;
- automatically generated OpenAPI, Swagger UI, and ReDoc.

Uvicorn serves the API at `http://127.0.0.1:8001`. Interactive documentation is exposed at `/docs` and `/redoc`.

### Command-line interface

`banking_agents/cli.py` and `banking_agents/__main__.py` provide local workflow commands through `python -m banking_agents`. Supporting scripts under `scripts/` seed demo data, build training data, train and inspect models, score artifacts, download an optional document model, and export OpenAPI.

## 4. Backend and agent architecture

The backend is organized into the following layers:

| Layer | Main modules | Responsibility |
| --- | --- | --- |
| Interfaces | `web_app.py`, `api_app.py`, `cli.py` | Input parsing, authentication, authorization, and response formatting |
| Application services | `loan_origination.py` | Coordinates business use cases across bounded agents |
| Workflow agents | `loan_agent.py`, `credit_bureau_agent.py`, `dormancy_agent.py`, `automation_agent.py` | Applies policies, advances permitted states, and creates human approvals |
| Verification and AI providers | `document_verification.py`, `document_ai.py`, `kyc_ai.py` | Normalizes document and KYC evidence without owning final authority |
| Support assistant | `chat_agent.py`, `chatbot_training.py` | Provides role-scoped, read-only workflow assistance |
| Domain and policy | `models.py`, `policy.py`, `progression.py` | Domain records, statuses, thresholds, and progression rules |
| Persistence and audit | `repository.py`, `audit.py`, `training_store.py`, `*_platform.py` | Stores workflow state, evidence, cases, audit events, and model governance data |
| Model lifecycle | `local_models.py`, training scripts | Feature collection, training, artifact verification, and advisory inference |

The design follows a bounded-agency model. Automated components can collect facts, classify work, recommend actions, and perform explicitly allowed transitions. Credit deviations, compliance sign-off, identity decisions, and customer-money movement remain behind human or external-system control boundaries.

## 5. Data and persistence

### Active local storage

The demo stores data under `data/` using standard-library persistence:

| Storage | Data |
| --- | --- |
| `state.json` | Loan, account, approval, and workflow state |
| `users.json` | Local users and password-verification records |
| JSON Lines audit file | Append-oriented audit events |
| `loan_exception_cases.sqlite3` | Loan-exception cases and supporting artifacts |
| `dormancy_cases.sqlite3` | Dormancy lifecycle cases and evidence |
| `credit_bureau.sqlite3` | Fictional local bureau fixtures and checks |
| Training SQLite databases | Examples, runs, metrics, provenance, and model registry metadata |
| Model artifact directories | Locally trained and integrity-checked advisory artifacts |

This storage is suitable for a local demonstration only. It does not provide production concurrency, high availability, centralized secrets, encryption-key management, backups, or regulated retention controls.

### PostgreSQL target

`database/schema.sql` describes the production-oriented relational contract. `docker-compose.yml` can start PostgreSQL 16 Alpine and initialize that schema. Psycopg is declared as the Python driver, but a PostgreSQL repository adapter is not yet implemented; starting the container does not change the application's active JSON/SQLite persistence.

## 6. AI and machine-learning stack

### Rule-based workflow intelligence

The primary agents are deterministic Python services backed by explicit policies and state transitions. They do not depend on a hosted LLM. This keeps authority boundaries, decision paths, and tests inspectable.

### Locally trained advisory models

scikit-learn and joblib support the locally trainable advisory components and support-chat intent model. The lifecycle includes feature allow-listing, provenance, minimum label requirements, evaluation metadata, artifact hashes, and fail-closed loading. Advisory predictions do not automatically approve credit or move customer funds.

### Optional document AI

The optional document-AI provider uses:

- PyTorch for tensor/model execution;
- Hugging Face Transformers for the vision-language model and processor;
- Accelerate for device-aware model loading;
- Pillow for image decoding and processing;
- Hugging Face Hub for model acquisition and caching.

The default configured model is `Qwen/Qwen2.5-VL-3B-Instruct`. The default runtime provider remains the local baseline unless `DOCUMENT_AI_PROVIDER` is changed. Model weights are separate from the Python packages and must be downloaded explicitly after reviewing licensing, security, data-residency, consent, hardware, and operational requirements.

## 7. Security and governance technologies

The local implementation uses Python cryptographic primitives for password and identifier handling, including PBKDF2-based password derivation, constant-time comparison, SHA-256 artifact hashing, and HMAC-based fictional bureau fixture lookup. It also implements role checks, entity ownership checks, document signature/type validation, audit logging, agent feature controls, and human approval gates.

These are reference controls, not a complete production security platform. Production requires bank-approved identity and access management, managed secrets and keys, TLS termination, database and object encryption, malware scanning, consent evidence, immutable audit retention, monitoring, and external provider controls.

## 8. Testing and quality

The test suite uses Python's built-in `unittest` framework. FastAPI endpoints are tested with `TestClient`, while temporary JSON and SQLite stores provide isolated integration tests. Coverage includes:

- API validation and response behavior;
- authentication, roles, and customer ownership;
- loan and credit-bureau workflows;
- dormancy and approval workflows;
- document and KYC controls;
- chat data scoping and read-only behavior;
- training data governance, artifact integrity, and advisory inference;
- persistence and audit behavior.

Run the complete suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 9. Dependency groups

Dependencies are intentionally separated by capability:

| File | Purpose |
| --- | --- |
| `requirements-api.txt` | FastAPI, Uvicorn, multipart handling, and API test client |
| `requirements-training.txt` | scikit-learn and joblib local training runtime |
| `requirements-postgres.txt` | Psycopg PostgreSQL client |
| `requirements-ai.txt` | Optional PyTorch/Transformers document-AI runtime |

Install the normal browser/API and training stack:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt -r requirements-training.txt
```

Install every optional capability:

```powershell
.\.venv\Scripts\python.exe -m pip install `
  -r requirements-api.txt `
  -r requirements-training.txt `
  -r requirements-postgres.txt `
  -r requirements-ai.txt
```

## 10. Runtime configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `BANKING_DATA_DIR` | `<project>/data` | Overrides the local data directory |
| `BANKING_CORS_ORIGINS` | Local browser origins on port 8000 | Comma-separated exact CORS origins |
| `CREDIT_BUREAU_HASH_KEY` | Unsafe local demo key | HMAC key for fictional bureau fixture identifiers |
| `DOCUMENT_AI_PROVIDER` | `baseline` | Selects the baseline or optional local document provider |
| `DOCUMENT_AI_MODEL` | `Qwen/Qwen2.5-VL-3B-Instruct` | Configures the optional local document model ID |

Production deployments must not rely on the local defaults for secrets or provider selection.

## 11. Production technology gaps

The following technologies and integrations are represented as boundaries or target designs but are not implemented as production runtime components:

- a PostgreSQL-backed repository and migrations;
- bank identity provider integration and durable token/session management;
- object storage, malware scanning, and immutable/WORM audit storage;
- real credit-bureau, KYC, notification, filing, payment, and core-banking adapters;
- centralized secret and key management;
- observability, alerting, distributed tracing, and service-level monitoring;
- production packaging, CI/CD, infrastructure-as-code, and orchestrated deployment;
- model-serving infrastructure, model registry integration, and controlled model rollout.

These gaps are deliberate: the repository is a local reference architecture and must not be treated as a production banking system without those controls.
