# services/payment_service.py
"""
Logic thanh toán:
    1. Kiểm tra đơn hàng hợp lệ
    2. INSERT Payment
    3. Cập nhật OrderStatus → 'đã thanh toán'
    4. Giải phóng bàn → 'trống'
"""

from datetime import date


def create_payment(conn, order_id: str, amount: float, method: str) -> dict:
    cur = conn.cursor()

    try:
        # ── 1. Kiểm tra đơn hàng ─────────────────────────────────────────
        cur.execute(
            "SELECT OrderStatus, TableID FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Đơn hàng không tồn tại")

        order_status, table_id = row

        if order_status == "đã thanh toán":
            raise ValueError("Đơn hàng này đã được thanh toán trước đó")
        if order_status == "đã hủy":
            raise ValueError("Không thể thanh toán đơn đã hủy")

        # ── 2. Sinh PaymentID ─────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM Payment")
        count      = cur.fetchone()[0]
        payment_id = f"PAY{str(count + 1).zfill(3)}"

        # ── 3. INSERT Payment ─────────────────────────────────────────────
        cur.execute(
            """
            INSERT INTO Payment (PaymentID, Amount, PaymentDate, PaymentMethod, PaymentStatus, OrderID)
            VALUES (%s, %s, %s, %s, 'thành công', %s)
            """,
            (payment_id, amount, date.today(), method, order_id),
        )

        # ── 4. Cập nhật trạng thái đơn ───────────────────────────────────
        cur.execute(
            "UPDATE Order_ SET OrderStatus = 'đã thanh toán' WHERE OrderID = %s",
            (order_id,),
        )

        # ── 5. Giải phóng bàn ────────────────────────────────────────────
        cur.execute(
            "UPDATE Table_ SET TableStatus = 'trống' WHERE TableID = %s",
            (table_id,),
        )

        conn.commit()
        return {
            "payment_id":     payment_id,
            "status":         "thành công",
            "table_released": table_id,
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
