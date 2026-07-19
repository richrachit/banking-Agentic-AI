# Architecture and Coding Standards

## Current architecture

The repository currently implements a local, browser-driven banking workflow reference. It combines a lightweight web application, domain models, policy-driven agents, an append-only audit log, and a JSON-backed repository.

## Feature-to-file map

| Feature | Primary module(s) | Persistence connection |
| --- | --- | --- |
| Role-based browser login and dashboard | `banking_agents/web_app.py` | Reads and writes via `banking_agents/repository.py` and `banking_agents/audit.py` |
| Customer loan submission | `banking_agents/web_app.py`, `banking_agents/loan_agent.py` | Writes loan records to `data/state.json` |
| Document verification and review | `banking_agents/document_verification.py`, `banking_agents/document_ai.py` | Evidence is carried through the loan record and persisted with the loan |
| Loan approval / rejection / reopen | `banking_agents/web_app.py`, `banking_agents/loan_agent.py` | Updates loan status in `data/state.json` and records audit events in `data/audit.jsonl` |
| Dormancy lifecycle and transfer approvals | `banking_agents/dormancy_agent.py` | Updates account state and approval records in `data/state.json` |
| Automation supervisor | `banking_agents/automation_agent.py` | Uses repository and audit outputs to drive the workflow |

### Components

| Layer | Responsibility | Local implementation |
| --- | --- | --- |
| Interface | Browser-based workflow entrypoint for customers, operations, credit, compliance, and admins | `banking_agents/web_app.py` |
| Orchestration | Coordinates loan exception handling, dormancy lifecycle processing, and automation | `banking_agents/loan_agent.py`, `banking_agents/dormancy_agent.py`, `banking_agents/automation_agent.py` |
| Policy | Stores deterministic business thresholds and role-based rules | `banking_agents/policy.py` |
| Domain models | Defines loan, account, approval, and status models | `banking_agents/models.py` |
| Verification | Explains document completeness and status for loan applications | `banking_agents/document_verification.py` |
| Document AI | Optional AI-assisted document review pipeline | `banking_agents/document_ai.py` |
| Persistence | Stores workflow state, approvals, and audit events locally | `banking_agents/repository.py`, `banking_agents/audit.py` |
| CLI | Provides command-line entrypoints for seed data, workflow runs, approvals, and transfer execution | `banking_agents/cli.py` |

## Runtime flow

```text
Browser UI
  -> request handler and role-based form submission
  -> workflow action dispatcher
  -> loan agent / dormancy agent / automation agent
  -> repository state update
  -> audit log write
  -> approval queue / dashboard refresh
```

## Current design decisions

- **Human authority remains explicit.** The agents can diagnose cases, request missing evidence, retry verification, and propose actions, but they do not bypass approvals for deviations or money movement.
- **Policy is data-driven.** Rules such as dormancy thresholds, transfer wait periods, income tolerance, and required roles live in `PolicyConfig` instead of embedded in the agent logic.
- **State transitions are visible and typed.** Loan applications and accounts move through well-defined status values that are persisted and displayed back to the user.
- **Every workflow action is auditable.** The local audit log captures the actor, action, target, outcome, and supporting metadata.
- **The demo stays local and safe.** The repository is file-based and does not perform real payment or identity verification outside the demo model.

## Component responsibilities

### Web app

The current web app is a local HTTP server that supports:

- customer loan submission with document upload fields,
- loan operations review,
- credit decision processing,
- compliance review and transfer approvals,
- automation cycle execution,
- and sign-in/out with role-based access.

### Loan exception agent

The loan agent evaluates the exception code and updates the loan state accordingly. It is responsible for:

- document completeness checks,
- verification retries,
- income deviation handling,
- approval package creation,
- and returning the loan to the main journey after approval.

### Dormancy agent

The dormancy agent handles account lifecycle progression:

