"""Reply drafts come from fixed templates, never free generation (document: nothing is generated freely).
Three tones (professional, warm, brief), an optional signature, the product name, and thank-you drafts for happy customers.
The manager edits the draft before anything is marked sent."""

OPENERS = {
    "safety": "Thank you for telling us. Your safety matters more than anything, and we are treating this as urgent.",
    "allergy": "Thank you for telling us, and we are sorry about the reaction. Please stop using the product while we look into it.",
    "fraud": "Thank you for raising this. We take authenticity seriously and want to check this order with you.",
    "legal": "Thank you for your message. We want to resolve this properly and a senior team member will contact you.",
}
ASPECT_LINES = {
    "packaging": "We are sorry the packaging did not protect or work as it should.",
    "delivery": "We are sorry your order was late or arrived in poor condition.",
    "price": "We hear you on value for money, and we are reviewing our pricing.",
    "quality": "We are sorry the quality fell short of what you expected.",
    "scent": "We are sorry the scent was not what you expected.",
    "results": "We are sorry you did not see the results you hoped for.",
    "ease of use": "We are sorry it was harder to use than it should be.",
    "customer service": "We are sorry about your experience with our support.",
}
GENERIC = "We are sorry your experience did not meet your expectations."
try:  # lines for restaurant, hotel, movie and app aspects (aspect profiles)
    from app.core.domains import EXTRA_REPLY_LINES
    for _k, _v in EXTRA_REPLY_LINES.items():
        ASPECT_LINES.setdefault(_k, _v)
except ImportError:
    pass

TONES = ("professional", "warm", "brief")
CLOSE = {
    "professional": "Please reply with your order number so we can put this right.",
    "warm": "We would really like to make this right. Could you reply with your order number so we can look into it?",
    "brief": "Please send your order number and we will sort this out.",
}
THANKS = {
    "professional": "Thank you for your honest feedback.",
    "warm": "Thank you so much for taking the time to write to us.",
    "brief": "Thank you for your feedback.",
}
PRAISE = {
    "professional": "Thank you for your review. We are pleased that you are happy with {what}.",
    "warm": "Thank you for such kind words! We are delighted that you are enjoying {what}.",
    "brief": "Thank you for the kind review of {what}.",
}
PRAISE_ASPECT = "We are especially glad you liked the {}."
PRAISE_CLOSE = {"professional": "We look forward to serving you again.", "warm": "We hope to see you again soon!", "brief": "We hope to see you again."}


def _finish(parts: list[str], language: str | None, signature: str | None) -> str:
    body = " ".join(p for p in parts if p)
    if signature and signature.strip():
        body += "\n\n" + signature.strip()
    if language not in (None, "en", "und"):
        body = f"[Review language: {language}. Translate before sending.] " + body
    return body


def draft_reply(severe: list[str], aspect: str | None, language: str | None = "en", *, product: str | None = None,
                tone: str = "professional", signature: str | None = None) -> str:
    tone = tone if tone in TONES else "professional"
    parts = []
    if severe:
        parts.append(OPENERS[severe[0]])
    else:
        t = THANKS[tone]
        if product and tone == "professional":
            t = f"Thank you for your honest feedback on {product}."
        parts += [t, ASPECT_LINES.get(aspect or "", GENERIC)]
    parts.append(CLOSE[tone])
    return _finish(parts, language, signature)


def draft_thanks(aspect: str | None, language: str | None = "en", *, product: str | None = None,
                 tone: str = "professional", signature: str | None = None) -> str:
    tone = tone if tone in TONES else "professional"
    parts = [PRAISE[tone].format(what=product or "your purchase")]
    if aspect and tone != "brief":
        parts.append(PRAISE_ASPECT.format(aspect))
    parts.append(PRAISE_CLOSE[tone])
    return _finish(parts, language, signature)
