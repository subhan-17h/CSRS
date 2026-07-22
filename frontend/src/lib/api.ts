import type {
  ChatResponse,
  DocumentsResponse,
  HealthResponse,
  IndexProgressEvent,
  ModelsResponse,
  ProgressEvent
} from "../types";

export type ChatOptions = {
  model?: string;
  topK?: number;
  temperature?: number;
  signal?: AbortSignal;
};

export type IndexPath = "/api/index/reload" | "/api/index/rebuild";

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

class StreamReadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StreamReadError";
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

async function readNdjson<T>(
  response: Response,
  onEvent: (event: T) => void,
  signal?: AbortSignal
): Promise<void> {
  if (!response.body) throw new Error("The streaming response did not include a body.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const processLine = (line: string) => {
    if (!line.trim()) return;
    onEvent(JSON.parse(line) as T);
  };

  try {
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") throw error;
        if (signal?.aborted) {
          throw new DOMException("The operation was aborted.", "AbortError");
        }
        if (error instanceof TypeError) throw new StreamReadError(error.message);
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

  let finalResponse: ChatResponse | null = null;

  try {
    await readNdjson<ProgressEvent>(
      response,
      (event) => {
        onEvent(event);
        if (event.event === "error") throw new Error(event.message);
        if (event.event === "final") finalResponse = event.response;
      },
      options.signal
    );
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    if (options.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }
    if (error instanceof StreamReadError) throw new StreamUnavailableError(error.message);
    throw error;
  }

  if (!finalResponse) {
    throw new Error("The streaming response ended before the final event.");
  }
  return finalResponse;
}

export async function streamIndex(
  path: IndexPath,
  onEvent: (event: IndexProgressEvent) => void,
  signal?: AbortSignal
): Promise<Extract<IndexProgressEvent, { event: "final" }>> {
  const response = await fetch(path, { method: "POST", signal });
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  if (!response.body) throw new Error("The streaming response did not include a body.");

  let finalEvent: Extract<IndexProgressEvent, { event: "final" }> | null = null;
  await readNdjson<IndexProgressEvent>(
    response,
    (event) => {
      onEvent(event);
      if (event.event === "error") throw new Error(event.message);
      if (event.event === "final") finalEvent = event;
    },
    signal
  );

  if (!finalEvent) throw new Error("The streaming response ended before the final event.");
  return finalEvent;
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
