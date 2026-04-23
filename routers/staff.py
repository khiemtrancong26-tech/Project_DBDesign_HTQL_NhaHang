# routers/staff.py
"""
Staff router:
    GET   /api/staff/{staff_id}/orders      — Xem đơn được phân công
    PATCH /api/orders/{order_id}/status     — Cập nhật trạng thái đơn
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_conn

router = APIRouter()

VALID_STATUSES = {"đang xử lý", "hoàn tất", "đã hủy"}


class UpdateStatusRequest(BaseModel):
    status: str


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
            SELECT o.OrderID, o.OrderDate, o.OrderStatus,
                   o.TotalAmount, o.TableID, c.FullName AS customer_name
            FROM Order_ o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            WHERE o.StaffID = %s
            ORDER BY
                CASE o.OrderStatus
                    WHEN 'đang xử lý' THEN 1
                    WHEN 'hoàn tất'   THEN 2
                    ELSE 3
                END,
                o.OrderDate DESC
            """,
            (staff_id,),
        )
        return [
            {
                "order_id":      r[0],
                "order_date":    str(r[1]),
                "status":        r[2],
                "total":         float(r[3]) if r[3] else None,
                "table_id":      r[4],
                "customer_name": r[5],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ── PATCH /api/orders/{order_id}/status ──────────────────────────────────

@router.patch("/orders/{order_id}/status")
def update_order_status(order_id: str, req: UpdateStatusRequest):
    """
    Nhân viên cập nhật trạng thái đơn.
    Chỉ cho phép chuyển sang: 'hoàn tất' hoặc 'đã hủy'.
    Trạng thái 'đã thanh toán' chỉ được set qua /api/payments.
    """
    if req.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Trạng thái không hợp lệ. Chỉ chấp nhận: {VALID_STATUSES}",
        )
    if req.status == "đã thanh toán":
        raise HTTPException(
            status_code=400,
            detail="Dùng endpoint /api/payments để thanh toán",
        )

    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            "SELECT OrderStatus FROM Order_ WHERE OrderID = %s",
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
        if row[0] == "đã thanh toán":
            raise HTTPException(status_code=400, detail="Đơn đã thanh toán, không thể sửa")

        cur.execute(
            "UPDATE Order_ SET OrderStatus = %s WHERE OrderID = %s",
            (req.status, order_id),
        )
        conn.commit()

        return {"order_id": order_id, "status": req.status}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
