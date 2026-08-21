# Retained Agents

| Agent/component | Inputs | Outputs | Authority |
|---|---|---|---|
| Bank Statement Extraction boundary | PDF/JPG/AA payload | Digital text or OCR review status | Cannot authenticate or decide |
| Bank Statement Analysis Agent | Header, transactions, consent, ITR/GST values | Clean transactions, categories, metrics, fraud flags, cross-validation, risk/explanations | Advisory only |
| Dormancy Agent | Account, activity date, rule pack, as-of date | Outreach, dates, packages, approvals, claims | Cannot approve transfer/payout |
| Operations Orchestrator | As-of date and repository state | Bounded dormancy cycle and pending actions | Cannot bypass maker-checker |

No generative LLM or locally trained ML model is active. Bank-statement categorization/risk and dormancy are deterministic and explainable. OCR and AA are interfaces awaiting approved providers. A future ML/LLM addition requires labelled data, evaluation, model-risk approval, prompt/data controls, monitoring and human review.
