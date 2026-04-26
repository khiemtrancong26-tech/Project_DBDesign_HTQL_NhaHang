# routers/customer.py
"""
Customer router.

Thay đổi so với v1:
    - /api/orders   : gọi create_reservation() thay create_order() — [FIX 2]
                      request thêm trường reservation_time
    - /api/payments : gọi create_payment() với payment_type — [FIX 3]
    - GET orders    : OrderDate → ReservationTime — [FIX 1]
    - GET invoice   : OrderDate → ReservationTime — [FIX 1]
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_conn
from services.order_service   import (
    create_reservation, add_items_to_order,
    request_payment as svc_request_payment,
    cancel_payment_request as svc_cancel_payment_request,
)
from services.payment_service import create_payment

router = APIRouter()


# ── REQUEST MODELS ────────────────────────────────────────────────────────

class OrderItem(BaseModel):
    menu_item_id: str
    quantity:     int


class CreateReservationRequest(BaseModel):
    customer_id:      str
    reservation_time: str          # ISO string: "2025-08-01T18:30:00"
    items:            list[OrderItem] = []   # có thể rỗng — §2.1


class AddItemsRequest(BaseModel):
    customer_id: str       # Để validate ownership — §2.3
    items:       list[OrderItem]


class PaymentRequest(BaseModel):
    order_id:     str
    amount:       float
    method:       str              # 'tiền mặt' | 'thẻ' | 'chuyển khoản'
    payment_type: str              # [FIX 3] 'cọc' | 'hoàn tất'


class PaymentRequestAction(BaseModel):
    customer_id: str


# ═══════════════════════════════════════════════════════════════
# GET /api/menu
# ═══════════════════════════════════════════════════════════════

@router.get("/menu")
def get_menu():
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT c.CategoryID, c.Category_name,
                   m.MenuItemID, m.Food_name, m.Price
            FROM Category c
            JOIN MenuItem m ON m.CategoryID = c.CategoryID
            WHERE m.Availability_status = 'available'
            ORDER BY c.Category_name, m.Food_name
            """
        )
        categories = {}
        for cat_id, cat_name, item_id, food_name, price in cur.fetchall():
            if cat_id not in categories:
                categories[cat_id] = {
                    "category_id":   cat_id,
                    "category_name": cat_name,
                    "items":         [],
                }
            categories[cat_id]["items"].append({
                "menu_item_id": item_id,
                "food_name":    food_name,
                "price":        float(price),
            })
        return list(categories.values())
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# POST /api/reservations   [FIX 2] — thay thế POST /api/orders cũ
# ═══════════════════════════════════════════════════════════════

