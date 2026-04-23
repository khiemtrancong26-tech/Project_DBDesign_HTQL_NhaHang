# routers/customer.py
"""
Customer router:
    GET  /api/menu                          — Xem menu theo category
    POST /api/orders                        — Đặt món
    GET  /api/orders/customer/{customer_id} — Xem đơn của khách
    GET  /api/orders/{order_id}/invoice     — Xem hóa đơn chi tiết
    POST /api/payments                      — Thanh toán
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_conn
from services.order_service import create_order
from services.payment_service import create_payment

router = APIRouter()


# ── REQUEST MODELS ────────────────────────────────────────────────────────

class OrderItem(BaseModel):
    menu_item_id: str
    quantity: int


class CreateOrderRequest(BaseModel):
    customer_id: str
    items: list[OrderItem]


class PaymentRequest(BaseModel):
    order_id: str
    amount: float
    method: str   # 'tiền mặt' | 'thẻ' | 'chuyển khoản'


# ── GET /api/menu ─────────────────────────────────────────────────────────

@router.get("/menu")
def get_menu():
    """Trả về toàn bộ menu available, nhóm theo category."""
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
        rows = cur.fetchall()

        categories = {}
        for cat_id, cat_name, item_id, food_name, price in rows:
            if cat_id not in categories:
                categories[cat_id] = {"category_id": cat_id, "category_name": cat_name, "items": []}
            categories[cat_id]["items"].append({
                "menu_item_id": item_id,
                "food_name":    food_name,
                "price":        float(price),
            })

        return list(categories.values())

    finally:
        cur.close()
        conn.close()


# ── POST /api/orders ──────────────────────────────────────────────────────

@router.post("/orders")
def place_order(req: CreateOrderRequest):
    """Tạo đơn mới — hệ thống tự phân công NV và bàn."""
    if not req.items:
        raise HTTPException(status_code=400, detail="Đơn hàng phải có ít nhất 1 món")

    conn = get_conn()
    try:
        items = [{"menu_item_id": i.menu_item_id, "quantity": i.quantity} for i in req.items]
        return create_order(conn, req.customer_id, items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── GET /api/orders/customer/{customer_id} ────────────────────────────────

@router.get("/orders/customer/{customer_id}")
def get_customer_orders(customer_id: str):
    """Xem tất cả đơn hàng của 1 khách, mới nhất trước."""
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            SELECT o.OrderID, o.OrderDate, o.OrderStatus,
                   o.TotalAmount, o.TableID, s.FullName AS staff_name
            FROM Order_ o
            JOIN Staff s ON s.StaffID = o.StaffID
            WHERE o.CustomerID = %s
            ORDER BY o.OrderDate DESC, o.OrderID DESC
            """,
            (customer_id,),
        )
        return [
            {
                "order_id":   r[0],
                "order_date": str(r[1]),
                "status":     r[2],
                "total":      float(r[3]) if r[3] else None,
                "table_id":   r[4],
                "staff_name": r[5],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ── GET /api/orders/{order_id}/invoice ───────────────────────────────────

@router.get("/orders/{order_id}/invoice")
def get_invoice(order_id: str):
    """Hóa đơn chi tiết: thông tin đơn + danh sách món."""
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount,
                   o.TableID, c.FullName, s.FullName
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
            "order_id":      row[0],
            "order_date":    str(row[1]),
            "status":        row[2],
            "total_amount":  float(row[3]) if row[3] else None,
            "table_id":      row[4],
            "customer_name": row[5],
            "staff_name":    row[6],
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


# ── POST /api/payments ────────────────────────────────────────────────────

@router.post("/payments")
def pay(req: PaymentRequest):
    """Thanh toán đơn hàng — tự động giải phóng bàn."""
    conn = get_conn()
    try:
        return create_payment(conn, req.order_id, req.amount, req.method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
