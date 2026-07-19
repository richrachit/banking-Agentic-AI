# Backend API Reference

This document describes the API implemented by `banking_agents/api_app.py`. The API is a local-development interface for the browser, Android, and iOS clients. It is not a production banking API: authentication tokens are in memory, workflow state is stored in local JSON/SQLite files, and the credit-bureau provider uses fictional fixtures.

## Start the API

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe scripts\seed_credit_bureau_demo.py
.\.venv\Scripts\python.exe -m uvicorn banking_agents.api_app:app --host 127.0.0.1 --port 8001 --reload
```

The default endpoints are:

- API base: `http://127.0.0.1:8001/api/v1`
- Swagger UI: `http://127.0.0.1:8001/docs`
- ReDoc: `http://127.0.0.1:8001/redoc`
- OpenAPI JSON: `http://127.0.0.1:8001/openapi.json`
- Checked-in snapshot: `docs/openapi.json`

Set `BANKING_DATA_DIR` before startup to use a different local data directory. The default is `<project>/data` when the server is started from the project root.

For an Expo web client, the local CORS defaults allow `http://localhost:8081` and `http://127.0.0.1:8081`. Override them with a comma-separated allowlist before startup:

```powershell
$env:BANKING_CORS_ORIGINS = "http://localhost:8081,https://approved.example"
```

## Protocol conventions

### Authentication

Protected routes use an opaque bearer token:

```http
Authorization: Bearer <access-token>
```

`POST /auth/login` returns the token. Tokens are kept only in the API process, have no configured expiry, and are invalidated by an API restart. This is appropriate only for the local demo. A production deployment needs an approved identity provider, short-lived signed/access tokens, MFA where required, revocation, session/device controls, and server-side entitlement checks.

### Success envelope

Successful responses use a consistent envelope and include the request correlation ID:

```json
{
  "data": {},
  "meta": {
    "requestId": "req_..."
  }
}
```

Clients may supply `X-Request-ID`; otherwise the API generates one. A supplied value is accepted only when it contains 1-128 letters, digits, `.`, `_`, `:`, or `-`. The value is also returned in the `X-Request-ID` response header.

Responses under `/api/v1` include `Cache-Control: no-store` so browsers/intermediaries do not cache customer and workflow payloads.

### Errors

Application-generated HTTP errors use `application/problem+json`:

```json
{
  "type": "https://local.banking-ai/problems/http-403",
  "title": "The authenticated role is not authorised for this action.",
  "status": 403,
  "detail": "The authenticated role is not authorised for this action.",
  "requestId": "req_..."
}
```

Request-shape errors also use `application/problem+json`. Their payload adds a `violations` array containing only field location, message, and type. The handler deliberately removes Pydantic's raw `input` values so credentials, PAN, and contact data are not echoed in an error response.

### Content types

- JSON endpoints accept and return `application/json`.
- Document upload uses `multipart/form-data` with `document_type` and `file` parts.
- Uploads accept `.pdf`, `.png`, `.jpg`, and `.jpeg`, must be non-empty, and are limited to 10 MiB.
- Supported document types are `PAN`, `AADHAAR`, `ADDRESS_PROOF`, `BANK_STATEMENT`, `INCOME_PROOF`, `SALARY_SLIP`, `EMPLOYMENT_PROOF`, `INCOME_TAX_RETURN`, `PROPERTY_DOCUMENT`, `BUSINESS_REGISTRATION`, and `FINANCIAL_STATEMENT`.
- Request models reject unknown JSON fields.

## Roles and data scope

| API role | Intended persona | Scope in the current API |
| --- | --- | --- |
| `CUSTOMER` | Applicant/account holder | Own loans and accounts only; create applications, upload own documents, request own-account reactivation |
| `LOAN` | Loan Operations | View loans and loan/credit-related approval context, upload documents, run the exception agent, run automation |
| `CREDIT` | Credit Manager | View loans and credit-manager approvals; decide matching approvals |
| `COMPLIANCE` | Compliance Officer | View accounts and compliance approvals; run dormancy; decide matching approvals; run automation |
| `ADMIN` | Local administrator | Cross-system visibility, automation, model registry, and—currently—any approval decision |

Customer ownership checks intentionally return `404` for another customer's resource to avoid confirming its existence. The current `ADMIN` decision permission is a demo convenience; production segregation of duties should prevent administrators from becoming implicit business approvers.

