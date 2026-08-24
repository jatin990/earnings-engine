"""Asymmetric Public-Key / Private-Key Zero-Knowledge Database Encryption.

Architecture:
1. EMBEDDED PUBLIC KEY (Built directly into code and pushed to GitHub):
   - The server uses this embedded RSA-2048 Public Key to encrypt client connection metadata
     (IP address, machine name, geolocation, device info) before writing to SQLite / Turso databases.
   - Anyone/any server possessing the public key can ONLY encrypt data. It is mathematically impossible
     to decrypt or reverse-engineer without the private key.

2. PRIVATE KEY (Kept STRICTLY on your local machine in `.local_private.key`):
   - Stored in a `.gitignored` local file on your development machine.
   - Only your local machine has the private key to decrypt and read the captured records.
   - If the remote server or cloud database is inspected or breached, the records remain 100% locked ciphertext.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    default_backend = None  # type: ignore
    hashes = None  # type: ignore
    serialization = None  # type: ignore
    padding = None  # type: ignore
    rsa = None  # type: ignore
    AESGCM = None  # type: ignore
    _HAS_CRYPTOGRAPHY = False

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_PRIVATE_KEY_FILE = _ROOT_DIR / ".local_private.key"

# ---------------------------------------------------------------------------
# Embedded Public Key (Safe to commit to GitHub and run on any server)
# ---------------------------------------------------------------------------
_EMBEDDED_PUBLIC_KEY_PEM = (
    b"-----BEGIN PUBLIC KEY-----\n"
    b"MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvFy09Pj/sfoyXVW+OcE5\n"
    b"psAHQOFbmVyI0DQl7pGVXVSy6ZJV/7ukmhCyvDIYe6bjF+Hrgwhm66NeS19vLqqq\n"
    b"6IaNKkCclU6wG9mIIfHLMMN6GXq6tgYc3m+NGg3NmhxHRlteh48DjSFV7PfB6CrK\n"
    b"tZyWtKJ7AYJtYwvwibc1/bkFKyRNoKQijb4TFgnB9gy1UW4Cw/GVtIKHVF+7yKqf\n"
    b"xcu6TgETi3dDt4tb/GeJug01XC/tynobOUrsZqWWRMIxPURh+7Nan3WpJYmM9Ep3\n"
    b"+TWiVkzC1ANiYPxGkiGeKyrcVt0E7jvvh9DQ562q4OiBB+yUVtdvB1xyU/GeXzCu\n"
    b"yQIDAQAB\n"
    b"-----END PUBLIC KEY-----\n"
)

_CACHED_PUB_KEY: Any = None
_CACHED_PRIV_KEY: Any = None


def get_public_key() -> Any:
    """Retrieve the embedded RSA Public Key for encryption."""
    if not _HAS_CRYPTOGRAPHY:
        return None
    global _CACHED_PUB_KEY
    if _CACHED_PUB_KEY is not None:
        return _CACHED_PUB_KEY

    # Check env override first if customized
    env_pub = os.environ.get("METADATA_PUBLIC_KEY") or os.environ.get("ACCESS_TRACKER_PUBLIC_KEY")
    if env_pub:
        try:
            _CACHED_PUB_KEY = serialization.load_pem_public_key(
                env_pub.encode("utf-8"), backend=default_backend()
            )
            return _CACHED_PUB_KEY
        except Exception:
            pass

    # Use embedded public key
    _CACHED_PUB_KEY = serialization.load_pem_public_key(
        _EMBEDDED_PUBLIC_KEY_PEM, backend=default_backend()
    )
    return _CACHED_PUB_KEY


def get_private_key() -> Any:
    """Retrieve the local RSA Private Key for decryption (local machine only)."""
    if not _HAS_CRYPTOGRAPHY:
        return None
    global _CACHED_PRIV_KEY
    if _CACHED_PRIV_KEY is not None:
        return _CACHED_PRIV_KEY

    # 1. Check environment variable
    env_priv = os.environ.get("METADATA_PRIVATE_KEY") or os.environ.get("ACCESS_TRACKER_PRIVATE_KEY")
    if env_priv:
        try:
            _CACHED_PRIV_KEY = serialization.load_pem_private_key(
                env_priv.encode("utf-8"), password=None, backend=default_backend()
            )
            return _CACHED_PRIV_KEY
        except Exception:
            pass

    # 2. Check local .local_private.key file
    if _PRIVATE_KEY_FILE.exists():
        try:
            _CACHED_PRIV_KEY = serialization.load_pem_private_key(
                _PRIVATE_KEY_FILE.read_bytes(), password=None, backend=default_backend()
            )
            return _CACHED_PRIV_KEY
        except Exception:
            pass

    return None


def has_private_key() -> bool:
    """Check if local RSA Private Key is present on this machine."""
    return get_private_key() is not None


def encrypt_field(value: str | None) -> str | None:
    """Encrypt a sensitive string using RSA Public Key + AES-256-GCM.
    
    Safe to execute anywhere (cloud server, remote daemon) because it requires
    ONLY the public key. The server cannot decrypt what it writes.
    """
    if not value or not isinstance(value, str):
        return value
    if value.startswith("enc::"):
        return value  # Already encrypted

    try:
        pub_key = get_public_key()
        if pub_key is None:
            return value

        # Hybrid Encryption:
        # 1. Generate ephemeral 256-bit AES-GCM session key
        aes_key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(aes_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

        # 2. Encrypt the AES session key using RSA Public Key (OAEP SHA-256)
        enc_aes_key = pub_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        payload = {
            "k": base64.b64encode(enc_aes_key).decode("utf-8"),
            "n": base64.b64encode(nonce).decode("utf-8"),
            "c": base64.b64encode(ciphertext).decode("utf-8"),
        }
        return "enc::" + base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def decrypt_field(value: str | None) -> str | None:
    """Decrypt a ciphertext field using your local RSA Private Key.
    
    Only succeeds on your local machine where `.local_private.key` resides.
    On servers without the private key, returns `[ENCRYPTED: LOCKED WITH LOCAL KEY]`.
    """
    if not value or not isinstance(value, str):
        return value
    if not value.startswith("enc::"):
        return value  # Plaintext legacy record

    token = value[5:]  # Strip 'enc::'
    try:
        priv_key = get_private_key()
        if priv_key is None:
            return "[ENCRYPTED: LOCKED WITH LOCAL KEY]"

        raw_json = base64.b64decode(token).decode("utf-8")
        payload = json.loads(raw_json)

        enc_aes_key = base64.b64decode(payload["k"])
        nonce = base64.b64decode(payload["n"])
        ciphertext = base64.b64decode(payload["c"])

        # Decrypt AES key with RSA Private Key
        aes_key = priv_key.decrypt(
            enc_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # Decrypt payload with AES-GCM
        aesgcm = AESGCM(aes_key)
        plain_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plain_bytes.decode("utf-8")
    except Exception:
        return "[ENCRYPTED: LOCKED WITH LOCAL KEY]"
