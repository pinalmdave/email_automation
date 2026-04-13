export interface EmailRecord {
  message_id: string;
  processed_at: string;
  subject: string;
  from_email: string;
  resume_file: string;
}

export interface FollowupRecord {
  message_id: string;
  processed_at: string;
  intent: string;
  summary: string;
}

export interface ResumeFile {
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface DashboardStats {
  total_emails: number;
  total_followups: number;
  total_resumes: number;
  recent_emails: EmailRecord[];
  pipeline_status: PipelineStatus;
}

export interface PipelineStatus {
  running: boolean;
  current_phase: string | null;
  last_run: string | null;
  last_result: string | null;
  emails_processed: number;
}

export interface DraftEmail {
  uid: string;
  to: string;
  subject: string;
  body: string;
  date: string;
  has_attachment: boolean;
}

export interface Conversation {
  recruiter_email: string;
  recruiter_name: string;
  latest_subject: string;
  message_count: number;
  last_activity: string;
}

export interface ConversationMessage {
  direction: "inbound" | "outbound";
  subject: string;
  body: string;
  date: string;
  intent?: string;
  resume_file?: string;
}

export interface ConversationDetail {
  recruiter_email: string;
  recruiter_name: string;
  messages: ConversationMessage[];
}
