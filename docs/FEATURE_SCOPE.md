# Feature Scope and Source Comparison

## Authoritative sources

- `Bank Statement Analysis.drawio.pdf`
- `2.2 Income & Employment Verification- Account Aggregator Verification.docx`
- `01 Dormant Account & Escheatment Lifecycle Agent.docx`
- `Dormant_Escheatment_Current_State_Before_AI.pdf`
- `Dormant_Escheatment_Future_State_After_AI.pdf`

## Retained feature set

| Feature | Implementation status |
|---|---|
| PDF/JPG upload, 10 MB limit, multiple files, password-protected PDF prompt | Implemented |
| Digital PDF text detection | Implemented; extracted text remains review-required |
| Image/scanned PDF OCR | Provider boundary; routed to `OCR_REVIEW_REQUIRED` |
| Header and transaction structured contract | Implemented |
| Deduplication, whitespace cleansing, standardized dates/currency | Implemented |
| Multi-line narration | Supported when extraction submits combined narration; OCR line reconstruction remains provider work |
| Transaction categorization and transfer-mode detection | Implemented with explainable deterministic patterns |
| Opening/closing/min/max/average balance | Implemented |
| Total debit/credit, monthly cash flow, surplus/deficit | Implemented |
| Income, expenses, EMI/credit-card liability, EMI-to-income | Implemented |
| ITR/GST cross-validation, filing delay and tax-demand risk | Implemented from supplied evidence |
| Large deposits, round amounts, rapid credit/debit, cheque bounce | Implemented/derived |
| Circular funds, related parties, business/personal separation | Requires counterparty graph and account-type/reference data |
| Explainable risk score | Implemented as advisory rules; always human-review required |
| Account Aggregator verification | Consent/source contract implemented; live AA/FIP/FIU connector absent |
| Continuous dormancy staging and configurable jurisdiction rule packs | Implemented; deployment scheduler required |
| Multi-channel outreach tracking | Implemented locally; gateway delivery absent |
| Statutory clock alerts | Implemented |
| Principal/interest transfer package and filing labels | Implemented/configurable; India rate defaults to zero until approved |
| Maker-checker transfer/reactivation/reclaim | Implemented with different-actor enforcement |
| CBS/GL/e-Kuber/UDGAM execution | Simulated status evidence only |
| Account pause/resume | Implemented and audited |
| Reclaim workflow | Implemented locally; entitlement/KYC/payment/refund integration absent |
| Tamper-evident audit | Implemented hash chain; production WORM/immutable store absent |
| Regulatory export | Versioned JSON evidence implemented; certified filing formats absent |

## Removed scope

The following former products were removed because none of the authoritative sources require them: credit-bureau/CIBIL decision agent, generic loan-document exception agent, general support chatbot, local scikit-learn training registry, Qwen document-VLM integration, and their APIs/scripts/database tables.

## Required production integrations

Account Aggregator/FIP/FIU, OCR, CBS, GL, CRM, communications, V-CIP/KYC, ITR/GST/tax data, e-Kuber, UDGAM, payments, object storage, enterprise IAM, KMS, WORM audit, scheduler/queue, tenant isolation, monitoring, and approved regulator schemas.
