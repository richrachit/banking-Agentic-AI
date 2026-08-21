# Workflow Reference

## Bank statement and AA verification

```text
Upload PDF/JPG or receive consented AA data
  -> validate type, signature, size and PDF password
  -> extract digital text or route to OCR review
  -> submit structured header + transactions + consent evidence
  -> cleanse and deduplicate
  -> categorize income/debits/liabilities and transaction mode
  -> calculate balance, income, expense and cash-flow metrics
  -> cross-check ITR/GST evidence
  -> detect risk patterns and explain each flag
  -> Underwriter human review
  -> bank-owned rule/decision process outside this service
```

The agent never approves/rejects lending. Account Aggregator source requires purpose-specific consent metadata. Live AA retrieval is not implemented.

## Dormancy and escheatment

```text
Ingest account + last activity
  -> rule-pack detection
  -> outreach before dormancy
  -> response tracking / KYC or V-CIP hand-off
  -> statutory dormancy and transfer clocks
  -> deadline alerts
  -> principal + configured interest + filing package
  -> maker approval
  -> different checker approval
  -> simulated CBS/GL/e-Kuber/UDGAM execution
  -> retained record
  -> customer reclaim
  -> maker-checker payout approval
  -> simulated payout status
```

Compliance/Admin may pause or resume an account with an audited reason. Paused accounts are skipped by automation and alerts.
