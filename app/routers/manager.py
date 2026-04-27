# routers/manager.py
"""
Manager router.

Thay đổi so với v1:
    - OrderDate → ReservationTime trong tất cả query — [FIX 1]
    - Thêm endpoints mới từ DESIGN_DECISIONS.md §6:
        GET  /api/manager/failed-bookings
        PATCH /api/manager/failed-bookings/{id}
        GET  /api/manager/audit-log
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_conn
from app.services.order_service import (
    create_reservation,
    reschedule_order,
    cancel_order,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# GET /api/manager/orders
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/orders")
def get_all_orders(status: str = None):
    conn = get_conn()
    cur  = conn.cursor()
    try:
        base_sql = """
            SELECT o.OrderID,
                   o.ReservationTime,    -- [FIX 1] OrderDate → ReservationTime
                   o.EstimatedEndTime,
                   o.OrderStatus,
                   o.TotalAmount,
                   o.DepositPaid,
                   o.TableID,
                   c.FullName AS customer,
                   s.FullName AS staff
            FROM Order_ o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            JOIN Staff    s ON s.StaffID    = o.StaffID
        """
        if status:
            cur.execute(
                base_sql + " WHERE o.OrderStatus = %s ORDER BY o.ReservationTime DESC, o.OrderID DESC",
                (status,),
            )
        else:
            cur.execute(base_sql + " ORDER BY o.ReservationTime DESC, o.OrderID DESC")

        return [
            {
                "order_id":         r[0],
                "reservation_time": r[1].isoformat() if r[1] else None,
                "estimated_end":    r[2].isoformat() if r[2] else None,
                "status":           r[3],
                "total":            float(r[4]) if r[4] else None,
                "deposit_paid":     float(r[5]) if r[5] else 0.0,
                "table_id":         r[6],
                "customer_name":    r[7],
                "staff_name":       r[8],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/manager/revenue
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/revenue")
def get_revenue():
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT c.Category_name,
                   COUNT(DISTINCT o.OrderID) AS so_don,
                   SUM(od.Subtotal)          AS doanh_thu
            FROM Category c
            JOIN MenuItem    m  ON m.CategoryID  = c.CategoryID
            JOIN OrderDetail od ON od.MenuItemID = m.MenuItemID
            JOIN Order_      o  ON o.OrderID     = od.OrderID
            WHERE o.OrderStatus = 'đã thanh toán'
            GROUP BY c.CategoryID, c.Category_name
            ORDER BY doanh_thu DESC
            """
        )
        rows  = cur.fetchall()
        total = sum(float(r[2]) for r in rows)
        return {
            "total_revenue": total,
            "by_category": [
                {
                    "category":  r[0],
                    "so_don":    r[1],
                    "doanh_thu": float(r[2]),
                }
                for r in rows
            ],
        }
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/manager/staff-performance
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/staff-performance")
def get_staff_performance():
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.StaffID,
                   s.FullName,
                   COUNT(CASE WHEN o.OrderStatus = 'đang xử lý' THEN 1 END)                        AS dang_xu_ly,
                   COUNT(CASE WHEN o.OrderStatus IN ('hoàn tất', 'đã thanh toán') THEN 1 END)      AS da_hoan_thanh,
                   COUNT(o.OrderID)                                                                  AS tong_don
            FROM Staff s
            LEFT JOIN Order_ o ON o.StaffID = s.StaffID
            WHERE s.Role_ = 'Phục vụ'
            GROUP BY s.StaffID, s.FullName
            ORDER BY da_hoan_thanh DESC, dang_xu_ly DESC
            """
        )
        return [
            {
                "staff_id":      r[0],
                "name":          r[1],
                "dang_xu_ly":    r[2],
                "da_hoan_thanh": r[3],
                "tong_don":      r[4],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/manager/failed-bookings   [NEW] — §6
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/failed-bookings")
def get_failed_bookings(contact_status: str = None):
    """
    Danh sách khách không đặt được bàn — §3.3, §6.
    Mặc định lấy tất cả, lọc theo contact_status nếu truyền vào.
    """
    conn = get_conn()
    cur  = conn.cursor()
    try:
        base_sql = """
            SELECT fb.FailedID, fb.RequestedTime, fb.CreatedAt,
                   fb.ContactStatus, fb.Note,
                   c.CustomerID, c.FullName
            FROM FailedBooking fb
            JOIN Customer c ON c.CustomerID = fb.CustomerID
        """
        if contact_status:
            cur.execute(
                base_sql + " WHERE fb.ContactStatus = %s ORDER BY fb.CreatedAt DESC",
                (contact_status,),
            )
        else:
            cur.execute(base_sql + " ORDER BY fb.ContactStatus ASC, fb.CreatedAt DESC")
            # ASC ContactStatus: 'chưa liên hệ' lên đầu (c < đ)

        return [
            {
                "failed_id":      r[0],
                "requested_time": r[1].isoformat() if r[1] else None,
                "created_at":     r[2].isoformat() if r[2] else None,
                "contact_status": r[3],
                "note":           r[4],
                "customer_id":    r[5],
                "customer_name":  r[6],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# PATCH /api/manager/failed-bookings/{failed_id}   [NEW] — §6
# ═══════════════════════════════════════════════════════════════

class UpdateFailedBookingRequest(BaseModel):
    contact_status: str   # 'chưa liên hệ' | 'đã liên hệ' | 'đã giải quyết'
    note:           str | None = None

VALID_CONTACT_STATUSES = {"chưa liên hệ", "đã liên hệ", "đã giải quyết"}

@router.patch("/manager/failed-bookings/{failed_id}")
def update_failed_booking(failed_id: str, req: UpdateFailedBookingRequest):
    """
    Manager cập nhật trạng thái liên hệ sau khi gọi điện cho khách.
    """
    if req.contact_status not in VALID_CONTACT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"contact_status không hợp lệ. Chỉ chấp nhận: {VALID_CONTACT_STATUSES}",
        )

    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT FailedID FROM FailedBooking WHERE FailedID = %s",
            (failed_id,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Không tìm thấy FailedBooking")

        cur.execute(
            """
            UPDATE FailedBooking
            SET ContactStatus = %s,
                Note          = COALESCE(%s, Note)   -- giữ note cũ nếu không truyền mới
            WHERE FailedID = %s
            """,
            (req.contact_status, req.note, failed_id),
        )
        conn.commit()

        return {"failed_id": failed_id, "contact_status": req.contact_status}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/manager/audit-log   [NEW] — §6
# ═══════════════════════════════════════════════════════════════

@router.get("/manager/audit-log")
def get_audit_log(
    actor_id:     str  = None,
    target_table: str  = None,
    limit:        int  = 50,
):
    """
    Xem audit trail — §4.4, §6.
    Có thể lọc theo actor_id hoặc target_table.
    limit mặc định 50, tối đa 200.
    """
    if limit > 200:
        limit = 200

    conn = get_conn()
    cur  = conn.cursor()
    try:
        conditions = []
        params     = []

        if actor_id:
            conditions.append("ActorID = %s")
            params.append(actor_id)
        if target_table:
            conditions.append("TargetTable = %s")
            params.append(target_table)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        cur.execute(
            f"""
            SELECT LogID, ActorID, ActorRole, Action,
                   TargetTable, TargetID, OldValue, NewValue, CreatedAt
            FROM AuditLog
            {where}
            ORDER BY CreatedAt DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "log_id":       r[0],
                "actor_id":     r[1],
                "actor_role":   r[2],
                "action":       r[3],
                "target_table": r[4],
                "target_id":    r[5],
                "old_value":    r[6],
                "new_value":    r[7],
                "created_at":   str(r[8]),
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
# GET /api/manager/contact   [NEW]
# Trả về thông tin liên lạc của quản lý — hiển thị cho khách
# khi họ muốn đổi giờ hoặc hủy bàn.
# ═══════════════════════════════════════════════════════════

