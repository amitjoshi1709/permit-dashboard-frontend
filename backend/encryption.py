"""
Symmetric encryption for sensitive settings (payment card data).

Uses Fernet from the `cryptography` library. The key is read from the
CARD_ENCRYPTION_KEY env var (a 32-byte base64-encoded Fernet key).

Generate a key once:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
import json
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.getenv("CARD_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("CARD_ENCRYPTION_KEY not configured in .env")
    return Fernet(key.encode())


def encrypt_card(card_dict: dict) -> str:
    plaintext = json.dumps(card_dict).encode("utf-8")
    return _get_fernet().encrypt(plaintext).decode("utf-8")


def decrypt_card(ciphertext: str) -> dict:
    plaintext = _get_fernet().decrypt(ciphertext.encode("utf-8"))
    return json.loads(plaintext.decode("utf-8"))
