import { useCallback, useEffect, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { Message, Typing } from "./components/Message";
import { ProgressSteps } from "./components/ProgressSteps";
import { Sidebar } from "./components/Sidebar";
import { sendChat, streamChat, StreamUnavailableError } from "./lib/api";
import type {
  ChatResponse,
  Message as MessageType,
  ProgressEvent,
  ProgressStep,
  ProgressTrace,
  Theme
} from "./types";

let uid = 0;
const nextId = () => `m${++uid}`;

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
  const [theme, setTheme] = useState<Theme>("dark");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [busy, setBusy] = useState(false);
  const [liveSteps, setLiveSteps] = useState<ProgressStep[]>([]);
  const [fallbackPending, setFallbackPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const requestAbort = useRef<AbortController | null>(null);

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

  const newChat = useCallback(() => {
    requestAbort.current?.abort();
    requestAbort.current = null;
    setMessages([]);
    setLiveSteps([]);
    setFallbackPending(false);
    setBusy(false);
  }, []);

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

  const completeAssistant = (
    assistantId: string,
    result: ChatResponse,
    progress?: ProgressTrace
  ) => {
    const answer = result.answer.trim() || "No answer was produced.";
    setMessages((current) => {
      const completed: MessageType = {
        id: assistantId,
        role: "assistant",
        text: answer,
        streaming: false,
        sources: result.sources,
        refused: result.refused,
        progress
      };
      const exists = current.some((message) => message.id === assistantId);
      return exists
        ? current.map((message) => (message.id === assistantId ? completed : message))
        : [...current, completed];
    });
  };

  const revealError = (error: unknown, assistantId: string) => {
    const detail = error instanceof Error ? error.message : String(error);
    setMessages((current) => {
      const failed: MessageType = {
        id: nextId(),
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

  const send = (text: string) => {
    if (busy || requestAbort.current) return;
    setMessages((current) => [...current, { id: nextId(), role: "user", text }]);
    setBusy(true);
    setLiveSteps([]);
    setFallbackPending(false);

    const controller = new AbortController();
    const assistantId = nextId();
    let steps: ProgressStep[] = [];
    let assistantStarted = false;
    let streamedText = "";
    let completed = false;
    requestAbort.current = controller;

    const isCurrent = () => requestAbort.current === controller && !controller.signal.aborted;
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
        completeAssistant(assistantId, event.response, freezeProgress(steps, event.total_ms));
      }
    };

    const run = async () => {
      try {
        try {
          const result = await streamChat(text, { signal: controller.signal }, onEvent);
          if (!isCurrent()) return;
          if (!completed) {
            completeAssistant(assistantId, result, freezeProgress(steps, result.elapsed_ms));
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
          const result = await sendChat(text, { signal: controller.signal });
          if (!isCurrent()) return;
          setFallbackPending(false);
          completeAssistant(assistantId, result);
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

  const isEmpty = messages.length === 0 && !fallbackPending;
  const appClass =
    "app" + (sidebarCollapsed ? " collapsed" : "") + (isEmpty ? " is-empty" : "");

  return (
    <div className={appClass}>
      <Sidebar
        theme={theme}
        setTheme={setTheme}
        onNewChat={newChat}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
      />
      <main className="board mode-enter">
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
          <EmptyState onPick={send} active={isEmpty} />
        </div>
        <Composer onSend={send} busy={busy} />
      </main>
    </div>
  );
}
