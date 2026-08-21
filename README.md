# Banking Verification and Dormancy AI

Focused reference implementation for two human-controlled banking workflows:

1. Bank-statement and Account Aggregator income/employment verification, including transaction cleansing, categorization, analytics, ITR/GST cross-validation, fraud indicators, and explainable risk insights.
2. Dormant-account and escheatment lifecycle, including detection, outreach, statutory clocks, configurable interest, maker-checker transfer, reclaim, alerts, pause/resume, and regulatory evidence export.

The former generic loan-exception, credit-bureau, support-chatbot, local model-training, and document-VLM products have been removed because they are outside the supplied target flows.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m uvicorn banking_agents.api_app:app --host 127.0.0.1 --port 8001
.\.venv\Scripts\python.exe -m banking_agents.web_app
```

- UI: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8001/docs`
- Health: `http://127.0.0.1:8001/api/v1/health`

Local demo users: `customer/customer123`, `underwriter/underwriter123`, `compliance.officer/compliance123`, and `admin/admin123`. Never use these credentials in production.

## Safety boundary

Risk output is advisory and always requires Underwriter review. Dormancy classification, transfer, reactivation, and claim payout remain human/rule controlled. CBS, GL, communication, V-CIP, Account Aggregator, e-Kuber, UDGAM, tax, and payment integrations are provider boundaries or local simulations; this repository does not move real funds or submit regulatory files.

## Documentation

- [Feature scope and source comparison](docs/FEATURE_SCOPE.md)
- [Workflows](docs/WORKFLOWS.md)
- [API](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Database](docs/DATABASE.md)
- [Agents](docs/AI_AGENTS_TECHNICAL.md)
- [Technology stack and libraries](docs/TECH_STACK.md)
- [Deployment](docs/DEPLOYMENT_PLAN.md)
- [UI design](docs/UI_DESIGN_SYSTEM.md)
- [Code map](docs/CODE_DOCUMENTATION.md)

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
