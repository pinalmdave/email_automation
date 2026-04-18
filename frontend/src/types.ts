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
}