@router.get("/manager/contact")
def get_manager_contact():
    """
    Khách hàng gọi endpoint này khi bấm nút "Đổi giờ / Hủy bàn".
    Trả về tên + SĐT của quản lý để khách liên hệ trực tiếp.
    Security note: PhoneNumber hiện plain text — khi tích hợp AES thì
    cần decrypt trước khi trả về (§5.2).
    """
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT FullName, PhoneNumber
            FROM Staff
            WHERE Role_ = 'Quản lý'
            LIMIT 1
            """,
        )
        row = cur.fetchone()
        if not row:
            return {"name": "Quản lý nhà hàng", "phone": "Liên hệ trực tiếp nhà hàng"}
        return {"name": row[0], "phone": row[1]}
    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
# POST /api/manager/reservations   [NEW] — §6
# Manager tạo đơn thay khách sau khi tư vấn FailedBooking
# ═══════════════════════════════════════════════════════════

class ManagerCreateReservationRequest(BaseModel):
    customer_id:      str
    reservation_time: str               # ISO format: "2025-12-25T19:00:00"
    items:            list[dict] = []   # có thể rỗng


@router.post("/manager/reservations")
def manager_create_reservation(req: ManagerCreateReservationRequest):
    """
    Manager tạo đơn thay khách sau khi đã tư vấn (§2.5, §3.3).

    - Không yêu cầu deposit dù có items (skip_deposit=True)
    - Vẫn dùng đầy đủ logic interval check + staff assignment
    """
    try:
        reservation_time = datetime.fromisoformat(req.reservation_time)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Định dạng reservation_time không hợp lệ. Dùng ISO format: 2025-12-25T19:00:00",
        )

    conn = get_conn()
    try:
        result = create_reservation(
            conn,
            customer_id=req.customer_id,
            reservation_time=reservation_time,
            items=req.items,
            skip_deposit=True,   # Manager tạo → không cần deposit
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# PATCH /api/manager/orders/{order_id}/reschedule   [NEW] — §6
# ═══════════════════════════════════════════════════════════

class RescheduleRequest(BaseModel):
    new_reservation_time: str   # ISO format


@router.patch("/manager/orders/{order_id}/reschedule")
def manager_reschedule(order_id: str, req: RescheduleRequest):
    """
    Manager đổi giờ đặt bàn (§2.5).

    Re-check interval overlap cho bàn hiện tại với khung giờ mới.
    Nếu bàn bị conflict → trả lỗi, manager phải xử lý thủ công.
    """
    try:
        new_time = datetime.fromisoformat(req.new_reservation_time)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Định dạng new_reservation_time không hợp lệ. Dùng ISO format.",
        )

    conn = get_conn()
    try:
        result = reschedule_order(conn, order_id=order_id, new_time=new_time)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# PATCH /api/manager/orders/{order_id}/cancel   [NEW] — §6
# ═══════════════════════════════════════════════════════════

@router.patch("/manager/orders/{order_id}/cancel")
def manager_cancel_order(order_id: str):
    """
    Manager hủy đơn — kể cả đơn đã cọc (§2.4).

    Cọc không hoàn lại. Response sẽ báo rõ số tiền cọc bị mất (nếu có).
    """
    conn = get_conn()
    try:
        result = cancel_order(conn, order_id=order_id, cancelled_by_role="manager")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# POST /api/manager/sql   [NEW]
# SQL Terminal — manager toàn quyền truy vấn và chỉnh sửa DB
# ═══════════════════════════════════════════════════════════

class SQLRequest(BaseModel):
    sql: str


@router.post("/manager/sql")
def run_sql(req: SQLRequest):
    """
    Chạy bất kỳ câu SQL nào — dành cho manager/dev (§0 DESIGN_DECISIONS).

    SELECT  → trả về columns + rows (dạng list of list)
    DML     → commit + trả về rowcount
    DDL     → commit (CREATE TABLE, ALTER TABLE,...)
    Error   → rollback + trả về 400 với message lỗi từ PostgreSQL

    Không có whitelist/blacklist — manager là người build hệ thống,
    có toàn quyền can thiệp DB khi cần (xử lý hủy bàn, sửa lịch, debug...).
    """
    if not req.sql.strip():
        raise HTTPException(status_code=400, detail="SQL không được rỗng")

    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(req.sql)

        if cur.description:
            # SELECT hoặc RETURNING — có kết quả trả về
            columns = [desc[0] for desc in cur.description]
            rows    = cur.fetchall()
            # Chuyển mỗi cell thành string để JSON serialize an toàn
            serialized = [
                [str(cell) if cell is not None else None for cell in row]
                for row in rows
            ]
            return {
                "type":     "select",
                "columns":  columns,
                "rows":     serialized,
                "rowcount": len(rows),
            }
        else:
            # DML / DDL — không có kết quả, chỉ có rowcount
            conn.commit()
            return {
                "type":     "dml",
                "rowcount": cur.rowcount if cur.rowcount >= 0 else 0,
                "message":  f"{max(cur.rowcount, 0)} row(s) affected",
            }

    except Exception as e:
        conn.rollback()
        # Trả nguyên văn lỗi PostgreSQL để manager debug được
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()
