# routers/auth.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import get_conn

router = APIRouter()


# ── REQUEST MODELS ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    role: str   # browser gửi lên: 'customer' | 'staff' | 'manager'
                # dùng để biết query bảng nào (Customer hay Staff)


class RegisterRequest(BaseModel):
    fullname: str
    phone: str
    username: str
    password: str
    # không có role vì chỉ customer mới tự đăng ký được


# ── HELPER: SINH CUSTOMER ID ──────────────────────────────────────────────

def _generate_customer_id(cur) -> str:
    # Dịch nghĩa: "đếm tổng số khách hàng hiện có"
    cur.execute("SELECT COUNT(*) FROM Customer")
    count = cur.fetchone()[0]   # lấy con số đếm được, ví dụ: 5
    return f"C{str(count + 1).zfill(6)}"
    # count+1 = 6 → zfill(6) = "000006" → "C000006"
    # Bug tiềm ẩn: nếu xóa khách thì COUNT giảm → có thể sinh ID trùng
    # Production nên dùng SERIAL hoặc UUID


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 1: Đăng nhập
# URL: POST /api/login
# ═══════════════════════════════════════════════════════════════

@router.post("/login")
def login(req: LoginRequest):
    conn = get_conn()
    cur  = conn.cursor()

    try:
        if req.role == "customer":
            cur.execute(
                """
                -- Dịch nghĩa:
                -- "Tìm khách hàng có đúng username VÀ password này"
                -- Nếu tìm thấy → đúng người → cho đăng nhập
                -- Nếu không → sai username hoặc sai password

                SELECT CustomerID, FullName
                FROM Customer
                WHERE username = %s AND password = %s
                """,
                (req.username, req.password),
            )
            row = cur.fetchone()  # 1 dòng hoặc None
            if not row:
                # không tìm thấy → trả 401 Unauthorized
                raise HTTPException(status_code=401, detail="Sai username hoặc password")
            # tìm thấy → trả thông tin về browser, lưu vào state.user
            return {"id": row[0], "name": row[1], "role": "customer"}

        elif req.role == "staff":
            cur.execute(
                """
                -- Dịch nghĩa:
                -- "Tìm nhân viên có đúng username, password VÀ phải là Phục vụ"
                -- Thêm điều kiện Role_ = 'Phục vụ' để:
                --   Quản lý không đăng nhập được vào màn hình Staff
                --   Tránh nhầm lẫn phân quyền

                SELECT StaffID, FullName, Role_
                FROM Staff
                WHERE username = %s AND password = %s AND Role_ = 'Phục vụ'
                """,
                (req.username, req.password),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Sai username hoặc password")
            return {"id": row[0], "name": row[1], "role": "staff", "actual_role": row[2]}
            # actual_role = row[2] = 'Phục vụ' — trả về để browser hiển thị

        elif req.role == "manager":
            cur.execute(
                """
                -- Dịch nghĩa:
                -- "Tìm nhân viên có đúng username, password VÀ phải là Quản lý"
                -- Nhân viên Phục vụ không đăng nhập được vào màn hình Manager

                SELECT StaffID, FullName, Role_
                FROM Staff
                WHERE username = %s AND password = %s AND Role_ = 'Quản lý'
                """,
                (req.username, req.password),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Sai username hoặc password")
            return {"id": row[0], "name": row[1], "role": "manager", "actual_role": row[2]}

        else:
            # role không phải customer/staff/manager → data sai
            raise HTTPException(status_code=400, detail="Role không hợp lệ")

    finally:
        cur.close()
        conn.close()


# ═══════════════════════════════════════════════════════════════
# ENDPOINT 2: Đăng ký
# URL: POST /api/register
# Chỉ dành cho khách hàng — staff/manager do admin tạo sẵn trong DB
# ═══════════════════════════════════════════════════════════════

@router.post("/register")
def register(req: RegisterRequest):
    conn = get_conn()
    cur  = conn.cursor()

    try:
        # ── BƯỚC 1: kiểm tra username đã tồn tại chưa ────────────────────
        cur.execute(
            """
            -- Dịch nghĩa:
            -- "Có dòng nào trong Customer có username này không?"
            -- SELECT 1 thay vì SELECT * vì chỉ cần biết có/không
            -- không cần lấy data thật

            SELECT 1 FROM Customer WHERE username = %s
            """,
            (req.username,),
        )
        if cur.fetchone():
            # fetchone() trả về (1,) nếu có, None nếu không
            # có rồi → báo lỗi, không cho đăng ký trùng
            raise HTTPException(status_code=400, detail="Username đã được sử dụng")

        # ── BƯỚC 2: sinh CustomerID mới ───────────────────────────────────
        customer_id = _generate_customer_id(cur)  # ví dụ: "C000006"

        # ── BƯỚC 3: INSERT khách hàng mới vào DB ─────────────────────────
        cur.execute(
            """
            -- Dịch nghĩa:
            -- "Thêm 1 dòng mới vào bảng Customer với thông tin vừa đăng ký"

            INSERT INTO Customer (CustomerID, FullName, PhoneNumber, username, password)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (customer_id, req.fullname, req.phone, req.username, req.password),
            # password lưu thẳng — demo đơn giản
            # production phải hash bằng bcrypt trước khi lưu
        )
        conn.commit()  # xác nhận lưu vào DB — thiếu dòng này thì INSERT không có hiệu lực

        return {"customer_id": customer_id, "name": req.fullname}

    except HTTPException:
        raise  # HTTPException tự mình ném ra → không bắt lại, ném tiếp lên
               # nếu không có dòng này thì except Exception bên dưới sẽ bắt mất

    except Exception as e:
        conn.rollback()  # có lỗi ngoài ý muốn → hủy INSERT, không lưu dữ liệu dở
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cur.close()
        conn.close()