Self-signup accepts `CUSTOMER`, `LOAN`, `CREDIT`, and `COMPLIANCE`. A customer is activated immediately; staff registrations are stored as `PENDING_APPROVAL`. This repository does not yet expose a staff-activation API. `ADMIN` self-signup is not supported.

## Endpoint matrix

All paths below are relative to `/api/v1`.

| Method and path | Authentication | Allowed roles | Result |
| --- | --- | --- | --- |
| `GET /health` | No | Public | Runtime status and active persistence type |
| `POST /auth/login` | No | Public | In-memory bearer token and user profile |
| `POST /auth/signup` | No | Public | Local user registration status |
| `POST /auth/logout` | Optional bearer | Any | Removes the supplied token if present |
| `GET /me` | Bearer | Any authenticated role | Current user identity |
| `GET /me/dashboard` | Bearer | Any authenticated role | Role-scoped metrics, recent applications, pending actions |
| `POST /loan-applications` | Bearer | `CUSTOMER` | Creates an ID, records the application, fetches the local bureau fixture, and routes the loan |
| `GET /loan-applications` | Bearer | `CUSTOMER`, `LOAN`, `CREDIT`, `ADMIN` | Customer-owned or role-wide loan list |
| `GET /loan-applications/{application_id}` | Bearer | `CUSTOMER`, `LOAN`, `CREDIT`, `ADMIN` | Application plus user-facing workflow progression |
| `POST /loan-applications/{application_id}/credit-review-requests` | Bearer | `CUSTOMER` | Requests Credit Manager reconsideration of the customer's low-score rejection |
| `POST /loan-applications/{application_id}/documents` | Bearer | `CUSTOMER`, `LOAN`, `ADMIN` | Stores a file locally and marks its evidence `PENDING` |
| `POST /loan-applications/{application_id}/run-exception-agent` | Bearer | `LOAN`, `ADMIN` | Runs deterministic loan exception handling |
| `GET /approvals` | Bearer | `LOAN`, `CREDIT`, `COMPLIANCE`, `ADMIN` | Role-scoped queue: Loan sees loan/credit context, Credit/Compliance see their authority, Admin sees all |
| `POST /approvals/{approval_id}/decision` | Bearer | `CREDIT`, `COMPLIANCE`, `ADMIN` | Approves/rejects only when the actor has the required authority |
| `GET /accounts` | Bearer | `CUSTOMER`, `COMPLIANCE`, `ADMIN` | Customer-owned or role-wide account list |
| `POST /accounts/{account_id}/reactivation-requests` | Bearer | `CUSTOMER` | Creates a compliance approval after current-KYC confirmation |
| `POST /dormancy/cycles` | Bearer | `COMPLIANCE`, `ADMIN` | Saves the supplied account facts and evaluates its lifecycle at an as-of date |
| `POST /automation/cycles` | Bearer | `LOAN`, `COMPLIANCE`, `ADMIN` | Runs the bounded loan/dormancy supervisor cycle |
| `GET /ai/models` | Bearer | `ADMIN` | Model catalog, local data counts, and latest training-run metadata |

The generated OpenAPI document is the field-level contract. The sections below explain the business behavior that cannot be inferred from schemas alone.

Regenerate the checked-in snapshot after any request/response/route change:

```powershell
.\.venv\Scripts\python.exe scripts\export_openapi.py
```

## Authentication examples

