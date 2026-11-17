
"""Reply drafts come from fixed templates, never free generation (document: nothing is generated freely).
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
from app.core.domains import EXTRA_REPLY_LINES  # noqa: E402

for _k, _v in EXTRA_REPLY_LINES.items():
    ASPECT_LINES.setdefault(_k, _v)
CLOSE = "Please reply with your order number so we can put this right."


def draft_reply(severe: list[str], aspect: str | None, language: str | None = "en") -> str:
    parts = []
    if severe:
        parts.append(OPENERS[severe[0]])
    else:
        parts.append("Thank you for your honest feedback.")
        parts.append(ASPECT_LINES.get(aspect or "", GENERIC))
    parts.append(CLOSE)
    body = " ".join(parts)
    if language not in (None, "en", "und"):
        body = f"[Review language: {language}. Translate before sending.] " + body
    return body

