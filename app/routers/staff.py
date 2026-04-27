# routers/staff.py
"""
Staff router:
    GET   /api/staff/{staff_id}/orders           — Xem đơn được phân công
    GET   /api/staff/{staff_id}/orders/{order_id}/details
                                                — Xem chi tiết đơn theo quyền staff phụ trách
    PATCH /api/orders/{order_id}/status          — Cập nhật trạng thái đơn (state machine)
    POST  /api/staff/orders/{order_id}/items     — Staff thêm món tại bàn (không cần deposit)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_conn
from app.services.order_service import (
    add_items_to_order, VALID_TRANSITIONS_STAFF,
    confirm_payment_request as svc_confirm_payment,
)

router = APIRouter()


class UpdateStatusRequest(BaseModel):
    staff_id: str   # Staff phải tự khai báo ID để validate quyền
    status:   str


class AddItemsRequest(BaseModel):
    staff_id: str
    items:    list[dict]   # [{"menu_item_id": "M006", "quantity": 2}]


class ConfirmPaymentRequest(BaseModel):
    staff_id: str


def _build_staff_order_payload(row) -> dict:
    status = row[3]
    deposit_paid = float(row[5]) if row[5] else 0.0

    return {
        "order_id":            row[0],
        "reservation_time":    row[1].isoformat() if row[1] else None,
        "estimated_end":       row[2].isoformat() if row[2] else None,
        "status":              status,
        "total":               float(row[4]) if row[4] else None,
        "deposit_paid":        deposit_paid,
        "table_id":            row[6],
        "customer_name":       row[7],
        "item_count":          int(row[8]),
        "can_add_items":       status == "đang xử lý",
        "can_confirm_payment": status == "chờ thanh toán",
        "can_cancel":          status == "đang xử lý" and deposit_paid <= 0,
    }


def _get_staff_order_summary(cur, staff_id: str, order_id: str) -> dict | None:
    cur.execute(
        """
        SELECT o.OrderID,
               o.ReservationTime,
               o.EstimatedEndTime,
               o.OrderStatus,
               o.TotalAmount,
               o.DepositPaid,
               o.TableID,
               c.FullName AS customer_name,
               COALESCE(SUM(od.Quantity), 0) AS item_count
        FROM Order_ o
        JOIN Customer c ON c.CustomerID = o.CustomerID
        LEFT JOIN OrderDetail od ON od.OrderID = o.OrderID
        WHERE o.OrderID = %s
          AND o.StaffID = %s
        GROUP BY o.OrderID, o.ReservationTime, o.EstimatedEndTime,
                 o.OrderStatus, o.TotalAmount, o.DepositPaid,
                 o.TableID, c.FullName
        """,
        (order_id, staff_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return _build_staff_order_payload(row)


# ── GET /api/staff/{staff_id}/orders ─────────────────────────────────────

@router.get("/staff/{staff_id}/orders")
def get_staff_orders(staff_id: str):
    """
    Trả về đơn được phân công cho nhân viên này.
    Ưu tiên hiện 'đang xử lý' trước, sau đó 'hoàn tất'.
    """
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            SELECT o.OrderID,
                   o.ReservationTime,
                   o.EstimatedEndTime,
                   o.OrderStatus,
                   o.TotalAmount,
                   o.DepositPaid,
                   o.TableID,
                   c.FullName AS customer_name,
                   COALESCE(SUM(od.Quantity), 0) AS item_count
            FROM Order_ o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            LEFT JOIN OrderDetail od ON od.OrderID = o.OrderID
            WHERE o.StaffID = %s
            GROUP BY o.OrderID, o.ReservationTime, o.EstimatedEndTime,
                     o.OrderStatus, o.TotalAmount, o.DepositPaid, o.TableID, c.FullName
            ORDER BY
                CASE o.OrderStatus
                    WHEN 'chờ thanh toán' THEN 1
                    WHEN 'đang xử lý'     THEN 2
                    WHEN 'hoàn tất'       THEN 3
                    ELSE 4
                END,
                o.ReservationTime DESC
            """,
            (staff_id,),
        )
        return [_build_staff_order_payload(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


@router.get("/staff/{staff_id}/orders/{order_id}/details")
def get_staff_order_details(staff_id: str, order_id: str):
    """
    Chi tiết đơn hàng dành riêng cho staff phụ trách.

    Chỉ staff được phân công mới xem được detail của order này.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        summary = _get_staff_order_summary(cur, staff_id, order_id)
        if not summary:
            raise HTTPException(
                status_code=403,
                detail="Bạn không có quyền xem chi tiết đơn này hoặc đơn không tồn tại",
            )

        cur.execute(
            """
            SELECT od.MenuItemID,
                   m.Food_name,
                   od.Quantity,
                   od.Unit_price,
                   od.Subtotal
            FROM OrderDetail od
            JOIN MenuItem m ON m.MenuItemID = od.MenuItemID
            WHERE od.OrderID = %s
            ORDER BY m.Food_name
            """,
            (order_id,),
        )
        items = [
            {
                "menu_item_id": r[0],
                "food_name": r[1],
                "quantity": int(r[2]),
                "unit_price": float(r[3]),
                "subtotal": float(r[4]),
            }
            for r in cur.fetchall()
        ]

        return {"order": summary, "items": items}
    finally:
        cur.close()
        conn.close()


# ── PATCH /api/orders/{order_id}/status ──────────────────────────────────

@router.patch("/orders/{order_id}/status")
def update_order_status(order_id: str, req: UpdateStatusRequest):
    """
    Nhân viên cập nhật trạng thái đơn — có validate state machine (§2.7).

    Transition hợp lệ cho staff:
        đang xử lý → đã hủy   (chỉ khi chưa cọc)

    'hoàn tất' chỉ được set qua /api/staff/orders/{id}/confirm-payment.
    'đã thanh toán' chỉ được set qua /api/payments.
    """
    if req.status == "đã thanh toán":
        raise HTTPException(
            status_code=400,
            detail="Dùng endpoint /api/payments để thanh toán",
        )

    conn = get_conn()
    cur  = conn.cursor()

    try:
        # ── Lấy thông tin đơn + validate nhân viên phụ trách ─────────────
        cur.execute(
            "SELECT OrderStatus, StaffID, DepositPaid FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")

        current_status, assigned_staff_id, deposit_paid = row
        deposit_paid = float(deposit_paid or 0)

        # Chỉ nhân viên được phân công mới được cập nhật đơn này
        if assigned_staff_id != req.staff_id:
            raise HTTPException(
                status_code=403,
                detail="Bạn không phải nhân viên phụ trách đơn này",
            )

        # ── §2.7 — State machine validation ──────────────────────────────
        allowed = VALID_TRANSITIONS_STAFF.get(current_status, set())
        if req.status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Không thể chuyển từ '{current_status}' sang '{req.status}'. "
                    f"Transition hợp lệ: {allowed or 'không có'}"
                ),
            )

        # Staff không được hủy đơn đã cọc
        if req.status == "đã hủy" and deposit_paid > 0:
            raise HTTPException(
                status_code=403,
                detail="Không thể hủy đơn đã cọc. Liên hệ quản lý để hủy.",
            )

        cur.execute(
            "UPDATE Order_ SET OrderStatus = %s WHERE OrderID = %s",
            (req.status, order_id),
        )
        conn.commit()

        updated = _get_staff_order_summary(cur, req.staff_id, order_id)
        return {
            "order_id": order_id,
            "status": req.status,
            "message": "Cập nhật trạng thái thành công",
            "order": updated,
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── POST /api/staff/orders/{order_id}/items ──────────────────────────────

@router.post("/staff/orders/{order_id}/items")
def staff_add_items(order_id: str, req: AddItemsRequest):
    """
    Staff thêm món tại bàn cho khách (§2.3).

    - Phải là nhân viên được phân công cho đơn đó.
    - Chỉ thêm khi đơn đang 'đang xử lý'.
    - Không bao giờ yêu cầu deposit — staff không pre-order.
    """
    conn = get_conn()
    cur  = conn.cursor()

    try:
        # Validate nhân viên phụ trách
        cur.execute(
            "SELECT StaffID FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")

        if row[0] != req.staff_id:
            raise HTTPException(
                status_code=403,
                detail="Bạn không phải nhân viên phụ trách đơn này",
            )

        result = add_items_to_order(
            conn,
            order_id=order_id,
            items=req.items,
            is_customer=False,   # Staff → không tính deposit
        )
        updated = _get_staff_order_summary(cur, req.staff_id, order_id)
        return {
            "message": "Đã thêm món thành công",
            "result": result,
            "order": updated,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── POST /api/staff/orders/{order_id}/confirm-payment ────────────────────

@router.post("/staff/orders/{order_id}/confirm-payment")
def confirm_payment(order_id: str, req: ConfirmPaymentRequest):
    """
    Nhân viên xác nhận yêu cầu thanh toán của khách (§2.6).

    Chuyển status 'chờ thanh toán' → 'hoàn tất'.
    Sau đó khách mới được phép tiến hành thanh toán QR/thẻ/tiền mặt.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        result = svc_confirm_payment(conn, order_id, req.staff_id)
        updated = _get_staff_order_summary(cur, req.staff_id, order_id)
        return {
            **result,
            "order": updated,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

