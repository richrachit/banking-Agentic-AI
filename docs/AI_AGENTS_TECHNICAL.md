# AI Agents: Technical Reference

This document explains the implemented agents, inputs, outputs, state changes, and authority limits. The only learned model is the switchable `UnifiedGenerativeAI`; all other components are deterministic policy/workflow controls. “Agentic AI” here means bounded orchestration around deterministic policy, one advisory model, tools, persistence, audit, and human approvals. It does not mean unsupervised authority over identity, credit, regulation, or customer money.

## 1. Execution topology

```text
Browser UI / FastAPI / CLI
          |
          +-- LoanOriginationService
          |       |
          |       +-- CreditBureauDecisionAgent -- CreditBureauProvider
          |       |
          |       +-- LoanExceptionAgent
          |               +-- DocumentVerificationModel
          |               +-- DocumentAIPipeline (optional provider)
          |               +-- IndiaKycAIAgent (separate control module)
          |
          +-- DormancyAgent
          |
          +-- OperationsAutomationAgent
          |
          +-- BankingSupportChatAgent (read-only, role-scoped)
          |
          +-- LocalRepository / AuditLog / case SQLite stores
          |
          +-- ModelTrainingDatabase / advisory model artifacts
```

The active web/API workflow is deterministic. Locally trained classifiers are kept behind a separate advisory runtime and do not currently drive application states.

## 2. Component registry

| Component | Implementation type | Trigger | Output | Authority limit |
| --- | --- | --- | --- | --- |
| Credit Bureau Decision Agent | Deterministic control | New customer loan after consent | Score metadata, band, rejection/review/continue route | Does not calculate CIBIL, approve, or disburse |
| Loan Exception Agent | Deterministic orchestrator | Held/reopened loan or automation cycle | Evidence request, retry, in-policy resolution, approval package | Cannot override policy/approval or disburse |
| Document Verification Model | Deterministic policy | Missing-document exception | Required/missing/non-valid evidence result | Completeness/status, not authenticity |
| Document AI Pipeline | Provider abstraction | Optional uploaded document triage | Classification/extraction/quality/risk suggestion | No identity or approval authority |
| Qwen Vision Provider | Pretrained foundation model adapter | Optional local image inference | Visual document observations | Always review guidance; not locally trained here |
| India KYC AI Agent | Deterministic control/orchestration | KYC evidence assessment | Pending external verification, manual review, rejection recommendation, or verified prerequisite result | Cannot authenticate Aadhaar/PAN by itself |
| Dormancy Agent | Deterministic orchestrator | Scheduled/as-of run, approval, claim | Outreach/dormancy/transfer/claim transition | No unapproved transfer/claim or legal interpretation |
| Operations Automation Agent | Deterministic supervisor | User/scheduler cycle | Delegated actions and pending human work | Cannot bypass specialist approval gates |
| Loan Exception Advisory | Trained scikit-learn classifier | Explicit local runtime call/script | Positive/negative routing pattern probability | No workflow mutation |
| Document Review Advisory | Trained scikit-learn classifier | Explicit local runtime call | Usable/review pattern probability | No authenticity/KYC/approval |
| Banking Support Chatbot | Deterministic retrieval plus optional trained intent classifier | Authenticated browser/API support question | Role-scoped explanation, safe navigation hints, bounded intent | No workflow mutation, tool call, decision, or customer-money authority |

The AI registry contains only `UnifiedGenerativeAI`. Baseline document and product rules are deterministic controls, not AI models. See [UNIFIED_GENERATIVE_AI.md](UNIFIED_GENERATIVE_AI.md).

## 3. Credit Bureau Decision Agent

### Contract

`CreditBureauProvider.fetch_score(pan, consent_recorded, application_id)` returns:

- nullable `score`;
- normalized band;
- provider identity;
- provider/reference ID; and
- UTC check time.

The local provider requires consent, validates the PAN shape, performs an HMAC-keyed fixture lookup, classifies the result with `PolicyConfig`, and records a lookup audit in `data/credit_bureau.sqlite3`. It is not a TransUnion CIBIL emulator or network adapter.

### Policy behavior

