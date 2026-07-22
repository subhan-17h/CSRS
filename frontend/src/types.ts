export type Theme = "dark" | "light";

export type Source = {
  doc_name: string;
  page: number | null;
  section: string | null;
  control_id: string | null;
  score: number;
  rank: number | null;
  text: string;
};

export type ChatResponse = {
  answer: string;
  refused: boolean;
  model: string;
  question: string;
  elapsed_ms: number;
  sources: Source[];
};

export type HealthResponse = {
  status: "ok";
  ollama_reachable: boolean;
  chunk_count: number;
  document_count: number;
};

export type DocumentSummary = {
  filename: string;
  chunk_count: number;
  page_count: number | null;
};

export type DocumentsResponse = {
  documents: DocumentSummary[];
  total_chunks: number;
};

export type ModelsResponse = {
  selectable_models: string[];
  missing_models: string[];
  ollama_reachable: boolean;
  default_model: string;
};

export type ProgressStepStatus = "running" | "done" | "error";

export type ProgressEvent =
  | {
      event: "stage_start";
      key: string;
      stage: string;
      message: string;
      detail: Record<string, unknown>;
      ts: number;
    }
  | {
      event: "stage_update";
      key: string;
      stage: string;
      message: string;
      detail: Record<string, unknown>;
      ts: number;
    }
  | {
      event: "stage_end";
      key: string;
      stage: string;
      message: string;
      detail: Record<string, unknown>;
      ts: number;
      elapsed_ms: number;
    }
  | { event: "final"; response: ChatResponse; total_ms: number; ts: number }
  | { event: "ping"; ts: number }
  | { event: "error"; message: string; ts?: number };

export interface ProgressStep {
  key: string;
  message: string;
  status: ProgressStepStatus;
  startedAt: number;
  elapsedMs: number | null;
}

export interface ProgressTrace {
  totalMs: number;
  steps: Array<{
    key: string;
    message: string;
    elapsedMs: number;
    status: ProgressStepStatus;
  }>;
}

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  sources?: Source[];
  refused?: boolean;
  error?: string | null;
  progress?: ProgressTrace;
};
