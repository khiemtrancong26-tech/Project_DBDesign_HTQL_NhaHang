# main.py
"""
Entry point — khởi động FastAPI app.

Chạy server:
    uvicorn main:app --reload

Mở trình duyệt:
    http://localhost:8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routers import auth, customer, staff, manager

app = FastAPI(title="Hệ Thống Quản Lý Nhà Hàng")

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API ROUTERS ───────────────────────────────────────────────────────────
# prefix="/api" — tất cả endpoint đều bắt đầu bằng /api/...
#
# auth.py    : POST /api/auth/login, POST /api/auth/register
# customer.py: GET  /api/menu
#              POST /api/reservations
#              POST /api/orders/{id}/items
#              GET  /api/orders/customer/{id}
#              GET  /api/orders/{id}/invoice
#              POST /api/payments
# staff.py   : GET  /api/staff/{id}/orders
#              PATCH /api/orders/{id}/status
# manager.py : GET  /api/manager/orders
#              GET  /api/manager/revenue
#              GET  /api/manager/staff-performance
#              GET  /api/manager/failed-bookings
#              PATCH /api/manager/failed-bookings/{id}
#              POST /api/manager/reservations
#              PATCH /api/manager/orders/{id}/reschedule
#              GET  /api/manager/audit-log

app.include_router(auth.router,     prefix="/api")
app.include_router(customer.router, prefix="/api")
app.include_router(staff.router,    prefix="/api")
app.include_router(manager.router,  prefix="/api")

# ── SERVE FRONTEND ────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def root():
    return FileResponse("frontend/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)