"""High-level security helpers used by the restaurant app."""

from security.sha256 import sha256
from security.rsa_impl import get_private_key, get_public_key, sign, verify

# Input constants required by the course.
KEY_NAME = "KhiemTranCong"
PLAINTEXT_SCHOOL = "UTH - University of Transport HCMC"

# Salt base for deterministic per-user salted SHA-256.
_SALT_BASE: bytes = sha256(KEY_NAME.encode())[:16]


def hash_password(password: str, username: str) -> str:
    """
    Return salted SHA-256 password string in the format: ``salt_hex:hash_hex``.
    """
    salt = sha256(_SALT_BASE + username.encode())[:16]
    pw_hash = sha256(salt + password.encode())
    return f"{salt.hex()}:{pw_hash.hex()}"


def verify_password(password: str, username: str, stored: str) -> bool:
    """
    Verify password against either:
    - legacy plain text (no ':')
    - salted SHA-256 format: ``salt_hex:hash_hex``
    """
    if ":" not in stored:
        return stored == password

    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        pw_hash = sha256(salt + password.encode())
        return pw_hash.hex() == hash_hex
    except Exception:
        return False


def sign_payment(payload_bytes: bytes) -> str:
    """Sign payment payload bytes using RSA private key and return hex signature."""
    return sign(payload_bytes, get_private_key())


def verify_payment_sig(payload_bytes: bytes, signature_hex: str) -> bool:
    """Verify payment signature with RSA public key."""
    return verify(payload_bytes, signature_hex, get_public_key())


if __name__ == "__main__":
    pw = "staff123"
    user = "staff_s001"
    stored = hash_password(pw, user)
    assert verify_password(pw, user, stored)
    assert not verify_password("wrong", user, stored)

    payload = b'{"amount": 185000.0, "order_id": "ORD001", "payment_id": "PAY001"}'
    sig = sign_payment(payload)
    assert verify_payment_sig(payload, sig)
    assert not verify_payment_sig(payload + b"tamper", sig)

    print("security.crypto self-test: PASS")
