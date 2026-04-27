# services/payment_service.py
"""
Payment service — xử lý 2 loại thanh toán (§2.3, §4.5):

    'cọc'    →  30% TotalAmount, ghi DepositPaid
    'hoàn tất' →  TotalAmount − DepositPaid, cập nhật OrderStatus

RSA Digital Signature (§5.4) được đánh dấu placeholder —
sẽ được wire vào khi tích hợp security layer.
"""

from datetime import date

DEPOSIT_RATE = 0.30   # §2.3


def create_payment(
    conn,
    order_id:     str,
    amount:       float,
    method:       str,         # 'tiền mặt' | 'thẻ' | 'chuyển khoản'
    payment_type: str,         # 'cọc' | 'hoàn tất'
) -> dict:
    """
    Entry point — validate chung rồi dispatch theo payment_type.
    Mọi exception đều rollback trước khi raise lên router.
    """
    cur = conn.cursor()
    try:
        # ── Validate đơn hàng ─────────────────────────────────────────────
        cur.execute(
            """
            SELECT OrderStatus, TotalAmount, DepositPaid
            FROM Order_
            WHERE OrderID = %s
            """,
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Đơn hàng không tồn tại")

        status, total_amount, deposit_paid = row
        total_amount = float(total_amount or 0)
        deposit_paid = float(deposit_paid or 0)

        if status == "đã thanh toán":
            raise ValueError("Đơn hàng này đã được thanh toán trước đó")
        if status == "đã hủy":
            raise ValueError("Không thể thanh toán đơn đã hủy")
        if total_amount == 0:
            raise ValueError("Đơn chưa có món ăn nào, không thể thanh toán")
        if payment_type == "cọc" and (method or "").strip().lower() != "chuyển khoản":
            raise ValueError("Đặt cọc chỉ hỗ trợ phương thức chuyển khoản")

        # ── Sinh PaymentID ────────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM Payment")
        count      = cur.fetchone()[0]
        payment_id = f"PAY{str(count + 1).zfill(3)}"

        # ── Dispatch theo loại ────────────────────────────────────────────
        if payment_type == "cọc":
            return _process_deposit(
                cur, conn,
                order_id, payment_id, amount, method,
                total_amount, deposit_paid,
            )
        elif payment_type == "hoàn tất":
            if status != "hoàn tất":
                raise ValueError(
                    "Chỉ được thanh toán sau khi nhân viên xác nhận yêu cầu của bạn. "
                    "Vui lòng chờ nhân viên đến xác nhận."
                )
            return _process_final(
                cur, conn,
                order_id, payment_id, amount, method,
                total_amount, deposit_paid,
            )
        else:
            raise ValueError("payment_type phải là 'cọc' hoặc 'hoàn tất'")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# Thanh toán cọc
# ══════════════════════════════════════════════════════════════════════════

def _process_deposit(
    cur, conn,
    order_id, payment_id, amount, method,
    total_amount, deposit_paid,
) -> dict:
    """
    §2.3 — Cọc 30% tổng đơn khi pre-order.

    required_deposit  = TotalAmount × 30%
    remaining_deposit = required_deposit − DepositPaid đã trả
    amount phải đúng bằng remaining_deposit.

    Sau khi thanh toán: UPDATE Order_.DepositPaid += amount
    OrderStatus KHÔNG thay đổi — đơn vẫn 'đang xử lý'.
    """
    required_deposit  = round(total_amount * DEPOSIT_RATE, 2)
    remaining_deposit = round(required_deposit - deposit_paid, 2)

    if remaining_deposit <= 0:
        raise ValueError(
            f"Cọc đã được thanh toán đủ ({deposit_paid:,.0f}đ). "
            f"Không cần đóng thêm."
        )

    if round(amount, 2) != remaining_deposit:
        raise ValueError(
            f"Số tiền cọc không đúng. "
            f"Cần: {remaining_deposit:,.0f}đ "
            f"(30% × {total_amount:,.0f}đ − đã cọc {deposit_paid:,.0f}đ)"
        )

    # INSERT Payment (cọc)
    cur.execute(
        """
        INSERT INTO Payment
            (PaymentID, Amount, PaymentDate, PaymentMethod, PaymentStatus, PaymentType, OrderID)
        VALUES (%s, %s, %s, %s, 'thành công', 'cọc', %s)
        """,
        (payment_id, amount, date.today(), method, order_id),
    )

    # Cập nhật DepositPaid trên Order_
    cur.execute(
        "UPDATE Order_ SET DepositPaid = DepositPaid + %s WHERE OrderID = %s",
        (amount, order_id),
    )

    # ── §5.4 RSA Digital Signature — placeholder ──────────────────────────
    # Khi tích hợp security layer:
    #   payload   = _serialize_payment(payment_id, order_id, amount, method, 'cọc')
    #   signature = sign_data(payload)           # security/crypto.py
    #   cur.execute("UPDATE Payment SET Signature = %s WHERE PaymentID = %s",
    #               (signature, payment_id))
    # ─────────────────────────────────────────────────────────────────────

    conn.commit()

    return {
        "payment_id":       payment_id,
        "payment_type":     "cọc",
        "amount":           amount,
        "status":           "thành công",
        "deposit_paid":     deposit_paid + amount,
        "remaining_to_pay": round(total_amount - (deposit_paid + amount), 2),
        "note":             "Cọc thành công. Phần còn lại thanh toán khi hoàn tất bữa ăn.",
    }


# ══════════════════════════════════════════════════════════════════════════
# Thanh toán hoàn tất
# ══════════════════════════════════════════════════════════════════════════

def _process_final(
    cur, conn,
    order_id, payment_id, amount, method,
    total_amount, deposit_paid,
) -> dict:
    """
    §4.5 — Thanh toán hoàn tất.

    remaining = TotalAmount − DepositPaid
    amount phải đúng bằng remaining.

    Sau khi thanh toán:
        INSERT Payment (hoàn tất)
        UPDATE OrderStatus → 'đã thanh toán'

    UNIQUE(OrderID, PaymentType) trong schema v2.1 đảm bảo
    không thể INSERT 2 payment 'hoàn tất' cho cùng 1 đơn.
    """
    remaining = round(total_amount - deposit_paid, 2)
    if remaining < 0:
        remaining = 0.0

    if round(amount, 2) != remaining:
        raise ValueError(
            f"Số tiền không đúng. "
            f"Cần thanh toán: {remaining:,.0f}đ "
            f"(tổng {total_amount:,.0f}đ − cọc đã trả {deposit_paid:,.0f}đ)"
        )

    # INSERT Payment (hoàn tất)
    cur.execute(
        """
        INSERT INTO Payment
            (PaymentID, Amount, PaymentDate, PaymentMethod, PaymentStatus, PaymentType, OrderID)
        VALUES (%s, %s, %s, %s, 'thành công', 'hoàn tất', %s)
        """,
        (payment_id, amount, date.today(), method, order_id),
    )

    # Cập nhật trạng thái đơn
    cur.execute(
        "UPDATE Order_ SET OrderStatus = 'đã thanh toán' WHERE OrderID = %s",
        (order_id,),
    )

    # ── §5.4 RSA Digital Signature — placeholder ──────────────────────────
    # Khi tích hợp security layer:
    #   payload   = _serialize_payment(payment_id, order_id, amount, method, 'hoàn tất')
    #   signature = sign_data(payload)           # security/crypto.py
    #   cur.execute("UPDATE Payment SET Signature = %s WHERE PaymentID = %s",
    #               (signature, payment_id))
    # ─────────────────────────────────────────────────────────────────────

    conn.commit()

    return {
        "payment_id":   payment_id,
        "payment_type": "hoàn tất",
        "amount":       amount,
        "status":       "thành công",
        "total_amount": total_amount,
        "deposit_paid": deposit_paid,
        "order_status": "đã thanh toán",
    }


# ══════════════════════════════════════════════════════════════════════════
# Serialize payload để RSA sign — dùng khi tích hợp security layer
# ══════════════════════════════════════════════════════════════════════════

def _serialize_payment(
    payment_id:   str,
    order_id:     str,
    amount:       float,
    method:       str,
    payment_type: str,
) -> bytes:
    """
    Chuẩn hóa hoá đơn thành bytes để ký RSA (§5.4).

    sort_keys=True đảm bảo cùng input → cùng bytes → signature verify được.
    Hàm này được dùng ở 2 nơi:
        payment_service (khi ký)
        customer.py GET /payments/{id}/verify (khi verify lại)
    → Phải giữ format nhất quán tuyệt đối.
    """
    import json
    payload = {
        "payment_id":   payment_id,
        "order_id":     order_id,
        "amount":       amount,
        "payment_date": str(date.today()),
        "method":       method,
        "payment_type": payment_type,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

