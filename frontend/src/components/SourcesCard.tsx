import { useId, useState } from "react";
import type { Source } from "../types";

const SCORE_FLOOR = 0.4;
const SCORE_CEILING = 0.95;

function withoutExtension(filename: string): string {
  return filename.replace(/\.[^.]+$/, "");
}

function scoreWidth(score: number): string {
  const scaled = (score - SCORE_FLOOR) / (SCORE_CEILING - SCORE_FLOOR);
  return `${Math.min(1, Math.max(0, scaled)) * 100}%`;
}

export function SourcesCard({ sources, refused = false }: { sources: Source[]; refused?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();

  if (sources.length === 0) return null;

  const documents = Array.from(new Set(sources.map((source) => withoutExtension(source.doc_name))));
  const sourceLabel = sources.length === 1 ? "source" : "sources";
  const passageLabel = sources.length === 1 ? "passage" : "passages";
  const countLabel = refused
    ? `${sources.length} ${passageLabel} retrieved, none sufficient`
    : `${sources.length} ${sourceLabel}`;

  return (
    <section
      className={"sources-card" + (refused ? " refused" : "")}
      aria-label={refused ? "Retrieved passages, none sufficient" : "Sources"}
    >
      <button
        type="button"
        className="sources-toggle"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="sources-count">{countLabel}</span>
        <span className="sources-divider" aria-hidden="true">
          &middot;
        </span>
        <span className="sources-documents">{documents.join(", ")}</span>
        <span className="sources-chevron" aria-hidden="true" />
      </button>

      {expanded && (
        <div className="sources-panel" id={panelId}>
          {sources.map((source, index) => {
            const rank = (source.rank ?? index) + 1;
            return (
              <article
                className="source-card"
                key={`${source.rank ?? index}-${source.doc_name}-${source.page ?? "none"}`}
              >
                <div className="source-card-head">
                  <span className="source-rank">#{rank}</span>
                  <span className="source-name">{source.doc_name}</span>
                  {source.page !== null && <span className="source-page">Page {source.page}</span>}
                </div>

                {(source.section || source.control_id) && (
                  <div className="source-context">
                    {source.section && <span className="source-section">{source.section}</span>}
                    {source.control_id && (
                      <span className="source-control">{source.control_id}</span>
                    )}
                  </div>
                )}

                <div className="source-score">
                  <span>Cosine score</span>
                  <div
                    className="hbar-track source-score-track"
                    role="img"
                    aria-label={`Cosine similarity ${source.score.toFixed(4)}`}
                  >
                    <div className="hbar-fill" style={{ width: scoreWidth(source.score) }} />
                  </div>
                  <span className="source-score-value">{source.score.toFixed(4)}</span>
                </div>

                <p className="source-text" title={source.text}>
                  {source.text}
                </p>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
