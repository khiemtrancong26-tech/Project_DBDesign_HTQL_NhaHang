"""
AES-128-CBC — Triển khai từ đầu, không dùng thư viện mật mã.
Theo đúng chuẩn FIPS 197 (AES) + NIST SP 800-38A (CBC mode).

Thông số:
    Key size  : 128 bit (16 byte)
    Block size: 128 bit (16 byte)
    Rounds    : 10

Demo (project):
    key       = b"KhiemTranCong\x00\x00\x00"
    plaintext = b"0901111001"
"""

# ══════════════════════════════════════════════════════════════════════════
# S-box (SubBytes) — Bảng thay thế phi tuyến (từ giáo trình Bai7.pdf)
# ══════════════════════════════════════════════════════════════════════════
_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]

# Inverse S-box — tính từ S-box (inv[SBOX[i]] = i)
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i

# Round constants cho KeyExpansion
_RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]


# ══════════════════════════════════════════════════════════════════════════
# GF(2⁸) — phép nhân trên trường Galois
# ══════════════════════════════════════════════════════════════════════════

def _xtime(a: int) -> int:
    """Nhân với 2 trong GF(2⁸), đa thức bất khả quy x⁸+x⁴+x³+x+1."""
    return ((a << 1) ^ 0x1b) & 0xff if (a & 0x80) else (a << 1) & 0xff


def _gmul(a: int, b: int) -> int:
    """Nhân a và b trong GF(2⁸) theo phương pháp Russian Peasant."""
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        high = a & 0x80
        a = (a << 1) & 0xff
        if high:
            a ^= 0x1b
        b >>= 1
    return p


# ══════════════════════════════════════════════════════════════════════════
# KeyExpansion — Mở rộng khóa 16 byte → 11 × 16 byte (11 round keys)
# ══════════════════════════════════════════════════════════════════════════

