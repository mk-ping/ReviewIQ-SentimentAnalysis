"""Product watchlist: one explainable 0-100 risk score per product, so a manager sees which product needs attention first.
Six signals, each scaled 0 to 1 and multiplied by its weight (the weights add to 100). Pure functions, so they test offline."""

WEIGHTS = {"negative": 30, "trend": 20, "rating_drop": 10, "severe": 15, "hidden": 10, "concentration": 15}
LABELS = {
    "negative": "Share of negative reviews",
    "trend": "Complaints rising recently",
    "rating_drop": "Average rating falling",
    "severe": "Safety, allergy, fraud or legal mentions",
    "hidden": "Unhappy customers inside 4 and 5 star reviews",
    "concentration": "One aspect drawing most complaints",
}
FULL_AT = {"negative": 0.40, "trend": 0.20, "rating_drop": 1.0, "severe": 3, "hidden": 0.20, "concentration": 0.25}
MIN_WINDOW = 10      # reviews needed in both the recent and the earlier window before a trend is judged
HIGH, WATCH = 60, 35
LOW_SAMPLE = 30


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def risk(m: dict) -> dict:
    """m: n, neg_share, recent_n, earlier_n, recent_neg, earlier_neg, recent_avg, earlier_avg, severe_n, hidden_share,
    top_aspect, top_aspect_share. Missing or None signals score 0 and are named in 'not_judged'."""
    n = m.get("n") or 0
    have_trend = (m.get("recent_n") or 0) >= MIN_WINDOW and (m.get("earlier_n") or 0) >= MIN_WINDOW
    raw: dict[str, float | None] = {
        "negative": _clip((m.get("neg_share") or 0) / FULL_AT["negative"]) if n else 0.0,
        "trend": _clip(((m.get("recent_neg") or 0) - (m.get("earlier_neg") or 0)) / FULL_AT["trend"]) if have_trend else None,
        "rating_drop": _clip(((m.get("earlier_avg") or 0) - (m.get("recent_avg") or 0)) / FULL_AT["rating_drop"])
        if have_trend and m.get("earlier_avg") is not None and m.get("recent_avg") is not None else None,
        "severe": _clip((m.get("severe_n") or 0) / FULL_AT["severe"]),
        "hidden": _clip(m["hidden_share"] / FULL_AT["hidden"]) if m.get("hidden_share") is not None else None,
        "concentration": _clip((m.get("top_aspect_share") or 0) / FULL_AT["concentration"]) if m.get("top_aspect") else 0.0,
    }
    parts = {k: round(WEIGHTS[k] * (v or 0.0), 1) for k, v in raw.items()}
    score = round(sum(parts.values()))
    level = "high" if score >= HIGH else "watch" if score >= WATCH else "ok"
    reasons = []
    for k in sorted(parts, key=lambda k: -parts[k]):
        if raw[k] is None or raw[k] < 0.5:
            continue
        if k == "negative":
            reasons.append(f"{round(100 * (m.get('neg_share') or 0))}% of reviews are negative.")
        elif k == "trend":
            reasons.append(f"Negative reviews rose from {round(100 * (m.get('earlier_neg') or 0))}% to {round(100 * (m.get('recent_neg') or 0))}% in the last 30 days.")
        elif k == "rating_drop":
            reasons.append(f"Average rating fell from {m['earlier_avg']:.1f} to {m['recent_avg']:.1f} stars recently.")
        elif k == "severe":
            reasons.append(f"{m.get('severe_n')} review(s) mention safety, allergy, fraud or legal terms.")
        elif k == "hidden":
            reasons.append(f"{round(100 * m['hidden_share'])}% of 4 and 5 star reviews still contain a complaint.")
        elif k == "concentration":
            reasons.append(f"{m['top_aspect']} draws complaints in {round(100 * (m.get('top_aspect_share') or 0))}% of reviews.")
    not_judged = [LABELS[k] for k, v in raw.items() if v is None]
    if n == 0:
        action = "No scored reviews yet."
    elif level == "ok":
        action = "No action needed now. Keep monitoring."
    elif m.get("top_aspect"):
        action = f"Start with {m['top_aspect']}: read its recent complaints and assign an owner."
    else:
        action = "Read the most recent negative reviews and assign an owner."
    return {"score": score, "level": level, "parts": parts, "reasons": reasons, "not_judged": not_judged,
            "low_sample": n < LOW_SAMPLE, "action": action}


def trend_word(m: dict) -> str:
    if (m.get("recent_n") or 0) < MIN_WINDOW or (m.get("earlier_n") or 0) < MIN_WINDOW:
        return "not enough recent reviews"
    d = (m.get("recent_neg") or 0) - (m.get("earlier_neg") or 0)
    return "rising" if d >= 0.05 else "falling" if d <= -0.05 else "steady"
