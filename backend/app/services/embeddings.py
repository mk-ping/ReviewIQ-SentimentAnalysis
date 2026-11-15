from app.core import thresholds as T

_models: dict = {}


def embed(texts: list[str], model: str | None = None):
    """Returns a (n, dim) array of unit-length sentence embeddings. Each model loads once per process."""
    name = model or T.EMBED_MODEL
    if name not in _models:
        from sentence_transformers import SentenceTransformer

        _models[name] = SentenceTransformer(name)
    return _models[name].encode(texts, normalize_embeddings=True, show_progress_bar=False)


def embed_model_for(language: str | None) -> str:
    """all-MiniLM-L6-v2 for English, the multilingual model for every other language."""
    from app.services.routing import group_of

    return T.SBERT_EN_MODEL if group_of(language) == "english" else T.EMBED_MODEL