def _key_expansion(key: bytes) -> list:
    """
    Tạo 11 round keys từ key 16 byte.
    Mỗi round key là 1 list 16 byte.
    """
    assert len(key) == 16, "AES-128 yêu cầu key 16 byte"

    # 4 word đầu = key gốc
    w = []
    for i in range(4):
        w.append([key[4*i], key[4*i+1], key[4*i+2], key[4*i+3]])

    for i in range(4, 44):
        temp = list(w[i-1])
        if i % 4 == 0:
            # RotWord: xoay vòng [a,b,c,d] → [b,c,d,a]
            temp = [temp[1], temp[2], temp[3], temp[0]]
            # SubWord: áp dụng S-box cho từng byte
            temp = [_SBOX[b] for b in temp]
            # XOR với Rcon
            temp[0] ^= _RCON[i // 4 - 1]
        w.append([w[i-4][j] ^ temp[j] for j in range(4)])

    # Nhóm thành 11 round keys, mỗi key 16 byte
    round_keys = []
    for r in range(11):
        rk = []
        for col in range(4):
            rk.extend(w[r*4 + col])
        round_keys.append(rk)
    return round_keys


# ══════════════════════════════════════════════════════════════════════════
# Các phép biến đổi trên state 4×4 byte
# ══════════════════════════════════════════════════════════════════════════

def _sub_bytes(state: list) -> list:
    """SubBytes: thay từng byte qua S-box."""
    return [[_SBOX[state[r][c]] for c in range(4)] for r in range(4)]


def _inv_sub_bytes(state: list) -> list:
    """InvSubBytes: thay từng byte qua Inverse S-box."""
    return [[_INV_SBOX[state[r][c]] for c in range(4)] for r in range(4)]


def _shift_rows(state: list) -> list:
    """ShiftRows: dịch vòng trái hàng r đi r vị trí."""
    return [
        [state[0][0], state[0][1], state[0][2], state[0][3]],
        [state[1][1], state[1][2], state[1][3], state[1][0]],
        [state[2][2], state[2][3], state[2][0], state[2][1]],
        [state[3][3], state[3][0], state[3][1], state[3][2]],
    ]


def _inv_shift_rows(state: list) -> list:
    """InvShiftRows: dịch vòng phải hàng r đi r vị trí."""
    return [
        [state[0][0], state[0][1], state[0][2], state[0][3]],
        [state[1][3], state[1][0], state[1][1], state[1][2]],
        [state[2][2], state[2][3], state[2][0], state[2][1]],
        [state[3][1], state[3][2], state[3][3], state[3][0]],
    ]


def _mix_columns(state: list) -> list:
    """
    MixColumns: nhân mỗi cột với ma trận cố định trong GF(2⁸).
    Ma trận:  [2,3,1,1]
              [1,2,3,1]
              [1,1,2,3]
              [3,1,1,2]
    """
    result = [[0]*4 for _ in range(4)]
    for c in range(4):
        col = [state[r][c] for r in range(4)]
        result[0][c] = _gmul(2,col[0]) ^ _gmul(3,col[1]) ^ col[2]        ^ col[3]
        result[1][c] = col[0]          ^ _gmul(2,col[1]) ^ _gmul(3,col[2]) ^ col[3]
        result[2][c] = col[0]          ^ col[1]           ^ _gmul(2,col[2]) ^ _gmul(3,col[3])
        result[3][c] = _gmul(3,col[0]) ^ col[1]           ^ col[2]          ^ _gmul(2,col[3])
    return result


def _inv_mix_columns(state: list) -> list:
    """
    InvMixColumns: nhân mỗi cột với ma trận nghịch đảo trong GF(2⁸).
    Ma trận:  [14,11,13, 9]
              [ 9,14,11,13]
              [13, 9,14,11]
              [11,13, 9,14]
    """
    result = [[0]*4 for _ in range(4)]
    for c in range(4):
        col = [state[r][c] for r in range(4)]
        result[0][c] = _gmul(14,col[0]) ^ _gmul(11,col[1]) ^ _gmul(13,col[2]) ^ _gmul( 9,col[3])
        result[1][c] = _gmul( 9,col[0]) ^ _gmul(14,col[1]) ^ _gmul(11,col[2]) ^ _gmul(13,col[3])
        result[2][c] = _gmul(13,col[0]) ^ _gmul( 9,col[1]) ^ _gmul(14,col[2]) ^ _gmul(11,col[3])
        result[3][c] = _gmul(11,col[0]) ^ _gmul(13,col[1]) ^ _gmul( 9,col[2]) ^ _gmul(14,col[3])
    return result


def _add_round_key(state: list, rk: list) -> list:
    """AddRoundKey: XOR state với round key."""
    rk_state = _bytes_to_state(rk)
    return [[state[r][c] ^ rk_state[r][c] for c in range(4)] for r in range(4)]


# ══════════════════════════════════════════════════════════════════════════
# Chuyển đổi block ↔ state (ma trận 4×4)
# ══════════════════════════════════════════════════════════════════════════

def _bytes_to_state(block: list) -> list:
    """16 byte → ma trận 4×4 (cột-major theo AES spec)."""
    return [[block[r + 4*c] for c in range(4)] for r in range(4)]


def _state_to_bytes(state: list) -> bytes:
    """Ma trận 4×4 → 16 byte."""
    out = bytearray(16)
    for r in range(4):
        for c in range(4):
            out[r + 4*c] = state[r][c]
    return bytes(out)


# ══════════════════════════════════════════════════════════════════════════
# AES-128: mã hoá / giải mã 1 block 16 byte
# ══════════════════════════════════════════════════════════════════════════

def _aes_encrypt_block(block: bytes, round_keys: list) -> bytes:
    """Mã hoá 1 block 16 byte với AES-128 (10 vòng)."""
    state = _bytes_to_state(list(block))

    # Round 0: AddRoundKey với round key 0
    state = _add_round_key(state, round_keys[0])

    # Round 1..9: SubBytes → ShiftRows → MixColumns → AddRoundKey
    for r in range(1, 10):
        state = _sub_bytes(state)
        state = _shift_rows(state)
        state = _mix_columns(state)
        state = _add_round_key(state, round_keys[r])

    # Round 10 (cuối): không có MixColumns
    state = _sub_bytes(state)
    state = _shift_rows(state)
    state = _add_round_key(state, round_keys[10])

    return _state_to_bytes(state)


def _aes_decrypt_block(block: bytes, round_keys: list) -> bytes:
    """Giải mã 1 block 16 byte với AES-128 (10 vòng)."""
    state = _bytes_to_state(list(block))

    state = _add_round_key(state, round_keys[10])

    for r in range(9, 0, -1):
        state = _inv_shift_rows(state)
        state = _inv_sub_bytes(state)
        state = _add_round_key(state, round_keys[r])
        state = _inv_mix_columns(state)

    state = _inv_shift_rows(state)
    state = _inv_sub_bytes(state)
    state = _add_round_key(state, round_keys[0])

    return _state_to_bytes(state)


# ══════════════════════════════════════════════════════════════════════════
# Padding PKCS#7
# ══════════════════════════════════════════════════════════════════════════

def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """Thêm padding PKCS#7 để data là bội số của block_size."""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    """Bỏ padding PKCS#7."""
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Padding không hợp lệ")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Padding PKCS#7 bị lỗi")
    return data[:-pad_len]


