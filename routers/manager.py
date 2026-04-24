# routers/manager.py

from fastapi import APIRouter, HTTPException
from db import get_conn

router = APIRouter()  # tạo nhóm router cho manager


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 1: Xem tất cả đơn hàng
# URL: GET /api/manager/orders
# URL: GET /api/manager/orders?status=đang xử lý  (có lọc)
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/orders")
def get_all_orders(status: str = None):  # status=None → không lọc, lấy tất cả
    conn = get_conn()   # mở kết nối DB
    cur  = conn.cursor()  # tạo cursor để chạy SQL

    try:
        if status:  # nếu có truyền ?status=... thì lọc
            cur.execute(
                """
                SELECT o.OrderID,       -- mã đơn
                       o.OrderDate,     -- ngày đặt
                       o.OrderStatus,   -- trạng thái đơn
                       o.TotalAmount,   -- tổng tiền
                       o.TableID,       -- bàn số mấy
                       c.FullName AS customer,  -- tên khách (lấy từ bảng Customer)
                       s.FullName AS staff      -- tên nhân viên (lấy từ bảng Staff)
                FROM Order_ o
                JOIN Customer c ON c.CustomerID = o.CustomerID  -- nối để lấy tên khách
                JOIN Staff    s ON s.StaffID    = o.StaffID     -- nối để lấy tên NV
                WHERE o.OrderStatus = %s        -- lọc theo trạng thái được truyền vào
                ORDER BY o.OrderDate DESC, o.OrderID DESC  -- mới nhất lên đầu
                """,
                (status,),  # giá trị điền vào %s
            )
        else:  # không có ?status thì lấy tất cả
            cur.execute(
                """
                SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount,
                       o.TableID, c.FullName AS customer, s.FullName AS staff
                FROM Order_ o
                JOIN Customer c ON c.CustomerID = o.CustomerID
                JOIN Staff    s ON s.StaffID    = o.StaffID
                ORDER BY o.OrderDate DESC, o.OrderID DESC
                """
                # không có WHERE → lấy hết
            )

        # cur.fetchall() = lấy tất cả dòng kết quả lên
        # dùng list comprehension để chuyển từng dòng (tuple) → dict
        return [
            {
                "order_id":      r[0],   # r[0] = cột 1 = OrderID
                "order_date":    str(r[1]),  # r[1] = OrderDate, str() để tránh lỗi JSON
                "status":        r[2],   # r[2] = OrderStatus
                "total":         float(r[3]) if r[3] else None,  # r[3] = TotalAmount, có thể NULL
                "table_id":      r[4],   # r[4] = TableID
                "customer_name": r[5],   # r[5] = FullName của Customer
                "staff_name":    r[6],   # r[6] = FullName của Staff
            }
            for r in cur.fetchall()  # loop qua từng dòng kết quả
        ]
    finally:
        cur.close()   # đóng cursor
        conn.close()  # đóng connection — dù có lỗi hay không


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 2: Doanh thu theo danh mục
# URL: GET /api/manager/revenue
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/revenue")
def get_revenue():
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            -- Dịch nghĩa câu SQL này:
            -- "Với mỗi danh mục món ăn, đếm số đơn và tính tổng doanh thu
            --  chỉ tính những đơn đã thanh toán"

            SELECT c.Category_name,               -- tên danh mục (Khai vị, Món chính...)
                   COUNT(DISTINCT o.OrderID) AS so_don,   -- đếm số đơn hàng (không trùng)
                   SUM(od.Subtotal)          AS doanh_thu  -- cộng tổng tiền các món
            FROM Category c
            -- nối Category → MenuItem (1 category có nhiều món)
            JOIN MenuItem    m  ON m.CategoryID  = c.CategoryID
            -- nối MenuItem → OrderDetail (1 món xuất hiện trong nhiều đơn)
            JOIN OrderDetail od ON od.MenuItemID = m.MenuItemID
            -- nối OrderDetail → Order_ (lấy trạng thái đơn)
            JOIN Order_      o  ON o.OrderID     = od.OrderID
            WHERE o.OrderStatus = 'đã thanh toán'  -- chỉ tính đơn đã trả tiền
            GROUP BY c.CategoryID, c.Category_name  -- gom nhóm theo danh mục
            ORDER BY doanh_thu DESC                  -- danh mục doanh thu cao nhất lên đầu
            """
        )
        rows = cur.fetchall()  # lấy tất cả dòng kết quả

        # tính tổng doanh thu bằng Python (cộng r[2] của tất cả dòng)
        total = sum(float(r[2]) for r in rows)

        return {
            "total_revenue": total,  # tổng doanh thu toàn bộ
            "by_category": [
                {
                    "category":  r[0],        # r[0] = Category_name
                    "so_don":    r[1],         # r[1] = COUNT(DISTINCT OrderID)
                    "doanh_thu": float(r[2]),  # r[2] = SUM(Subtotal)
                }
                for r in rows
            ],
        }
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 3: Hiệu suất nhân viên
# URL: GET /api/manager/staff-performance
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/staff-performance")
def get_staff_performance():
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            -- Dịch nghĩa câu SQL này:
            -- "Với mỗi nhân viên Phục vụ, đếm:
            --   - đang có bao nhiêu đơn chưa xong
            --   - đã hoàn thành bao nhiêu đơn
            --   - tổng cộng bao nhiêu đơn"

            SELECT s.StaffID,
                   s.FullName,
                   -- đếm đơn 'đang xử lý': nếu đúng trạng thái thì đếm, không thì bỏ qua
                   COUNT(CASE WHEN o.OrderStatus = 'đang xử lý' THEN 1 END) AS dang_xu_ly,
                   -- đếm đơn hoàn thành: gồm cả 'hoàn tất' và 'đã thanh toán'
                   COUNT(CASE WHEN o.OrderStatus IN ('hoàn tất', 'đã thanh toán') THEN 1 END) AS da_hoan_thanh,
                   -- đếm tổng tất cả đơn của nhân viên này
                   COUNT(o.OrderID) AS tong_don
            FROM Staff s
            -- LEFT JOIN: lấy cả nhân viên chưa có đơn nào (Order_ sẽ NULL)
            LEFT JOIN Order_ o ON o.StaffID = s.StaffID
            WHERE s.Role_ = 'Phục vụ'  -- chỉ lấy nhân viên Phục vụ, bỏ Quản lý
            GROUP BY s.StaffID, s.FullName  -- gom nhóm theo từng nhân viên
            ORDER BY da_hoan_thanh DESC, dang_xu_ly DESC  -- ai làm nhiều nhất lên đầu
            """
        )
        return [
            {
                "staff_id":      r[0],  # r[0] = StaffID
                "name":          r[1],  # r[1] = FullName
                "dang_xu_ly":    r[2],  # r[2] = số đơn đang xử lý
                "da_hoan_thanh": r[3],  # r[3] = số đơn đã xong
                "tong_don":      r[4],  # r[4] = tổng đơn
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()