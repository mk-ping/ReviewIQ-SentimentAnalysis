import json

import httpx

from app.core.config import settings
from app.services.detection import ROLES


def validate_mapping(raw, header: list[str]) -> dict[str, str]:
    """Keeps only known roles whose column really exists in the file, each column at most once."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    used: set[str] = set()
    for role, col in raw.items():
        if role in ROLES and isinstance(col, str) and col in header and col not in used:
            out[role] = col
            used.add(col)
    return out


async def suggest_mapping(header: list[str], sample_rows: list[list[str]]) -> dict[str, str] | None:
    sample = [dict(zip(header, [c[:200] for c in r])) for r in sample_rows[:5]]
    system = (
        "You map spreadsheet columns to roles for a customer-review file. Roles: " + ", ".join(ROLES) + ". "
        "'text' is the review body and is required. Return ONLY JSON: {\"mapping\": {\"role\": \"exact column name\"}}. "
        "Use each column at most once. Omit roles you cannot find. Copy column names exactly from the header."
    )
    user = f"Header: {json.dumps(header, ensure_ascii=False)}\nSample rows: {json.dumps(sample, ensure_ascii=False)}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{settings.llm_url}/api/chat",
                json={"model": settings.llm_model, "stream": False, "format": "json", "options": {"temperature": 0},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            )
            r.raise_for_status()
            data = json.loads(r.json()["message"]["content"])
    except Exception:
        return None
    mapping = validate_mapping(data.get("mapping") if isinstance(data, dict) else None, header)
    return mapping or None
