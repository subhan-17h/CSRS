import { useCallback, useEffect, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { CorpusExplorer } from "./components/CorpusExplorer";
import { EmptyState } from "./components/EmptyState";
import { Message, Typing } from "./components/Message";
import { ProgressSteps } from "./components/ProgressSteps";
import { Sidebar } from "./components/Sidebar";
import {
  fetchDocuments,
  fetchHealth,
  fetchModels,
  sendChat,
  streamChat,
  streamIndex,
  StreamUnavailableError
} from "./lib/api";
import type { IndexPath } from "./lib/api";
import {
  load as loadHistory,
  MAX_CONVERSATIONS,
  save as saveHistory,
  titleFromQuestion
} from "./lib/history";
import type { Conversation } from "./lib/history";
import type {
  AppMode,
  ChatResponse,
  DocumentsResponse,
  HealthResponse,
  IndexProgressEvent,
  IndexResult,
  Message as MessageType,
  ModelsResponse,
  ProgressEvent,
  ProgressStep,
  ProgressTrace,
  Theme
} from "./types";

let fallbackUid = 0;

function nextId(prefix: "c" | "m"): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  fallbackUid += 1;
  return `${prefix}-${Date.now().toString(36)}-${fallbackUid.toString(36)}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function reduceProgress(steps: ProgressStep[], event: ProgressEvent): ProgressStep[] {
  if (
    event.event !== "stage_start" &&
    event.event !== "stage_update" &&
    event.event !== "stage_end"
  ) {
    return steps;
  }

  const index = steps.findIndex((step) => step.key === event.key);
  const existing = index >= 0 ? steps[index] : null;
  const now = performance.now();
  let next: ProgressStep;

  if (event.event === "stage_start") {
    next = {
      key: event.key,
      message: event.message,
      status: "running",
      startedAt: now,
      elapsedMs: null
    };
  } else if (event.event === "stage_update") {
    next = existing
      ? { ...existing, message: event.message }
      : {
          key: event.key,
          message: event.message,
          status: "running",
          startedAt: now,
          elapsedMs: null
        };
  } else {
    next = {
      key: event.key,
      message: event.message,
      status: "done",
      startedAt: existing?.startedAt ?? now - event.elapsed_ms,
      elapsedMs: event.elapsed_ms
    };
  }

  if (index < 0) return [...steps, next];
  return steps.map((step, stepIndex) => (stepIndex === index ? next : step));
}

function freezeProgress(steps: ProgressStep[], totalMs: number): ProgressTrace {
  const now = performance.now();
  return {
    totalMs,
    steps: steps.map((step) => ({
      key: step.key,
      message: step.message,
      elapsedMs: step.elapsedMs ?? Math.max(0, now - step.startedAt),
      status: step.status === "running" ? "done" : step.status
    }))
  };
}

export function App() {
  const [initialChat] = useState(() => {
    const stored = loadHistory();
    return {
      conversations: stored,
      activeConversationId: stored[0]?.id ?? null,
      messages: stored[0]?.messages ?? []
    };
  });
  const [mode, setMode] = useState<AppMode>("chat");
  const [theme, setTheme] = useState<Theme>("dark");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [conversations, setConversations] = useState<Conversation[]>(
    initialChat.conversations
  );
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    initialChat.activeConversationId
  );
  const [messages, setMessages] = useState<MessageType[]>(initialChat.messages);
  const [busy, setBusy] = useState(false);
  const [liveSteps, setLiveSteps] = useState<ProgressStep[]>([]);
  const [fallbackPending, setFallbackPending] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentsResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [topK, setTopK] = useState(5);
  const [temperature, setTemperature] = useState(0.1);
  const [indexOperation, setIndexOperation] = useState<"reload" | "rebuild" | null>(null);
  const [indexProgress, setIndexProgress] = useState<string[]>([]);
  const [indexResult, setIndexResult] = useState<IndexResult | null>(null);
  const [indexError, setIndexError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const requestAbort = useRef<AbortController | null>(null);
  const indexAbort = useRef<AbortController | null>(null);
  const runtimeRequestId = useRef(0);
  const conversationsRef = useRef(conversations);
  const activeConversationIdRef = useRef(activeConversationId);

  const refreshRuntime = useCallback(async () => {
    const requestId = ++runtimeRequestId.current;
    const [nextHealth, nextModels, nextDocuments] = await Promise.allSettled([
      fetchHealth(),
      fetchModels(),
      fetchDocuments()
    ]);
    if (requestId !== runtimeRequestId.current) return;

    if (nextHealth.status === "fulfilled") {
      setHealth(nextHealth.value);
      setHealthError(null);
    } else {
      setHealthError(errorMessage(nextHealth.reason));
    }

    if (nextModels.status === "fulfilled") {
      setModels(nextModels.value);
      setModelsError(null);
      setSelectedModel((current) => {
        if (nextModels.value.selectable_models.includes(current)) return current;
        if (nextModels.value.selectable_models.includes(nextModels.value.default_model)) {
          return nextModels.value.default_model;
        }
        return nextModels.value.selectable_models[0] ?? "";
      });
    } else {
      setModelsError(errorMessage(nextModels.reason));
    }

    if (nextDocuments.status === "fulfilled") {
      setDocuments(nextDocuments.value);
      setDocumentsError(null);
    } else {
      setDocumentsError(errorMessage(nextDocuments.reason));
    }
  }, []);

  useEffect(() => {
    void refreshRuntime();
    return () => {
      runtimeRequestId.current += 1;
    };
  }, [refreshRuntime]);

  useEffect(
    () => () => {
      requestAbort.current?.abort();
      indexAbort.current?.abort();
    },
    []
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const stickBottom = useCallback(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, []);

  useEffect(() => {
    stickBottom();
  }, [fallbackPending, liveSteps, messages, stickBottom]);

  const abortChatRequest = useCallback(() => {
    requestAbort.current?.abort();
    requestAbort.current = null;
    setLiveSteps([]);
    setFallbackPending(false);
    setBusy(false);
  }, []);

  const newChat = useCallback(() => {
    abortChatRequest();
    activeConversationIdRef.current = null;
    setActiveConversationId(null);
    setMessages([]);
    setMode("chat");
  }, [abortChatRequest]);

  const selectConversation = useCallback((conversationId: string) => {
    const conversation = conversationsRef.current.find(
      (candidate) => candidate.id === conversationId
    );
    if (!conversation) return;

    abortChatRequest();
    activeConversationIdRef.current = conversation.id;
    setActiveConversationId(conversation.id);
    setMessages(conversation.messages);
    setMode("chat");
  }, [abortChatRequest]);

  const deleteConversation = useCallback((conversationId: string) => {
    abortChatRequest();
    const remaining = conversationsRef.current.filter(
      (conversation) => conversation.id !== conversationId
    );
    conversationsRef.current = remaining;
    setConversations(remaining);
    saveHistory(remaining);

    if (activeConversationIdRef.current === conversationId) {
      activeConversationIdRef.current = null;
      setActiveConversationId(null);
      setMessages([]);
      setMode("chat");
      return;
    }

    const active = remaining.find(
      (conversation) => conversation.id === activeConversationIdRef.current
    );
    if (!active) {
      activeConversationIdRef.current = null;
      setActiveConversationId(null);
      setMessages([]);
      return;
    }
    setMessages(active.messages);
  }, [abortChatRequest]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        newChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [newChat]);

  const revealError = (error: unknown, assistantId: string) => {
    const detail = error instanceof Error ? error.message : String(error);
    setMessages((current) => {
      const failed: MessageType = {
        id: nextId("m"),
        role: "assistant",
        text: "The request could not be completed.",
        streaming: false,
        error: detail
      };
      if (!current.some((message) => message.id === assistantId)) return [...current, failed];
      return current.map((message) =>
        message.id === assistantId ? { ...failed, id: assistantId } : message
      );
    });
    setBusy(false);
  };

  const indexRunning = indexOperation !== null;
  const ollamaReachable = Boolean(health?.ollama_reachable && models?.ollama_reachable);
  const chatBlockedReason = indexRunning
    ? "Chat is disabled while the document index is updating."
    : !health
      ? healthError
        ? `Chat is disabled because Ollama status is unavailable: ${healthError}`
        : "Chat is disabled while Ollama status is checked."
      : !models
        ? modelsError
          ? `Chat is disabled because model inventory is unavailable: ${modelsError}`
          : "Chat is disabled while model inventory is checked."
        : !ollamaReachable
          ? "Chat is disabled because Ollama is disconnected. Start Ollama with `ollama serve`."
          : !selectedModel
            ? "Chat is disabled because no supported answer model is installed."
            : null;

  const send = (text: string) => {
    if (busy || requestAbort.current || chatBlockedReason) return;
    const existingConversation = conversationsRef.current.find(
      (conversation) => conversation.id === activeConversationIdRef.current
    );
    const conversationId = existingConversation?.id ?? nextId("c");
    const conversationCreatedAt = existingConversation?.createdAt ?? Date.now();
    const userMessage: MessageType = { id: nextId("m"), role: "user", text };
    const completedHistory: { question: string; answer: string }[] = [];
    for (let index = 0; index < messages.length - 1; index += 1) {
      const question = messages[index];
      const answer = messages[index + 1];
      if (question.role !== "user" || answer.role !== "assistant") continue;
      if (answer.streaming || !answer.text.trim()) continue;
      completedHistory.push({ question: question.text, answer: answer.text });
    }
    const history = completedHistory.slice(-2);
    const answeredMessages = [...messages, userMessage];
    activeConversationIdRef.current = conversationId;
    setActiveConversationId(conversationId);
    setMessages(answeredMessages);
    setBusy(true);
    setLiveSteps([]);
    setFallbackPending(false);

    const controller = new AbortController();
    const assistantId = nextId("m");
    let steps: ProgressStep[] = [];
    let assistantStarted = false;
    let streamedText = "";
    let completed = false;
    const chatOptions = {
      model: selectedModel,
      topK,
      temperature,
      history,
      signal: controller.signal
    };
    requestAbort.current = controller;

    const isCurrent = () => (
      requestAbort.current === controller &&
      !controller.signal.aborted &&
      activeConversationIdRef.current === conversationId
    );
    const completeAssistant = (result: ChatResponse, progress?: ProgressTrace) => {
      const completedMessages: MessageType[] = [
        ...answeredMessages,
        {
          id: assistantId,
          role: "assistant",
          text: result.answer.trim() || "No answer was produced.",
          streaming: false,
          sources: result.sources,
          refused: result.refused,
          progress
        }
      ];
      const now = Date.now();
      const current = conversationsRef.current;
      const previous = current.find((conversation) => conversation.id === conversationId);
      const completedConversation: Conversation = {
        id: conversationId,
        title: previous?.title ?? titleFromQuestion(text),
        createdAt: previous?.createdAt ?? conversationCreatedAt,
        updatedAt: now,
        messages: completedMessages
      };
      const nextConversations = [
        completedConversation,
        ...current.filter((conversation) => conversation.id !== conversationId)
      ].slice(0, MAX_CONVERSATIONS);

      setMessages(completedMessages);
      conversationsRef.current = nextConversations;
      setConversations(nextConversations);
      saveHistory(nextConversations);
    };
    const onEvent = (event: ProgressEvent) => {
      if (!isCurrent()) return;

      if (
        event.event === "stage_start" ||
        event.event === "stage_update" ||
        event.event === "stage_end"
      ) {
        steps = reduceProgress(steps, event);
        if (!assistantStarted) setLiveSteps(steps);
        return;
      }

      if (event.event === "token") {
        streamedText += event.text;
        if (!assistantStarted) {
          assistantStarted = true;
          setLiveSteps([]);
          setMessages((current) => [
            ...current,
            {
              id: assistantId,
              role: "assistant",
              text: streamedText,
              streaming: true
            }
          ]);
        } else {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, text: streamedText } : message
            )
          );
        }
        return;
      }

      if (event.event === "final") {
        completed = true;
        setLiveSteps([]);
        completeAssistant(event.response, freezeProgress(steps, event.total_ms));
      }
    };

    const run = async () => {
      try {
        try {
          const result = await streamChat(text, chatOptions, onEvent);
          if (!isCurrent()) return;
          if (!completed) {
            completeAssistant(result, freezeProgress(steps, result.elapsed_ms));
          }
        } catch (error) {
          if (!isCurrent()) return;
          if (!(error instanceof StreamUnavailableError)) throw error;

          steps = [];
          assistantStarted = false;
          streamedText = "";
          setLiveSteps([]);
          setMessages((current) => current.filter((message) => message.id !== assistantId));
          setFallbackPending(true);
          const result = await sendChat(text, chatOptions);
          if (!isCurrent()) return;
          setFallbackPending(false);
          completeAssistant(result);
        }

        if (!isCurrent()) return;
        requestAbort.current = null;
        setBusy(false);
      } catch (error) {
        if (requestAbort.current !== controller) return;
        requestAbort.current = null;
        setLiveSteps([]);
        setFallbackPending(false);
        if (error instanceof Error && error.name === "AbortError") {
          setMessages((current) => current.filter((message) => message.id !== assistantId));
          setBusy(false);
          return;
        }
        revealError(error, assistantId);
      }
    };

    void run();
  };

  const runIndex = (path: IndexPath) => {
    if (indexAbort.current || indexRunning || busy) return;

    const controller = new AbortController();
    const operation = path.endsWith("/rebuild") ? "rebuild" : "reload";
    indexAbort.current = controller;
    setIndexOperation(operation);
    setIndexProgress([]);
    setIndexResult(null);
    setIndexError(null);

    const isCurrent = () => indexAbort.current === controller && !controller.signal.aborted;
    const onEvent = (event: IndexProgressEvent) => {
      if (!isCurrent()) return;
      if (
        event.event === "stage_start" ||
        event.event === "stage_update" ||
        event.event === "stage_end"
      ) {
        setIndexProgress((current) => [...current, event.message]);
      }
    };

    const run = async () => {
      try {
        const finalEvent = await streamIndex(path, onEvent, controller.signal);
        if (!isCurrent()) return;
        setIndexResult(finalEvent.result);
        await refreshRuntime();
      } catch (error) {
        if (!isCurrent()) return;
        if (!(error instanceof Error && error.name === "AbortError")) {
          setIndexError(errorMessage(error));
        }
      } finally {
        if (indexAbort.current === controller) {
          indexAbort.current = null;
          setIndexOperation(null);
        }
      }
    };

    void run();
  };

  const isEmpty = messages.length === 0 && !fallbackPending;
  const appClass =
    "app" +
    (sidebarCollapsed ? " collapsed" : "") +
    (mode === "chat" && isEmpty ? " is-empty" : "");

  return (
    <div className={appClass}>
      <Sidebar
        mode={mode}
        onModeChange={setMode}
        theme={theme}
        setTheme={setTheme}
        onNewChat={newChat}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={selectConversation}
        onDeleteConversation={deleteConversation}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        health={health}
        models={models}
        documents={documents}
        runtimeError={healthError ?? modelsError}
        documentsError={documentsError}
        ollamaReachable={ollamaReachable}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        topK={topK}
        onTopKChange={setTopK}
        temperature={temperature}
        onTemperatureChange={setTemperature}
        indexOperation={indexOperation}
        indexProgress={indexProgress}
        indexResult={indexResult}
        indexError={indexError}
        indexActionsDisabled={busy}
        onReload={() => runIndex("/api/index/reload")}
        onRebuild={() => runIndex("/api/index/rebuild")}
      />
      <main
        className={"board mode-panel" + (mode === "chat" ? " mode-enter" : " inactive")}
        aria-hidden={mode !== "chat"}
      >
        <div className="stage">
          <div className="thread-scroll" ref={scrollRef}>
            <div className="thread">
              {messages.map((message) => (
                <Message key={message.id} msg={message} />
              ))}
              {liveSteps.length > 0 && <ProgressSteps steps={liveSteps} />}
              {fallbackPending && <Typing />}
            </div>
          </div>
          <EmptyState onPick={send} active={isEmpty} disabled={Boolean(chatBlockedReason) || busy} />
        </div>
        <Composer onSend={send} busy={busy} disabledReason={chatBlockedReason} />
      </main>
      <CorpusExplorer active={mode === "corpus"} />
    </div>
  );
}
