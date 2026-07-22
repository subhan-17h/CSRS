import { useCallback, useEffect, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { Message, Typing } from "./components/Message";
import { Sidebar } from "./components/Sidebar";
import { sendChat } from "./lib/api";
import type { ChatResponse, Message as MessageType, Theme } from "./types";

let uid = 0;
const nextId = () => `m${++uid}`;

export function App() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const timers = useRef<ReturnType<typeof window.setTimeout>[]>([]);
  const requestAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const clearTimers = useCallback(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const stickBottom = useCallback(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, []);

  useEffect(() => {
    stickBottom();
  }, [messages, typing, stickBottom]);

  const newChat = useCallback(() => {
    requestAbort.current?.abort();
    requestAbort.current = null;
    clearTimers();
    setMessages([]);
    setBusy(false);
    setTyping(false);
  }, [clearTimers]);

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

  const revealAssistant = (result: ChatResponse) => {
    const assistantId = nextId();
    const answer = result.answer.trim() || "No answer was produced.";
    setMessages((current) => [
      ...current,
      { id: assistantId, role: "assistant", text: "", streaming: true }
    ]);

    let index = 0;
    const tick = () => {
      index += Math.max(1, Math.round(answer.length / 60));
      const text = answer.slice(0, index);
      setMessages((current) =>
        current.map((message) => (message.id === assistantId ? { ...message, text } : message))
      );

      if (index < answer.length) {
        timers.current.push(window.setTimeout(tick, 18));
        return;
      }

      timers.current.push(
        window.setTimeout(() => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    streaming: false,
                    sources: result.sources,
                    refused: result.refused
                  }
                : message
            )
          );
          setBusy(false);
        }, 160)
      );
    };
    tick();
  };

  const revealError = (error: unknown) => {
    const detail = error instanceof Error ? error.message : String(error);
    setMessages((current) => [
      ...current,
      {
        id: nextId(),
        role: "assistant",
        text: "The request could not be completed.",
        streaming: false,
        error: detail
      }
    ]);
    setBusy(false);
  };

  const send = (text: string) => {
    if (busy) return;
    clearTimers();
    setMessages((current) => [...current, { id: nextId(), role: "user", text }]);
    setBusy(true);
    setTyping(true);

    const controller = new AbortController();
    requestAbort.current = controller;
    sendChat(text, { signal: controller.signal })
      .then((result) => {
        if (requestAbort.current !== controller) return;
        requestAbort.current = null;
        setTyping(false);
        revealAssistant(result);
      })
      .catch((error: unknown) => {
        if (requestAbort.current !== controller) return;
        requestAbort.current = null;
        setTyping(false);
        if (error instanceof Error && error.name === "AbortError") {
          setBusy(false);
          return;
        }
        revealError(error);
      });
  };

  const isEmpty = messages.length === 0 && !typing;
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
              {typing && <Typing />}
            </div>
          </div>
          <EmptyState onPick={send} active={isEmpty} />
        </div>
        <Composer onSend={send} busy={busy} />
      </main>
    </div>
  );
}
