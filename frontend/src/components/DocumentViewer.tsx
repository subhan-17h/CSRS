import { useEffect, useState } from "react";
import { documentFileUrl, fetchDocumentText } from "../lib/api";
import type { DocumentSummary } from "../types";

type DocumentViewerProps = {
  document: DocumentSummary;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function DocumentViewer({ document }: DocumentViewerProps) {
  const extension = document.filename.split(".").pop()?.toLocaleLowerCase();
  const isTextDocument = extension === "txt";
  const [text, setText] = useState<string | null>(null);
  const [textError, setTextError] = useState<string | null>(null);
  const [textLoading, setTextLoading] = useState(isTextDocument);

  useEffect(() => {
    if (!isTextDocument) return;

    const controller = new AbortController();
    setTextLoading(true);
    setTextError(null);
    setText(null);

    const load = async () => {
      try {
        setText(await fetchDocumentText(document.filename, controller.signal));
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setTextError(errorMessage(error));
      } finally {
        if (!controller.signal.aborted) setTextLoading(false);
      }
    };

    void load();
    return () => controller.abort();
  }, [document.filename, isTextDocument]);

  const pageCount = document.page_count === null
    ? "Page count unavailable"
    : `${document.page_count} ${document.page_count === 1 ? "page" : "pages"}`;
  const chunkCount = `${document.chunk_count} ${document.chunk_count === 1 ? "chunk" : "chunks"}`;

  const renderContent = () => {
    if (extension === "pdf") {
      return (
        <iframe
          className="dv-document-frame"
          src={documentFileUrl(document.filename)}
          title={`${document.filename} source document`}
        />
      );
    }

    if (!isTextDocument) {
      return (
        <div className="dv-state error" role="alert">
          This document type cannot be displayed.
        </div>
      );
    }

    if (textLoading) {
      return (
        <div className="dv-state" role="status">
          <span className="dv-spinner" aria-hidden="true" />
          Loading source document...
        </div>
      );
    }

    if (textError) {
      return <div className="dv-state error" role="alert">{textError}</div>;
    }

    return <div className="dv-document-text">{text}</div>;
  };

  return (
    <div className="dv-document-viewer">
      <header className="dv-document-head">
        <span className="dv-document-name">{document.filename}</span>
        <span className="dv-document-meta">{pageCount} | {chunkCount}</span>
      </header>
      <div className="dv-document-content">{renderContent()}</div>
    </div>
  );
}