@router.post("/reservations")
def make_reservation(req: CreateReservationRequest):
    """
    Tạo đặt bàn — §2.1, §2.2, §2.3, §3.1, §3.2, §3.3.

    reservation_time: ISO string từ frontend datetime-local input.
    items: có thể rỗng (gọi món sau khi đến cũng được — §2.1).

    Trả về dict với key "success":
        True  → đặt thành công (+ deposit_required nếu pre-order)
        False → hết bàn/nhân viên, đã ghi FailedBooking
    """
    try:
        reservation_time = datetime.fromisoformat(req.reservation_time)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="reservation_time không hợp lệ. Dùng định dạng ISO: 2025-08-01T18:30:00",
        )

    items = [{"menu_item_id": i.menu_item_id, "quantity": i.quantity} for i in req.items]

    conn = get_conn()
    try:
        return create_reservation(conn, req.customer_id, reservation_time, items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# POST /api/orders/{order_id}/items   [NEW] — §2.3 gọi thêm món
# ═══════════════════════════════════════════════════════════════

@router.post("/orders/{order_id}/items")
def add_items(order_id: str, req: AddItemsRequest):
    """
    Gọi thêm món vào đơn đang active — bất kỳ lúc nào (§2.3).
    Nếu đặt trước giờ đến và có pre-order, trả về deposit_amount cần bổ sung.
    """
    if not req.items:
        raise HTTPException(status_code=400, detail="Phải có ít nhất 1 món")

    items = [{"menu_item_id": i.menu_item_id, "quantity": i.quantity} for i in req.items]

    conn = get_conn()
    try:
        return add_items_to_order(
            conn,
            order_id=order_id,
            items=items,
            customer_id=req.customer_id,
            is_customer=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# POST /api/orders/{order_id}/request-payment   [NEW] — §2.6
# ═══════════════════════════════════════════════════════════════

@router.post("/orders/{order_id}/request-payment")
def request_payment_endpoint(order_id: str, req: PaymentRequestAction):
    """
    Khách hàng yêu cầu thanh toán → đổi status 'đang xử lý' → 'chờ thanh toán'.
    Nhân viên sẽ nhận thông báo và xác nhận trước khi khách thanh toán.
    """
    conn = get_conn()
    try:
        return svc_request_payment(conn, order_id, req.customer_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# POST /api/orders/{order_id}/cancel-payment-request   [NEW] — §2.6
# ═══════════════════════════════════════════════════════════════

@router.post("/orders/{order_id}/cancel-payment-request")
def cancel_payment_request_endpoint(order_id: str, req: PaymentRequestAction):
    """
    Khách hàng hủy yêu cầu thanh toán → đổi status 'chờ thanh toán' → 'đang xử lý'.
    """
    conn = get_conn()
    try:
        return svc_cancel_payment_request(conn, order_id, req.customer_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/orders/customer/{customer_id}
# ═══════════════════════════════════════════════════════════════

@router.get("/orders/customer/{customer_id}")
def get_customer_orders(customer_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT o.OrderID,
                   o.ReservationTime,    -- [FIX 1] OrderDate → ReservationTime
                   o.EstimatedEndTime,
                   o.OrderStatus,
                   o.TotalAmount,
                   o.DepositPaid,
                   o.TableID,
                   s.FullName AS staff_name
            FROM Order_ o
            JOIN Staff s ON s.StaffID = o.StaffID
            WHERE o.CustomerID = %s
            ORDER BY o.ReservationTime DESC    -- [FIX 1]
            """,
            (customer_id,),
        )
        return [
            {
                "order_id":         r[0],
                "reservation_time": r[1].isoformat() if r[1] else None,
                "estimated_end":    r[2].isoformat() if r[2] else None,
                "status":           r[3],
                "total":            float(r[4]) if r[4] else None,
                "deposit_paid":     float(r[5]) if r[5] else 0.0,
                "table_id":         r[6],
                "staff_name":       r[7],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/orders/{order_id}/invoice
# ═══════════════════════════════════════════════════════════════

@router.get("/orders/{order_id}/invoice")
def get_invoice(order_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT o.OrderID,
                   o.ReservationTime,    -- [FIX 1] OrderDate → ReservationTime
                   o.EstimatedEndTime,
                   o.OrderStatus,
                   o.TotalAmount,
                   o.DepositPaid,
                   o.TableID,
                   c.FullName,
                   s.FullName
            FROM Order_ o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            JOIN Staff    s ON s.StaffID    = o.StaffID
            WHERE o.OrderID = %s
            """,
            (order_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")

        order = {
            "order_id":         row[0],
            "reservation_time": row[1].isoformat() if row[1] else None,
            "estimated_end":    row[2].isoformat() if row[2] else None,
            "status":           row[3],
            "total_amount":     float(row[4]) if row[4] else None,
            "deposit_paid":     float(row[5]) if row[5] else 0.0,
            "table_id":         row[6],
            "customer_name":    row[7],
            "staff_name":       row[8],
        }

        cur.execute(
            """
            SELECT m.Food_name, od.Quantity, od.Unit_price, od.Subtotal
            FROM OrderDetail od
            JOIN MenuItem m ON m.MenuItemID = od.MenuItemID
            WHERE od.OrderID = %s
            ORDER BY m.Food_name
            """,
            (order_id,),
        )
        items = [
            {
                "food_name":  r[0],
                "quantity":   r[1],
                "unit_price": float(r[2]),
                "subtotal":   float(r[3]),
            }
            for r in cur.fetchall()
        ]

        return {"order": order, "items": items}
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# POST /api/payments   [FIX 3] — thêm payment_type
# ═══════════════════════════════════════════════════════════════

@router.post("/payments")
def pay(req: PaymentRequest):
    """
    Thanh toán cọc hoặc hoàn tất — §2.3, §4.5.
    payment_type: 'cọc' | 'hoàn tất'
    """
    conn = get_conn()
    try:
        return create_payment(conn, req.order_id, req.amount, req.method, req.payment_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/payments/{payment_id}/verify   [NEW] — §5.4 verify RSA signature
# ═══════════════════════════════════════════════════════════════

@router.get("/payments/{payment_id}/verify")
def verify_payment(payment_id: str):
    """
    Verify RSA digital signature của hoá đơn (§5.4).
    Placeholder — sẽ wire vào crypto layer khi tích hợp security.
    """
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT p.PaymentID, p.Amount, p.PaymentDate,
                   p.PaymentMethod, p.PaymentType, p.Signature, p.OrderID
            FROM Payment p
            WHERE p.PaymentID = %s
            """,
            (payment_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy thanh toán")

        payment_id_, amount, pay_date, method, pay_type, signature, order_id = row

        if not signature:
            return {
                "payment_id": payment_id_,
                "verified":   False,
                "note":       "Chữ ký số chưa được gắn (security layer chưa tích hợp)",
            }

        # Khi wire security layer:
        # from services.payment_service import _serialize_payment
        # from security.crypto import verify_signature
        # payload  = _serialize_payment(payment_id_, order_id, float(amount), method, pay_type)
        # verified = verify_signature(payload, signature)
        # return {"payment_id": payment_id_, "verified": verified}

        return {
            "payment_id": payment_id_,
            "verified":   None,
            "note":       "Verify logic chưa được wire — signature tồn tại trong DB",
        }
    finally:
        cur.close()
        conn.close()