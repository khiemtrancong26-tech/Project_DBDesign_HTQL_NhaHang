"""
Auth router — login & register.

Password hashing & verification dùng `security.crypto`
(SHA-256 + salt, fallback plain-text cho seed data).
Phone lưu plain text (manager cần tra cứu liên hệ nhanh).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_conn
from security.auth_guard import create_access_token
from security.crypto import encrypt_text_aes, hash_password, verify_password

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str  # customer | staff | manager


class RegisterRequest(BaseModel):
    fullname: str
    phone: str
    username: str
    password: str


def _generate_customer_id(cur) -> str:
    cur.execute("SELECT COUNT(*) FROM Customer")
    count = cur.fetchone()[0]
    return f"C{str(count + 1).zfill(6)}"


def _is_staff_role(role_value: str | None) -> bool:
    normalized = " ".join((role_value or "").strip().split()).casefold()
    return normalized == "phục vụ"


def _is_manager_role(role_value: str | None) -> bool:
    normalized = " ".join((role_value or "").strip().split()).casefold()
    return normalized == "quản lý"


@router.post("/auth/login")
def login(req: LoginRequest):
    conn = get_conn()
    cur = conn.cursor()
    try:
        if req.role == "customer":
            cur.execute(
                "SELECT CustomerID, FullName, password FROM Customer WHERE username = %s",
                (req.username,),
            )
            row = cur.fetchone()
            if not row or not verify_password(req.password, req.username, row[2] or ""):
                raise HTTPException(status_code=401, detail="Sai username hoac password")

            token = create_access_token(user_id=row[0], role="customer")
            return {"id": row[0], "name": row[1], "role": "customer", "token": token}

        if req.role in {"staff", "manager"}:
            cur.execute(
                "SELECT StaffID, FullName, Role_, password FROM Staff WHERE username = %s",
                (req.username,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Sai username hoac password")

            staff_id, name, role_value, stored_pw = row
            if not verify_password(req.password, req.username, stored_pw or ""):
                raise HTTPException(status_code=401, detail="Sai username hoac password")

            if req.role == "staff" and not _is_staff_role(role_value):
                raise HTTPException(status_code=401, detail="Sai username hoac password")
            if req.role == "manager" and not _is_manager_role(role_value):
                raise HTTPException(status_code=401, detail="Sai username hoac password")

            token = create_access_token(user_id=staff_id, role=req.role)
            return {
                "id": staff_id,
                "name": name,
                "role": req.role,
                "actual_role": role_value,
                "token": token,
            }

        raise HTTPException(status_code=400, detail="Role khong hop le")
    finally:
        cur.close()
        conn.close()


@router.post("/auth/register")
def register(req: RegisterRequest):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM Customer WHERE username = %s", (req.username,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Username da duoc su dung")

        customer_id = _generate_customer_id(cur)
        secured_password = hash_password(req.password, req.username)
        encrypted_phone = encrypt_text_aes(req.phone)

        cur.execute(
            """
            INSERT INTO Customer (CustomerID, FullName, PhoneNumber, username, password)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (customer_id, req.fullname, encrypted_phone, req.username, secured_password),
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