Login request:

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "<username>",
  "password": "<password>",
  "user_type": "CUSTOMER"
}
```

Signup request:

```json
{
  "username": "new.customer",
  "password": "a-long-local-password",
  "display_name": "New Customer",
  "email": "customer@example.test",
  "user_type": "CUSTOMER"
}
```

Passwords must contain at least 10 characters for registered users. Local static demo users are implemented in `banking_agents/auth_service.py`, but credentials should not be displayed in an application screen or copied into production configuration.

## Create a loan application

`POST /loan-applications` accepts:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `applicant_name` | string | Yes | Local application record only |
| `date_of_birth` | ISO date | Yes | Must be a valid date in the past |
| `email`, `phone`, `residential_address` | string | Yes | PII; must be protected and minimized in production |
| `loan_product` | enum | No | `PERSONAL`, `HOME`, or `BUSINESS`; defaults to `PERSONAL` |
| `requested_amount` | number | Yes | Must be greater than zero |
| `tenure_months` | integer | Yes | Must be greater than zero |
| `loan_purpose` | string | Yes | 1-500 characters |
| `employment_type` | enum | Yes | `SALARIED`, `SELF_EMPLOYED`, or `BUSINESS_OWNER` |
| `employer_name` | string | No | Defaults to empty |
| `monthly_income` | number | Yes | Must be greater than zero; annual declared income is derived as monthly × 12 |
| `pan_for_bureau_lookup` | string | Yes | PAN-shaped value (`AAAAA9999A`); used for HMAC fixture lookup and not placed in the loan model |
| `credit_bureau_consent` | boolean | Yes | Must be `true` before lookup |
| `consent_version` | enum | No | Only `CREDIT_BUREAU_CONSENT_V1`; stored with purpose/time in local loan, audit, and check records |
| `uploaded_document_types` | string array | No | Up to 20 supported types; creates `PENDING` metadata, then bytes are uploaded separately |

Example using a fictional seeded development subject:

```json
{
  "applicant_name": "Example Applicant",
  "date_of_birth": "1990-01-01",
  "email": "applicant@example.test",
  "phone": "9999999999",
  "residential_address": "Example address",
  "loan_product": "PERSONAL",
  "requested_amount": 250000,
  "tenure_months": 24,
  "loan_purpose": "Education",
  "employment_type": "SALARIED",
  "employer_name": "Example Employer",
  "monthly_income": 50000,
  "pan_for_bureau_lookup": "DEMOA0001A",
  "credit_bureau_consent": true,
  "consent_version": "CREDIT_BUREAU_CONSENT_V1",
  "uploaded_document_types": ["PAN", "AADHAAR", "BANK_STATEMENT"]
}
```

The application ID is generated by `LocalRepository.generate_application_id()`; clients must not submit it.

## Credit-bureau/CIBIL-style decision branch

The local provider is `LOCAL_CIBIL_STYLE_FIXTURE`; it is not TransUnion CIBIL and makes no network call. Run `scripts/seed_credit_bureau_demo.py` to install fictional fixtures. PAN values are normalized, validated, and converted to an HMAC-SHA256 subject key; the raw value is not stored in the fixture/check database. The default HMAC key is deliberately marked unsafe for production.

The local `PolicyConfig` implements illustrative bank thresholds:

| Provider result | Local band | Current demo result |
| --- | --- | --- |
| Score `300-649` | `LOW` | `REJECTED` with `REJECTED_LOW_SCORE` when `auto_reject_low_credit_score=True` |
| Score `650-749` | `REVIEW` | `AWAITING_APPROVAL`; creates `CREDIT_SCORE_REVIEW` for `credit.manager` |
| Score `750-900` | `HIGH` | `PROCEED_TO_WORKFLOW`; document/exception checks continue, but the loan is not approved or disbursed |
| Provider returns no score | `NO_HISTORY` | `AWAITING_APPROVAL`; never coerced to zero |
| No local fixture/provider result | n/a | `AWAITING_APPROVAL`; creates `CREDIT_BUREAU_UNAVAILABLE` for manual retrieval/retry |

These cutoffs are application policy, not a rule supplied by CIBIL or RBI. CIBIL describes scores as ranging from 300 to 900 and says higher scores indicate lower credit risk; a bureau signal does not itself approve a loan. A real deployment must use the bank's authorised bureau product/API, capture purpose-specific consent evidence, version the policy, explain an adverse result, and provide review/dispute handling. See the [CIBIL score FAQ](https://www.cibil.com/faq/understand-your-credit-score-and-report), [TransUnion CIBIL Consumer Credit Risk Assessment](https://apimarketplace.transunioncibil.com/products/credit-data/consumer-credit-risk-assessment), and [RBI Digital Lending Directions, 2025](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0).

The local runtime records the supported consent version, fixed purpose, and UTC time on the loan and in the audit log; the fixture-check row records version and purpose with the provider result. It still lacks a separately signed/hashed consent-evidence object, revocation/deletion lifecycle, and immutable retention. The PostgreSQL target includes `credit_bureau_consent`, `credit_bureau_enquiry`, and `credit_policy_decision` so evidence hash, provider reference, idempotency, reason codes, and overrides can be retained. Implement that adapter before production use.

### Low-score reconsideration

The owner of a loan with `status=REJECTED` and `credit_score_decision=REJECTED_LOW_SCORE` may call the reconsideration route:

```json
{
  "reason": "The bureau record has been corrected; please review the updated information.",
  "bureau_dispute_reference": "OPTIONAL-REFERENCE"
}
```

`reason` must contain 10-1000 characters. The route creates `CREDIT_RECONSIDERATION` for `credit.manager`; it does not silently reverse the decision. When the Credit Manager approves, the loan returns to `HELD` and the exception agent continues. When rejected, the adverse state is retained with the decision note. The local flow is only a workflow demonstration, not a complete CIC dispute/grievance process.

## Upload a document

Upload after the application has been created:

```powershell
curl.exe -X POST "http://127.0.0.1:8001/api/v1/loan-applications/<application-id>/documents" `
  -H "Authorization: Bearer <access-token>" `
  -F "document_type=PAN" `
  -F "file=@C:\path\to\pan.pdf;type=application/pdf"
```

