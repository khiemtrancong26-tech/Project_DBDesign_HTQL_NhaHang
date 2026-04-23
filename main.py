# main.py
"""
Entry point — khởi động FastAPI app, mount toàn bộ router.

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
app.include_router(auth.router,     prefix="/api")
app.include_router(customer.router, prefix="/api")
app.include_router(staff.router,    prefix="/api")
app.include_router(manager.router,  prefix="/api")

# ── SERVE FRONTEND ────────────────────────────────────────────────────────
# Mount CSS/JS as static files
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Trang chủ → trả về index.html
@app.get("/")
def root():
    return FileResponse("frontend/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)