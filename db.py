# db.py
"""
Kết nối PostgreSQL qua psycopg2.

Mỗi request gọi get_conn() → mở connection mới → dùng xong đóng lại.
Pattern đơn giản, phù hợp demo — không dùng connection pool.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    """
    Trả về 1 connection mới tới PostgreSQL.
    Caller có trách nhiệm gọi conn.close() sau khi dùng xong.
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
