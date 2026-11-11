import re

from lingua import Language, LanguageDetectorBuilder

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
LATIN = re.compile(r"[A-Za-z]")

# Romanized Hindi words that are not ordinary English words.
HINGLISH_WORDS = {
    "hai", "hain", "nahi", "nahin", "bahut", "accha", "acha", "achha", "bakwas", "zyada", "jyada",
    "thoda", "thodi", "lekin", "kaafi", "kafi", "bilkul", "paisa", "paise", "wala", "wali", "kya",
    "kyun", "mujhe", "mera", "meri", "aur", "bhi", "toh", "sab", "kharab", "badhiya", "mast", "sahi",
    "dikkat", "tha", "thi", "raha", "rahi", "karna", "karo", "liya", "diya", "mila", "pasand", "aaya",
}

_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        L = Language
        _detector = LanguageDetectorBuilder.from_languages(
            L.ENGLISH, L.HINDI, L.SPANISH, L.FRENCH, L.GERMAN, L.PORTUGUESE, L.ITALIAN, L.ARABIC,
        ).build()
    return _detector


def detect_language(text: str) -> tuple[str, str]:
    """Returns (language, script). language: en, hi, hinglish, es, ... or und."""
    dev = len(DEVANAGARI.findall(text))
    lat = len(LATIN.findall(text))
    if dev + lat == 0:
        return "und", "none"

    if dev > 0:
        share = dev / (dev + lat)
        if share >= 0.5:
            return "hi", "devanagari"
        return "hinglish", "mixed"

    tokens = re.findall(r"[a-z]+", text.lower())
    hits = sum(1 for t in tokens if t in HINGLISH_WORDS)
    if hits >= 2 or (hits >= 1 and tokens and hits / len(tokens) >= 0.2):
        return "hinglish", "latin"

    if len(tokens) < 3:
        return "und", "latin"
    lang = _get_detector().detect_language_of(text)
    if lang is None:
        return "und", "latin"
    return lang.iso_code_639_1.name.lower(), "latin"
