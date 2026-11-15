
"""Severe rare complaints (final pipeline document, section 10): safety, allergy, fraud and legal terms.
They are shown regardless of how few reviews mention them. The list favours recall, because a person reads every hit;
a hit can be a false alarm (for example 'no rash at all'). Terms are matched as whole words or word starts."""
import re

SEVERE = {
    "safety": ["caught fire", "catch fire", "on fire", "fire hazard", "exploded", "explosion", "electric shock", "electrocut",
               "injur", "hospital", "choking", "choked", "poison", "toxic", "unsafe", "burnt my", "burned my", "chemical burn"],
    "allergy": ["allergic", "allergy", "allergies", "rash", "hives", "swollen", "swelling", "anaphyla", "breakout",
                "burning sensation", "blister"],
    "fraud": ["fake", "counterfeit", "scam", "fraud", "not genuine", "not authentic", "knock off", "knockoff", "nakli", "dhokha",
              "expired product", "expiry date passed"],
    "legal": ["lawyer", "lawsuit", "legal action", "consumer court", "consumer forum", "sue you", "sue them", "trading standards",
              "fda", "report you", "police"],
}


def _rx(terms: list[str]) -> re.Pattern:
    return re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(t) for t in terms) + r")", re.I)


_RX = {cat: _rx(terms) for cat, terms in SEVERE.items()}
# One regex for a cheap database prefilter (Postgres ~* syntax is close enough for plain alternation).
PREFILTER = r"(^|[^a-z])(" + "|".join(re.escape(t) for terms in SEVERE.values() for t in terms) + ")"


def severe_hits(text: str) -> list[str]:
    """Categories whose terms appear in the text, in a fixed order."""
    return [cat for cat, rx in _RX.items() if rx.search(text or "")]
