# routers/auth.py
"""
Auth router — 2 endpoint:
    POST /api/login     — Khách hàng / Phục vụ / Quản lý đăng nhập
    POST /api/register  — Chỉ dành cho Khách hàng tự đăng ký
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_conn

router = APIRouter()


# ── REQUEST MODELS ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    role: str   # 'customer' | 'staff' | 'manager'


class RegisterRequest(BaseModel):
    fullname: str
    phone: str
    username: str
    password: str


# ── HELPER: SINH CUSTOMER ID ──────────────────────────────────────────────

def _generate_customer_id(cur) -> str:
    cur.execute("SELECT COUNT(*) FROM Customer")
    count = cur.fetchone()[0]
    return f"C{str(count + 1).zfill(6)}"


# ── POST /api/login ───────────────────────────────────────────────────────

@router.post("/login")
def login(req: LoginRequest):
    conn = get_conn()
    cur  = conn.cursor()

    try:
        if req.role == "customer":
            cur.execute(
                """
                SELECT CustomerID, FullName
                FROM Customer
                WHERE username = %s AND password = %s
                """,
                (req.username, req.password),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Sai username hoặc password")
            return {"id": row[0], "name": row[1], "role": "customer"}

        elif req.role == "staff":
            # Chỉ cho phép Role_ = 'Phục vụ'
            cur.execute(
                """
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

        elif req.role == "manager":
            # Chỉ cho phép Role_ = 'Quản lý'
            cur.execute(
                """
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
            raise HTTPException(status_code=400, detail="Role không hợp lệ")

    finally:
        cur.close()
        conn.close()


# ── POST /api/register ────────────────────────────────────────────────────

@router.post("/register")
def register(req: RegisterRequest):
    """Chỉ dành cho Khách hàng. Backend tự sinh CustomerID."""
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute(
            "SELECT 1 FROM Customer WHERE username = %s",
            (req.username,),
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Username đã được sử dụng")

        customer_id = _generate_customer_id(cur)

        cur.execute(
            """
            INSERT INTO Customer (CustomerID, FullName, PhoneNumber, username, password)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (customer_id, req.fullname, req.phone, req.username, req.password),
        )
        conn.commit()
        return {"customer_id": customer_id, "name": req.fullname}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()