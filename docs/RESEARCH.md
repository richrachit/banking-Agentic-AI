# Market and regulatory research

## Evidence-backed conclusions

- The loan-exception workflow should be narrow, policy-constrained, and human-gated for deviations. This project therefore automates diagnosis, evidence collection, retry, and case packaging, while reserving policy overrides and financial actions for named approvers.
- Dormant-account work is particularly well suited to rules plus workflow orchestration: the differentiator is jurisdictional clock accuracy, outreach evidence, filing preparation, and defensible records rather than autonomous money movement. Eisen describes this same end-to-end pattern for bank escheatment operations. [Eisen](https://www.witheisen.com/solution/escheatment-for-banks)
- In India, balances in inoperative/unclaimed deposit accounts for ten years or more are transferred to the RBI DEA Fund; the RBI also requires KYC-update availability for activation. [RBI 2025 amendment](https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx?Id=12864)
- RBI's UDGAM portal provides search across 30 banks. [UDGAM](https://systemhealth.rbi.org.in/udgam.rbi.org.in/index.html) A transferred balance remains claimable: the bank repays the customer and seeks an equivalent refund from the Fund, with tranche-level records retained. [DEA Fund Scheme](https://rbi.org.in/scripts/NotificationUser.aspx?Id=8907)

## Implementation implications

1. Treat AI scores as recommendations, never as authority to transfer funds, override credit policy, or reject a customer without an approved policy basis.
2. Version every policy and model, retain model inputs/outputs and human decisions, and give users an explainable progression view.
3. Use PostgreSQL, object storage, KMS-managed encryption, immutable audit storage, queue-based integrations, and SSO/MFA in deployment—not local JSON, filesystem uploads, or demo credentials.
