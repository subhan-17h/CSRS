import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message as MessageType } from "../types";
import { Ico } from "./icons";
import { ProgressSummary } from "./ProgressSteps";
import { SourcesCard } from "./SourcesCard";

export function Message({ msg }: { msg: MessageType }) {
  const isUser = msg.role === "user";
  return (
    <div className={"msg " + (isUser ? "user" : "assistant")}>
      <div className="msg-avatar">{isUser ? "Q" : <Ico.Spark className="spark" />}</div>
      <div className="msg-col">
        {!isUser && !msg.streaming && msg.progress && <ProgressSummary trace={msg.progress} />}
        {(msg.text || msg.streaming) && (
          <div className={"bubble" + (msg.refused ? " refused" : "")}>
            {!isUser && !msg.streaming ? (
              <div className="markdown">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ children }) => (
                      <div className="markdown-table-wrap">
                        <table>{children}</table>
                      </div>
                    )
                  }}
                >
                  {msg.text}
                </ReactMarkdown>
              </div>
            ) : (
              <>
                {msg.text}
                {msg.streaming && <span className="caret" />}
              </>
            )}
          </div>
        )}
        {msg.error && !msg.streaming && <div className="api-error">{msg.error}</div>}
        {!isUser && !msg.streaming && (msg.sources?.length ?? 0) > 0 && (
          <SourcesCard sources={msg.sources ?? []} refused={msg.refused} />
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
