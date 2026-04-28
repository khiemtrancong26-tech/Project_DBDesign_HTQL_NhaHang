"""
RSA — Triển khai từ đầu, không dùng thư viện mật mã.
Bao gồm: sinh khóa và chữ ký số RSA-SHA256.

Thông số demo:
    Dùng RSA-512 để chạy nhanh trong môi trường học.
    Ghi chú: hệ thống thực tế dùng RSA-2048.

Chỉ dùng built-in Python:
    pow(base, exp, mod)  — tích hợp sẵn trong interpreter
    Không import thêm gì ngoài sha256 tự viết.
"""

import sys as _sys, os as _os
if __name__ == '__main__' and __package__ is None:
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from security.sha256 import sha256

_RSA_SEED = b"KhiemTranCong"

# ══════════════════════════════════════════════════════════════════════════
# PRNG xác định (deterministic) — dùng SHA-256 làm bộ sinh số giả ngẫu nhiên
# Seed = tên sinh viên → không cần os.urandom
# ══════════════════════════════════════════════════════════════════════════

class _SHA256PRNG:
    """
    PRNG dựa trên SHA-256.
    Mỗi lần gọi next_bytes(n) → hash lại seed với counter tăng dần.
    Deterministic: cùng seed → cùng chuỗi số.
    """
    def __init__(self, seed: bytes):
        self._state   = sha256(seed)   # 32 byte
        self._counter = 0

    def next_bytes(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            self._counter += 1
            block = sha256(self._state + self._counter.to_bytes(8, 'big'))
            out.extend(block)
            self._state = block          # chain: state mới = hash vừa tính
        return bytes(out[:n])

    def next_int(self, bits: int) -> int:
        """Sinh số nguyên dương ngẫu nhiên có đúng `bits` bit."""
        byte_len   = (bits + 7) // 8
        raw        = self.next_bytes(byte_len)
        n          = int.from_bytes(raw, 'big')
        # Đảm bảo đủ `bits` bit: set MSB = 1
        n         |= (1 << (bits - 1))
        # Đảm bảo số lẻ (dễ tìm số nguyên tố)
        n         |= 1
        return n


# ══════════════════════════════════════════════════════════════════════════
# Kiểm tra nguyên tố — Miller-Rabin (deterministic witnesses)
# ══════════════════════════════════════════════════════════════════════════

def _miller_rabin(n: int, witnesses: list) -> bool:
    """
    Kiểm tra n có phải số nguyên tố bằng Miller-Rabin.
    Với witnesses xác định, kết quả là chính xác 100% cho n < 3.3×10²⁴.
    """
    if n < 2:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0:
        return False

    # Viết n-1 = 2^r × d
    r, d = 0, n - 1
    while d % 2 == 0:
        r += 1
        d //= 2

    for a in witnesses:
        if a >= n:
            continue
        x = pow(a, d, n)             # pow() built-in Python: modular exponentiation
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False             # n là hợp số
    return True                      # n nhiều khả năng là nguyên tố


# Witnesses đủ để quyết định chính xác với n < 3.3×10²⁴
_WITNESSES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]


def _is_prime(n: int) -> bool:
    """Kiểm tra số nguyên tố bằng Miller-Rabin với witnesses chuẩn."""
    return _miller_rabin(n, _WITNESSES)


# ══════════════════════════════════════════════════════════════════════════
# Thuật toán Euclid mở rộng — tính nghịch đảo modular
# ══════════════════════════════════════════════════════════════════════════

