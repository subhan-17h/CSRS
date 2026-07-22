import type { Message, Source } from "../types";

export const HISTORY_STORAGE_KEY = "csrs.history.v1";
export const MAX_CONVERSATIONS = 20;

const HISTORY_VERSION = 1;
const MAX_TITLE_LENGTH = 60;
const MAX_SOURCES_PER_MESSAGE = 20;

export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
};

export type HistoryStorage = Pick<Storage, "getItem" | "setItem">;

type HistoryPayload = {
  version: typeof HISTORY_VERSION;
  conversations: Conversation[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function parseSource(value: unknown): Source | null {
  if (!isRecord(value)) return null;
  if (typeof value.doc_name !== "string") return null;
  if (value.page !== null && (!isFiniteNumber(value.page) || !Number.isInteger(value.page))) {
    return null;
  }
  if (value.section !== null && typeof value.section !== "string") return null;
  if (value.control_id !== null && typeof value.control_id !== "string") return null;
  if (!isFiniteNumber(value.score)) return null;
  if (value.rank !== null && (!isFiniteNumber(value.rank) || !Number.isInteger(value.rank))) {
    return null;
  }
  if (typeof value.text !== "string") return null;

  return {
    doc_name: value.doc_name,
    page: value.page,
    section: value.section,
    control_id: value.control_id,
    score: value.score,
    rank: value.rank,
    text: value.text
  };
}

function parseMessage(value: unknown): Message | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || !value.id) return null;
  if (value.role !== "user" && value.role !== "assistant") return null;
  if (typeof value.text !== "string") return null;
  if ("refused" in value && typeof value.refused !== "boolean") return null;
  if ("sources" in value && !Array.isArray(value.sources)) return null;
  if (
    Array.isArray(value.sources) &&
    value.sources.length > MAX_SOURCES_PER_MESSAGE
  ) {
    return null;
  }

  let sources: Source[] | undefined;
  if (Array.isArray(value.sources)) {
    sources = [];
    for (const sourceValue of value.sources) {
      const source = parseSource(sourceValue);
      if (!source) return null;
      sources.push(source);
    }
  }

  return {
    id: value.id,
    role: value.role,
    text: value.text,
    ...(sources ? { sources } : {}),
    ...(typeof value.refused === "boolean" ? { refused: value.refused } : {})
  };
}

function parseConversation(value: unknown): Conversation | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || !value.id) return null;
  if (
    typeof value.title !== "string" ||
    !value.title.trim() ||
    value.title.length > MAX_TITLE_LENGTH
  ) {
    return null;
  }
  if (!isFiniteNumber(value.createdAt) || value.createdAt < 0) return null;
  if (!isFiniteNumber(value.updatedAt) || value.updatedAt < value.createdAt) return null;
  if (!Array.isArray(value.messages) || value.messages.length === 0) return null;

  const messages: Message[] = [];
  const messageIds = new Set<string>();
  for (const messageValue of value.messages) {
    const message = parseMessage(messageValue);
    if (!message || messageIds.has(message.id)) return null;
    messageIds.add(message.id);
    messages.push(message);
  }

  return {
    id: value.id,
    title: value.title,
    createdAt: value.createdAt,
    updatedAt: value.updatedAt,
    messages
  };
}

function defaultStorage(): HistoryStorage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function storedMessage(message: Message): Message {
  return {
    id: message.id,
    role: message.role,
    text: message.text,
    ...(message.sources ? { sources: message.sources } : {}),
    ...(typeof message.refused === "boolean" ? { refused: message.refused } : {})
  };
}

function storedConversations(conversations: Conversation[]): Conversation[] {
  return conversations
    .filter((conversation) => conversation.messages.length > 0)
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, MAX_CONVERSATIONS)
    .map((conversation) => ({
      id: conversation.id,
      title: conversation.title,
      createdAt: conversation.createdAt,
      updatedAt: conversation.updatedAt,
      messages: conversation.messages.map(storedMessage)
    }));
}

function isQuotaExceeded(error: unknown): boolean {
  if (!isRecord(error)) return false;
  return (
    error.name === "QuotaExceededError" ||
    error.name === "NS_ERROR_DOM_QUOTA_REACHED" ||
    error.code === 22 ||
    error.code === 1014
  );
}

export function titleFromQuestion(question: string): string {
  const title = question.replace(/\s+/g, " ").trim();
  if (title.length <= MAX_TITLE_LENGTH) return title;
  return `${title.slice(0, MAX_TITLE_LENGTH - 3).trimEnd()}...`;
}

export function load(storage: HistoryStorage | null = defaultStorage()): Conversation[] {
  if (!storage) return [];

  try {
    const raw = storage.getItem(HISTORY_STORAGE_KEY);
    if (raw === null) return [];
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.version !== HISTORY_VERSION) return [];
    if (!Array.isArray(value.conversations)) return [];

    const conversations: Conversation[] = [];
    const conversationIds = new Set<string>();
    for (const conversationValue of value.conversations) {
      const conversation = parseConversation(conversationValue);
      if (!conversation || conversationIds.has(conversation.id)) return [];
      conversationIds.add(conversation.id);
      conversations.push(conversation);
    }
    return conversations
      .sort((left, right) => right.updatedAt - left.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
  } catch {
    return [];
  }
}

export function save(
  conversations: Conversation[],
  storage: HistoryStorage | null = defaultStorage()
): void {
  if (!storage) return;

  const candidates = storedConversations(conversations);
  while (true) {
    try {
      const payload: HistoryPayload = {
        version: HISTORY_VERSION,
        conversations: candidates
      };
      storage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(payload));
      return;
    } catch (error) {
      if (!isQuotaExceeded(error) || candidates.length === 0) return;
      // Large source passages make the least-recent conversation the safest sacrifice.
      candidates.pop();
    }
  }
}
