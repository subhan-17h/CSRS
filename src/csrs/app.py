"""Minimal Streamlit interface for the CSRS pipeline."""

import streamlit as st

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

    question = st.text_input("Ask a question about the indexed documents")
    if question:
        try:
            answer = pipeline.ask(question)
        except ConnectionError:
            st.error(_CONNECTION_ERROR)
            return
        st.write(answer.text)


if __name__ == "__main__":
    main()
