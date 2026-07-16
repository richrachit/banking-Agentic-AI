# Code Documentation

## Project purpose

This repository is a local banking workflow demo that shows how a bank could model loan exception handling, dormant-account lifecycle management, document review, approval routing, and auditability in a simple Python application.

## Main entry points

- Browser app: banking_agents/web_app.py
- CLI workflow runner: banking_agents/cli.py
- Loan workflow engine: banking_agents/loan_agent.py
- Dormancy workflow engine: banking_agents/dormancy_agent.py
- Automation supervisor: banking_agents/automation_agent.py

## File-by-file map

### banking_agents/web_app.py
- Main browser UI and HTTP server.
- Connects the login page, role-based dashboard, customer loan submission, loan review actions, and application detail view.
- Connects to the repository and audit log for persistence and history.
- Feature areas: login, customer onboarding, loan review, approve/reject/reopen, credit/compliance forms, automation trigger.

### banking_agents/loan_agent.py
- Core loan exception workflow engine.
- Handles missing documents, verification retries, income variance, approval requests, and loan approval/rejection/reopen actions.
- Connects to the repository for loan state changes and to the audit log for events.
- Also connects to the document verification engine and optional document AI pipeline.

### banking_agents/dormancy_agent.py
- Manages dormant-account lifecycle progression.
- Handles outreach, dormancy classification, transfer approvals, transfer execution, and claims.
- Connects to the repository and audit log, and to the dormant-case database for case persistence.

### banking_agents/automation_agent.py
- Orchestrates the overall workflow cycle.
- Runs the loan and dormancy agents in a safe human-gated loop.
- Connects to the repository and audit log to collect pending actions.

### banking_agents/repository.py
- Local persistence layer for the demo.
- Main connection point for loan records, account records, approval records, and state updates.
- Stores data in data/state.json.

### banking_agents/audit.py
- Append-only audit log.
- Stores workflow history for actions such as loan review, approval decisions, transfer execution, and automation events.
- Writes to data/audit.jsonl.

### banking_agents/models.py
- Domain models for LoanApplication, Account, Approval, and workflow statuses.
- Defines the business objects that flow through the UI, agents, and repository.

### banking_agents/document_verification.py
- Rules-based document verification engine.
- Checks the product-based required documents and evidence statuses.
- Connects to the loan workflow before applications can proceed.

### banking_agents/document_ai.py
- Optional AI-assisted document review pipeline.
- Produces review suggestions without auto-approving documents.
- Connects to the loan workflow as an optional enhancement layer.

## Feature-to-module mapping

| Feature | Module(s) |
| --- | --- |
| Login and user roles | banking_agents/web_app.py |
| Customer loan submission | banking_agents/web_app.py, banking_agents/loan_agent.py |
| Loan document verification | banking_agents/document_verification.py, banking_agents/loan_agent.py |
| Loan approval / rejection / reopen | banking_agents/web_app.py, banking_agents/loan_agent.py |
| Loan detail view | banking_agents/web_app.py |
| Dormancy lifecycle | banking_agents/dormancy_agent.py |
| Transfer approvals | banking_agents/dormancy_agent.py |
| Claim approvals | banking_agents/dormancy_agent.py |
| Automation cycle | banking_agents/automation_agent.py |
| Persistent state storage | banking_agents/repository.py |
| Audit history | banking_agents/audit.py |

## Persistence and database connections

### Local JSON storage
- data/state.json
  - Stores loans, accounts, and approvals.
  - Connected through banking_agents/repository.py.

### Append-only audit log
- data/audit.jsonl
  - Stores workflow events.
  - Connected through banking_agents/audit.py.

### SQLite-backed case databases
- data/loan_exception_cases.sqlite3
  - Stores loan-exception case records.
  - Connected through banking_agents/loan_exception_platform.py via the loan agent.

- data/dormancy_cases.sqlite3
  - Stores dormant-account and escheatment workflow cases.
  - Connected through banking_agents/dormancy_escheatment_platform.py via the dormancy agent.

## How to follow the flow

1. Start the browser app from banking_agents/web_app.py.
2. Submit or review a loan application from the dashboard.
3. The web app dispatches the request to the loan agent.
4. The loan agent updates status and may create approval records.
5. The repository saves the new state and the audit log records the event.
6. Related dashboards and queues reflect the updated state.

## Notes for future extension

- Replace the local repository with real LOS, CRM, KYC, and core-banking integrations.
- Replace the local audit log with immutable or regulated storage.
- Add stronger authentication and authorization for production use.
