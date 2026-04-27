# services/availability_service.py
"""
Tầng availability — 3 trách nhiệm độc lập:

    find_available_table()   →  §3.1 Interval Overlap Check
    find_available_staff()   →  §3.2 Sweep Line / Critical Points
    insert_failed_booking()  →  §3.3 Ghi lại yêu cầu thất bại

File này không import gì từ order_service hay payment_service
→ không có circular dependency.
Được gọi từ: order_service.create_reservation()
             manager.py  reschedule endpoint (nếu muốn re-check conflict)
"""

from datetime import datetime

MAX_TABLES_PER_STAFF = 3   # §1 — giới hạn nghiệp vụ cứng


# ══════════════════════════════════════════════════════════════════════════
# §3.1 — Interval Overlap Check: tìm bàn trống
# ══════════════════════════════════════════════════════════════════════════

def find_available_table(
    conn,
    new_start: datetime,
    new_end:   datetime,
) -> str | None:
    """
    Tìm 1 bàn KHÔNG có đơn active nào conflict với [new_start, new_end).

    Điều kiện conflict (§3.1):
        existing.ReservationTime  < new_end
        AND
        existing.EstimatedEndTime > new_start

    Chỉ xét đơn active (không tính 'đã hủy', 'đã thanh toán').
    Trả về TableID hoặc None nếu tất cả bàn đều bị chiếm.

    SQL dùng NOT EXISTS thay vì LEFT JOIN / IS NULL
    vì NOT EXISTS dừng ngay khi tìm thấy conflict đầu tiên — hiệu quả hơn.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT t.TableID
            FROM Table_ t
            WHERE NOT EXISTS (
                SELECT 1
                FROM Order_ o
                WHERE o.TableID      = t.TableID
                  AND o.OrderStatus NOT IN ('đã hủy', 'đã thanh toán')
                  AND o.ReservationTime  < %s    -- existing bắt đầu trước khi slot mới kết thúc
                  AND o.EstimatedEndTime > %s    -- existing kết thúc sau khi slot mới bắt đầu
            )
            LIMIT 1
            """,
            (new_end, new_start),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# §3.2 — Sweep Line: tính peak concurrent load của nhân viên
# ══════════════════════════════════════════════════════════════════════════

def _peak_concurrent_load(
    overlapping_orders: list[tuple],
    new_start:          datetime,
    new_end:            datetime,
) -> int:
    """
    Private helper — tính peak concurrent tại các critical points.

    overlapping_orders: list of (ReservationTime, EstimatedEndTime)
                        — đã được lọc để chỉ gồm đơn overlap với [new_start, new_end)

    Thuật toán §3.2:
        Critical points = {new_start} ∪ {ReservationTime của đơn bắt đầu trong (new_start, new_end)}
        Tại mỗi critical point cp: count = số đơn có res_time <= cp < end_time
        peak = max(count) trên tất cả critical points

    Tại sao không dùng COUNT(overlap)?
        Ví dụ: A(15:00→17:30), B(15:00→17:30), C(18:00→20:30)
        Đơn mới 16:00→18:30 overlap với cả 3, nhưng tại bất kỳ điểm nào
        chỉ gặp tối đa A+B hoặc C — không bao giờ cả 3 cùng lúc.
        COUNT(overlap) = 3 → loại staff oan.
        Sweep line → peak = 2 → staff eligible.
    """
    # Bước 1: xây critical points
    critical_points = {new_start}
    for res_time, end_time in overlapping_orders:
        if new_start < res_time < new_end:
            critical_points.add(res_time)

    # Bước 2: đếm tại từng critical point
    peak = 0
    for cp in critical_points:
        count = sum(
            1 for res_time, end_time in overlapping_orders
            if res_time <= cp < end_time
        )
        peak = max(peak, count)

    return peak