| Condition | `credit_score_decision` | State/action |
| --- | --- | --- |
| Score below `credit_score_reject_below` and demo flag enabled | `REJECTED_LOW_SCORE` | `REJECTED`, explanatory diagnosis |
| No score or below `credit_score_proceed_at_or_above` | `HUMAN_REVIEW` | `AWAITING_APPROVAL`, `CREDIT_SCORE_REVIEW` for Credit Manager |
| Provider fixture/result unavailable | `HUMAN_REVIEW_BUREAU_UNAVAILABLE` | `AWAITING_APPROVAL`, `CREDIT_BUREAU_UNAVAILABLE`; never auto-reject |
| Score at/above proceed threshold | `PROCEED_TO_WORKFLOW` | Remains `HELD`; Loan Origination invokes exception agent |

Defaults are `<650` reject and `>=750` continue, with `650–749` review. These are illustrative bank policy. A score is only an external input; high does not mean approved and no-history does not mean zero.

### Audit/privacy behavior

The loan stores consent version/purpose/time and score, band, provider, reference, checked time, and routing result. Audit/check rows also retain the consent version and fixed purpose; the SQLite bureau database stores the HMAC subject key rather than raw PAN. The default HMAC secret is a local-demo fallback and must be replaced with managed key material. The runtime does not yet implement a signed consent-evidence object or revocation/deletion lifecycle; see the target schema and [API.md](API.md).

An owner of a low-score-rejected loan can create `CREDIT_RECONSIDERATION`. It remains pending until `credit.manager` decides it. Approval re-enters exception checks; rejection preserves the adverse decision. Approved/rejected intermediate, no-history, and unavailable cases also receive an explicit follow-on transition. `LoanExceptionAgent.approve_application()` rejects direct operations approval while a bureau/Credit Manager decision is required.

## 4. Loan Exception Agent

`LoanExceptionAgent` receives a persisted `LoanApplication`, explicit exception code, document evidence, repository, audit log, policy, and optional exception case store.

| Exception | Diagnosis/tool use | Output |
| --- | --- | --- |
| `MISSING_DOCUMENT` | Resolve product requirements; compare evidence states | Precise request and `AWAITING_CUSTOMER`, or resolved path |
| `VERIFY_TRANSIENT_FAILURE` | Execute bounded retry and record attempt | Recovery to `READY_FOR_MAIN_JOURNEY` or retained action |
| `INCOME_VARIANCE` | Compute absolute declared/verified difference ratio | Resolve within tolerance or `LOAN_DEVIATION` approval |

The separate SQLite case store avoids creating another local case for repeated processing of the same application. That is not sufficient for real distributed idempotency; LOS writes and notifications need client/request idempotency keys, a transaction/outbox, and external acknowledgement tracking.

## 5. Document intelligence

### Product rule model

| Product | Required documents |
| --- | --- |
| `PERSONAL` | PAN, Aadhaar, address proof, bank statement, income proof |
| `HOME` | Personal set plus property document |
| `BUSINESS` | PAN, Aadhaar, business registration, bank statement, financial statement |

`DocumentVerificationModel` recognizes `VALID`, `PENDING`, `INVALID`, `EXPIRED`, and `UNREADABLE`. It is intentionally explainable and deterministic because required evidence is policy, not a learned preference.

### Document AI provider interface

`DocumentAIPipeline` keeps provider code outside loan policy. The baseline provider performs conservative file checks and returns pending review. The optional Qwen2.5-VL provider can run local image-text generation for document-type/extraction/quality observations. Neither provider turns an uploaded file into verified identity or an approved loan.

Uploaded file bytes are plain local demo files. The API applies a document-type allowlist plus basic PDF/PNG/JPEG magic-byte matching, but production processing must still introduce malware scanning, full content/container validation, decompression limits, encrypted object storage, content hashes, redaction, approved OCR/authenticity models, model/prompt version capture, and human review.

## 6. India KYC control agent

`IndiaKycAIAgent` combines:

- explicit consent;
- local PAN format and Aadhaar checksum/format checks;
- document-AI risk indicators;
- face-match threshold;
- sanctions result; and
- evidence that approved external PAN and Aadhaar/OVD/CKYCR/V-CIP pathways succeeded as applicable.

