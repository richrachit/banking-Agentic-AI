# AI and Agent Technical Reference

The repository contains one learned model: `UnifiedGenerativeAI`. Loan,
credit-bureau, document-rule, KYC, dormancy, and automation components are
deterministic workflow controls. Calling them agents does not make them separate
AI models.

## Architecture

```text
Authenticated browser/API request
        |
        +-- deterministic authorization and ownership scope
        |
        +-- deterministic banking workflow controls
        |      +-- bureau consent/routing
        |      +-- loan exceptions
        |      +-- document requirements/file checks
        |      +-- KYC prerequisites
        |      +-- dormancy/transfer/claim lifecycle
        |
        +-- UnifiedGenerativeAI (advisory only)
               +-- local provider
               \-- hosted provider
```

The model receives only explicitly supplied task context. It has no repository
write method or workflow tool interface.

## Unified task contract

| Task | Intended output | Allowed roles |
| --- | --- | --- |
| `CUSTOMER_SUPPORT` | Bounded explanation | All authenticated roles |
| `LOAN_EXCEPTION_SUMMARY` | Evidence/exception summary | Loan Operations, Administrator |
| `DOCUMENT_REVIEW` | Review observations | Loan Operations, Administrator |
| `KYC_REVIEW` | Missing checks and review needs | Loan Operations, Administrator |
| `CREDIT_REVIEW_DRAFT` | Non-decisional credit note | Credit Manager, Administrator |
| `DORMANCY_CASE_SUMMARY` | Lifecycle summary | Compliance, Administrator |
| `COMPLIANCE_REVIEW_DRAFT` | Non-decisional compliance note | Compliance, Administrator |

Every result includes summary, observations, risks, recommended next steps,
provider/model metadata, `requires_human_review=true`, and
`advisory_only=true`.

## Provider switching

`GENAI_PROVIDER` selects the default: `disabled`, `local`, or `hosted`.
`GENAI_ALLOWED_PROVIDERS` is the server-side allowlist. An authorized request
may select `local` or `hosted` only when allowed. Hosted configuration requires
an endpoint, model ID, and API key. Prompts and context are not written to the
local audit event.

## Authority boundary

The model cannot:

- approve or reject credit;
- authenticate PAN, Aadhaar, or another document;
- claim that an external verification occurred;
- override policy or role checks;
- change a loan/account/approval;
- disburse, transfer, or pay money; or
- expose another user's data.

Deterministic policy and correctly authorized human decisions remain
authoritative.

## Prompt and output controls

- A fixed system instruction defines the advisory boundary.
- Context is serialized as untrusted workflow data.
- Context is limited to 32 KB.
- Hosted output is requested as JSON and validated locally.
- Invalid JSON or unsupported tasks fail closed.
- Provider selection outside the allowlist fails closed.
- Audit records provider/model/task metadata but not prompt text.

These controls reduce risk but do not eliminate hallucination, prompt
injection, privacy leakage, bias, or unsafe recommendations.

## Training

The one model supports:

- LoRA;
- Linux/CUDA QLoRA;
- full supervised fine-tuning; and
- DPO preference tuning after reviewed SFT.

The generated dataset covers all seven tasks plus refusals for unauthorized
approval, identity claims, money movement, policy bypass, and cross-customer
disclosure. It is a small pipeline fixture, not production training evidence.

Production datasets must be approved, de-identified, minimized, versioned, and
split into independent training/validation/test sets. Evaluation must include
privacy, role leakage, prompt injection, hallucination, factual grounding,
authority-boundary compliance, subgroup performance, and human-review quality.

## Deterministic agents

- `CreditBureauDecisionAgent` consumes explicit consent and an authorized/local
  score signal, then applies versionable policy bands.
- `LoanExceptionAgent` diagnoses evidence/retry/variance conditions and creates
  human approval packages.
- `IndiaKycAIAgent` enforces consent, format, risk, and external-verification
  prerequisites; it does not independently verify identity.
- `DormancyAgent` calculates configured dates and waits for compliance/claims
  authority before transfer/payment boundaries.
- `OperationsAutomationAgent` coordinates existing authorized steps without
  expanding authority.

## Governance

The administrator registry contains exactly one model key:
`unified_generative_ai`. Disabling it makes generative task requests return a
fail-closed response. Deterministic workflows continue because they are safety
and business controls, not alternate AI models.

For configuration and commands, see
[UNIFIED_GENERATIVE_AI.md](UNIFIED_GENERATIVE_AI.md).
