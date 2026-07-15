# Banking Operations Resolution Agents

A local, dependency-free reference implementation for two bank-operations agents:

- **Loan Exception Resolution Agent**: investigates stalled applications, obtains missing evidence, retries checks, resolves permitted exceptions, and creates approval cases for deviations.
- **Dormant Account & Unclaimed Balance Agent**: identifies accounts nearing dormancy, drives re-engagement, classifies dormant accounts, manages statutory timelines, prepares DEA-style transfers, and supports customer claims.

> This is a workflow and integration reference, not a production banking system. Production deployment requires approved integrations, identity/consent controls, encryption, segregation of duties, regulator-approved rules, and legal/compliance validation for each jurisdiction.

## What runs locally

The CLI persists its state to `data/state.json` and emits an append-only audit log to `data/audit.jsonl`. It uses deterministic policy rules and deliberately keeps money movement and policy deviations behind a human approval gate.

```text
Input adapters -> Detect/classify -> Diagnose -> Resolve / seek evidence
                                       |                 |
                                       +-> Human approval +-> Core-system update
                                                              -> Audit + notify
```

## Quick start

Requirements: Python 3.11+ (no package install required).

```powershell
cd "D:\Agentic Ai"
python -m banking_agents seed-demo
python -m banking_agents run-loan --application-id LN-1001
python -m banking_agents run-loan --application-id LN-1002
python -m banking_agents decide --approval-id APR-0001 --actor credit.manager --approve
python -m banking_agents run-dormancy --as-of 2026-07-15
python -m banking_agents decide --approval-id APR-0002 --actor compliance.officer --approve
python -m banking_agents execute-transfers
python -m banking_agents request-claim --account-id AC-2001 --claim-id CLM-001 --validated
python -m banking_agents decide --approval-id APR-0003 --actor claims.officer --approve
python -m banking_agents execute-claims
python -m banking_agents list-events
```

## Three-user browser application

Start the local application and open `http://127.0.0.1:8000` in a browser:

```powershell
.\.venv\Scripts\python.exe -m banking_agents.web_app
```

It has separate forms for **Loan Operations**, **Credit Manager**, and **Compliance Officer**. Each user submits their details and the resulting workflow status and approval queue are displayed immediately. This is a local demo UI; production authentication must use the bank identity provider and enforce roles server-side.

### Agentic automation

The **Agentic AI Automation Controller** runs the operational cycle without an operator having to process each record: it scans all open cases, delegates loan exceptions to the loan specialist, runs dormancy lifecycle checks, applies already-approved decisions, and records each action. It is intentionally constrained by policy: only the Credit Manager can approve a loan deviation and only the Compliance Officer can approve an unclaimed-balance transfer.

### Loan document verification model

For a `MISSING_DOCUMENT` loan exception, the application now checks the required document set by product and requests the exact outstanding item. Supported products and base requirements are:

| Product | Required documents |
| --- | --- |
| Personal | PAN, Aadhaar, address proof, bank statement, income proof |
| Home | Personal requirements plus property document |
| Business | PAN, Aadhaar, business registration, bank statement, financial statement |

In the browser form, enter evidence as `DOCUMENT:STATUS`, for example `PAN:VALID,AADHAAR:EXPIRED`. Accepted statuses are `VALID`, `PENDING`, `INVALID`, `EXPIRED`, and `UNREADABLE`. The model is an explainable completeness/status rules engine; it is not a replacement for a regulated document-authenticity, OCR, KYC, or fraud model.

Run a cycle from the command line:

```powershell
.\.venv\Scripts\python.exe -m banking_agents run-automation --as-of 2026-07-15
```

After approving `APR-0001`, run `run-loan` again to apply the approved deviation and return the loan application to the main journey.

## Workflows

### 1. Loan exception resolution

```text
LOS exception
  -> classify (document / verification / policy deviation)
  -> diagnose from documents and verification results
  -> request missing item OR retry a transient check
  -> auto-resolve only if policy permits
  -> otherwise create an approval package
  -> apply approved decision to LOS
  -> notify customer / relationship manager and write audit event
```

Supported demo cases:

| Exception | Agent action |
| --- | --- |
| `MISSING_DOCUMENT` | Requests the exact document and records the customer task. |
| `VERIFY_TRANSIENT_FAILURE` | Re-executes verification; succeeds on the configured retry. |
| `INCOME_VARIANCE` | Auto-resolves when within tolerance; otherwise creates a credit approval package. |

### 2. Dormancy and unclaimed balance lifecycle

```text
Active account approaching threshold
  -> schedule multi-channel re-engagement
  -> classify dormant at policy threshold
  -> calculate transfer due date by jurisdiction
  -> prepare transfer package once due
  -> compliance approval
  -> execute ledger transfer and retain claim record
  -> validate and pay later customer claims (approval required)
```

The included `IN-RBI-DEA` example uses *illustrative* timelines. Configure rules only after compliance confirms the governing law and bank policy.

## Architecture and coding standards

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component boundaries, controls, extension points, and coding standards. See [docs/WORKFLOWS.md](docs/WORKFLOWS.md) for the implementation-level workflow steps.

## Commands

```powershell
python -m banking_agents --help
python -m banking_agents reset-demo             # removes only generated local data
python -m banking_agents list-approvals
python -m banking_agents list-events
python -m unittest discover -s tests -v
```

Run tests from the project root with the module command above. Do **not** run `python tests/test_workflows.py` directly, because that makes the `tests` folder the import root and causes `ModuleNotFoundError: banking_agents`. In VS Code, select **Debug workflow tests** from the Run and Debug panel; the project includes `.vscode/launch.json` with the correct working directory.

## Local setup steps

1. Install Python 3.11 or newer and ensure `python --version` works in PowerShell.
2. Copy this project to a local folder and open PowerShell in that folder.
3. Run `python -m banking_agents seed-demo` to initialize sample applications, accounts, and policies.
4. Run the Quick start commands above.
5. Inspect `data/state.json` and `data/audit.jsonl` to see persisted workflow state and immutable-style audit events.
6. Replace the JSON repositories in `banking_agents/repository.py` with LOS, core-banking, CRM, document, verification, and payment adapters before connecting real systems.

## Optional local document-AI model

The app includes an optional Qwen2.5-VL vision-language provider for image document triage. It requires substantial disk/RAM and benefits from a GPU. It only produces a review suggestion and never automatically approves a document.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
.\.venv\Scripts\python.exe scripts\download_document_model.py
$env:DOCUMENT_AI_PROVIDER = "qwen"
```

Set `DOCUMENT_AI_MODEL` to another approved model identifier or a local model path if needed. Qwen2.5-VL image-text generation is documented by [Hugging Face Transformers](https://huggingface.co/docs/transformers/model_doc/qwen2_5_vl); check the model card/license and customer-data requirements before downloading or deploying it.

## Production integration checklist

- Use API adapters with mTLS/OAuth, least-privilege service identities, idempotency keys, and retry/dead-letter handling.
- Store audit evidence in WORM/immutable storage; do not rely on the local JSON log.
- Keep rules versioned, approved, jurisdiction-scoped, and tested before activation.
- Require maker-checker approval for deviations, filings, transfers, and claims.
- Encrypt sensitive data, tokenize documents, enforce consent and retention/deletion schedules.
- Reconcile transfer batches with the general ledger and regulator acknowledgements.
>>>>>>> ea8f23d (feat: Implement document AI pipeline for loan-document verification)
