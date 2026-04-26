# services/order_service.py
"""
Order service — lifecycle của đơn hàng.

    create_reservation()   →  §2.1, §2.2, §2.3, §3.1, §3.2, §3.3
    add_items_to_order()   →  §2.3 — khách hoặc nhân viên/manager thêm món
    reschedule_order()     →  §2.5 — manager đổi giờ
    cancel_order()         →  §2.4 — staff/manager hủy đơn
    _insert_order_details() →  private helper dùng chung

Gọi availability_service để tách biệt thuật toán khỏi order logic.
"""

from datetime import datetime, timedelta

from services.availability_service import (
    find_available_table,
    find_available_staff,
    insert_failed_booking,
)

BLOCK_MINUTES = 150    # §2.1 — 120 phút dùng bữa + 30 phút buffer
DEPOSIT_RATE  = 0.30   # §2.3 — cọc 30% tổng đơn khi pre-order

# §2.7 — State machine
# Statuses: đang xử lý → chờ thanh toán → hoàn tất → đã thanh toán
#           đang xử lý / chờ thanh toán / hoàn tất  → đã hủy
#
# Staff KHÔNG tự đánh dấu 'hoàn tất' — chỉ xác nhận payment request từ khách.
VALID_TRANSITIONS_STAFF = {
    "đang xử lý":      {"đã hủy"},   # staff chỉ được hủy (khi chưa cọc)
    "chờ thanh toán":  set(),         # confirm payment dùng endpoint riêng
    "hoàn tất":        set(),
}
VALID_TRANSITIONS_MANAGER = {
    "đang xử lý":      {"đã hủy"},
    "chờ thanh toán":  {"đã hủy"},
    "hoàn tất":        {"đã hủy"},
}


# ══════════════════════════════════════════════════════════════════════════
# create_reservation
# ══════════════════════════════════════════════════════════════════════════

def create_reservation(
    conn,
    customer_id:      str,
    reservation_time: datetime,
    items:            list[dict],   # [{"menu_item_id": "M006", "quantity": 2}]
                                    # có thể rỗng — §2.1: gọi món sau khi đến cũng được
    skip_deposit:     bool = False, # True khi manager tạo đơn thay khách — không cần deposit
) -> dict:
    """
    Luồng đầy đủ tạo đặt bàn:

        1. Check §2.2: khách chỉ có 1 order active
        2. Tính EstimatedEndTime = ReservationTime + 150 phút (§2.1)
        3. find_available_table() — §3.1 interval overlap
           → Hết bàn: INSERT FailedBooking, trả về thông báo (§3.3)
        4. find_available_staff() — §3.2 sweep line
           → Hết nhân viên: INSERT FailedBooking (rất hiếm — §1)
        5. INSERT Order_
        6. Nếu có items → INSERT OrderDetail + UPDATE TotalAmount
        7. Nếu có items và không skip_deposit và là pre-order → báo cần cọc 30% (§2.3)
        8. commit

    Trả về dict với key "success":
        True  → đặt bàn thành công
        False → hết bàn / hết nhân viên, đã ghi FailedBooking
    """
    estimated_end = reservation_time + timedelta(minutes=BLOCK_MINUTES)
    cur = conn.cursor()

    try:
        # ── 1. §2.2 — Kiểm tra 1 active order per customer ───────────────
        cur.execute(
            """
            SELECT OrderID FROM Order_
            WHERE CustomerID  = %s
              AND OrderStatus NOT IN ('đã thanh toán', 'đã hủy')
            """,
            (customer_id,),
        )
        if cur.fetchone():
            raise ValueError(
                "Bạn còn đơn đang active. Thanh toán hoặc hủy đơn cũ trước khi đặt mới."
            )

        # ── 2. §3.1 — Tìm bàn trống ──────────────────────────────────────
        table_id = find_available_table(conn, reservation_time, estimated_end)

        if not table_id:
            # §3.3 — Hết bàn: ghi FailedBooking, không raise exception
            failed_id = insert_failed_booking(conn, customer_id, reservation_time)
            conn.commit()
            return {
                "success":        False,
                "reason":         "Nhà hàng đã kín bàn vào giờ này. Chúng tôi sẽ liên hệ bạn để tư vấn.",
                "failed_id":      failed_id,
                "requested_time": reservation_time.isoformat(),
            }

        # ── 3. §3.2 — Tìm nhân viên (sweep line) ─────────────────────────
        staff_id = find_available_staff(conn, reservation_time, estimated_end)

        if not staff_id:
            # Rất hiếm theo §1 — bàn là bottleneck trước nhân viên
            failed_id = insert_failed_booking(conn, customer_id, reservation_time)
            conn.commit()
            return {
                "success":        False,
                "reason":         "Không còn nhân viên phục vụ vào giờ này. Chúng tôi sẽ liên hệ bạn để tư vấn.",
                "failed_id":      failed_id,
                "requested_time": reservation_time.isoformat(),
            }

        # ── 4. Sinh OrderID ───────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM Order_")
        count    = cur.fetchone()[0]
        order_id = f"ORD{str(count + 1).zfill(3)}"

        # ── 5. INSERT Order_ ──────────────────────────────────────────────
        cur.execute(
            """
            INSERT INTO Order_
                (OrderID, ReservationTime, EstimatedEndTime, OrderStatus,
                 TotalAmount, DepositPaid, CustomerID, StaffID, TableID)
            VALUES (%s, %s, %s, 'đang xử lý', NULL, 0, %s, %s, %s)
            """,
            (order_id, reservation_time, estimated_end, customer_id, staff_id, table_id),
        )

        # ── 6. INSERT OrderDetail nếu có items ───────────────────────────
        total = 0.0
        if items:
            total = _insert_order_details(cur, order_id, items)
            cur.execute(
                "UPDATE Order_ SET TotalAmount = %s WHERE OrderID = %s",
                (total, order_id),
            )

        # ── 7. §2.3 — Báo cần cọc nếu pre-order (chỉ cho khách, không cho manager) ───
        deposit_required = bool(items and total > 0 and not skip_deposit)
        deposit_amount   = round(total * DEPOSIT_RATE, 2) if deposit_required else 0.0

        conn.commit()

        result: dict = {
            "success":          True,
            "order_id":         order_id,
            "staff_assigned":   staff_id,
            "table_assigned":   table_id,
            "reservation_time": reservation_time.isoformat(),
            "estimated_end":    estimated_end.isoformat(),
            "status":           "đang xử lý",
            "total_amount":     total if items else None,
        }
        if deposit_required:
            result["deposit_required"] = True
            result["deposit_amount"]   = deposit_amount
            result["deposit_note"]     = (
                f"Vui lòng thanh toán cọc {deposit_amount:,.0f}đ "
                f"(30% tổng đơn) để xác nhận đặt bàn."
            )

        return result

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# add_items_to_order
# ══════════════════════════════════════════════════════════════════════════

