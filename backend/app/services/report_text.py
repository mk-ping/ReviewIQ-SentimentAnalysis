"""Plain-language wording for the PDF report and the product statuses. Pure functions, so they test offline."""

ASPECT_PRAISE = "Customers most often praise {}."


def product_status(p: dict) -> tuple[str, str]:
    """(short label, tone) for the True Rating table. Never says 'too few reviews'."""
    if p.get("low_sample"):
        return f"Early read ({p['n']} reviews)", "neutral"
    if p.get("clear_difference"):
        if (p.get("true_rating") or 0) < (p.get("shown_avg") or 0):
            return "Customers are less happy than the stars show", "bad"
        return "Customers are happier than the stars show", "good"
    return "Stars match what customers write", "good"


def date_span(d1, d2) -> str:
    if not d1 or not d2:
        return ""
    return f"{d1:%d %b %Y} to {d2:%d %b %Y}"


def headlines(d: dict) -> list[str]:
    """Up to seven short sentences that tell a manager where things stand."""
    s, dist = d["summary"], d["dist"]
    n = s["reviews"]
    out = []
    span = date_span(d.get("date_from"), d.get("date_to"))
    first = f"{n:,} reviews across {d['n_products']} product{'s' if d['n_products'] != 1 else ''}" + (f" ({span})" if span else "") + "."
    if dist.get("audience"):
        first += f" Customers are {dist['audience']}."
    out.append(first)
    if s.get("average_rating") is not None and s.get("percent_negative") is not None:
        out.append(f"The average rating is {s['average_rating']:.2f} stars and {s['percent_negative']:.0f}% of reviews read as negative.")
    mm = s.get("mismatch_rate")
    if mm is not None and mm >= 0.15:
        out.append(f"Stars and written text disagree on {mm * 100:.0f}% of reviews, so the star average alone can mislead.")
    if d["issues"]:
        name, asp, cnt = d["issues"][0][0], d["issues"][0][1], d["issues"][0][2]
        out.append(f"The biggest problem is {name} ({asp}), mentioned in {cnt} reviews.")
    flagged = [w for w in d.get("watch", []) if w["level"] != "ok"]
    if flagged:
        out.append("Products that need attention first: " + ", ".join(f"{w['product']} (risk {w['score']})" for w in flagged[:3]) + ".")
    elif d.get("watch"):
        out.append("No product is flagged as at risk right now.")
    if s.get("top_strengths"):
        out.append(ASPECT_PRAISE.format(s["top_strengths"][0]["aspect"]))
    if d.get("severe_n"):
        out.append(f"{d['severe_n']} review{'s' if d['severe_n'] != 1 else ''} mention safety, allergy, fraud or legal terms and should be read first.")
    if n < 30:
        out.append(f"This is an early read based on {n} reviews. The figures will firm up as more reviews arrive.")
    return out
