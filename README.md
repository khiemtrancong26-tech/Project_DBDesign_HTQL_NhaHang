# Hệ Thống Quản Lý Nhà Hàng

Ứng dụng web quản lý nhà hàng với 3 vai trò: **Khách hàng**, **Nhân viên phục vụ**, **Quản lý**.
Backend dùng FastAPI + PostgreSQL, frontend thuần HTML/CSS/JS.

---

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Backend | FastAPI + Uvicorn |
| Database | PostgreSQL + psycopg2 |
| Frontend | HTML / CSS / JavaScript |
| Config | python-dotenv |

---

## Cài đặt

### Yêu cầu
- Python 3.11+
- PostgreSQL đang chạy

### 1. Clone repo

```bash
git clone https://github.com/khiemtrancong26-tech/Project_DBDesign_HTQL_NhaHang.git
cd Project_DBDesign_HTQL_NhaHang
```

### 2. Tạo và kích hoạt môi trường ảo

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Cài thư viện

```bash
pip install -r requirements.txt
```

### 4. Cấu hình `.env`

Tạo file `.env` ở thư mục gốc:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ten_database
DB_USER=postgres
DB_PASSWORD=mat_khau_cua_ban
APP_AUTH_SECRET=mot_chuoi_bi_mat_rat_dai
CORS_ALLOW_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

### 5. Khởi tạo database

Chạy lần lượt trong PostgreSQL:

```sql
\i database/01_schema.sql
\i database/02_seed_demo_data.sql
```

(Tuỳ chọn) Sau khi seed, chạy script bảo mật để hash mật khẩu seed và ký RSA cho Payment hiện có:

```bash
python database/secure_seed.py
```

---

## Chạy ứng dụng

```bash
uvicorn app.main:app --reload
```

Sau đó mở:

```text
http://localhost:8000
```

---

## Cấu trúc project

```text
app/
   ├── main.py
   ├── db.py
   ├── routers/
   │   ├── auth.py
   │   ├── customer.py
   │   ├── staff.py
   │   └── manager.py
   └── services/
       ├── availability_service.py
       ├── order_service.py
       └── payment_service.py

security/                        # Toàn bộ tầng bảo mật (tự cài, không dùng lib mật mã)
   ├── sha256.py
   ├── aes.py
   ├── rsa_impl.py
   ├── crypto.py                 # High-level API: hash/verify password, sign/verify payment
   └── auth_guard.py             # HMAC bearer token cho FastAPI

database/
   ├── 01_schema.sql
   ├── 02_seed_demo_data.sql
   └── secure_seed.py            # Migrate seed → hashed pwd + signed payments

frontend/
   ├── index.html
   ├── js/
   └── styles/
```

---

## Vai trò từng tầng

| Tầng | Vai trò |
|---|---|
| `frontend/` | Giao diện demo, gọi API, render dữ liệu |
| `app/routers/` | Nhận request, validate input cơ bản, gọi service |
| `app/services/` | Xử lý nghiệp vụ chính |
| `database/` | Schema, ràng buộc, dữ liệu mẫu |
| `app/db.py` | Kết nối PostgreSQL |
| `app/main.py` | Khởi động FastAPI app và serve frontend |

---

## Ghi chú bảo mật và kiến trúc

- `PhoneNumber` được lưu plain text theo chủ đích nghiệp vụ để quản lý tra cứu nhanh khi xử lý đổi giờ/hủy bàn.
- `POST /api/manager/sql` là endpoint toàn quyền (không sandbox). Chỉ dùng cho vai trò manager trong môi trường demo/dev.
- Một số mã định danh đang dùng chiến lược `COUNT(*) + 1` để sinh ID. Cách này phù hợp demo đơn luồng; không tối ưu cho môi trường concurrent cao.

---

## API endpoints chính

### Auth

| Method | Endpoint |
|---|---|
| POST | `/api/auth/login` |
| POST | `/api/auth/register` |

### Customer

| Method | Endpoint |
|---|---|
| GET | `/api/menu` |
| POST | `/api/reservations` |
| POST | `/api/orders/{order_id}/items` |
| GET | `/api/orders/customer/{customer_id}` |
| GET | `/api/orders/{order_id}/invoice` |
| GET | `/api/payments/{payment_id}/verify` |
| POST | `/api/orders/{order_id}/request-payment` |
| POST | `/api/orders/{order_id}/cancel-payment-request` |
| POST | `/api/payments` |

### Staff

| Method | Endpoint |
|---|---|
| GET | `/api/staff/{staff_id}/orders` |
| GET | `/api/staff/{staff_id}/orders/{order_id}/details` |
| POST | `/api/staff/orders/{order_id}/items` |
| POST | `/api/staff/orders/{order_id}/confirm-payment` |
| PATCH | `/api/orders/{order_id}/status` |

### Manager

| Method | Endpoint |
|---|---|
| GET | `/api/manager/orders` |
| GET | `/api/manager/revenue` |
| GET | `/api/manager/staff-performance` |
| GET | `/api/manager/failed-bookings` |
| PATCH | `/api/manager/failed-bookings/{failed_id}` |
| GET | `/api/manager/audit-log` |
| GET | `/api/manager/contact` |
| POST | `/api/manager/reservations` |
| PATCH | `/api/manager/orders/{order_id}/cancel` |
| PATCH | `/api/manager/orders/{order_id}/reschedule` |
| POST | `/api/manager/secure-seed` |
| POST | `/api/manager/sql` |
