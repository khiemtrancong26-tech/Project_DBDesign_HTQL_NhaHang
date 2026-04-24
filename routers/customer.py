# routers/customer.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_conn
from services.order_service import create_order
from services.payment_service import create_payment

router = APIRouter()


# ── REQUEST MODELS ────────────────────────────────────────────────────────
# BaseModel = pydantic tự động parse JSON từ browser → object Python
# Nếu thiếu field hoặc sai kiểu → FastAPI tự trả lỗi 422, không cần tự kiểm

class OrderItem(BaseModel):
    menu_item_id: str   # mã món ăn, ví dụ "M006"
    quantity: int       # số lượng, ví dụ 2


class CreateOrderRequest(BaseModel):
    customer_id: str         # mã khách hàng, ví dụ "C000001"
    items: list[OrderItem]   # danh sách món đặt, ví dụ [{M006, 2}, {M020, 3}]


class PaymentRequest(BaseModel):
    order_id: str    # mã đơn cần thanh toán
    amount: float    # số tiền
    method: str      # hình thức: 'tiền mặt' | 'thẻ' | 'chuyển khoản'


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 1: Lấy menu
# URL: GET /api/menu
# ═══════════════════════════════════════════════════════════════

@router.get("/menu")
def get_menu():
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            -- Dịch nghĩa:
            -- "Lấy tất cả món ăn đang available, kèm tên danh mục của nó,
            --  sắp xếp theo tên danh mục rồi tên món"

            SELECT c.CategoryID,      -- mã danh mục (dùng làm key gom nhóm)
                   c.Category_name,   -- tên danh mục: Khai vị, Món chính...
                   m.MenuItemID,      -- mã món
                   m.Food_name,       -- tên món: Bò lúc lắc, Bia Heineken...
                   m.Price            -- giá
            FROM Category c
            JOIN MenuItem m ON m.CategoryID = c.CategoryID  -- nối để lấy món thuộc danh mục nào
            WHERE m.Availability_status = 'available'        -- chỉ lấy món đang bán, bỏ hết hàng
            ORDER BY c.Category_name, m.Food_name            -- sắp xếp A-Z theo danh mục rồi tên món
            """
        )
        rows = cur.fetchall()  # lấy tất cả dòng — mỗi dòng là 1 món kèm danh mục

        # Vấn đề: SQL trả về phẳng — mỗi dòng lặp lại tên danh mục
        # Ví dụ kết quả thô:
        # CAT001 | Khai vị | M001 | Gỏi cuốn | 45000
        # CAT001 | Khai vị | M002 | Chả giò  | 50000
        # CAT002 | Món chính | M006 | Bò lúc lắc | 185000

        # Giải pháp: dùng dict Python để gom nhóm theo CategoryID
        categories = {}
        for cat_id, cat_name, item_id, food_name, price in rows:
            if cat_id not in categories:
                # lần đầu gặp category này → tạo mới
                categories[cat_id] = {
                    "category_id":   cat_id,
                    "category_name": cat_name,
                    "items": []      # danh sách món sẽ được append dần
                }
            # thêm món vào đúng danh mục
            categories[cat_id]["items"].append({
                "menu_item_id": item_id,
                "food_name":    food_name,
                "price":        float(price),
            })

        # Kết quả trả về browser:
        # [
        #   { category_id: CAT001, category_name: Khai vị, items: [{M001,...}, {M002,...}] },
        #   { category_id: CAT002, category_name: Món chính, items: [{M006,...}, ...] },
        # ]
        return list(categories.values())

    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 2: Đặt hàng
# URL: POST /api/orders
# ═══════════════════════════════════════════════════════════════

@router.post("/orders")
def place_order(req: CreateOrderRequest):
    if not req.items:
        # kiểm tra đơn có ít nhất 1 món — không cần query DB
        raise HTTPException(status_code=400, detail="Đơn hàng phải có ít nhất 1 món")

    conn = get_conn()
    try:
        # chuyển list[OrderItem] (pydantic object) → list[dict] (Python thuần)
        # để truyền vào create_order trong order_service.py
        items = [{"menu_item_id": i.menu_item_id, "quantity": i.quantity} for i in req.items]

        # logic tạo đơn nằm trong order_service.py — không viết ở đây
        # lý do tách ra: router chỉ lo HTTP, service mới lo business logic
        return create_order(conn, req.customer_id, items)

    except ValueError as e:
        # ValueError do order_service ném ra — lỗi do data sai (hết bàn, món không có...)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # lỗi bất kỳ khác → lỗi server
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()  # không có cur.close() vì cur được tạo bên trong order_service


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 3: Xem đơn của khách
# URL: GET /api/orders/customer/{customer_id}
# ═══════════════════════════════════════════════════════════════

@router.get("/orders/customer/{customer_id}")
def get_customer_orders(customer_id: str):
    # {customer_id} trên URL → FastAPI tự lấy vào tham số customer_id
    # ví dụ: GET /api/orders/customer/C000001 → customer_id = "C000001"
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            -- Dịch nghĩa:
            -- "Lấy tất cả đơn hàng của khách này,
            --  kèm tên nhân viên phụ trách, mới nhất lên đầu"

            SELECT o.OrderID,       -- mã đơn
                   o.OrderDate,     -- ngày đặt
                   o.OrderStatus,   -- trạng thái: đang xử lý / hoàn tất / đã thanh toán / đã hủy
                   o.TotalAmount,   -- tổng tiền (có thể NULL nếu đơn đang xử lý dở)
                   o.TableID,       -- bàn số mấy
                   s.FullName AS staff_name  -- tên NV (lấy từ bảng Staff qua JOIN)
            FROM Order_ o
            JOIN Staff s ON s.StaffID = o.StaffID  -- nối để lấy tên NV thay vì chỉ có StaffID
            WHERE o.CustomerID = %s                 -- chỉ lấy đơn của khách này
            ORDER BY o.OrderDate DESC, o.OrderID DESC  -- mới nhất lên đầu
            """,
            (customer_id,),  # %s = customer_id truyền vào
        )
        return [
            {
                "order_id":   r[0],
                "order_date": str(r[1]),
                "status":     r[2],
                "total":      float(r[3]) if r[3] else None,  # TotalAmount có thể NULL
                "table_id":   r[4],
                "staff_name": r[5],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 4: Xem hóa đơn chi tiết
# URL: GET /api/orders/{order_id}/invoice
# ═══════════════════════════════════════════════════════════════

@router.get("/orders/{order_id}/invoice")
def get_invoice(order_id: str):
    conn = get_conn()
    cur  = conn.cursor()

    try:
        # ── QUERY 1: lấy thông tin chung của đơn ──────────────────────────
        cur.execute(
            """
            -- Dịch nghĩa:
            -- "Lấy thông tin đơn hàng này, kèm tên khách và tên nhân viên"

            SELECT o.OrderID,
                   o.OrderDate,
                   o.OrderStatus,
                   o.TotalAmount,
                   o.TableID,
                   c.FullName,   -- tên khách (JOIN Customer)
                   s.FullName    -- tên NV    (JOIN Staff)
            FROM Order_ o
            JOIN Customer c ON c.CustomerID = o.CustomerID  -- lấy tên khách
            JOIN Staff    s ON s.StaffID    = o.StaffID     -- lấy tên NV
            WHERE o.OrderID = %s                             -- đúng đơn này
            """,
            (order_id,),
        )
        row = cur.fetchone()  # chỉ có 1 đơn duy nhất → fetchone, không fetchall

        if not row:
            # không tìm thấy đơn → trả 404
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")

        # gom thông tin đơn vào dict
        order = {
            "order_id":      row[0],
            "order_date":    str(row[1]),
            "status":        row[2],
            "total_amount":  float(row[3]) if row[3] else None,
            "table_id":      row[4],
            "customer_name": row[5],  # row[5] = c.FullName
            "staff_name":    row[6],  # row[6] = s.FullName
        }

        # ── QUERY 2: lấy danh sách món trong đơn ─────────────────────────
        cur.execute(
            """
            -- Dịch nghĩa:
            -- "Lấy tất cả món trong đơn này,
            --  kèm tên món (từ MenuItem), số lượng, đơn giá, thành tiền"

            SELECT m.Food_name,    -- tên món: Bò lúc lắc, Bia Heineken...
                   od.Quantity,    -- số lượng đặt
                   od.Unit_price,  -- giá tại thời điểm đặt (khác MenuItem.Price nếu đã đổi giá)
                   od.Subtotal     -- thành tiền = Quantity × Unit_price
            FROM OrderDetail od
            JOIN MenuItem m ON m.MenuItemID = od.MenuItemID  -- nối để lấy tên món
            WHERE od.OrderID = %s   -- chỉ lấy món của đơn này
            ORDER BY m.Food_name    -- sắp xếp A-Z cho dễ đọc
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

        # trả về cả 2: thông tin đơn + danh sách món
        return {"order": order, "items": items}

    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 5: Thanh toán
# URL: POST /api/payments
# ═══════════════════════════════════════════════════════════════

@router.post("/payments")
def pay(req: PaymentRequest):
    conn = get_conn()
    try:
        # logic thanh toán nằm trong payment_service.py
        # gồm: kiểm tra đơn → INSERT Payment → UPDATE OrderStatus → giải phóng bàn
        return create_payment(conn, req.order_id, req.amount, req.method)

    except ValueError as e:
        # lỗi do data sai: đơn đã thanh toán rồi, đơn đã hủy...
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()