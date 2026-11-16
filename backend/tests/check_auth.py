"""Offline checks for passwords and session tokens. Run: python -m tests.check_auth"""
from app.core.security import hash_password, make_token, read_token, verify_password

h = hash_password("correct horse", iterations=1000)
assert verify_password("correct horse", h)
assert not verify_password("wrong", h)
assert not verify_password("x", None) and not verify_password("x", "garbage")
assert hash_password("same", 1000) != hash_password("same", 1000)      # fresh salt every time

t = make_token(7, "secret-a", 3600, now=1000)
assert read_token(t, "secret-a", now=2000) == 7
assert read_token(t, "secret-b", now=2000) is None                      # wrong key
assert read_token(t, "secret-a", now=1000 + 3601) is None               # expired
uid, exp, sig = t.split(".")
assert read_token("8." + exp + "." + sig, "secret-a", now=2000) is None  # user id swapped
assert read_token(None, "secret-a") is None and read_token("a.b", "secret-a") is None
print("auth checks passed")
