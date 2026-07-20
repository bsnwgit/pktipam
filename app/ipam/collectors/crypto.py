"""
Fernet-based encryption for collector credentials (DHCP/DNS server API keys
and passwords, WinRM/SSH credentials, SNMP community strings/v3 auth
secrets) stored in collectors.config_json. The whole config dict is
encrypted as one blob rather than field-by-field — nothing in a collector
config is ever needed in plaintext at rest.

credential_key is generated once by install.sh (Fernet.generate_key()) and
written to config.yaml, the same way secret_key is handled for JWT signing.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.credential_key
    if not key:
        raise RuntimeError(
            "credential_key is not configured — set it in config.yaml "
            "(generate with: python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\")"
        )
    return Fernet(key.encode())


def encrypt_config(config: dict) -> str:
    return _fernet().encrypt(json.dumps(config).encode()).decode()


def decrypt_config(token: str) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()).decode())
    except InvalidToken:
        return {}


def encrypt_str(value: str) -> str:
    """Per-field encryption for the snmp_credentials table's auth_key_enc/
    priv_key_enc columns — same key as encrypt_config, just one string at a
    time instead of a whole config dict."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_str(token: str | None) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