def find_available_staff(
    conn,
    new_start: datetime,
    new_end:   datetime,
) -> str | None:
    """
    §3.2 + §2.5 — Chọn nhân viên Phục vụ có peak concurrent load thấp nhất.

    Với mỗi nhân viên:
        1. Query tất cả đơn active overlap với [new_start, new_end)
        2. Tính peak bằng sweep line
        3. Nếu peak + 1 <= MAX_TABLES_PER_STAFF → eligible

    Greedy: chọn người eligible có peak THẤP NHẤT (least-load-first).
    Nếu bằng peak, tie-break theo FIFO:
        - Nhân viên có thời điểm assign gần nhất CŨ hơn sẽ được ưu tiên.
        - Nếu vẫn bằng nhau, fallback theo StaffID tăng dần.
    Tại sao greedy đúng ở đây: §1 — 4 nhân viên × 3 = 12 capacity > 8 bàn.
    Bàn là bottleneck trước nhân viên → không cần tối ưu phức tạp hơn.

    Trả về StaffID hoặc None nếu tất cả đã đạt MAX.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT StaffID FROM Staff WHERE Role_ = 'Phục vụ' ORDER BY StaffID"
        )
        staff_ids = [r[0] for r in cur.fetchall()]

        best_staff_id  = None
        best_peak      = MAX_TABLES_PER_STAFF  # chỉ chọn nếu peak < MAX
        best_last_seen = datetime.max

        for staff_id in staff_ids:
            # Lấy các đơn active của nhân viên này overlap với slot mới
            cur.execute(
                """
                SELECT ReservationTime, EstimatedEndTime
                FROM Order_
                WHERE StaffID    = %s
                  AND OrderStatus NOT IN ('đã hủy', 'đã thanh toán')
                  AND ReservationTime  < %s
                  AND EstimatedEndTime > %s
                """,
                (staff_id, new_end, new_start),
            )
            overlapping = cur.fetchall()

            peak = _peak_concurrent_load(overlapping, new_start, new_end)
            if peak >= MAX_TABLES_PER_STAFF:
                continue

            # FIFO tie-break:
            # lấy mốc assign gần nhất của staff (ReservationTime lớn nhất).
            # Ai có mốc cũ hơn (nhỏ hơn) sẽ được ưu tiên nhận đơn tiếp theo.
            cur.execute(
                """
                SELECT MAX(ReservationTime)
                FROM Order_
                WHERE StaffID = %s
                """,
                (staff_id,),
            )
            last_assigned = cur.fetchone()[0]
            if last_assigned is None:
                # Chưa từng nhận đơn -> ưu tiên cao nhất theo FIFO (đứng đầu hàng đợi)
                last_assigned = datetime.min

            # 1) peak thấp hơn -> tốt hơn
            # 2) cùng peak -> ai nhận đơn lâu hơn (last_assigned nhỏ hơn) thắng
            # 3) cùng last_assigned -> StaffID nhỏ hơn thắng (ổn định)
            if (
                peak < best_peak
                or (peak == best_peak and last_assigned < best_last_seen)
                or (peak == best_peak and last_assigned == best_last_seen and (best_staff_id is None or staff_id < best_staff_id))
            ):
                best_peak      = peak
                best_last_seen = last_assigned
                best_staff_id  = staff_id

        return best_staff_id
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════════════════
# §3.3 — Ghi nhận yêu cầu đặt bàn thất bại
# ══════════════════════════════════════════════════════════════════════════

def insert_failed_booking(
    conn,
    customer_id:    str,
    requested_time: datetime,
) -> str:
    """
    Ghi FailedBooking khi hết bàn hoặc hết nhân viên.
    Không raise exception — đây là luồng bình thường, không phải lỗi.

    conn.commit() do caller (order_service) thực hiện,
    để đảm bảo FailedBooking và toàn bộ transaction commit cùng lúc.
    """
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM FailedBooking")
        count     = cur.fetchone()[0]
        failed_id = f"FB{str(count + 1).zfill(6)}"

        cur.execute(
            """
            INSERT INTO FailedBooking (FailedID, CustomerID, RequestedTime)
            VALUES (%s, %s, %s)
            """,
            (failed_id, customer_id, requested_time),
        )
        return failed_id
    finally:
        cur.close()

