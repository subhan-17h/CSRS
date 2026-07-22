import { useEffect, useState } from "react";
import type {
  AppMode,
  DocumentsResponse,
  HealthResponse,
  IndexResult,
  ModelsResponse,
  Theme
} from "../types";
import { Ico } from "./icons";
import { Logo } from "./Logo";

type SidebarProps = {
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  onNewChat: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  health: HealthResponse | null;
  models: ModelsResponse | null;
  documents: DocumentsResponse | null;
  runtimeError: string | null;
  documentsError: string | null;
  ollamaReachable: boolean;
  selectedModel: string;
  onModelChange: (model: string) => void;
  topK: number;
  onTopKChange: (topK: number) => void;
  temperature: number;
  onTemperatureChange: (temperature: number) => void;
  indexOperation: "reload" | "rebuild" | null;
  indexProgress: string[];
  indexResult: IndexResult | null;
  indexError: string | null;
  indexActionsDisabled: boolean;
  onReload: () => void;
  onRebuild: () => void;
};

export function Sidebar({
  mode,
  onModeChange,
  theme,
  setTheme,
  onNewChat,
  collapsed,
  onToggleCollapse,
  health,
  models,
  documents,
  runtimeError,
  documentsError,
  ollamaReachable,
  selectedModel,
  onModelChange,
  topK,
  onTopKChange,
  temperature,
  onTemperatureChange,
  indexOperation,
  indexProgress,
  indexResult,
  indexError,
  indexActionsDisabled,
  onReload,
  onRebuild
}: SidebarProps) {
  const [confirmRebuild, setConfirmRebuild] = useState(false);

  useEffect(() => {
    if (indexOperation) setConfirmRebuild(false);
  }, [indexOperation]);

  const runtimeLoaded = health !== null && models !== null;
  const statusLabel = runtimeError && !runtimeLoaded
    ? "Status unavailable"
    : ollamaReachable
      ? "Ollama connected"
      : runtimeLoaded
        ? "Ollama disconnected"
        : "Checking Ollama";
  const modelLabel = selectedModel || "Model unavailable";
  const indexBusy = indexOperation !== null;
  const actionsDisabled = indexBusy || indexActionsDisabled;
  const documentCount = indexResult?.documents_indexed ?? documents?.documents.length ?? 0;
  const totalChunks = indexResult?.chunks_created ?? documents?.total_chunks ?? 0;

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
          <button
            className={"side-nav-item" + (mode === "chat" ? " active" : "")}
            type="button"
            onClick={() => onModeChange("chat")}
            aria-current={mode === "chat" ? "page" : undefined}
            title="Chat"
          >
            <Ico.Chat className="nav-ico" />
            <span className="label hideable">Chat</span>
          </button>
          <button
            className={"side-nav-item" + (mode === "corpus" ? " active" : "")}
            type="button"
            onClick={() => onModeChange("corpus")}
            aria-current={mode === "corpus" ? "page" : undefined}
            title="Corpus"
          >
            <Ico.Grid className="nav-ico" />
            <span className="label hideable">Corpus</span>
          </button>
        </nav>

        <div className="settings-panel hideable">
          <section className="settings-section" aria-labelledby="application-settings-title">
            <h2 id="application-settings-title" className="settings-title">
              Application settings
            </h2>

            <div className={"runtime-banner" + (ollamaReachable ? " connected" : " offline")}>
              <span className="runtime-dot" aria-hidden="true" />
              <span>
                {runtimeError && !runtimeLoaded
                  ? "Ollama status unavailable"
                  : ollamaReachable
                    ? "Ollama: Connected"
                    : runtimeLoaded
                      ? "Ollama: Disconnected"
                      : "Checking Ollama..."}
              </span>
            </div>

            {runtimeError && <p className="settings-notice">{runtimeError}</p>}
            {runtimeLoaded && !ollamaReachable && (
              <p className="settings-notice">
                Could not connect to Ollama. Start Ollama with <code>ollama serve</code>.
                Chat is disabled until it reconnects.
              </p>
            )}
            {models && models.missing_models.length > 0 && (
              <div className="settings-warning">
                <p>Required models are missing. Install them with:</p>
                {models.missing_models.map((name) => (
                  <code key={name}>ollama pull {name}</code>
                ))}
              </div>
            )}
            {models?.ollama_reachable && models.selectable_models.length === 0 && (
              <p className="settings-notice">No supported answer models are installed.</p>
            )}

            <label className="settings-field">
              <span>Model</span>
              <select
                value={selectedModel}
                onChange={(event) => onModelChange(event.target.value)}
                disabled={!ollamaReachable || models?.selectable_models.length === 0}
              >
                {!selectedModel && <option value="">Model unavailable</option>}
                {models?.selectable_models.map((model) => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
            </label>

            <label className="settings-field">
              <span className="settings-label-row">
                Retrieved chunks (top_k)
                <output>{topK}</output>
              </span>
              <input
                type="range"
                min="1"
                max="20"
                step="1"
                value={topK}
                onChange={(event) => onTopKChange(event.currentTarget.valueAsNumber)}
              />
            </label>

            <label className="settings-field">
              <span className="settings-label-row">
                Temperature
                <output>{temperature.toFixed(1)}</output>
              </span>
              <input
                type="number"
                min="0"
                max="2"
                step="0.1"
                value={temperature}
                onChange={(event) => {
                  const value = event.currentTarget.valueAsNumber;
                  if (Number.isFinite(value)) {
                    onTemperatureChange(Math.min(2, Math.max(0, value)));
                  }
                }}
              />
            </label>
          </section>

          <section className="settings-section" aria-labelledby="indexed-documents-title">
            <h2 id="indexed-documents-title" className="settings-title">Indexed documents</h2>
            <p className="settings-total">
              {documents
                ? `${documents.documents.length} documents | ${documents.total_chunks} chunks`
                : documentsError
                  ? "Documents unavailable"
                  : "Loading documents..."}
            </p>
            {documentsError && <p className="settings-notice">{documentsError}</p>}
            {documents?.documents.length === 0 && (
              <p className="settings-notice">No documents loaded.</p>
            )}
            <div className="document-list">
              {documents?.documents.map((document) => (
                <article className="document-item" key={document.filename}>
                  <code>{document.filename}</code>
                  <span>
                    {document.chunk_count} chunks | {document.page_count === null
                      ? "page count not applicable"
                      : `${document.page_count} pages`}
                  </span>
                </article>
              ))}
            </div>
          </section>

          <section className="settings-section" aria-labelledby="document-controls-title">
            <h2 id="document-controls-title" className="settings-title">Document controls</h2>
            <button
              className="index-button primary"
              type="button"
              onClick={onReload}
              disabled={actionsDisabled}
            >
              Restart & Reload Documents
            </button>

            {!confirmRebuild ? (
              <button
                className="index-button"
                type="button"
                onClick={() => setConfirmRebuild(true)}
                disabled={actionsDisabled}
                title="Reprocess every document. Use only when the incremental index is wrong."
              >
                Full Rebuild Documents
              </button>
            ) : (
              <div className="rebuild-confirm" role="alert">
                <p>
                  Full rebuild reprocesses every document and takes about five minutes.
                  Continue?
                </p>
                <div className="confirm-actions">
                  <button type="button" onClick={onRebuild} disabled={actionsDisabled}>
                    Confirm rebuild
                  </button>
                  <button type="button" onClick={() => setConfirmRebuild(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {indexBusy && (
              <div className="index-status" aria-live="polite">
                <strong>
                  {indexOperation === "rebuild" ? "Full rebuild in progress" : "Reload in progress"}
                </strong>
                <ul>
                  {indexProgress.map((message, index) => (
                    <li key={`${index}-${message}`}>{message}</li>
                  ))}
                </ul>
              </div>
            )}
            {indexResult && !indexBusy && (
              <div className="index-result" role="status">
                <strong>Document index updated</strong>
                <span>
                  Added {indexResult.added}, updated {indexResult.updated}, skipped{" "}
                  {indexResult.skipped}, removed {indexResult.removed}.
                </span>
                <span>New totals: {documentCount} documents | {totalChunks} chunks.</span>
              </div>
            )}
            {indexError && !indexBusy && (
              <p className="settings-notice index-error" role="alert">{indexError}</p>
            )}
          </section>
        </div>
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
            className={"status-dot hideable" + (ollamaReachable ? "" : " offline")}
            aria-hidden="true"
          />
        </div>
      </div>
    </aside>
  );
}