def _extended_gcd(a: int, b: int):
    """
    Thuật toán Euclid mở rộng.
    Trả về (gcd, x, y) sao cho: a*x + b*y = gcd(a, b)
    """
    if b == 0:
        return a, 1, 0
    g, x, y = _extended_gcd(b, a % b)
    return g, y, x - (a // b) * y


def _mod_inverse(e: int, phi: int) -> int:
    """
    Tính d sao cho e*d ≡ 1 (mod phi).
    Dùng thuật toán Euclid mở rộng.
    """
    g, x, _ = _extended_gcd(e % phi, phi)
    if g != 1:
        raise ValueError(f"Không tồn tại nghịch đảo: gcd({e},{phi}) = {g}")
    return x % phi


# ══════════════════════════════════════════════════════════════════════════
# Sinh khóa RSA
# ══════════════════════════════════════════════════════════════════════════

def generate_rsa_keypair(bits: int = 512, seed: bytes = _RSA_SEED):
    """
    Sinh cặp khóa RSA.

    Quy trình (theo giáo trình Bai8):
        1. Sinh 2 số nguyên tố lớn p, q (mỗi cái bits/2 bit)
        2. n  = p × q           (modulus)
        3. φ(n) = (p-1)(q-1)   (Euler's totient)
        4. Chọn e = 65537       (số nguyên tố Fermat — chuẩn thực tế)
        5. d = e⁻¹ mod φ(n)    (khóa riêng, dùng Euclid mở rộng)

    Returns:
        public_key  = (e, n)
        private_key = (d, n)
    """
    prng     = _SHA256PRNG(seed)
    half     = bits // 2

    # Tìm p
    while True:
        candidate = prng.next_int(half)
        if _is_prime(candidate):
            p = candidate
            break

    # Tìm q ≠ p
    while True:
        candidate = prng.next_int(half)
        if _is_prime(candidate) and candidate != p:
            q = candidate
            break

    n   = p * q
    phi = (p - 1) * (q - 1)
    e   = 65537                          # số nguyên tố Fermat phổ biến

    # Đảm bảo gcd(e, phi) = 1
    g, _, _ = _extended_gcd(e, phi)
    if g != 1:
        # Hiếm xảy ra — thử lại (đơn giản hoá cho bài học)
        e = 3
        g, _, _ = _extended_gcd(e, phi)
        assert g == 1, "Không tìm được e hợp lệ"

    d = _mod_inverse(e, phi)

    return (e, n), (d, n)


# ══════════════════════════════════════════════════════════════════════════
# Chữ ký số RSA-SHA256
# (Theo giáo trình Bai10.pdf — cách tiếp cận RSA)
# ══════════════════════════════════════════════════════════════════════════

def sign(message: bytes, private_key: tuple) -> str:
    """
    Ký thông điệp bằng khóa riêng RSA.

    Quy trình (từ giáo trình Bai10):
        1. hash  = SHA-256(message)          → 32 byte = 256 bit
        2. h_int = int.from_bytes(hash, 'big')
        3. sig   = h_int^d mod n             (mã hoá bằng private key)

    Returns:
        Chữ ký dưới dạng chuỗi hex.
    """
    d, n = private_key

    if n.bit_length() < 257:
        raise ValueError(
            f"n ({n.bit_length()} bit) phải lớn hơn 256 bit để ký SHA-256 hash."
        )

    hash_bytes = sha256(message)                        # 32 byte
    h_int      = int.from_bytes(hash_bytes, 'big')     # 256-bit số nguyên
    sig_int    = pow(h_int, d, n)                       # sig = H^d mod n
    return hex(sig_int)[2:]                             # chuỗi hex, bỏ "0x"


def verify(message: bytes, signature_hex: str, public_key: tuple) -> bool:
    """
    Xác minh chữ ký bằng khóa công khai RSA.

    Quy trình:
        1. h_int_recv = sig^e mod n          (giải mã bằng public key)
        2. hash_calc  = SHA-256(message)
        3. h_int_calc = int.from_bytes(hash_calc, 'big')
        4. Hợp lệ nếu h_int_recv == h_int_calc
    """
    e, n = public_key
    try:
        sig_int    = int(signature_hex, 16)
        h_recv     = pow(sig_int, e, n)                # H' = sig^e mod n
        hash_bytes = sha256(message)
        h_calc     = int.from_bytes(hash_bytes, 'big')
        return h_recv == h_calc
    except (ValueError, TypeError):
        return False


# ══════════════════════════════════════════════════════════════════════════
# Keys mặc định cho project (sinh 1 lần, dùng lại)
# Seed = tên sinh viên → deterministic, không cần os.urandom
# ══════════════════════════════════════════════════════════════════════════

# Sinh key 1 lần khi module load — kết quả luôn giống nhau với cùng seed
_PUBLIC_KEY, _PRIVATE_KEY = generate_rsa_keypair(bits=512, seed=_RSA_SEED)


def get_public_key():
    """Trả về public key (e, n) của project."""
    return _PUBLIC_KEY


def get_private_key():
    """Trả về private key (d, n) của project."""
    return _PRIVATE_KEY


# ══════════════════════════════════════════════════════════════════════════
# Demo / self-test
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=== RSA Demo ===")
    print("Generating RSA-512 keys (deterministic from project seed)...")

    pub, priv = generate_rsa_keypair(bits=512, seed=_RSA_SEED)
    e, n = pub
    d, _ = priv

    print(f"e (public exp)  : {e}")
    print(f"n (modulus, hex): {hex(n)[:40]}...")
    print("d (private exp) : [hidden - internal use only]")

    print("\n=== RSA-SHA256 Signature Demo ===")
    payload = b'{"payment_id":"PAY001","amount":185000.0}'
    print(f"Payload : {payload.decode()}")

    sig = sign(payload, priv)
    print(f"Signature (hex, first 40 chars): {sig[:40]}...")

    ok = verify(payload, sig, pub)
    print(f"Verify  : {'VALID' if ok else 'INVALID'}")

    tampered = payload + b"tamper"
    ok2 = verify(tampered, sig, pub)
    print(f"Verify (tampered): {'VALID' if ok2 else 'INVALID (expected)'}")

    assert ok and not ok2, "RSA signature self-test failed"
    print("\nSelf-test: PASS")
