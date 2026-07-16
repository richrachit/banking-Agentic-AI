-- PostgreSQL schema for the banking-operations AI platform.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_user (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username text UNIQUE NOT NULL,
  role text NOT NULL CHECK (role IN ('CUSTOMER','LOAN_OPERATIONS','CREDIT_MANAGER','COMPLIANCE','OPERATIONS','ADMIN')),
  password_hash text NOT NULL, status text NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE loan_application (
  application_id text PRIMARY KEY, customer_id uuid REFERENCES app_user(user_id), loan_product text NOT NULL,
  status text NOT NULL, exception_code text, applicant_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  financial_data jsonb NOT NULL DEFAULT '{}'::jsonb, requested_amount numeric(18,2), tenure_months integer,
  ai_decision jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE loan_document (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id text NOT NULL REFERENCES loan_application(application_id),
  document_type text NOT NULL, object_key text NOT NULL, sha256 text NOT NULL, verification_status text NOT NULL DEFAULT 'PENDING',
  ai_result jsonb NOT NULL DEFAULT '{}'::jsonb, uploaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE workflow_step (
  step_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), entity_type text NOT NULL, entity_id text NOT NULL,
  stage text NOT NULL, owner_role text NOT NULL, actor text NOT NULL, outcome text NOT NULL, detail jsonb NOT NULL DEFAULT '{}'::jsonb, occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE approval_case (
  approval_id text PRIMARY KEY, entity_type text NOT NULL, entity_id text NOT NULL, required_role text NOT NULL,
  package jsonb NOT NULL, status text NOT NULL, decision_by uuid REFERENCES app_user(user_id), decision_note text, created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz
);
CREATE TABLE dormant_account_case (
  account_id text PRIMARY KEY, customer_id uuid REFERENCES app_user(user_id), jurisdiction text NOT NULL,
  balance numeric(18,2) NOT NULL, last_customer_activity date NOT NULL, status text NOT NULL, transfer_due_on date,
  filing_data jsonb NOT NULL DEFAULT '{}'::jsonb, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE outreach_attempt (
  outreach_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), account_id text NOT NULL REFERENCES dormant_account_case(account_id),
  channel text NOT NULL, status text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(), evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE immutable_audit_event (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), correlation_id uuid, actor text NOT NULL, action text NOT NULL,
  entity_type text NOT NULL, entity_id text NOT NULL, outcome text NOT NULL, detail jsonb NOT NULL DEFAULT '{}'::jsonb, occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_workflow_entity ON workflow_step(entity_type, entity_id, occurred_at);
CREATE INDEX ix_loan_status ON loan_application(status, updated_at);
CREATE INDEX ix_dormancy_due ON dormant_account_case(status, transfer_due_on);
