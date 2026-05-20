"""
SwiftHub Authentication Module
Mirrors the handleLogin flow from the Next.js frontend.
"""

import base64
import json
import threading
import time
import urllib.error
import urllib.request
import urllib.parse

_LOGIN_URL = "https://api.swifthub.net/api/identity/v1/Authentication/login"


# ── JWT helpers ──────────────────────────────────────────────────────────────

def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload section of a JWT (no signature verification needed)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        padding = 4 - len(parts[1]) % 4
        raw = base64.urlsafe_b64decode(parts[1] + "=" * padding)
        return json.loads(raw)
    except Exception:
        return {}


def _decode_jwt_exp(token: str) -> float:
    return float(_decode_jwt_payload(token).get("exp", 0))


# ── HTTP helper ──────────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, token: "Optional[str]" = None, timeout: int = 15) -> dict:
    """POST JSON, return parsed response dict, raise RuntimeError on failure."""
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept":       "application/json, text/plain, */*",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
        except Exception:
            err = {"message": body}
        raise RuntimeError(err.get("message") or f"HTTP {e.code}") from None


# ── Public API ───────────────────────────────────────────────────────────────

def login_user(login_credential: str, password: str) -> dict:
    """
    Authenticate a user directly with their own credentials.

    Mirrors the JS handleLogin:
        POST /Authentication/login  { loginCredential, password }

    Returns:
        {
            "token":      "<JWT>",
            "userName":   "<loginCredential>",
            "userId":     "<UserId from JWT payload>",
            "userType":   "<userType>",
            "needChangePassword": bool,
        }

    Raises RuntimeError with a human-readable message on failure.
    """
    resp = _post_json(_LOGIN_URL, {
        "loginCredential": login_credential,
        "password":        password,
    })

    if resp.get("status") != 1:
        raise RuntimeError(resp.get("message") or "Login failed")

    data = resp.get("data", {})
    token = data.get("token")
    if not token:
        raise RuntimeError("No token returned from SwiftHub.")

    payload = _decode_jwt_payload(token)

    return {
        "token":             token,
        "userName":          login_credential,
        "userId":            payload.get("UserId", login_credential),
        "userType":          data.get("userType", ""),
        "needChangePassword": data.get("needChangePassword", False),
    }


def get_user_info(user_id: str, token: str) -> dict:
    """
    Fetch full user profile from SwiftHub.
    GET /api/identity/v1/User/getUserInfo?id=<user_id>

    Returns a dict with the useful fields:
        fullName, email, userName, tenantName, userTypeName, userRoles, isActive
    """
    url = f"https://api.swifthub.net/api/identity/v1/User/getUserInfo?id={urllib.parse.quote(user_id)}"
    headers = {
        "Accept":        "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"getUserInfo failed: HTTP {e.code}") from None

    if body.get("status") != 1:
        raise RuntimeError(body.get("message") or "getUserInfo returned error")

    d = body.get("data", {})
    return {
        "id":           d.get("id", user_id),
        "fullName":     d.get("fullName", ""),
        "email":        d.get("email", ""),
        "userName":     d.get("userName", ""),
        "tenantName":   d.get("tenantName", ""),
        "userTypeName": d.get("userTypeName", ""),
        "isActive":     d.get("isActive", True),
        "userRoles":    [r.get("roleName", "") for r in d.get("userRoles", [])],
    }
