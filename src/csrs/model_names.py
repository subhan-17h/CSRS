"""Shared Ollama model-name handling."""

__all__ = ("canonical_model_name",)


def canonical_model_name(name: str) -> str:
    """Add Ollama's implicit latest tag for reliable model-name comparisons."""
    final_component = name.rsplit("/", 1)[-1]
    return name if ":" in final_component else f"{name}:latest"
