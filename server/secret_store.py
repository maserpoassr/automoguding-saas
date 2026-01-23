import base64
import hashlib
import os
from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc$"

def _get_fernet() -> Fernet | None:
    key = (os.getenv("USER_PASSWORD_KEY") or os.getenv("FERNET_KEY") or "").strip()
    if not key:
        return None
    try:
        raw = key.encode("utf-8")
        if len(raw) == 44:
            return Fernet(raw)
    except Exception:
        pass
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt_secret(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    f = _get_fernet()
    if not f:
        return s
    token = f.encrypt(s.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"

def decrypt_secret(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if not s.startswith(_PREFIX):
        return s
    f = _get_fernet()
    if not f:
        raise ValueError("密钥未配置，无法解密")
    token = s[len(_PREFIX) :]
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("密钥错误或密文损坏")

