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
```

### 5. Khởi tạo database

Chạy lần lượt trong PostgreSQL:

```sql
\i database/01_schema.sql
\i database/02_seed_demo_data.sql
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
   ├──main.py
   ├──db.py
   ├──routers/
   |   ├──auth.py
   |   ├──customer.py
   |   ├──staff.py
   |   ├──manager.py
   ├──services/
       ├── availability_service.py
       ├──order_service.py
       ├──payment_service.py


database/
   ├──01_schema.sql
   ├──02_seed_demo_data.sql


frontend/
   ├──index.html
   ├──js/
   ├──styles/
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
| PATCH | `/api/manager/orders/{order_id}/cancel` |
| PATCH | `/api/manager/orders/{order_id}/reschedule` |
| POST | `/api/manager/sql` |