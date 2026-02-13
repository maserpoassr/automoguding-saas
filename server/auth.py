import base64
import hashlib
import hmac
import json
import os
import time
import secrets
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)
_SECRET_CACHE: bytes | None = None

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))

def _secret() -> bytes:
    global _SECRET_CACHE
    if _SECRET_CACHE is not None:
        return _SECRET_CACHE
    key = (os.getenv("APP_SECRET") or "").strip()
    if key:
        _SECRET_CACHE = key.encode("utf-8")
        return _SECRET_CACHE

    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    require = (os.getenv("REQUIRE_APP_SECRET") or "").strip().lower() in ["1", "true", "yes", "on"]
    if require or app_env in ["prod", "production"]:
        raise RuntimeError("APP_SECRET 未配置（生产环境必须设置）")

    _SECRET_CACHE = secrets.token_bytes(32)
    return _SECRET_CACHE

def hash_password(password: str) -> str:
    pw = (password or "").encode("utf-8")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw, salt, 200_000)
    return f"pbkdf2_sha256$200000${_b64url_encode(salt)}${_b64url_encode(dk)}"

def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iter_s, salt_b64, dk_b64 = (password_hash or "").split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(dk_b64)
        pw = (password or "").encode("utf-8")
        got = hashlib.pbkdf2_hmac("sha256", pw, salt, iterations)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False

def issue_token(subject: str, role: str, ttl_seconds: int = 12 * 60 * 60) -> str:
    payload = {
        "sub": subject,
        "role": role,
        "exp": int(time.time()) + int(ttl_seconds),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"

def verify_token(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("bad token")
        payload_b64, sig_b64 = parts
        expected_sig = hmac.new(_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = int(payload.get("exp") or 0)
        if exp <= int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

def require_roles(payload: dict, roles: list[str]) -> dict:
    if payload.get("role") not in roles:
        raise HTTPException(status_code=403, detail="权限不足")
    return payload

def get_auth_payload(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return verify_token(credentials.credentials)

def get_admin(payload: dict = Depends(get_auth_payload)) -> dict:
    return require_roles(payload, ["admin"])

def get_operator(payload: dict = Depends(get_auth_payload)) -> dict:
    return require_roles(payload, ["admin", "operator"])

def get_viewer(payload: dict = Depends(get_auth_payload)) -> dict:
    return require_roles(payload, ["admin", "operator", "viewer"])

def get_user(payload: dict = Depends(get_auth_payload)) -> dict:
    return require_roles(payload, ["user"])

def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
