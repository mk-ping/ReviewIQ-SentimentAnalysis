"""Password hashing and signed session tokens. Standard library only."""
import base64
import hashlib
import hmac
import secrets
import time

ITERATIONS = 200_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2$%d$%s$%s" % (iterations, salt.hex(), dk.hex())


def verify_password(password: str, stored: str | None) -> bool:
    try:
        kind, it, salt, want = (stored or "").split("$")
        if kind != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), want)
    except (ValueError, TypeError):
        return False


def _sig(secret: str, body: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def make_token(user_id: int, secret: str, ttl_seconds: int, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + ttl_seconds)
    body = "%d.%d" % (user_id, exp)
    return body + "." + _sig(secret, body)


def read_token(token: str | None, secret: str, now: float | None = None) -> int | None:
    """Returns the user id, or None when the token is missing, altered or expired."""
    try:
        uid, exp, sig = (token or "").split(".")
        if not hmac.compare_digest(sig, _sig(secret, uid + "." + exp)):
            return None
        if int(exp) < (time.time() if now is None else now):
            return None
        return int(uid)
    except (ValueError, TypeError):
        return None