Outcomes include `PENDING_EXTERNAL_VERIFICATION`, `MANUAL_REVIEW`, `REJECTED`, and `VERIFIED`. `VERIFIED` is only reachable when the supplied external evidence says the approved prerequisites have passed; the module itself has no UIDAI, CKYCR, PAN issuer, sanctions, or V-CIP network connection.

Face matching and document vision are probabilistic support signals. They must not be treated as proof of identity, and biometric/data processing must follow the applicable approved KYC/privacy architecture.

## 7. Dormancy and unclaimed-balance agent

`DormancyAgent` consumes an account, jurisdiction rule, balance, last-customer-activity date, and as-of date. Its state machine is:

```text
ACTIVE -> OUTREACH -> DORMANT -> TRANSFER_PENDING
       -> TRANSFERRED -> CLAIM_PENDING -> CLAIM_PAID
```

The agent calculates thresholds, records outreach, packages a due transfer, and waits for `compliance.officer`. Later claims require validated entitlement and `claims.officer`. Statutory timelines, eligibility, compliance sign-off, transfer posting, regulator filing, acknowledgement, and claim payment must remain versioned rules plus authorised/reconciled system actions—not learned model predictions.

## 8. Operations automation agent

`OperationsAutomationAgent.run_cycle(as_of)` coordinates existing specialist agents. It can process eligible loans, evaluate dormant accounts, apply already-approved transitions, and report human queues. It does not expand the caller's authority or manufacture an approval.

For production scheduling, add distributed locking, run IDs, checkpoints, idempotency, bounded concurrency, retry/dead-letter handling, timeouts, alerting, and replay controls.

## 9. Local advisory classifiers

Two classifiers are implemented with scikit-learn:

- `loan_exception_resolution_advisory`: derived exception/product/evidence/income/retry/affordability-ratio signals.
- `document_review_advisory`: derived quality/issue/text-length/file-signal features.

Training uses standardized numeric inputs and balanced logistic regression. The runtime returns a label/probability and records an advisory prediction without updating the source application/document. Synthetic examples exist only to exercise both positive and negative paths. Normal training requires at least 20 human-verified positive and 20 human-verified negative examples per model and still requires independent validation beyond that code minimum.

CIBIL/bureau routing is not one of these trainable classifiers. It remains an explicit provider signal plus deterministic policy.

## 10. Model governance controls in code

`ModelTrainingDatabase` records:

- component type, implementation, risk tier, positive/negative meaning, feature schema, authority boundary;
- hashed entity ID, numeric derived features, label name/source, human/synthetic flags, and source hash;
- run status, algorithm, dataset fingerprint, class/provenance counts, metrics, dependency versions, artifact path/SHA-256, and error;
- prediction features, label/probability, hashed entity ID, and `advisory_only=True`.

The runtime checks feature-schema equality, approved directory, artifact existence, SHA-256, model key, and run ID before inference. Joblib is pickle-based and can execute code during load; checksum/provenance controls reduce accidental/supply-chain exposure but do not make an untrusted artifact safe.

## 11. State and database design

### Active local stores

| Store | Agent data |
| --- | --- |
| `state.json` | Applications, accounts, approvals and current status |
| `audit.jsonl` | Actor/action/entity/outcome/detail events |
| `credit_bureau.sqlite3` | Fictional bureau fixtures/checks keyed by HMAC subject |
| `loan_exception_cases.sqlite3` | Exception/document case history |
| `dormancy_cases.sqlite3` | Dormancy/outreach/filing case history |
| `model_training.sqlite3` | Catalog, training examples/runs/predictions |
| `models/*.joblib` | Local advisory artifacts |
| `chatbot_training.sqlite3` | Curated support-intent examples and training-run metadata; never live messages |
| `agent_settings.json` | Component enabled states and last Administrator change |

### PostgreSQL target

