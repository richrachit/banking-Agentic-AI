# Unified generative AI

The project has one advisory task contract with switchable `local` and `hosted`
providers. Both providers return the same structured result and have no direct
access to workflow mutation methods.

Supported tasks:

- customer support;
- loan-exception summaries;
- document and KYC review observations;
- credit-review drafts;
- dormancy-case summaries; and
- compliance-review drafts.

Every response is forced to `advisory_only=true` and
`requires_human_review=true`. The model cannot approve/reject a loan, verify
identity, authenticate a document, override policy, change an account, or move
money.

## Provider configuration

The service defaults to disabled:

```env
GENAI_PROVIDER=disabled
GENAI_ALLOWED_PROVIDERS=local,hosted
```

`GENAI_ALLOWED_PROVIDERS` is the server-side allowlist. An API caller may select
a provider for an individual request only when it is on this list.

### Local

Download the default local text model:

```sh
docker compose --profile generative-ai run --rm genai-download
```

Configure and rebuild the API with AI libraries:

```env
BANKING_IMAGE_TARGET=document-ai
GENAI_PROVIDER=local
GENAI_LOCAL_MODEL=/models/qwen2.5-1.5b-instruct
```

CPU inference is possible but can be slow. Production sizing should account for
model weights, KV cache, concurrent requests, context limits, and GPU/driver
compatibility.

### Hosted

Configure an approved OpenAI-compatible chat-completions endpoint:

```env
GENAI_PROVIDER=hosted
GENAI_HOSTED_ENDPOINT=https://YOUR-APPROVED-PROVIDER.example/v1/chat/completions
GENAI_HOSTED_MODEL=YOUR_APPROVED_MODEL
GENAI_HOSTED_API_KEY=YOUR_SECRET
```

Do not commit `.env`. Before sending banking context to a hosted provider,
complete vendor, privacy, residency, retention, security, and model-risk review.
Minimize/redact prompt context. The audit event records provider/model metadata
but deliberately does not retain the prompt or context.

## Runtime switching

Administrators can inspect configuration:

```http
GET /api/v1/ai/generative/status
```

An authorized role can request a bounded task:

```http
POST /api/v1/ai/generative/tasks
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "task": "LOAN_EXCEPTION_SUMMARY",
  "prompt": "Summarize the missing evidence and safe next steps.",
  "context": {"application_id": "LN-1001", "diagnosis": "Missing bank statement"},
  "provider": "local"
}
```

Set `"provider": "hosted"` to switch for that request. Omit it to use
`GENAI_PROVIDER`. Role-to-task authorization is enforced before either provider
is invoked.

## Fine-tuning

The repository provides four practical training modes for the same model:

- `lora`: recommended for the local 6 GB GPU;
- `qlora`: four-bit Linux/CUDA training with bitsandbytes;
- `full-sft`: full supervised fine-tuning for a substantially larger GPU; and
- `dpo`: preference tuning after a reviewed SFT checkpoint.

Build the curated, non-PII task, refusal, preference, and evaluation datasets:

```powershell
.\.venv-run\Scripts\python.exe scripts\build_genai_datasets.py
```

Install training libraries:

```powershell
.\.venv-run\Scripts\python.exe -m pip install -r requirements-genai-training.txt
```

Run LoRA on the local machine:

```powershell
.\.venv-run\Scripts\python.exe scripts\train_unified_genai.py --method lora
```

Linux/CUDA QLoRA:

```sh
python scripts/train_unified_genai.py --method qlora
```

Full SFT and preference tuning:

```sh
python scripts/train_unified_genai.py --method full-sft
python scripts/train_unified_genai.py --method dpo --model PATH_TO_REVIEWED_SFT_CHECKPOINT
```

The included dataset is a pipeline fixture, not enough evidence for production
fitness. Add only approved, de-identified, human-reviewed examples; retain
separate validation/test sets; test privacy, hallucination, prompt injection,
role leakage, calibration, subgroup performance, and every authority boundary.
Do not use loan approval history as a proxy target or ingest live chat/customer
records without an approved governance process.
