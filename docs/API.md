# API Reference

Base: `/api/v1`. Bearer tokens are process-memory local-demo tokens. Responses use `{data, meta.requestId}`; errors use `application/problem+json`. Sensitive responses carry `Cache-Control: no-store`.

| Method and path | Roles | Purpose |
|---|---|---|
| `GET /health` | Public | Runtime status and retained scope |
| `POST /auth/login` | Public | Local authentication |
| `POST /financial-documents` | Customer, Underwriter, Admin | Multipart PDF/JPG upload for bank statement, ITR or GST |
| `POST /bank-statement-analyses` | Customer, Underwriter, Admin | Analyze structured transactions and evidence |
| `GET /bank-statement-analyses/{id}` | Underwriter, Admin | Retrieve analysis |
| `GET /accounts` | Customer, Compliance, Admin | Role-scoped dormant accounts |
| `POST /dormancy/cycles` | Compliance, Admin | Run configured lifecycle |
| `POST /accounts/{id}/outreach-responses` | Customer owner | Record response/reactivation intent |
| `POST /accounts/{id}/reactivation-requests` | Customer owner | Request KYC-gated reactivation |
| `POST /accounts/{id}/reclaims` | Customer owner | Request claim review |
| `GET /approvals` | Compliance, Admin | Retained approval queue |
| `POST /approvals/{id}/decision` | Compliance, Admin | Maker/checker decision |
| `GET /dormancy/deadline-alerts` | Compliance, Admin | Upcoming/overdue deadlines |
| `POST /accounts/{id}/automation-pause` | Compliance, Admin | Pause/resume with reason |
| `GET /accounts/{id}/regulatory-export` | Compliance, Admin | Simulated versioned evidence export |

The field-level contract is [openapi.json](openapi.json). Upload accepts multiple `files`, `document_type`, and optional `password`. Each file is limited to 10 MB. Analysis input contains `header`, `transactions`, and `evidence`, including consent/source and optional ITR/GST values.