# ══════════════════════════════════════════════════════════════════════════
# AES-128-CBC: mã hoá / giải mã dữ liệu tuỳ độ dài
# ══════════════════════════════════════════════════════════════════════════

def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR 2 byte string cùng độ dài."""
    return bytes(x ^ y for x, y in zip(a, b))


def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """
    Mã hoá plaintext bằng AES-128-CBC.

    Args:
        key      : 16 byte
        iv       : 16 byte (Initialization Vector)
        plaintext: dữ liệu cần mã hoá (bất kỳ độ dài)

    Returns:
        ciphertext (bytes) — đã bao gồm padding

    CBC flow (từ giáo trình Bai7.pdf):
        C₀ = E(P₀ XOR IV)
        Cᵢ = E(Pᵢ XOR Cᵢ₋₁)
    """
    round_keys = _key_expansion(key)
    padded     = _pkcs7_pad(plaintext)
    prev_block = iv
    ciphertext = bytearray()

    for i in range(0, len(padded), 16):
        block     = padded[i:i+16]
        xored     = _xor_bytes(block, prev_block)      # Pᵢ XOR Cᵢ₋₁
        encrypted = _aes_encrypt_block(xored, round_keys)
        ciphertext.extend(encrypted)
        prev_block = encrypted

    return bytes(ciphertext)


def aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """
    Giải mã ciphertext bằng AES-128-CBC.

    CBC giải mã:
        Pᵢ = D(Cᵢ) XOR Cᵢ₋₁
        P₀ = D(C₀) XOR IV
    """
    round_keys = _key_expansion(key)
    prev_block = iv
    plaintext  = bytearray()

    for i in range(0, len(ciphertext), 16):
        block     = ciphertext[i:i+16]
        decrypted = _aes_decrypt_block(block, round_keys)
        plaintext.extend(_xor_bytes(decrypted, prev_block))
        prev_block = block

    return _pkcs7_unpad(bytes(plaintext))


# ══════════════════════════════════════════════════════════════════════════
# Demo / self-test
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    # Key = tên sinh viên (padded 16 byte)
    KEY = b"KhiemTranCong\x00\x00\x00"
    # IV  = 16 byte cố định (demo)
    IV  = bytes([0x00] * 16)

    plaintext = b"0901111001"

    print("=== AES-128-CBC Demo ===")
    print(f"Key (hex)       : {KEY.hex()}")
    print(f"IV  (hex)       : {IV.hex()}")
    print(f"Plaintext       : {plaintext.decode()}")

    ct = aes_cbc_encrypt(KEY, IV, plaintext)
    print(f"Ciphertext (hex): {ct.hex()}")

    pt = aes_cbc_decrypt(KEY, IV, ct)
    print(f"Decrypted       : {pt.decode()}")

    assert pt == plaintext, "Decrypt thất bại!"
    print("Self-test: PASS")
