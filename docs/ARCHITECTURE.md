# Architecture and Coding Standards

## Components

| Layer | Responsibility | Local implementation |
| --- | --- | --- |
| Interface | CLI/API trigger and operator actions | `cli.py` |
| Orchestration | Coordinates a workflow and compensates failures | `loan_agent.py`, `dormancy_agent.py` |
| Policy | Deterministic, versioned decisions; no hidden policy in prompts | `policy.py` |
| Domain models | Typed business data and state transitions | `models.py` |
| Integrations | LOS/core/CRM/verification/payment boundaries | repository protocol in `repository.py` |
| Evidence | Audit events and approval packages | `audit.py`, `repository.py` |

## Design decisions

- **Human authority is explicit.** The agent may diagnose, request information, retry a non-financial check, and apply narrowly defined in-policy resolutions. It never approves a policy deviation, executes a regulator transfer, or pays a claim without a recorded approval.
- **Policy is data.** Thresholds and statutory periods are represented in `PolicyConfig`; a production version should load signed, versioned policy from a governance-controlled source.
- **Idempotent state transitions.** Re-running an agent does not duplicate approval cases, transfers, or outreach for the same business condition.
- **Auditable actions.** Every material command emits an event with correlation ID, actor, action, outcome, timestamp, and non-sensitive detail.
- **No raw personal data in logs.** The demo only logs identifiers. Production logging must redact/tokenize PII and document contents.

## Recommended production deployment

```text
Event bus / scheduler
   -> workflow service (durable state machine)
       -> policy/rules service
       -> integration adapters: LOS | core banking | KYC | DMS | CRM | payments
       -> approval work queue
       -> immutable audit store + monitoring
```

Use a durable workflow engine for asynchronous waits (customer document, verifier callback, approval, regulator acknowledgement). Keep agent reasoning constrained to retrieving allowed evidence and proposing actions; validate every action against policy and authorization before execution.

## Coding standards

- Python 3.11+, standard library only in this reference implementation.
- Type hints on public functions; `dataclass` models with `Enum` states.
- One business capability per module; orchestration must not contain integration-specific details.
- Use UTC ISO-8601 timestamps, stable IDs, and correlation IDs.
- Prefer explicit state transitions and typed policy decisions over boolean flag sprawl.
- Test normal, retry, duplicate-run, rejection, and approval paths.
- Do not place secrets, regulator credentials, or customer documents in source control or audit logs.
