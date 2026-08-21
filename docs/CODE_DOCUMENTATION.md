# Code Map

| File | Responsibility |
|---|---|
| `api_app.py` | Focused REST API, authentication, RBAC, uploads, analysis and dormancy endpoints |
| `web_app.py` | Responsive browser shell for retained products |
| `bank_statement_agent.py` | Domain records, SQLite persistence, cleansing, categorization, analytics, cross-validation and risk |
| `dormancy_agent.py` | Dormancy, outreach, clocks, interest, approvals, transfer, reclaim, alerts, pause and export |
| `dormancy_escheatment_platform.py` | Dormancy case/outreach/filing SQLite evidence |
| `automation_agent.py` | Bounded dormancy orchestration |
| `policy.py` | JSON rule-pack loader and validation |
| `repository.py` | Local dormant account and approval persistence |
| `audit.py` | Actor-attributed SHA-256 hash-chain events |
| `auth_service.py`, `user_registry.py` | Local-demo identity |
| `models.py` | Dormancy and approval domain objects |

Tests mirror API, analytics, dormancy database, users and UI scope. `scripts/export_openapi.py` regenerates the API snapshot.
