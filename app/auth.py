"""
SwiftHub Authentication Module
Mirrors the loginAndGetToken → loginAsUser flow from route.ts
"""

import time
import threading
import urllib.request
import urllib.error
import json

# ── Admin credentials (mirrored from route.ts) ──────────────────────────────
_LOGIN_URL       = "https://api.swifthub.net/api/identity/v1/Authentication/login"
_LOGIN_AS_USER   = "https://api.swifthub.net/api/identity/v1/Authentication/loginAsUser"
_ADMIN_USERNAME  = "swh.admin"
_ADMIN_PASSWORD  = "@SwiftHub3005"

# ── Cached admin token with thread-safety ───────────────────────────────────
_token_lock  = threading.Lock()
_admin_token: str | None = None
_token_exp:   float = 0.0


def _decode_jwt_exp(token: str) -> float:
    """Decode expiry from a JWT without external libraries."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0.0
        import base64
        padding = 4 - len(parts[1]) % 4
        payload = base64.urlsafe_b64decode(parts[1] + "=" * padding)
        return float(json.loads(payload).get("exp", 0))
    except Exception:
        return 0.0


def _post_json(url: str, payload: dict, token: str | None = None, timeout: int = 15) -> dict:
    """Minimal HTTP POST that returns parsed JSON, raises on error."""
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type":  "application/json",
        "Accept":        "application/json, text/plain, */*",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
        except Exception:
            err = {"message": body}
        raise RuntimeError(
            err.get("message") or f"HTTP {e.code}"
        ) from None


def get_admin_token() -> str:
    """Return a valid cached admin token, refreshing it when expired."""
    global _admin_token, _token_exp

    with _token_lock:
        now = time.time()
        if _admin_token and _token_exp > now + 10:
            return _admin_token

        resp = _post_json(_LOGIN_URL, {
            "loginCredential": _ADMIN_USERNAME,
            "password":        _ADMIN_PASSWORD,
        })

        if resp.get("status") != 1:
            raise RuntimeError(resp.get("message") or "Admin login failed")

        token = resp.get("data", {}).get("token")
        if not token:
            raise RuntimeError("No token returned from admin login")

        _admin_token = token
        _token_exp   = _decode_jwt_exp(token)
        return _admin_token


def login_as_user(user_name: str) -> dict:
    """
    Authenticate a warehouse user against SwiftHub.

    Returns a dict with:
        {
            "token":      "<JWT>",
            "userName":   "<email>",
            "userType":   "<type>",
        }

    Raises RuntimeError with a human-readable message on failure.
    """
    admin_token = get_admin_token()

    resp = _post_json(_LOGIN_AS_USER, {"userName": user_name}, token=admin_token)

    if resp.get("status") != 1:
        msg = resp.get("message") or "Login as user failed"
        # Map error codes from SwiftHub (Msg025 = user not found)
        if any(k in msg for k in ("not found", "does not exist", "Msg025")):
            raise LookupError(f"User '{user_name}' not found in SwiftHub.")
        raise RuntimeError(msg)

    data = resp.get("data", {})
    token = data.get("token")
    if not token:
        raise RuntimeError("No user token returned from SwiftHub.")

    return {
        "token":    token,
        "userName": user_name,
        "userType": data.get("userType", ""),
    }
