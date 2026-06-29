export interface UsageBucket {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  total_tokens: number;
  api_calls: number;
  cost_usd: number;
  started_at: string;
}

export interface UsageSnapshot {
  session: UsageBucket;
  total: UsageBucket;
}

export interface ResumeInfo {
  filename: string;
  download_url: string;
  role: string;
  company: string;
}

export interface EvaluationInfo {
  score: number;
  accepted: boolean;
  feedback: string;
  recommend_decline?: boolean;
  decline_reason?: string;
}

export interface QualitySettings {
  max_iterations: number;
  acceptance_threshold: number;
}

export type ProcessedEmailStatus = "new" | "approved" | "rejected" | "cancelled" | "sent" | "archived";

export interface ProcessedEmail {
  message_id: string;
  subject: string;
  from_email: string;
  processed_at: string;
  resume_filename: string;
  resume_download_url: string;
  pending_reply_id: string;
  status: ProcessedEmailStatus;
}

export interface Conversation {
  id: string;
  kind: "recruiter_initial" | "followup";
  status: "pending" | "approved" | "sent" | "cancelled" | "send_failed";
  created_at: string;
  updated_at: string;
  intent?: string;
  resume_filename?: string;
  resume_path?: string;
  staffing_company_name?: string;
  target_role_title?: string;
  last_error?: string;
  original: {
    message_id: string;
    from_email: string;
    subject: string;
    date: string;
    imap_uid: string;
    folder: string;
  };
  reply: {
    to: string;
    subject: string;
    body: string;
  };
}

export type ApplyPlanStatus = "planning" | "ready" | "applied" | "cancelled";

export interface ApplyPlan {
  id: string;
  status: ApplyPlanStatus;
  job_url: string;
  job_title: string;
  company_name: string;
  source: string;
  jd_text: string;
  resume_filename: string;
  resume_path: string;
  target_role_title: string;
  staffing_company_name: string;
  evaluation_score?: number;
  recommendation?: "apply" | "decline" | "";
  decline_reason?: string;
  notes: string;
  created_at: string;
  updated_at: string;
  applied_at: string;
}

export interface AppConfig {
  gmail_account: string;
  available_folders: string[];
  default_folders: string[];
  default_hours: number;
  duration_options_hours: number[];
  auto_apply_duration_options_hours?: number[];
  default_max_iterations: number;
  default_acceptance_threshold: number;
  max_iteration_options: number[];
  threshold_options: number[];
}

export interface ProgressEvent {
  event: "started" | "node_complete" | "done" | "error";
  node?: string;
  label?: string;
  current_email?: { subject: string; from_email: string };
  resume?: ResumeInfo;
  evaluation?: EvaluationInfo;
  iteration?: number;
  scanned_count?: number;
  errors?: string[];
  summary?: string;
  usage?: UsageSnapshot;
  message?: string;
  quality?: QualitySettings;
}
