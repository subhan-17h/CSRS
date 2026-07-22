import { useEffect, useState } from "react";
import { fetchHealth, fetchModels } from "../lib/api";
import type { Theme } from "../types";
import { Ico } from "./icons";
import { Logo } from "./Logo";

type SidebarProps = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  onNewChat: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
};

type RuntimeStatus = {
  reachable: boolean;
  model: string;
};

export function Sidebar({
  theme,
  setTheme,
  onNewChat,
  collapsed,
  onToggleCollapse
}: SidebarProps) {
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [statusError, setStatusError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchHealth(), fetchModels()])
      .then(([health, models]) => {
        if (cancelled) return;
        setRuntime({
          reachable: health.ollama_reachable && models.ollama_reachable,
          model: models.default_model
        });
      })
      .catch(() => {
        if (!cancelled) setStatusError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const statusLabel = statusError
    ? "Status unavailable"
    : runtime?.reachable
      ? "Ollama connected"
      : runtime
        ? "Ollama offline"
        : "Checking Ollama";
  const modelLabel = runtime?.model ?? "Model unavailable";

  return (
    <aside className={"sidebar" + (collapsed ? " collapsed" : "")}>
      <div className="side-top">
        <div className="brand">
          <button
            className="brand-mark"
            onClick={() => collapsed && onToggleCollapse()}
            aria-label={collapsed ? "Expand sidebar" : "CSRS"}
            type="button"
          >
            <Logo className="brand-logo" />
            <Ico.Panel className="brand-toggle-ico" />
          </button>
          <span className="brand-word hideable">CSRS</span>
        </div>
        <button
          className="rail-toggle"
          onClick={onToggleCollapse}
          title="Collapse sidebar"
          type="button"
        >
          <Ico.Panel />
        </button>
      </div>

      <button className="new-chat" onClick={onNewChat} type="button">
        <span className="plus">
          <Ico.Plus style={{ width: 13, height: 13 }} />
        </span>
        <span className="nc-label hideable">New conversation</span>
        <kbd className="hideable">Ctrl N</kbd>
      </button>

      <div className="side-scroll">
        <nav className="side-nav" aria-label="Application navigation">
          <button className="side-nav-item active" type="button">
            <Ico.Chat className="nav-ico" />
            <span className="label hideable">Chat</span>
          </button>
        </nav>
      </div>

      <div className="side-foot">
        <div className="theme-toggle">
          <button className={theme === "dark" ? "on" : ""} onClick={() => setTheme("dark")}>
            <Ico.Moon style={{ width: 14, height: 14 }} /> <span className="hideable">Dark</span>
          </button>
          <button className={theme === "light" ? "on" : ""} onClick={() => setTheme("light")}>
            <Ico.Sun style={{ width: 14, height: 14 }} /> <span className="hideable">Light</span>
          </button>
        </div>
        <div className="user-row" title={`${statusLabel}; active model ${modelLabel}`}>
          <div className="avatar" aria-hidden="true">
            <Ico.Shield />
          </div>
          <div className="user-meta hideable">
            <span className="user-name">{statusLabel}</span>
            <span className="user-role">Active model: {modelLabel}</span>
          </div>
          <span
            className={"status-dot hideable" + (runtime?.reachable ? "" : " offline")}
            aria-hidden="true"
          />
        </div>
      </div>
    </aside>
  );
}
