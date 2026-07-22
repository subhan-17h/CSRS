import type {
  ChatResponse,
  DocumentsResponse,
  HealthResponse,
  ModelsResponse,
  ProgressEvent
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

export class StreamUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StreamUnavailableError";
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

export async function streamChat(
  question: string,
  options: ChatOptions = {},
  onEvent: (event: ProgressEvent) => void
): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await fetch("/api/chat/stream", {
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
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    if (options.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }
    if (error instanceof TypeError) {
      throw new StreamUnavailableError(error.message);
    }
    throw error;
  }

  if (!response.ok) {
    throw new StreamUnavailableError(await errorDetail(response));
  }
  if (!response.body) {
    throw new StreamUnavailableError("The streaming response did not include a body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: ChatResponse | null = null;

  const processLine = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as ProgressEvent;
    onEvent(event);
    if (event.event === "error") throw new Error(event.message);
    if (event.event === "final") finalResponse = event.response;
  };

  try {
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") throw error;
        if (options.signal?.aborted) {
          throw new DOMException("The operation was aborted.", "AbortError");
        }
        if (error instanceof TypeError) {
          throw new StreamUnavailableError(error.message);
        }
        throw error;
      }

      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      lines.forEach(processLine);
    }

    buffer += decoder.decode();
    processLine(buffer);
  } finally {
    reader.releaseLock();
  }

  if (!finalResponse) {
    throw new Error("The streaming response ended before the final event.");
  }
  return finalResponse;
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
