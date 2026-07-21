# Market and regulatory research

## Evidence-backed conclusions

- The loan-exception workflow should be narrow, policy-constrained, and human-gated for deviations. This project therefore automates diagnosis, evidence collection, retry, and case packaging, while reserving policy overrides and financial actions for named approvers.
- Dormant-account work is particularly well suited to rules plus workflow orchestration: the differentiator is jurisdictional clock accuracy, outreach evidence, filing preparation, and defensible records rather than autonomous money movement. Eisen describes this same end-to-end pattern for bank escheatment operations. [Eisen](https://www.witheisen.com/solution/escheatment-for-banks)
- In India, balances in inoperative/unclaimed deposit accounts for ten years or more are transferred to the RBI DEA Fund; the RBI also requires KYC-update availability for activation. [RBI 2025 amendment](https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx?Id=12864)
- RBI's UDGAM portal provides search across 30 banks. [UDGAM](https://systemhealth.rbi.org.in/udgam.rbi.org.in/index.html) A transferred balance remains claimable: the bank repays the customer and seeks an equivalent refund from the Fund, with tranche-level records retained. [DEA Fund Scheme](https://rbi.org.in/scripts/NotificationUser.aspx?Id=8907)

## Applied market patterns

## Agent design research applied to this codebase

The implementation follows the safest common enterprise pattern: narrow agents with deterministic controls and explicit escalation, rather than a single general-purpose agent acting on customer money.

| Market / regulatory insight | Project implementation |
| --- | --- |
| Loan-document automation is valuable when it narrows manual review to exceptions. | `LoanExceptionAgent` and `DocumentVerificationModel` identify the exact evidence gap and route it. |
| AI reliability does not justify unsupervised financial action. | Role checks, approval packages, and audit events gate deviations, transfer, claims, and review actions. |
| Escheatment is primarily a jurisdiction and records problem. | `DormancyAgent` separates outreach, clock calculation, approval, execution, and reclaim. |
| KYC requires authoritative checks, not image understanding alone. | `IndiaKycAIAgent` treats AI as triage and requires approved PAN/Aadhaar/OVD, CKYCR, sanctions, and V-CIP integrations. |
| Document AI is useful for extraction and risk signals. | The provider interface supports approved OCR/VLM/fraud providers but defaults to `PENDING`. |
| Customer-facing AI needs data minimization and a clear authority boundary. | `BankingSupportChatAgent` is role-scoped/read-only, refuses mutating requests, audits intent metadata only, and excludes live chat from training. |
| Operational AI needs an accountable stop control. | Administrator settings disable protected dependencies fail closed; the target database records availability state and audit events, while production requires formal change control. |

## KYC research and regulatory design

The RBI KYC Master Direction describes authorised identification pathways and controls, including PAN verification through the issuing authority, digital/offline Aadhaar or OVD verification where applicable, CKYCR retrieval, and V-CIP standards. It also requires secure infrastructure and controls for non-face-to-face onboarding. [RBI KYC Master Direction](https://systemhealth.rbi.org.in/Scripts/BS_ViewMasDirections.aspx_id%3D11566%282%29.html), [RBI master-directions index](https://old.rbi.org.in/commonman/English/Scripts/MasterDirection.aspx)

This project intentionally does not treat an AI claim as proof that PAN/Aadhaar is authentic. Production onboarding must use contracted, authorised providers and a bank-approved KYC/AML policy, with legal/privacy review before face matching, biometric processing, sanctions screening, or model deployment.

## Production implementation implications

1. Treat AI scores as recommendations, never as authority to transfer funds, override credit policy, or reject a customer without an approved policy basis.
2. Version every policy and model, retain model inputs/outputs and human decisions, and give users an explainable progression view.
3. Use PostgreSQL, object storage, KMS-managed encryption, immutable audit storage, queue-based integrations, and SSO/MFA in deployment—not local JSON, filesystem uploads, or demo credentials.
