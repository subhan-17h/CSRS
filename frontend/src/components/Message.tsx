import type { Message as MessageType, Source } from "../types";
import { Ico } from "./icons";
import { ProgressSummary } from "./ProgressSteps";

function sourceDetails(source: Source): string[] {
  const details: string[] = [];
  if (source.page !== null) details.push(`Page ${source.page}`);
  if (source.section) details.push(source.section);
  if (source.control_id) details.push(`Control ${source.control_id}`);
  details.push(`Score ${source.score.toFixed(3)}`);
  return details;
}

export function Message({ msg }: { msg: MessageType }) {
  const isUser = msg.role === "user";
  return (
    <div className={"msg " + (isUser ? "user" : "assistant")}>
      <div className="msg-avatar">{isUser ? "Q" : <Ico.Spark className="spark" />}</div>
      <div className="msg-col">
        {!isUser && !msg.streaming && msg.progress && <ProgressSummary trace={msg.progress} />}
        {(msg.text || msg.streaming) && (
          <div className={"bubble" + (msg.refused ? " refused" : "")}>
            {msg.text}
            {msg.streaming && <span className="caret" />}
          </div>
        )}
        {msg.error && !msg.streaming && <div className="api-error">{msg.error}</div>}
        {!isUser && !msg.streaming && (msg.sources?.length ?? 0) > 0 && (
          <div className="sources-list" aria-label="Sources">
            <div className="sources-title">Sources</div>
            <ol>
              {msg.sources?.map((source, index) => (
                <li key={`${source.rank ?? index}-${source.doc_name}-${source.page ?? "none"}`}>
                  <span className="source-name">{source.doc_name}</span>
                  <span className="source-details">{sourceDetails(source).join(" | ")}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

export function Typing() {
  return (
    <div className="msg assistant">
      <div className="msg-avatar">
        <Ico.Spark className="spark" />
      </div>
      <div className="msg-col">
        <div className="bubble" style={{ padding: 0 }}>
          <div className="typing">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        </div>
      </div>
    </div>
  );
}
