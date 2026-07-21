-- PostgreSQL schema for the banking-operations AI platform.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_user (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username text UNIQUE NOT NULL,
  role text NOT NULL CHECK (role IN ('CUSTOMER','LOAN','CREDIT','LOAN_OPERATIONS','CREDIT_MANAGER','COMPLIANCE','OPERATIONS','ADMIN')),
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
CREATE TABLE credit_bureau_consent (
  consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id text NOT NULL REFERENCES loan_application(application_id),
  customer_id uuid REFERENCES app_user(user_id), purpose text NOT NULL, consent_version text NOT NULL,
  granted boolean NOT NULL, granted_at timestamptz NOT NULL, revoked_at timestamptz,
  evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE credit_bureau_enquiry (
  enquiry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id text NOT NULL REFERENCES loan_application(application_id),
  consent_id uuid NOT NULL REFERENCES credit_bureau_consent(consent_id), provider text NOT NULL,
  product_name text NOT NULL, provider_reference text, response_status text NOT NULL,
  score integer CHECK (score BETWEEN 300 AND 900), score_band text,
  idempotency_key text UNIQUE NOT NULL, raw_response_hash text,
  requested_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE TABLE credit_policy_decision (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id text NOT NULL REFERENCES loan_application(application_id),
  enquiry_id uuid REFERENCES credit_bureau_enquiry(enquiry_id), policy_version text NOT NULL,
  outcome text NOT NULL, reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  explanation text NOT NULL, human_review_required boolean NOT NULL,
  override_by uuid REFERENCES app_user(user_id), override_reason text,
  created_at timestamptz NOT NULL DEFAULT now()
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

-- Model governance contract. Store only de-identified derived features here;
-- raw documents and direct identity attributes belong in approved source systems.
CREATE TABLE ai_model_catalog (
  model_key text PRIMARY KEY, display_name text NOT NULL, component_type text NOT NULL,
  implementation text NOT NULL, training_supported boolean NOT NULL DEFAULT false,
  risk_tier text NOT NULL, positive_definition text NOT NULL, negative_definition text NOT NULL,
  authority_boundary text NOT NULL, feature_schema jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ai_training_example (
  example_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), example_key text UNIQUE NOT NULL,
  model_key text NOT NULL REFERENCES ai_model_catalog(model_key), entity_type text NOT NULL,
  entity_id_hash text NOT NULL, features jsonb NOT NULL, label smallint NOT NULL CHECK (label IN (0, 1)),
  label_name text NOT NULL, label_source text NOT NULL, human_verified boolean NOT NULL DEFAULT false,
  synthetic boolean NOT NULL DEFAULT false, observed_at timestamptz, source_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ai_training_run (
  run_id text PRIMARY KEY, model_key text NOT NULL REFERENCES ai_model_catalog(model_key),
  status text NOT NULL, algorithm text NOT NULL, dataset_fingerprint text NOT NULL,
  sample_count integer NOT NULL, positive_count integer NOT NULL, negative_count integer NOT NULL,
  human_verified_count integer NOT NULL, synthetic_count integer NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb, artifact_uri text, artifact_sha256 text,
  library_versions jsonb NOT NULL DEFAULT '{}'::jsonb, error_message text,
  started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE TABLE ai_model_prediction (
  prediction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id text NOT NULL REFERENCES ai_training_run(run_id),
  model_key text NOT NULL, entity_type text NOT NULL, entity_id_hash text NOT NULL,
  features jsonb NOT NULL, predicted_label smallint NOT NULL CHECK (predicted_label IN (0, 1)),
  positive_probability numeric(7,6) NOT NULL, advisory_only boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- AI operating controls and bounded support-assistant training. These tables
-- deliberately exclude live chat messages and replies. Only reviewed,
-- curated support examples may be inserted into chatbot_training_example.
CREATE TABLE ai_agent_setting (
  model_key text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT true,
  changed_by uuid REFERENCES app_user(user_id),
  changed_at timestamptz NOT NULL DEFAULT now(),
  change_reason text,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0)
);
CREATE TABLE chatbot_training_example (
  example_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  example_key text UNIQUE NOT NULL,
  utterance text NOT NULL,
  intent text NOT NULL,
  source text NOT NULL,
  synthetic boolean NOT NULL DEFAULT false,
  approved_by uuid REFERENCES app_user(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE chatbot_training_run (
  run_id text PRIMARY KEY,
  status text NOT NULL,
  sample_count integer NOT NULL CHECK (sample_count >= 0),
  intent_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  artifact_uri text,
  artifact_sha256 text,
  library_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  training_data_policy text NOT NULL,
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
-- This event has metadata only. Do not store customer chat text or generated
-- replies here; retain those only through an explicitly approved policy.
CREATE TABLE chat_assistant_event (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id uuid REFERENCES app_user(user_id),
  role text NOT NULL,
  intent text NOT NULL,
  source text NOT NULL,
  mode text NOT NULL,
  read_only boolean NOT NULL DEFAULT true,
  correlation_id uuid,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_workflow_entity ON workflow_step(entity_type, entity_id, occurred_at);
CREATE INDEX ix_loan_status ON loan_application(status, updated_at);
CREATE INDEX ix_bureau_application ON credit_bureau_enquiry(application_id, completed_at);
CREATE INDEX ix_dormancy_due ON dormant_account_case(status, transfer_due_on);
CREATE INDEX ix_ai_training_model ON ai_training_example(model_key, label, label_source);
CREATE INDEX ix_ai_run_model ON ai_training_run(model_key, status, started_at);
CREATE INDEX ix_chatbot_training_intent ON chatbot_training_example(intent, source);
CREATE INDEX ix_chatbot_run_status ON chatbot_training_run(status, started_at);
CREATE INDEX ix_chat_assistant_actor ON chat_assistant_event(actor_user_id, occurred_at);
