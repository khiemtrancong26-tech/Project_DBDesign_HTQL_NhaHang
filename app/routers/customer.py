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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db import get_conn
from security.auth_guard import authenticate_request, ensure_actor_matches
from app.services.order_service   import (
    create_reservation, add_items_to_order,
    request_payment as svc_request_payment,
    cancel_payment_request as svc_cancel_payment_request,
)
from app.services.payment_service import create_payment, serialize_payment
from security.crypto import verify_payment_sig

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
def make_reservation(req: CreateReservationRequest, request: Request):
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
    actor = authenticate_request(request, {"customer"})
    ensure_actor_matches(actor, req.customer_id, "customer_id")

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
def add_items(order_id: str, req: AddItemsRequest, request: Request):
    """
    Gọi thêm món vào đơn đang active — bất kỳ lúc nào (§2.3).
    Nếu đặt trước giờ đến và có pre-order, trả về deposit_amount cần bổ sung.
    """
    if not req.items:
        raise HTTPException(status_code=400, detail="Phải có ít nhất 1 món")

    items = [{"menu_item_id": i.menu_item_id, "quantity": i.quantity} for i in req.items]
    actor = authenticate_request(request, {"customer"})
    ensure_actor_matches(actor, req.customer_id, "customer_id")

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
def request_payment_endpoint(order_id: str, req: PaymentRequestAction, request: Request):
    """
    Khách hàng yêu cầu thanh toán → đổi status 'đang xử lý' → 'chờ thanh toán'.
    Nhân viên sẽ nhận thông báo và xác nhận trước khi khách thanh toán.
    """
    actor = authenticate_request(request, {"customer"})
    ensure_actor_matches(actor, req.customer_id, "customer_id")
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
def cancel_payment_request_endpoint(order_id: str, req: PaymentRequestAction, request: Request):
    """
    Khách hàng hủy yêu cầu thanh toán → đổi status 'chờ thanh toán' → 'đang xử lý'.
    """
    actor = authenticate_request(request, {"customer"})
    ensure_actor_matches(actor, req.customer_id, "customer_id")
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
def get_customer_orders(customer_id: str, request: Request):
    actor = authenticate_request(request, {"customer"})
    ensure_actor_matches(actor, customer_id, "customer_id")
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
def get_invoice(order_id: str, request: Request):
    actor = authenticate_request(request, {"customer"})
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT o.OrderID,
                   o.CustomerID,
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
        if row[1] != actor["uid"]:
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem hóa đơn này")

        order = {
            "order_id":         row[0],
            "reservation_time": row[2].isoformat() if row[2] else None,
            "estimated_end":    row[3].isoformat() if row[3] else None,
            "status":           row[4],
            "total_amount":     float(row[5]) if row[5] else None,
            "deposit_paid":     float(row[6]) if row[6] else 0.0,
            "table_id":         row[7],
            "customer_name":    row[8],
            "staff_name":       row[9],
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
def pay(req: PaymentRequest, request: Request):
    """
    Thanh toán cọc hoặc hoàn tất — §2.3, §4.5.
    payment_type: 'cọc' | 'hoàn tất'
    """
    actor = authenticate_request(request, {"customer"})
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT CustomerID FROM Order_ WHERE OrderID = %s", (req.order_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
        if row[0] != actor["uid"]:
            raise HTTPException(status_code=403, detail="Bạn không có quyền thanh toán đơn này")
        return create_payment(conn, req.order_id, req.amount, req.method, req.payment_type)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/payments/{payment_id}/verify   [NEW] — §5.4 verify RSA signature
# ═══════════════════════════════════════════════════════════════

@router.get("/payments/{payment_id}/verify")
def verify_payment(payment_id: str, request: Request):
    """
    Verify RSA digital signature của hoá đơn (§5.4).
    """
    actor = authenticate_request(request, {"customer", "manager"})
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT p.PaymentID, p.Amount, p.PaymentDate,
                   p.PaymentMethod, p.PaymentType, p.Signature, p.OrderID, o.CustomerID
            FROM Payment p
            JOIN Order_ o ON o.OrderID = p.OrderID
            WHERE p.PaymentID = %s
            """,
            (payment_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy thanh toán")

        payment_id_, amount, pay_date, method, pay_type, signature, order_id, owner_customer_id = row

        if actor["role"] == "customer" and actor["uid"] != owner_customer_id:
            raise HTTPException(status_code=403, detail="Bạn không có quyền verify hóa đơn này")

        if not signature:
            return {
                "payment_id": payment_id_,
                "verified":   False,
                "note":       "Hóa đơn này chưa có chữ ký số (bản ghi cũ trước tích hợp security).",
            }

        payload = serialize_payment(
            payment_id=payment_id_,
            order_id=order_id,
            amount=float(amount),
            method=method,
            payment_type=pay_type,
            payment_date=pay_date,
        )

        try:
            verified = bool(verify_payment_sig(payload, signature))
        except Exception:
            verified = False

        return {
            "payment_id": payment_id_,
            "verified":   verified,
            "note":       "Chữ ký RSA hợp lệ." if verified else "Chữ ký không hợp lệ hoặc dữ liệu đã bị thay đổi.",
        }
    finally:
        cur.close()
        conn.close()
