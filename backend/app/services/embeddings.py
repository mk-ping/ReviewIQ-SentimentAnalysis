from app.core import thresholds as T

_model = None


def embed(texts: list[str]):
    """Returns a (n, dim) array of unit-length sentence embeddings. Loads the model once per process."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(T.EMBED_MODEL)
    return _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
