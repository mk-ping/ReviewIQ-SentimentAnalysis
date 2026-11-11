from app.services.language import detect_language

CASES = [
    ("Great scent, but the pump broke after a week.", "en", "latin"),
    ("Bahut accha product hai but price thoda zyada hai", "hinglish", "latin"),
    ("\u092f\u0939 \u092c\u0939\u0941\u0924 \u0905\u091a\u094d\u091b\u093e \u0939\u0948", "hi", "devanagari"),
    ("Product \u092c\u0939\u0941\u0924 \u0905\u091a\u094d\u091b\u093e hai", "hinglish", "mixed"),
    ("Good", "und", "latin"),
]
for text, lang, script in CASES:
    got = detect_language(text)
    print(got, "expected", (lang, script))
    assert got == (lang, script), text
print("Producto excelente, muy buena calidad y llego rapido ->", detect_language("Producto excelente, muy buena calidad y llego rapido"))
print("all language checks passed")
