# routers/manager.py
"""
Manager router:
    GET /api/manager/orders             — Xem tất cả đơn
    GET /api/manager/revenue            — Doanh thu theo danh mục
    GET /api/manager/staff-performance  — Số đơn xử lý theo nhân viên
"""

from fastapi import APIRouter, HTTPException
from db import get_conn

router = APIRouter()


# ── GET /api/manager/orders ───────────────────────────────────────────────

@router.get("/manager/orders")
def get_all_orders(status: str = None):
    """
    Xem tất cả đơn hàng.
    Query param ?status=đang xử lý để lọc theo trạng thái.
    """
    conn = get_conn()
    cur  = conn.cursor()

    try:
        if status:
            cur.execute(
                """
                SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount,
                       o.TableID, c.FullName AS customer, s.FullName AS staff
                FROM Order_ o
                JOIN Customer c ON c.CustomerID = o.CustomerID
                JOIN Staff    s ON s.StaffID    = o.StaffID
                WHERE o.OrderStatus = %s
                ORDER BY o.OrderDate DESC, o.OrderID DESC
                """,
                (status,),
            )
        else:
            cur.execute(
                """
                SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount,
                       o.TableID, c.FullName AS customer, s.FullName AS staff
                FROM Order_ o
                JOIN Customer c ON c.CustomerID = o.CustomerID
                JOIN Staff    s ON s.StaffID    = o.StaffID
                ORDER BY o.OrderDate DESC, o.OrderID DESC
                """
            )

        return [
            {
                "order_id":      r[0],
                "order_date":    str(r[1]),
                "status":        r[2],
                "total":         float(r[3]) if r[3] else None,
                "table_id":      r[4],
                "customer_name": r[5],
                "staff_name":    r[6],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ── GET /api/manager/revenue ──────────────────────────────────────────────

@router.get("/manager/revenue")
def get_revenue():
    """
    Doanh thu theo danh mục món ăn.
    Chỉ tính các đơn đã thanh toán.
    """
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            SELECT c.Category_name,
                   COUNT(DISTINCT o.OrderID)  AS so_don,
                   SUM(od.Subtotal)           AS doanh_thu
            FROM Category c
            JOIN MenuItem    m  ON m.CategoryID  = c.CategoryID
            JOIN OrderDetail od ON od.MenuItemID = m.MenuItemID
            JOIN Order_      o  ON o.OrderID     = od.OrderID
            WHERE o.OrderStatus = 'đã thanh toán'
            GROUP BY c.CategoryID, c.Category_name
            ORDER BY doanh_thu DESC
            """
        )
        rows = cur.fetchall()

        total = sum(float(r[2]) for r in rows)

        return {
            "total_revenue": total,
            "by_category": [
                {
                    "category":   r[0],
                    "so_don":     r[1],
                    "doanh_thu":  float(r[2]),
                }
                for r in rows
            ],
        }
    finally:
        cur.close()
        conn.close()


# ── GET /api/manager/staff-performance ───────────────────────────────────

@router.get("/manager/staff-performance")
def get_staff_performance():
    """
    Hiệu suất từng nhân viên Phục vụ:
    số đơn đang xử lý + tổng đơn đã hoàn tất/thanh toán.
    """
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            """
            SELECT s.StaffID, s.FullName,
                   COUNT(CASE WHEN o.OrderStatus = 'đang xử lý' THEN 1 END) AS dang_xu_ly,
                   COUNT(CASE WHEN o.OrderStatus IN ('hoàn tất', 'đã thanh toán') THEN 1 END) AS da_hoan_thanh,
                   COUNT(o.OrderID) AS tong_don
            FROM Staff s
            LEFT JOIN Order_ o ON o.StaffID = s.StaffID
            WHERE s.Role_ = 'Phục vụ'
            GROUP BY s.StaffID, s.FullName
            ORDER BY da_hoan_thanh DESC, dang_xu_ly DESC
            """
        )
        return [
            {
                "staff_id":       r[0],
                "name":           r[1],
                "dang_xu_ly":     r[2],
                "da_hoan_thanh":  r[3],
                "tong_don":       r[4],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()
