"""
SHA-256 — Triển khai từ đầu, không dùng thư viện mật mã.
Theo đúng chuẩn FIPS 180-4.

Demo (project):
    payload = b'{"payment_id":"PAY001","amount":185000.0}'
    hash    = sha256_hex(payload)
"""

# ══════════════════════════════════════════════════════════════════════════
# Hằng số K[0..63]: 32 bit đầu của phần thập phân căn bậc 3
#                   của 64 số nguyên tố đầu tiên.
# ══════════════════════════════════════════════════════════════════════════
_K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

# Giá trị hash khởi tạo H[0..7]: 32 bit đầu của phần thập phân
# căn bậc 2 của 8 số nguyên tố đầu tiên.
_H0 = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]

_MASK32 = 0xFFFFFFFF


# ══════════════════════════════════════════════════════════════════════════
# Hàm hỗ trợ bit
# ══════════════════════════════════════════════════════════════════════════

def _rotr32(x: int, n: int) -> int:
    """Rotate right 32-bit integer x đi n vị trí."""
    return ((x >> n) | (x << (32 - n))) & _MASK32


def _ch(x: int, y: int, z: int) -> int:
    """Choose: nếu bit x=1 chọn y, ngược lại chọn z."""
    return ((x & y) ^ (~x & z)) & _MASK32


def _maj(x: int, y: int, z: int) -> int:
    """Majority: bit nào xuất hiện ≥ 2 lần."""
    return (x & y) ^ (x & z) ^ (y & z)


def _sigma0(x: int) -> int:
    """Σ₀(x) = ROTR²(x) ⊕ ROTR¹³(x) ⊕ ROTR²²(x)"""
    return _rotr32(x, 2) ^ _rotr32(x, 13) ^ _rotr32(x, 22)


def _sigma1(x: int) -> int:
    """Σ₁(x) = ROTR⁶(x) ⊕ ROTR¹¹(x) ⊕ ROTR²⁵(x)"""
    return _rotr32(x, 6) ^ _rotr32(x, 11) ^ _rotr32(x, 25)


def _gamma0(x: int) -> int:
    """σ₀(x) = ROTR⁷(x) ⊕ ROTR¹⁸(x) ⊕ SHR³(x)"""
    return _rotr32(x, 7) ^ _rotr32(x, 18) ^ (x >> 3)


def _gamma1(x: int) -> int:
    """σ₁(x) = ROTR¹⁷(x) ⊕ ROTR¹⁹(x) ⊕ SHR¹⁰(x)"""
    return _rotr32(x, 17) ^ _rotr32(x, 19) ^ (x >> 10)


# ══════════════════════════════════════════════════════════════════════════
# SHA-256 chính
# ══════════════════════════════════════════════════════════════════════════

def sha256(data: bytes) -> bytes:
    """
    Tính SHA-256 của data.

    Bước 1 — Pre-processing (padding):
        Gắn bit '1', đệm bit '0', gắn độ dài 64-bit big-endian.
        Kết quả: bội số của 512 bit (64 byte).

    Bước 2 — Xử lý từng chunk 512-bit:
        Mở rộng 16 word → 64 word (message schedule).
        64 vòng nén với a, b, c, d, e, f, g, h.

    Bước 3 — Tổng hợp kết quả 256-bit (32 byte).
    """
    # ── Bước 1: Padding ───────────────────────────────────
    msg        = bytearray(data)
    bit_length = len(data) * 8

    msg.append(0x80)                          # thêm bit '1' dưới dạng 0x80
    while len(msg) % 64 != 56:               # đệm 0x00 đến khi còn 8 byte cuối
        msg.append(0x00)

    # Gắn độ dài gốc (64-bit big-endian)
    for shift in range(56, -1, -8):
        msg.append((bit_length >> shift) & 0xFF)

    # ── Bước 2: Xử lý từng chunk ─────────────────────────
    h = list(_H0)                             # sao chép giá trị khởi tạo

    for base in range(0, len(msg), 64):
        chunk = msg[base: base + 64]

        # Message schedule W[0..63]
        w = []
        for i in range(16):
            w.append(
                (chunk[i*4]     << 24) |
                (chunk[i*4 + 1] << 16) |
                (chunk[i*4 + 2] <<  8) |
                 chunk[i*4 + 3]
            )
        for i in range(16, 64):
            s = (_gamma0(w[i-15]) + w[i-16] + _gamma1(w[i-2]) + w[i-7]) & _MASK32
            w.append(s)

        # Biến làm việc
        a, b, c, d, e, f, g, hh = h

        # 64 vòng nén
        for i in range(64):
            t1 = (hh + _sigma1(e) + _ch(e, f, g)  + _K[i] + w[i]) & _MASK32
            t2 = (_sigma0(a)      + _maj(a, b, c))                  & _MASK32
            hh = g;  g = f;  f = e
            e  = (d + t1) & _MASK32
            d  = c;  c = b;  b = a
            a  = (t1 + t2) & _MASK32

        # Cộng dồn vào hash hiện tại
        add = [a, b, c, d, e, f, g, hh]
        h   = [(h[i] + add[i]) & _MASK32 for i in range(8)]

    # ── Bước 3: Xuất 32 byte ─────────────────────────────
    out = bytearray()
    for word in h:
        for shift in range(24, -1, -8):
            out.append((word >> shift) & 0xFF)
    return bytes(out)


def sha256_hex(data: bytes) -> str:
    """Trả về hash SHA-256 dưới dạng chuỗi hex 64 ký tự."""
    return ''.join(f'{b:02x}' for b in sha256(data))


# ══════════════════════════════════════════════════════════════════════════
# Demo / self-test (chạy trực tiếp: python security/sha256.py)
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    # Vector kiểm tra chuẩn NIST
    assert sha256_hex(b'') == \
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    assert sha256_hex(b'abc') == \
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

    # Demo theo dữ liệu project
    plaintext = b'{"payment_id":"PAY001","amount":185000.0}'
    print("=== SHA-256 Demo ===")
    print(f"Input    : {plaintext.decode()}")
    print(f"SHA-256  : {sha256_hex(plaintext)}")
    print("Self-test: PASS")
