CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_user (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_subject text UNIQUE NOT NULL,
  role text NOT NULL CHECK (role IN ('CUSTOMER','UNDERWRITER','COMPLIANCE','ADMIN')),
  tenant_id text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE financial_document (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  customer_id text NOT NULL,
  document_type text NOT NULL CHECK (document_type IN ('BANK_STATEMENT','ITR','GST')),
  object_key text NOT NULL,
  sha256 text NOT NULL,
  media_type text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
  password_protected boolean NOT NULL DEFAULT false,
  extraction_status text NOT NULL,
  created_by uuid REFERENCES app_user(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, sha256, document_type)
);

CREATE TABLE verification_consent (
  consent_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  customer_id text NOT NULL,
  purpose text NOT NULL CHECK (purpose='INCOME_AND_EMPLOYMENT_VERIFICATION'),
  source text NOT NULL CHECK (source IN ('DOCUMENT_UPLOAD','ACCOUNT_AGGREGATOR')),
  consented_at timestamptz NOT NULL,
  revoked_at timestamptz,
  evidence_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE bank_statement_analysis (
  analysis_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  customer_id text NOT NULL,
  consent_id text NOT NULL REFERENCES verification_consent(consent_id),
  bank_name text NOT NULL,
  account_number_masked text NOT NULL,
  ifsc_code text,
  branch_name text,
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL DEFAULT 'REVIEW_REQUIRED',
  risk_score integer NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
  risk_level text NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
  metrics jsonb NOT NULL,
  monthly_analysis jsonb NOT NULL,
  category_totals jsonb NOT NULL,
  explanations jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE bank_transaction (
  transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id uuid NOT NULL REFERENCES bank_statement_analysis(analysis_id) ON DELETE CASCADE,
  transaction_key text NOT NULL,
  transaction_date date NOT NULL,
  narration text NOT NULL,
  debit numeric(18,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
  credit numeric(18,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  running_balance numeric(18,2) NOT NULL,
  reference_number text,
  transaction_mode text NOT NULL,
  category text NOT NULL,
  subcategory text,
  UNIQUE (analysis_id, transaction_key),
  CHECK (NOT (debit > 0 AND credit > 0))
);

CREATE TABLE statement_cross_validation (
  analysis_id uuid PRIMARY KEY REFERENCES bank_statement_analysis(analysis_id) ON DELETE CASCADE,
  gst_reported_turnover numeric(18,2),
  itr_reported_income numeric(18,2),
  business_credits numeric(18,2) NOT NULL,
  income_credits numeric(18,2) NOT NULL,
  gst_variance_percent numeric(9,2),
  itr_variance_percent numeric(9,2),
  gst_filing_delays integer NOT NULL DEFAULT 0,
  itr_filing_delays integer NOT NULL DEFAULT 0,
  outstanding_tax_demand numeric(18,2) NOT NULL DEFAULT 0,
  evidence jsonb NOT NULL
);

CREATE TABLE statement_risk_indicator (
  indicator_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id uuid NOT NULL REFERENCES bank_statement_analysis(analysis_id) ON DELETE CASCADE,
  indicator_type text NOT NULL,
  transaction_date date,
  amount numeric(18,2),
  explanation text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dormant_account_case (
  account_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  customer_id text NOT NULL,
  jurisdiction text NOT NULL,
  product_type text,
  status text NOT NULL,
  balance numeric(18,2) NOT NULL,
  last_customer_activity date NOT NULL,
  dormant_on date,
  transfer_due_on date,
  transfer_principal numeric(18,2) NOT NULL DEFAULT 0,
  transfer_interest numeric(18,2) NOT NULL DEFAULT 0,
  automation_paused boolean NOT NULL DEFAULT false,
  pause_reason text,
  paused_by uuid REFERENCES app_user(user_id),
  policy_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outreach_attempt (
  outreach_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id text NOT NULL REFERENCES dormant_account_case(account_id),
  channel text NOT NULL,
  template_version text,
  status text NOT NULL,
  provider_reference text,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  response_at timestamptz,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE approval_case (
  approval_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id text NOT NULL REFERENCES dormant_account_case(account_id),
  kind text NOT NULL CHECK (kind IN ('STATUTORY_CLASSIFICATION','ACCOUNT_REACTIVATION','UNCLAIMED_TRANSFER','CUSTOMER_RECLAIM')),
  status text NOT NULL,
  maker_id uuid REFERENCES app_user(user_id),
  maker_at timestamptz,
  checker_id uuid REFERENCES app_user(user_id),
  checker_at timestamptz,
  decision_note text,
  package jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (maker_id IS NULL OR checker_id IS NULL OR maker_id <> checker_id)
);

CREATE TABLE regulatory_transfer (
  transfer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id text NOT NULL REFERENCES dormant_account_case(account_id),
  approval_id uuid NOT NULL REFERENCES approval_case(approval_id),
  principal numeric(18,2) NOT NULL,
  interest numeric(18,2) NOT NULL,
  gl_status text NOT NULL,
  cbs_status text NOT NULL,
  ekuber_status text NOT NULL,
  udgam_status text NOT NULL,
  regulator_reference text,
  filing_manifest jsonb NOT NULL,
  executed_at timestamptz,
  reconciled_at timestamptz
);

CREATE TABLE customer_reclaim (
  claim_id text PRIMARY KEY,
  account_id text NOT NULL REFERENCES dormant_account_case(account_id),
  approval_id uuid REFERENCES approval_case(approval_id),
  entitlement_status text NOT NULL,
  kyc_status text NOT NULL,
  principal numeric(18,2) NOT NULL,
  interest numeric(18,2) NOT NULL,
  payout_status text NOT NULL,
  payout_reference text,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  paid_at timestamptz
);

CREATE TABLE immutable_audit_event (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_subject text NOT NULL,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  outcome text NOT NULL,
  detail jsonb NOT NULL,
  previous_hash text NOT NULL,
  event_hash text NOT NULL UNIQUE
);

CREATE INDEX ix_transaction_analysis_date ON bank_transaction(analysis_id, transaction_date);
CREATE INDEX ix_statement_customer_created ON bank_statement_analysis(tenant_id, customer_id, created_at DESC);
CREATE INDEX ix_dormancy_deadline ON dormant_account_case(tenant_id, status, transfer_due_on);
CREATE INDEX ix_approval_queue ON approval_case(status, kind, created_at);
CREATE INDEX ix_audit_entity ON immutable_audit_event(tenant_id, entity_type, entity_id, occurred_at);
