"""Minimal Streamlit interface for the CSRS pipeline."""

import streamlit as st

from csrs.config import settings
from csrs.pipeline import IndexResult, Pipeline

_CONNECTION_ERROR = "Could not connect to Ollama. Start Ollama with `ollama serve`."


@st.cache_resource
def load_pipeline() -> tuple[Pipeline, IndexResult]:
    """Construct and index the shared pipeline once."""
    # Streamlit reruns this script on interactions; caching prevents re-indexing each time.
    pipeline = Pipeline()
    result = pipeline.index()
    return pipeline, result


def main() -> None:
    """Render the question-and-answer interface."""
    st.title("Cybersecurity Standards RAG System")

    with st.spinner("Indexing documents..."):
        try:
            pipeline, index_result = load_pipeline()
        except ConnectionError:
            st.error(_CONNECTION_ERROR)
            return

    document_names = ", ".join(pipeline.document_names()) or "no TXT documents"
    st.caption(
        f"Indexed {index_result.documents_indexed} documents in "
        f"{index_result.chunks_created} chunks: {document_names}"
    )

    model_availability = pipeline.model_availability()
    selected_model: str | None = None
    with st.sidebar:
        st.header("Answer model")
        if not model_availability.ollama_reachable:
            st.error(_CONNECTION_ERROR)
        else:
            if model_availability.missing_models:
                pull_commands = "\n\n".join(
                    f"`ollama pull {name}`"
                    for name in model_availability.missing_models
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
            else:
                st.warning("No supported answer models are installed.")

    question = st.text_input("Ask a question about the indexed documents")
    if question and selected_model is not None:
        try:
            answer = pipeline.ask(question, model=selected_model)
        except ConnectionError:
            st.error(_CONNECTION_ERROR)
            return
        st.write(answer.text)
        st.caption(f"Answered by {answer.model}")


if __name__ == "__main__":
    main()