The `document_type` must be in the API's supported allowlist. The adapter checks PDF/PNG/JPEG magic bytes against the filename extension, writes the bytes to `data/uploads/<application-id>/`, and stores `PENDING` evidence in the loan state. It does not perform malware scanning, full MIME/container validation, encryption, object-storage retention, OCR, authenticity checks, or KYC. Those are mandatory production integration boundaries.

## Approval decisions

```json
{
  "decision": "APPROVED",
  "note": "Reviewed against policy version and supporting evidence."
}
```

`decision` accepts only `APPROVED` or `REJECTED`; a rejection requires a non-empty note and an already-decided approval returns `409`. Credit actors can decide `credit.manager` cases; compliance actors can decide `compliance.officer` cases. The endpoint applies the matching follow-on transition: credit review/reconsideration continues or rejects the loan, loan-deviation approval/rejection updates it, reactivation approval restores the local account to `ACTIVE`, and approved transfer/claim cases invoke their local execution paths. Loan disbursement is not implemented.

The response contains `approval`, nullable `updatedEntity`, `executedTransfers`, and `executedClaims`, allowing a client to refresh the affected workflow without guessing which follow-on action occurred.

## Dormant-account requests

Customer reactivation:

```json
{
  "kyc_confirmed": true
}
```

This is accepted only for the customer's `OUTREACH`, `DORMANT`, or `TRANSFER_PENDING` account and creates `ACCOUNT_REACTIVATION` for `compliance.officer`. Approval restores the local account to `ACTIVE`, clears dormancy/transfer dates, refreshes its last-activity date, and cancels a pending transfer approval. A real KYC/core-banking reactivation is still an external integration.

Compliance lifecycle run:

```json
{
  "account_id": "AC-EXAMPLE",
  "customer_id": "CUST-EXAMPLE",
  "jurisdiction": "IN-RBI-DEA",
  "balance": 12500,
  "last_customer_activity": "2015-01-15",
  "as_of_date": "2026-07-20"
}
```

The included jurisdiction thresholds are illustrative. Legal/compliance must approve current rules before any live dormancy classification, filing, transfer, or claim processing.

## Production hardening checklist

- Replace local users and in-memory tokens with the bank IdP, least-privilege RBAC/ABAC, MFA, token expiry, rotation, and revocation.
- Replace JSON/SQLite adapters with transactional PostgreSQL repositories and optimistic/concurrency controls.
- Replace the fictional bureau provider with an authorised integration using mTLS/OAuth, explicit consent evidence, idempotency, provider response validation, and reconciliation.
- Move document bytes to encrypted object storage; add malware/content scanning, signed upload URLs, checksums, retention, and deletion workflows.
- Configure `BANKING_CORS_ORIGINS` as a comma-separated allowlist for browser clients. The local defaults allow `http://localhost:8081` and `http://127.0.0.1:8081`; wildcard origins are discarded and credentials are disabled.
- Apply request/rate limits, abuse controls, structured audit logging, secret management, observability, backups, disaster recovery, and immutable evidence storage.
- Remove the demo `ADMIN` approval capability to preserve maker-checker segregation of duties.
- Treat generated OpenAPI as a versioned artifact and add compatibility/contract tests before releasing mobile or partner clients.

## Tests covering the API

`tests/test_api_app.py` covers OpenAPI/health, validation redaction, CORS/cache headers, role and ownership boundaries, score branches/provider unavailability, consent metadata, reconsideration, approval continuation/idempotency, document validation, account reactivation, and admin-only model-registry access. `tests/test_credit_bureau_agent.py` covers high, low, intermediate, no-history, unavailable-provider, consent-version/purpose, continuation, and raw-PAN non-storage behavior.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
