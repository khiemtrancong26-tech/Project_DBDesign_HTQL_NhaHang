# He Thong Quan Ly Nha Hang

Ung dung web quan ly nha hang voi 3 vai tro: **Khach hang**, **Nhan vien phuc vu**, **Quan ly**.
Backend dung FastAPI + PostgreSQL, frontend thuan HTML/CSS/JS.

---

## Cong nghe

| Thanh phan | Cong nghe |
|---|---|
| Backend | FastAPI + Uvicorn |
| Database | PostgreSQL + psycopg2 |
| Frontend | HTML / CSS / JavaScript |
| Config | python-dotenv |

---

## Cai dat

### Yeu cau
- Python 3.11+
- PostgreSQL dang chay

### 1. Clone repo

```bash
git clone https://github.com/khiemtrancong26-tech/Project_DBDesign_HTQL_NhaHang.git
cd Project_DBDesign_HTQL_NhaHang
```

### 2. Tao va kich hoat moi truong ao

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Cai thu vien

```bash
pip install -r requirements.txt
```

### 4. Cau hinh `.env`

Tao file `.env` o thu muc goc:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ten_database
DB_USER=postgres
DB_PASSWORD=mat_khau_cua_ban
```

### 5. Khoi tao database

Chay lan luot trong PostgreSQL:

```sql
\i database/01_schema.sql
\i database/02_seed_demo_data.sql
```

---

## Chay ung dung

```bash
uvicorn app.main:app --reload
```

Sau do mo:

```text
http://localhost:8000
```

---

## Cau truc project

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

## Vai tro tung tang

| Tang | Vai tro |
|---|---|
| `frontend/` | Giao dien demo, goi API, render du lieu |
| `app/routers/` | Nhan request, validate input co ban, goi service |
| `app/services/` | Xu ly nghiep vu chinh |
| `database/` | Schema, rang buoc, du lieu mau |
| `app/db.py` | Ket noi PostgreSQL |
| `app/main.py` | Khoi dong FastAPI app va serve frontend |

---

## API endpoints chinh

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