# services/order_service.py
"""
Logic tạo đơn hàng:
    1. Tìm bàn trống
    2. Tìm nhân viên Phục vụ ít đơn nhất (load balancing)
    3. INSERT Order_ + OrderDetail
    4. Tính TotalAmount
    5. Cập nhật TableStatus → 'đang dùng'
"""

from datetime import date


def create_order(conn, customer_id: str, items: list) -> dict:
    cur = conn.cursor()

    try:
        # ── 1. Tìm bàn trống ──────────────────────────────────────────────
        cur.execute(
            "SELECT TableID FROM Table_ WHERE TableStatus = 'trống' LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Nhà hàng hiện không còn bàn trống")
        table_id = row[0]

        # ── 2. Tìm nhân viên Phục vụ ít đơn 'đang xử lý' nhất ───────────
        cur.execute(
            """
            SELECT s.StaffID
            FROM Staff s
            WHERE s.Role_ = 'Phục vụ'
            ORDER BY (
                SELECT COUNT(*) FROM Order_ o
                WHERE o.StaffID = s.StaffID
                  AND o.OrderStatus = 'đang xử lý'
            ) ASC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không có nhân viên phục vụ")
        staff_id = row[0]

        # ── 3. Sinh OrderID ───────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM Order_")
        count = cur.fetchone()[0]
        order_id = f"ORD{str(count + 1).zfill(3)}"

        # ── 4. INSERT Order_ ──────────────────────────────────────────────
        cur.execute(
            """
            INSERT INTO Order_ (OrderID, OrderDate, OrderStatus, TotalAmount, CustomerID, StaffID, TableID)
            VALUES (%s, %s, 'đang xử lý', NULL, %s, %s, %s)
            """,
            (order_id, date.today(), customer_id, staff_id, table_id),
        )

        # ── 5. INSERT OrderDetail + tính tổng ────────────────────────────
        total = 0.0
        for item in items:
            cur.execute(
                """
                SELECT Price FROM MenuItem
                WHERE MenuItemID = %s AND Availability_status = 'available'
                """,
                (item["menu_item_id"],),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Món {item['menu_item_id']} không tồn tại hoặc không available")

            unit_price = float(row[0])
            quantity   = item["quantity"]
            subtotal   = unit_price * quantity
            total     += subtotal

            cur.execute(
                """
                INSERT INTO OrderDetail (OrderID, MenuItemID, Quantity, Unit_price, Subtotal)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order_id, item["menu_item_id"], quantity, unit_price, subtotal),
            )

        # ── 6. Cập nhật TotalAmount ───────────────────────────────────────
        cur.execute(
            "UPDATE Order_ SET TotalAmount = %s WHERE OrderID = %s",
            (total, order_id),
        )

        # ── 7. Đánh dấu bàn đang dùng ────────────────────────────────────
        cur.execute(
            "UPDATE Table_ SET TableStatus = 'đang dùng' WHERE TableID = %s",
            (table_id,),
        )

        conn.commit()
        return {
            "order_id":       order_id,
            "staff_assigned": staff_id,
            "table_assigned": table_id,
            "total_amount":   total,
            "status":         "đang xử lý",
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
