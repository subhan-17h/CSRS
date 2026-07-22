"""Minimal Streamlit interface for the CSRS pipeline."""

import streamlit as st

from csrs.config import settings
from csrs.pipeline import IndexResult, Pipeline

_CONNECTION_ERROR = "Could not connect to Ollama. Start Ollama with `ollama serve`."


@st.cache_resource
def load_pipeline(_force: bool = False) -> tuple[Pipeline, IndexResult]:
    """Construct and index the shared pipeline once."""
    # The leading underscore keeps force out of the cache key. Reload clears this cache
    # before rebuilding, so the following rerun reuses the newly indexed Pipeline.
    pipeline = Pipeline()
    result = pipeline.index(force=_force)
    return pipeline, result


def load_pipeline_with_status(
    label: str,
    *,
    force: bool = False,
) -> tuple[Pipeline, IndexResult]:
    """Load the cached pipeline while presenting indexing activity."""
    with st.status(label, expanded=True) as status:
        pipeline, result = load_pipeline(_force=force)
        status.write(
            f"Added {result.added}, updated {result.updated}, skipped {result.skipped}, "
            f"removed {result.removed}."
        )
        status.update(
            label=(
                f"Indexed {result.documents_indexed} documents in "
                f"{result.chunks_created} chunks."
            ),
            state="complete",
            expanded=False,
        )
    return pipeline, result


def main() -> None:
    """Render the question-and-answer interface."""
    st.title("Cybersecurity Standards RAG System")

    try:
        pipeline, index_result = load_pipeline_with_status("Indexing documents...")
    except ConnectionError:
        st.error(_CONNECTION_ERROR)
        return

    st.caption(
        f"Indexed {index_result.documents_indexed} documents in "
        f"{index_result.chunks_created} chunks."
    )

    model_availability = pipeline.model_availability()
    documents = pipeline.documents()
    selected_model: str | None = None

    with st.sidebar:
        st.header("Application settings")
        if model_availability.ollama_reachable:
            st.success("Ollama: Connected")
        else:
            st.error("Ollama: Disconnected")
            st.caption(_CONNECTION_ERROR)

        if model_availability.missing_models:
            pull_commands = "\n\n".join(
                f"`ollama pull {name}`" for name in model_availability.missing_models
            )
            st.warning(f"Required models are missing. Install them with:\n\n{pull_commands}")
        if model_availability.selectable_models:
            default_index = (
                model_availability.selectable_models.index(settings.default_llm)
                if settings.default_llm in model_availability.selectable_models
                else 0
            )
            selected_model = st.selectbox(
                "Model",
                model_availability.selectable_models,
                index=default_index,
            )
        elif model_availability.ollama_reachable:
            st.warning("No supported answer models are installed.")

        # Phase 2 has no reranker, so values above 20 can silently overflow num_ctx.
        top_k = st.slider(
            "Retrieved chunks (top_k)",
            min_value=1,
            max_value=20,
            value=max(1, min(settings.top_k_dense, 20)),
        )
        temperature = st.number_input(
            "Temperature",
            min_value=0.0,
            value=float(settings.temperature),
            step=0.1,
        )

        st.divider()
        st.header("Indexed documents")
        total_chunks = sum(document.chunk_count for document in documents)
        st.caption(f"{len(documents)} documents | {total_chunks} chunks")
        if not documents:
            st.caption("No documents loaded.")
        for document in documents:
            page_text = (
                f"{document.page_count} pages"
                if document.page_count is not None
                else "page count not applicable"
            )
            st.markdown(
                f"`{document.filename}`  \n{document.chunk_count} chunks | {page_text}"
            )

        st.divider()
        st.header("Document controls")
        reload_clicked = st.button(
            "Restart & Reload Documents",
            type="primary",
            use_container_width=True,
        )
        full_rebuild_clicked = st.button(
            "Full Rebuild Documents (about five minutes)",
            help="Reprocess every document. Use only when the incremental index is wrong.",
            use_container_width=True,
        )

    if reload_clicked or full_rebuild_clicked:
        st.cache_resource.clear()
        try:
            load_pipeline_with_status(
                "Rebuilding the complete document index..."
                if full_rebuild_clicked
                else "Checking for new, changed, and removed documents...",
                force=full_rebuild_clicked,
            )
        except ConnectionError:
            st.error(_CONNECTION_ERROR)
            return
        st.rerun()

    question = st.text_input("Ask a question about the indexed documents")
    if question and selected_model is not None:
        try:
            answer = pipeline.ask(
                question,
                k=top_k,
                model=selected_model,
                temperature=temperature,
            )
        except ConnectionError:
            st.error(_CONNECTION_ERROR)
            return
        st.write(answer.text)
        st.caption(f"Answered by {answer.model}")


if __name__ == "__main__":
    main()
