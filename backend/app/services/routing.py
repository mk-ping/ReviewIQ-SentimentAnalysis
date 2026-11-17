EURO = {"es", "fr", "de", "it", "nl"}
MEMBERS = {
    "english": ["tfidf", "roberta", "nlptown", "ft"],
    "european": ["tfidf", "nlptown", "xlmr", "ft"],
    "multi": ["tfidf", "xlmr", "distil", "ft"],
}


def group_of(language: str | None) -> str:
    """Route group from the detected language. Hindi, Hinglish, undetermined and other languages use the multilingual group."""
    if language == "en":
        return "english"
    if language in EURO:
        return "european"
    return "multi"
