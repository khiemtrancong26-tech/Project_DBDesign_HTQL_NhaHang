"""High-level security helpers used by the restaurant app."""

import os

from security.aes import aes_cbc_encrypt, aes_cbc_decrypt
from security.sha256 import sha256
from security.rsa_impl import get_private_key, get_public_key, sign, verify

# Input constants required by the course.
KEY_NAME = "KhiemTranCong"
PLAINTEXT_SCHOOL = "UTH - University of Transport HCMC"

# Salt base for deterministic per-user salted SHA-256.
_SALT_BASE: bytes = sha256(KEY_NAME.encode())[:16]


def _derive_aes_key() -> bytes:
    """
    Derive stable 16-byte AES key for app-level encrypted text.

    Priority:
      1) APP_AES_KEY
      2) APP_AUTH_SECRET
      3) DB_PASSWORD
      4) dev-only-secret
    """
    base = (
        os.getenv("APP_AES_KEY")
        or os.getenv("APP_AUTH_SECRET")
        or os.getenv("DB_PASSWORD")
        or "dev-only-secret"
    )
    return sha256(base.encode("utf-8"))[:16]


def encrypt_text_aes(plaintext: str) -> str:
    """
    Encrypt UTF-8 text with AES-128-CBC.

    Output format:
        aes1:<iv_hex>:<cipher_hex>
    """
    if plaintext is None:
        raise ValueError("Giá trị cần mã hóa không được None")
    iv = os.urandom(16)
    ciphertext = aes_cbc_encrypt(_derive_aes_key(), iv, plaintext.encode("utf-8"))
    return f"aes1:{iv.hex()}:{ciphertext.hex()}"


def _parse_aes_payload(value: str) -> tuple[bytes, bytes]:
    """
    Parse encrypted payload in one of 2 accepted formats:
      - aes1:<iv_hex>:<cipher_hex>
      - <iv_hex>:<cipher_hex>
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Giá trị cần giải mã không được rỗng")

    if raw.startswith("aes1:"):
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise ValueError("Định dạng aes1 không hợp lệ. Cần: aes1:<iv_hex>:<cipher_hex>")
        _, iv_hex, ct_hex = parts
    else:
        parts = raw.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Định dạng không hợp lệ. Cần: <iv_hex>:<cipher_hex>")
        iv_hex, ct_hex = parts

    try:
        iv = bytes.fromhex(iv_hex.strip())
        ciphertext = bytes.fromhex(ct_hex.strip())
    except ValueError as exc:
        raise ValueError("IV/ciphertext phải là chuỗi hex hợp lệ") from exc

    if len(iv) != 16:
        raise ValueError("IV phải đúng 16 byte")
    if not ciphertext or len(ciphertext) % 16 != 0:
        raise ValueError("Ciphertext phải có độ dài là bội số của 16 byte")

    return iv, ciphertext


def decrypt_text_aes(value: str) -> str:
    """Decrypt encrypted text payload and return UTF-8 plaintext."""
    iv, ciphertext = _parse_aes_payload(value)
    plaintext = aes_cbc_decrypt(_derive_aes_key(), iv, ciphertext)
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Giải mã xong nhưng dữ liệu không phải UTF-8 text") from exc


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
