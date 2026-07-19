export type UserRole = 'CUSTOMER' | 'LOAN' | 'CREDIT' | 'COMPLIANCE' | 'ADMIN';

export type AuthenticatedUser = {
  username: string;
  role: UserRole;
  display_name: string;
  customer_id: string;
};

export type Session = {
  accessToken: string;
  user: AuthenticatedUser;
};

export type LoanApplication = {
  application_id: string;
  exception_code: string;
  loan_product: string;
  status: string;
  requested_documents: string[];
  documents: string[];
  document_evidence: Record<string, string>;
  verification_attempts: number;
  declared_income: number;
  verified_income: number;
  relationship_manager: string;
  diagnosis: string;
  applicant_name: string;
  date_of_birth: string;
  email: string;
  phone: string;
  residential_address: string;
  employment_type: string;
  employer_name: string;
  monthly_income: number;
  requested_amount: number;
  tenure_months: number;
  loan_purpose: string;
  submitted_by: string;
  credit_score: number | null;
  credit_score_band: string;
  credit_score_provider: string;
  credit_score_reference: string;
  credit_score_checked_at: string;
  credit_score_decision: string;
};

export type ProgressStage = {
  name: string;
  owner: string;
  ai_active: boolean;
  completed: boolean;
};

export type LoanDetail = {
  application: LoanApplication;
  progress: ProgressStage[];
};

export type Approval = {
  approval_id: string;
  kind: string;
  entity_id: string;
  required_role: string;
  package: Record<string, unknown>;
  status: string;
  decision_by: string | null;
  decision_note: string | null;
};

export type Account = {
  account_id: string;
  customer_id: string;
  jurisdiction: string;
  balance: number;
  last_customer_activity: string;
  status: string;
  outreach_sent: boolean;
  dormant_on: string | null;
  transfer_due_on: string | null;
  transferred_amount: number;
};

export type Dashboard = {
  role: UserRole;
  metrics: {
    loanApplications: number;
    accounts: number;
    pendingApprovals: number;
  };
  recentApplications: LoanApplication[];
  pendingActions: Approval[];
};

export type ChatAction = {
  label: string;
  path: string;
};

export type ChatAssistantResult = {
  reply: string;
  intent: string;
  source: string;
  suggested_prompts: string[];
  actions: ChatAction[];
  agent_name: string;
  mode: string;
  read_only: boolean;
  authority_boundary: string;
};

export type ModelComponent = {
  model_key: string;
  display_name: string;
  component_type: string;
  implementation: string;
  training_supported: boolean;
  risk_tier: string;
  positive_definition: string;
  negative_definition: string;
  authority_boundary: string;
  examples: {
    total: number;
    positive: number;
    negative: number;
    human_verified: number;
    synthetic: number;
  };
  latest_run: null | {
    status: string;
    algorithm: string;
    metrics?: Record<string, number>;
  };
};

export type ModelRegistry = {
  database: string;
  components: ModelComponent[];
};

export type AgentSetting = {
  model_key: string;
  display_name: string;
  component_type: string;
  training_supported: boolean;
  risk_tier: string;
  authority_boundary: string;
  enabled: boolean;
  changed_by: string | null;
  changed_at: string | null;
  fail_closed_when_disabled: boolean;
};

export type ChatbotTrainingSummary = {
  status?: string;
  examples?: {
    total?: number;
    positive?: number;
    negative?: number;
    human_verified?: number;
    synthetic?: number;
  };
  latest_run?: {
    status?: string;
    algorithm?: string;
    metrics?: Record<string, number>;
  } | null;
};

export type AgentSettingsResponse = {
  agents: AgentSetting[];
  chatbotTraining: ChatbotTrainingSummary;
};