def add_items_to_order(
    conn,
    order_id:    str,
    items:       list[dict],   # [{"menu_item_id": "M006", "quantity": 2}]
    customer_id: str  = None,  # Bắt buộc khi is_customer=True — để validate ownership
    is_customer: bool = True,  # False khi staff hoặc manager gọi
) -> dict:
    """
    Gọi thêm món vào đơn đang 'đang xử lý' (§2.3, §2.7).

    is_customer=True  (khách hàng):
        - Validate order.CustomerID == customer_id (ownership check)
        - Tính deposit nếu pre-order (ReservationTime > now())
    is_customer=False (staff / manager):
        - Không cần customer_id
        - Không bao giờ yêu cầu deposit

    1. Verify order tồn tại và đang 'đang xử lý'
    2. Nếu là khách: verify ownership
    3. INSERT OrderDetail (hoặc tăng Quantity nếu món đã có)
    4. Recalculate TotalAmount từ SUM(OrderDetail.Subtotal)
    5. Nếu là khách và pre-order: tính cọc còn thiếu
    """
    cur = conn.cursor()
    try:
        # ── 1. Verify order ───────────────────────────────────────────────
        cur.execute(
            """
            SELECT OrderStatus, ReservationTime, TotalAmount, DepositPaid, CustomerID
            FROM Order_
            WHERE OrderID = %s
            """,
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không tìm thấy đơn hàng")

        status, reservation_time, current_total, deposit_paid, order_customer_id = row
        deposit_paid = float(deposit_paid or 0)

        # §2.7 — Chỉ cho phép thêm món khi 'đang xử lý'
        # 'chờ thanh toán': khách đã yêu cầu thanh toán → không thêm được nữa
        # 'hoàn tất': staff đã xác nhận, chờ khách quét QR → không thêm được
        if status != "đang xử lý":
            if status == "chờ thanh toán":
                raise ValueError(
                    "Bạn đã gửi yêu cầu thanh toán. "
                    "Hủy yêu cầu trước nếu muốn gọi thêm món."
                )
            raise ValueError(
                f"Không thể thêm món vào đơn ở trạng thái '{status}'."
            )

        # ── 2. Ownership check (chỉ khách hàng) ──────────────────────────
        if is_customer:
            if customer_id is None:
                raise ValueError("Thiếu customer_id khi thêm món với vai trò khách hàng")
            if order_customer_id != customer_id:
                raise ValueError("Bạn không có quyền thêm món vào đơn này")

        # ── 3. INSERT / UPDATE OrderDetail ───────────────────────────────
        _insert_order_details(cur, order_id, items)

        # ── 4. Recalculate TotalAmount từ DB ─────────────────────────────
        cur.execute(
            "SELECT COALESCE(SUM(Subtotal), 0) FROM OrderDetail WHERE OrderID = %s",
            (order_id,),
        )
        new_total = float(cur.fetchone()[0])

        cur.execute(
            "UPDATE Order_ SET TotalAmount = %s WHERE OrderID = %s",
            (new_total, order_id),
        )

        # ── 5. §2.3 — Check pre-order deposit (chỉ cho khách) ────────────
        deposit_required   = False
        additional_deposit = 0.0

        if is_customer and new_total > 0:
            now          = datetime.now()
            is_pre_order = reservation_time > now
            if is_pre_order:
                required_total_deposit = round(new_total * DEPOSIT_RATE, 2)
                additional_deposit     = round(required_total_deposit - deposit_paid, 2)
                if additional_deposit > 0:
                    deposit_required = True

        conn.commit()

        result: dict = {
            "order_id":    order_id,
            "items_added": len(items),
            "new_total":   new_total,
            "new_status":  "đang xử lý",  # luôn là 'đang xử lý' sau khi thêm món
        }
        if deposit_required:
            result["deposit_required"]   = True
            result["deposit_amount"]     = additional_deposit
            result["deposit_note"]       = (
                f"Pre-order — cần bổ sung cọc {additional_deposit:,.0f}đ "
                f"(tổng cọc 30% = {round(new_total * DEPOSIT_RATE, 2):,.0f}đ, "
                f"đã trả {deposit_paid:,.0f}đ)"
            )

        return result

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# reschedule_order
# ══════════════════════════════════════════════════════════════════════════

def reschedule_order(
    conn,
    order_id:     str,
    new_time:     datetime,
) -> dict:
    """
    Manager đổi giờ đặt bàn (§2.5).

    Điều kiện:
        - Order phải ở trạng thái 'đang xử lý' (chưa phục vụ xong / chưa thanh toán)
        - Bàn hiện tại vẫn phải available trong khung giờ mới

    Nếu bàn bị conflict với khung giờ mới → raise ValueError,
    manager phải xử lý thủ công (đàm phán bàn khác với khách).
    """
    cur = conn.cursor()
    try:
        # ── 1. Lấy thông tin đơn hiện tại ────────────────────────────────
        cur.execute(
            """
            SELECT OrderStatus, TableID, ReservationTime, EstimatedEndTime
            FROM Order_
            WHERE OrderID = %s
            """,
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không tìm thấy đơn hàng")

        status, table_id, old_start, old_end = row

        # §2.5 — Chỉ reschedule khi 'đang xử lý'
        if status != "đang xử lý":
            raise ValueError(
                f"Chỉ có thể đổi giờ đơn đang 'đang xử lý', đơn này đang '{status}'"
            )

        new_end = new_time + timedelta(minutes=BLOCK_MINUTES)

        # ── 2. Re-check interval overlap cho bàn hiện tại ─────────────────
        # Loại trừ chính đơn này khỏi conflict check (không conflict với chính nó)
        cur.execute(
            """
            SELECT 1 FROM Order_
            WHERE TableID  = %s
              AND OrderID  != %s
              AND OrderStatus NOT IN ('đã hủy', 'đã thanh toán')
              AND ReservationTime  < %s
              AND EstimatedEndTime > %s
            LIMIT 1
            """,
            (table_id, order_id, new_end, new_time),
        )
        if cur.fetchone():
            raise ValueError(
                f"Bàn {table_id} đã có đặt chỗ trong khung giờ mới "
                f"({new_time} — {new_end}). Vui lòng chọn giờ khác."
            )

        # ── 3. Cập nhật thời gian ─────────────────────────────────────────
        cur.execute(
            """
            UPDATE Order_
            SET ReservationTime = %s, EstimatedEndTime = %s
            WHERE OrderID = %s
            """,
            (new_time, new_end, order_id),
        )

        conn.commit()

        return {
            "order_id":         order_id,
            "old_time":          old_start.isoformat() if old_start else None,
            "new_time":          new_time.isoformat(),
            "new_estimated_end": new_end.isoformat(),
        }

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# cancel_order
# ══════════════════════════════════════════════════════════════════════════

def cancel_order(
    conn,
    order_id:           str,
    cancelled_by_role:  str,  # 'staff' hoặc 'manager'
) -> dict:
    """
    Hủy đơn hàng (§2.4).

    Phân quyền:
        - staff   : chỉ hủy đơn 'đang xử lý' và chưa cọc (DepositPaid = 0)
        - manager : hủy đơn 'đang xử lý' hoặc 'hoàn tất', kể cả đã cọc

    Cọc không hoàn lại khi hủy.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT OrderStatus, DepositPaid FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không tìm thấy đơn hàng")

        status, deposit_paid = row
        deposit_paid = float(deposit_paid or 0)

        # ── Kiểm tra quyền hủy theo role ──────────────────────────────────
        if cancelled_by_role == "staff":
            if status != "đang xử lý":
                raise ValueError(
                    f"Nhân viên chỉ được hủy đơn 'đang xử lý', đơn này đang '{status}'"
                )
            if deposit_paid > 0:
                raise ValueError(
                    "Nhân viên không được hủy đơn đã cọc. Liên hệ quản lý để hủy."
                )
        elif cancelled_by_role == "manager":
            if status not in ("đang xử lý", "hoàn tất"):
                raise ValueError(
                    f"Không thể hủy đơn ở trạng thái '{status}'"
                )
        else:
            raise ValueError(f"Role '{cancelled_by_role}' không có quyền hủy đơn")

        # ── Cập nhật trạng thái ────────────────────────────────────────────
        cur.execute(
            "UPDATE Order_ SET OrderStatus = 'đã hủy' WHERE OrderID = %s",
            (order_id,),
        )

        conn.commit()

        result = {
            "order_id":        order_id,
            "status":          "đã hủy",
            "cancelled_by":    cancelled_by_role,
        }
        if deposit_paid > 0:
            result["deposit_forfeited"] = deposit_paid
            result["deposit_note"]      = (
                f"Cọc {deposit_paid:,.0f}đ không được hoàn lại do hủy sau khi đã đặt cọc."
            )

        return result

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# Private helper
# ══════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════
# request_payment / confirm_payment_request / cancel_payment_request
# ══════════════════════════════════════════════════════════════════════════

def request_payment(conn, order_id: str, customer_id: str) -> dict:
    """
    Khách yêu cầu thanh toán — gửi tín hiệu cho nhân viên.

    Điều kiện:
        - Order phải thuộc về customer_id
        - Status phải là 'đang xử lý' (chưa trong quá trình thanh toán)
        - Phải có ít nhất 1 món (TotalAmount > 0)

    → Status chuyển sang 'chờ thanh toán'.
    Nhân viên sẽ thấy thông báo và xác nhận trước khi khách thanh toán thật.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT OrderStatus, TotalAmount, CustomerID FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không tìm thấy đơn hàng")

        status, total, order_customer_id = row

        if order_customer_id != customer_id:
            raise ValueError("Bạn không có quyền thao tác trên đơn này")

        if status != "đang xử lý":
            raise ValueError(
                f"Chỉ yêu cầu thanh toán khi đơn đang 'đang xử lý', hiện tại: '{status}'"
            )

        if not total or float(total) <= 0:
            raise ValueError("Đơn chưa có món nào. Gọi món trước khi yêu cầu thanh toán.")

        cur.execute(
            "UPDATE Order_ SET OrderStatus = 'chờ thanh toán' WHERE OrderID = %s",
            (order_id,),
        )
        conn.commit()

        return {
            "order_id": order_id,
            "status":   "chờ thanh toán",
            "message":  "Đã gửi yêu cầu. Nhân viên sẽ đến xác nhận và bạn sẽ nhận được thông báo thanh toán.",
        }

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def cancel_payment_request(conn, order_id: str, customer_id: str) -> dict:
    """
    Khách hủy yêu cầu thanh toán — muốn gọi thêm món hoặc đổi ý.

    → Status revert về 'đang xử lý'.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT OrderStatus, CustomerID FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không tìm thấy đơn hàng")

        status, order_customer_id = row

        if order_customer_id != customer_id:
            raise ValueError("Bạn không có quyền thao tác trên đơn này")

        if status != "chờ thanh toán":
            raise ValueError(
                f"Không có yêu cầu thanh toán đang chờ (trạng thái hiện tại: '{status}')"
            )

        cur.execute(
            "UPDATE Order_ SET OrderStatus = 'đang xử lý' WHERE OrderID = %s",
            (order_id,),
        )
        conn.commit()

        return {
            "order_id": order_id,
            "status":   "đang xử lý",
            "message":  "Đã hủy yêu cầu thanh toán. Bạn có thể tiếp tục gọi món.",
        }

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def confirm_payment_request(conn, order_id: str, staff_id: str) -> dict:
    """
    Nhân viên xác nhận yêu cầu thanh toán của khách.

    Điều kiện:
        - Phải là nhân viên được phân công cho đơn này
        - Status phải là 'chờ thanh toán'

    → Status chuyển sang 'hoàn tất'.
    Khách sẽ thấy trạng thái đổi và được phép tiến hành thanh toán thật.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT OrderStatus, StaffID, TotalAmount FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Không tìm thấy đơn hàng")

        status, assigned_staff, total = row

        if assigned_staff != staff_id:
            raise ValueError("Bạn không phải nhân viên phụ trách đơn này")

        if status != "chờ thanh toán":
            raise ValueError(
                f"Đơn không ở trạng thái 'chờ thanh toán' (hiện tại: '{status}')"
            )

        cur.execute(
            "UPDATE Order_ SET OrderStatus = 'hoàn tất' WHERE OrderID = %s",
            (order_id,),
        )
        conn.commit()

        return {
            "order_id":    order_id,
            "status":      "hoàn tất",
            "total":       float(total) if total else 0,
            "message":     "Đã xác nhận. Khách có thể tiến hành thanh toán.",
        }

    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _insert_order_details(cur, order_id: str, items: list[dict]) -> float:
    """
    INSERT hoặc UPDATE OrderDetail cho từng món.

    Nếu món đã có trong đơn: tăng Quantity, giữ nguyên Unit_price gốc
    (giá khóa tại thời điểm gọi lần đầu — tránh thay đổi giá giữa chừng).

    Nếu món chưa có: INSERT với giá hiện tại từ MenuItem.

    Subtotal là GENERATED ALWAYS AS (Quantity * Unit_price) trong schema v2.1
    → không cần INSERT/UPDATE Subtotal thủ công — PostgreSQL tự tính.

    Trả về tổng subtotal của items vừa thêm (để caller tính deposit nếu cần).
    """
    added_subtotal = 0.0

    for item in items:
        menu_item_id = item["menu_item_id"]
        quantity     = item["quantity"]

        if quantity <= 0:
            raise ValueError(f"Quantity phải > 0, nhận được {quantity} cho món {menu_item_id}")

        # Kiểm tra món đã có trong đơn chưa
        cur.execute(
            """
            SELECT od.Quantity, od.Unit_price
            FROM OrderDetail od
            WHERE od.OrderID    = %s
              AND od.MenuItemID = %s
            """,
            (order_id, menu_item_id),
        )
        existing = cur.fetchone()

        if existing:
            # Món đã có → tăng Quantity, giữ Unit_price gốc
            existing_qty, unit_price = existing[0], float(existing[1])
            new_qty = existing_qty + quantity

            cur.execute(
                """
                UPDATE OrderDetail
                SET Quantity = %s
                WHERE OrderID = %s AND MenuItemID = %s
                """,
                (new_qty, order_id, menu_item_id),
            )
            added_subtotal += unit_price * quantity

        else:
            # Món mới → lấy giá hiện tại từ MenuItem
            cur.execute(
                """
                SELECT Price FROM MenuItem
                WHERE MenuItemID          = %s
                  AND Availability_status = 'available'
                """,
                (menu_item_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    f"Món {menu_item_id} không tồn tại hoặc hiện không available"
                )
            unit_price = float(row[0])

            cur.execute(
                """
                INSERT INTO OrderDetail (OrderID, MenuItemID, Quantity, Unit_price)
                VALUES (%s, %s, %s, %s)
                """,
                (order_id, menu_item_id, quantity, unit_price),
            )
            added_subtotal += unit_price * quantity

    return added_subtotal
