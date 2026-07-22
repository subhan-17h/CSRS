import type {
  ChatResponse,
  DocumentsResponse,
  HealthResponse,
  ModelsResponse
} from "../types";

export type ChatOptions = {
  model?: string;
  topK?: number;
  temperature?: number;
  signal?: AbortSignal;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    // Some proxy failures return HTML, so the status remains the useful fallback.
  }
  return `Request failed with HTTP ${response.status}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response));
  }
  return (await response.json()) as T;
}

export async function sendChat(
  question: string,
  options: ChatOptions = {}
): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      model: options.model,
      top_k: options.topK,
      temperature: options.temperature
    }),
    signal: options.signal
  });
  return readJson<ChatResponse>(response);
}

export async function fetchHealth(): Promise<HealthResponse> {
  return readJson<HealthResponse>(await fetch("/api/health"));
}

export async function fetchDocuments(): Promise<DocumentsResponse> {
  return readJson<DocumentsResponse>(await fetch("/api/documents"));
}

export async function fetchModels(): Promise<ModelsResponse> {
  return readJson<ModelsResponse>(await fetch("/api/models"));
}