`database/schema.sql` defines application/document, bureau consent/enquiry/decision, workflow/approval/audit, dormant-account/outreach, model-governance, AI-availability, and chatbot-governance records. The running agents do not use this schema yet. Production must implement transactional repositories, object/WORM storage, migration/version controls, row-level authorization, retention, backup/restore, and reconciliation.

## 12. Agent audit contract

A material agent action should record:

- who/which service acted;
- normalized action and entity;
- outcome/state transition;
- input/evidence references or hashes;
- policy/provider/model/prompt version;
- confidence/reason codes where relevant;
- approval/override identity and rationale; and
- correlation/idempotency/external reference IDs.

The local `AuditLog` covers a subset. It is append-only-style JSON, not an immutable regulatory record.

## 13. Human-in-the-loop matrix

| Action | Agent may prepare | Agent may execute | Human/system authority required |
| --- | --- | --- | --- |
| Request missing evidence | Yes | Yes, through future notification adapter | Approved template/channel and customer preference |
| Retry transient verification | Yes | Within bounded policy | Provider/system escalation after limit |
| Resolve narrow in-policy exception | Yes | Yes | Versioned policy evidence |
| Reject low-score application | Local demo only | Demo policy can | Production-approved adverse policy, reasons, review/grievance path |
| Approve credit deviation/review | Package only | No | Credit Manager |
| Establish KYC | Evidence orchestration only | No | Approved external KYC route and authorised controls |
| Classify dormancy | Calculate/route | Only against approved rule | Current compliance-approved jurisdiction policy |
| Transfer unclaimed balance | Package only | Only after recorded approval, at local state level | Compliance + core/ledger/regulator adapters/reconciliation |
| Pay customer claim | Package only | Only after validation/approval, at local state level | Claims authority + payment/core integration |
| Disburse loan | No | No | Underwriting/operations/core banking |

## 14. Monitoring recommendations

Monitor agent operations and models separately:

- workflow: case age, evidence turnaround, retry recovery, approval SLA, duplicate actions, transfer timeliness, reconciliation failures;
- credit policy: band distribution, low-score adverse rate, manual-review outcome/overrides, reason completeness, complaints/disputes;
- document/KYC: unreadable/mismatch rates, human overturn, provider failures, subgroup error analysis where lawful;
- trained models: input drift, calibration, precision/recall by approved segment, abstention/review rate, artifact/version health;
- platform: authorization failures, token/session anomalies, upload threats, storage errors, queue depth, API latency/error rate.

See [WORKFLOWS.md](WORKFLOWS.md) for step-by-step business flow, [API.md](API.md) for client contracts, and [ARCHITECTURE.md](ARCHITECTURE.md) for trust boundaries and production evolution.

## 15. Support-chatbot and availability-control implementation

`BankingSupportChatAgent` is intentionally not a general-purpose banking chatbot. It reads only the workflow records visible to the authenticated role and uses a bounded intent set: welcome, loan status, documents, bureau guidance, dormancy, approval queue, AI explanation, action boundary, or fallback. A customer is filtered to loans submitted under their username and accounts matching their customer ID; Compliance is never given loan records; internal queue summaries are filtered to the relevant approver role.

The agent detects requests to approve/reject, change KYC or score, disburse, transfer, or pay money and returns `ACTION_BOUNDARY` without calling a mutating workflow service. The API audit record contains the selected intent/source and `read_only=true`, but no message or reply text.

`LocalChatbotIntentTrainer` seeds 36 curated local phrases into a separate SQLite database and trains a TF-IDF (unigrams/bigrams) plus balanced logistic-regression classifier. The runtime accepts an artifact only when its registered run ID, model key, parent directory, and SHA-256 all match. Confidence below the configured threshold returns `FALLBACK`; an absent/tampered/unloadable artifact also falls back to deterministic retrieval. The classifier chooses a support topic only and cannot invoke tools.

`AgentSettingsStore` exposes an Administrator-controlled enabled flag for all registered components plus the chatbot. Active API/browser workflows check their required component before work begins. A disabled required component produces an unavailable/fail-closed result; the setting never enables a weaker substitute or bypasses human approval. The local JSON file is a demo control plane only. Production needs approved change requests, dual control, centralized feature management, alerts, and an auditable emergency procedure.
