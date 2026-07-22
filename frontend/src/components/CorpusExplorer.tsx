import { useEffect, useMemo, useState } from "react";
import { fetchDocumentChunks, fetchDocuments } from "../lib/api";
import type { DocumentChunk, DocumentChunksResponse, DocumentsResponse } from "../types";
import { Ico } from "./icons";

const PAGE_SIZE = 50;

type CorpusExplorerProps = {
  active: boolean;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function matchesFilter(chunk: DocumentChunk, query: string): boolean {
  const fields = [
    chunk.id,
    chunk.text,
    chunk.section,
    chunk.control_id,
    chunk.page === null ? null : String(chunk.page)
  ];
  return fields.some((field) => field?.toLocaleLowerCase().includes(query));
}

export function CorpusExplorer({ active }: CorpusExplorerProps) {
  const [documents, setDocuments] = useState<DocumentsResponse | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [chunks, setChunks] = useState<DocumentChunksResponse | null>(null);
  const [chunksError, setChunksError] = useState<string | null>(null);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        const response = await fetchDocuments(controller.signal);
        setDocuments(response);
        setDocumentsError(null);
        setSelectedDocument((current) => current || response.documents[0]?.filename || "");
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setDocumentsError(errorMessage(error));
      }
    };

    void load();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedDocument) {
      setChunks(null);
      return;
    }

    const controller = new AbortController();
    setChunksLoading(true);
    setChunksError(null);
    setChunks(null);

    const load = async () => {
      try {
        const response = await fetchDocumentChunks(
          selectedDocument,
          PAGE_SIZE,
          offset,
          controller.signal
        );
        setChunks(response);
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setChunksError(errorMessage(error));
      } finally {
        if (!controller.signal.aborted) setChunksLoading(false);
      }
    };

    void load();
    return () => controller.abort();
  }, [offset, selectedDocument]);

  const normalizedFilter = filter.trim().toLocaleLowerCase();
  const visibleChunks = useMemo(
    () => chunks?.chunks.filter((chunk) => matchesFilter(chunk, normalizedFilter)) ?? [],
    [chunks, normalizedFilter]
  );
  const filterActive = normalizedFilter.length > 0;
  const pageStart = chunks && chunks.total > 0 ? chunks.offset + 1 : 0;
  const pageEnd = chunks ? Math.min(chunks.offset + chunks.chunks.length, chunks.total) : 0;
  const previousDisabled = !chunks || chunks.offset === 0 || chunksLoading;
  const nextDisabled = !chunks || chunks.offset + chunks.limit >= chunks.total || chunksLoading;

  const selectDocument = (filename: string) => {
    if (filename === selectedDocument) return;
    setSelectedDocument(filename);
    setOffset(0);
    setFilter("");
  };

  const showPrevious = () => {
    if (previousDisabled || !chunks) return;
    setOffset(Math.max(0, chunks.offset - chunks.limit));
  };

  const showNext = () => {
    if (nextDisabled || !chunks) return;
    setOffset(chunks.offset + chunks.limit);
  };

  const renderContent = () => {
    if (!documents && !documentsError) {
      return (
        <div className="dv-state" role="status">
          <span className="dv-spinner" aria-hidden="true" />
          Loading indexed documents...
        </div>
      );
    }

    if (documentsError) {
      return <div className="dv-state error" role="alert">{documentsError}</div>;
    }

    if (documents?.documents.length === 0) {
      return <div className="dv-state">No indexed documents are available.</div>;
    }

    if (chunksLoading) {
      return (
        <div className="dv-state" role="status">
          <span className="dv-spinner" aria-hidden="true" />
          Loading document chunks...
        </div>
      );
    }

    if (chunksError) {
      return <div className="dv-state error" role="alert">{chunksError}</div>;
    }

    if (!chunks) return null;

    if (visibleChunks.length === 0) {
      return (
        <div className="dv-state">
          {filterActive ? "No chunks on this page match the filter." : "This document has no chunks."}
        </div>
      );
    }

    return (
      <div className="dv-chunks">
        {visibleChunks.map((chunk) => (
          <article className="dv-chunk" key={chunk.id}>
            <header className="dv-chunk-head">
              <code className="dv-chunk-id">{chunk.id}</code>
              {chunk.page !== null && <span className="dv-chunk-page">Page {chunk.page}</span>}
              {chunk.control_id !== null && (
                <span className="source-control">{chunk.control_id}</span>
              )}
            </header>
            {chunk.section !== null && <p className="dv-chunk-section">{chunk.section}</p>}
            <p className="dv-chunk-text">{chunk.text}</p>
          </article>
        ))}
      </div>
    );
  };

  return (
    <main
      className={"board dv-board mode-panel" + (active ? " mode-enter" : " inactive")}
      aria-hidden={!active}
    >
      <header className="board-header">
        <div className="bh-text">
          <h1 className="bh-title">Corpus Explorer</h1>
          <p className="bh-sub">Inspect indexed documents and their stored chunks.</p>
        </div>
        <div className="bh-right">
          <span className="pill guard"><Ico.Lock /> Read only</span>
          {documents && (
            <span className="pill">
              {documents.documents.length} documents | {documents.total_chunks} chunks
            </span>
          )}
        </div>
      </header>

      {documents && documents.documents.length > 0 && (
        <div className="dv-tabs" aria-label="Indexed documents">
          {documents.documents.map((document) => (
            <button
              className={"dv-tab" + (document.filename === selectedDocument ? " active" : "")}
              type="button"
              aria-pressed={document.filename === selectedDocument}
              onClick={() => selectDocument(document.filename)}
              key={document.filename}
            >
              <span className="d" aria-hidden="true" />
              <span className="dv-tab-name">{document.filename}</span>
              <span className="dv-tab-count">{document.chunk_count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="dv-area">
        <section className="dv-card" aria-label="Document chunks">
          {documents && documents.documents.length > 0 && (
            <div className="dv-toolbar">
              <label className="dv-search">
                <Ico.Search className="gs-icon" />
                <input
                  type="search"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Filter chunks on this page"
                  aria-label="Filter chunks on this page"
                />
              </label>
              <span className="dv-count" aria-live="polite">
                {chunks && (filterActive
                  ? `${visibleChunks.length} of ${chunks.chunks.length} on this page`
                  : `${chunks.chunks.length} chunks on this page`)}
              </span>
            </div>
          )}

          <div className="dv-scroll">{renderContent()}</div>

          {chunks && !chunksError && (
            <footer className="dv-foot">
              <span className="dv-page-summary">
                Showing {pageStart}-{pageEnd} of {chunks.total}
              </span>
              <div className="dv-pagination" aria-label="Chunk pagination">
                <button
                  className="ghost-btn"
                  type="button"
                  onClick={showPrevious}
                  disabled={previousDisabled}
                >
                  Previous
                </button>
                <button
                  className="ghost-btn"
                  type="button"
                  onClick={showNext}
                  disabled={nextDisabled}
                >
                  Next
                </button>
              </div>
            </footer>
          )}
        </section>
      </div>
    </main>
  );
}