- outreach scheduling,
- dormancy classification,
- transfer due date calculation,
- approval request creation,
- transfer execution after approval,
- and claim lifecycle handling.

### Automation controller

The automation agent is a safe supervisor. It iterates through open loans and accounts, executes the constrained workflow steps, and collects pending human actions without bypassing approvals.

## Data and persistence model

The repository persists:

- loan applications,
- account records,
- approvals,
- and workflow events.

The audit layer stores append-only events so the state of the system can be reconstructed and reviewed.

## Production evolution path

To evolve this demo into a production-grade workflow system, the following should be introduced:

- durable workflow orchestration rather than in-process execution,
- real adapters for LOS, KYC, document management, CRM, and core banking,
- signed and versioned policy services,
- identity and authorization infrastructure for real users,
- encrypted document storage and redaction of PII in logs,
- and immutable audit storage with monitoring and replay.

## Coding standards

- Python 3.11+ is the target runtime for this reference implementation.
- Use type hints on public functions and dataclasses for structured business objects.
- Keep modules focused on one business capability; avoid mixing orchestration and integration logic.
- Prefer explicit state transitions and policy-driven rules over ad-hoc conditionals.
- Test success, retry, approval, rejection, and duplicate-run scenarios.
- Keep secrets, customer documents, and regulator-sensitive data out of source control and local audit logs.

## PostgreSQL production data contract

`database/schema.sql` provides a PostgreSQL baseline for users/roles, loan applications, document metadata and AI outputs, workflow steps, approvals, dormant-account cases, outreach, and immutable audit events. Store document bytes in encrypted object storage; persist only an object key, content hash, model result, and retention metadata in PostgreSQL. The JSON and SQLite stores are local-demo adapters, not a production persistence design.

## KYC AI control boundary

`banking_agents/kyc_ai.py` is an AI-assisted KYC orchestration layer. It validates basic PAN/Aadhaar format, consumes document-AI risk results, and requires consent, issuer PAN verification, an authorised Aadhaar/OVD or CKYCR route, and V-CIP where appropriate. It deliberately cannot call UIDAI, CKYCR, PAN issuer, sanctions, or V-CIP services; those must be approved bank integrations. AI results can only route or flag cases, never establish identity by themselves.

## AI agent and model catalog

| Component | Module | What it does | Decision boundary |
| --- | --- | --- | --- |
| Loan Exception Agent | `loan_agent.py` | Diagnoses loan holds, requests evidence, retries verification, resolves narrow variances, and creates credit packages. | Cannot override policy or disburse funds. |
| Dormancy Agent | `dormancy_agent.py` | Applies jurisdiction clocks, starts outreach, prepares transfer approvals, and executes only approved transfers/claims. | Cannot approve or execute unapproved money movement. |
| Operations Automation Agent | `automation_agent.py` | Schedules specialist agents and reports human work queues. | Cannot bypass approval gates. |
| Document Verification Model | `document_verification.py` | Applies product document requirements and identifies missing, pending, invalid, expired, or unreadable evidence. | Completeness only; not authenticity proof. |
| Document AI Pipeline | `document_ai.py` | Provider interface for classification, OCR, field extraction, and tamper-risk signals. | Default provider returns `PENDING`; never identity proof. |
| Qwen Vision Provider | `document_ai.py` | Optional local image-to-text document triage using Qwen2.5-VL. | Review suggestion only; no autonomous approval. |
| India KYC AI Agent | `kyc_ai.py` | Combines consent, format checks, AI risk, face-match thresholds, sanctions, and external KYC prerequisites. | Requires authorised PAN/Aadhaar/OVD, CKYCR, and/or V-CIP checks before `VERIFIED`. |

```text
Customer event -> rules + AI triage -> evidence request / recommendation / exception
               -> named human authority where policy, KYC, fraud, or money movement requires it
               -> audited state update
```

No component in this repository is an autonomous authority for identity proof, policy override, customer-money movement, regulatory sign-off, or disbursement.
