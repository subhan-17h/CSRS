import { useEffect, useState } from "react";
import type { ProgressStep, ProgressTrace } from "../types";
import { Ico } from "./icons";

function StepRail({ status, isLast }: { status: ProgressStep["status"]; isLast: boolean }) {
  return (
    <span className="pstep-rail" aria-hidden="true">
      {status === "done" ? <Ico.Check /> : <span className="pstep-dot" />}
      {!isLast && <span className="pstep-line" />}
    </span>
  );
}

function formatElapsed(elapsedMs: number) {
  return `${(elapsedMs / 1000).toFixed(1)}s`;
}

export function ProgressSteps({ steps }: { steps: ProgressStep[] }) {
  const hasRunning = steps.some((step) => step.status === "running");
  const [now, setNow] = useState(() => performance.now());

  useEffect(() => {
    if (!hasRunning) return;

    setNow(performance.now());
    const timer = window.setInterval(() => setNow(performance.now()), 100);
    return () => window.clearInterval(timer);
  }, [hasRunning]);

  return (
    <div className="msg assistant">
      <div className="msg-avatar">
        <Ico.Spark className="spark" />
      </div>
      <div className="msg-col">
        <div className="progress-steps">
          {steps.map((step, index) => {
            const elapsed =
              step.status === "running"
                ? Math.max(0, now - step.startedAt)
                : Math.max(0, step.elapsedMs ?? 0);
            return (
              <div className={`pstep ${step.status}`} key={step.key}>
                <StepRail status={step.status} isLast={index === steps.length - 1} />
                <span className="pstep-msg">{step.message}</span>
                <span className="pstep-time">{formatElapsed(elapsed)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function ProgressSummary({ trace }: { trace: ProgressTrace }) {
  const [expanded, setExpanded] = useState(false);
  const hasError = trace.steps.some((step) => step.status === "error");
  const label = hasError ? "Stopped after" : "Completed in";

  return (
    <div className={`progress-summary${expanded ? " expanded" : ""}${hasError ? " error" : ""}`}>
      <button
        className="progress-summary-head"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {hasError ? <Ico.Clock /> : <Ico.Check />}
        <span>
          {label} <span className="pstep-time">{formatElapsed(trace.totalMs)}</span> -{" "}
          <span className="pstep-time">{trace.steps.length}</span> steps
        </span>
        <svg
          className="progress-chevron"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m4 6 4 4 4-4" />
        </svg>
      </button>
      <div className="progress-summary-body">
        <div>
          <div className="progress-steps">
            {trace.steps.map((step, index) => (
              <div className={`pstep ${step.status}`} key={step.key}>
                <StepRail status={step.status} isLast={index === trace.steps.length - 1} />
                <span className="pstep-msg">{step.message}</span>
                <span className="pstep-time">{formatElapsed(Math.max(0, step.elapsedMs))}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
