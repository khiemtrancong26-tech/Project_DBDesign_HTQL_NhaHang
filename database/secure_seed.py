"""
Post-seed security migration.

Keep 01_schema.sql and 02_seed_demo_data.sql unchanged.
Run after seeding (or after manager inserts raw rows via SQL Terminal):
    - Hash plain-text passwords for Customer and Staff
    - Add RSA signatures for Payment rows without Signature

Usage CLI:
    python database/secure_seed.py
    python database/secure_seed.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db import get_conn
from app.services.payment_service import serialize_payment
from security.crypto import hash_password, sign_payment


def _secure_users(
    cur,
    *,
    table_name: str,
    id_col: str,
    dry_run: bool,
) -> tuple[int, int]:
    cur.execute(
        f"""
        SELECT {id_col}, username, password
        FROM {table_name}
        """
    )
    rows = cur.fetchall()

    updated_count = 0
    password_count = 0

    for entity_id, username, password in rows:
        new_password = password

        if password and ":" not in password:
            new_password = hash_password(password, username)
            password_count += 1

        if new_password != password:
            updated_count += 1
            if not dry_run:
                cur.execute(
                    f"""
                    UPDATE {table_name}
                    SET password = %s
                    WHERE {id_col} = %s
                    """,
                    (new_password, entity_id),
                )

    return updated_count, password_count


def _secure_payments(cur, *, dry_run: bool) -> int:
    cur.execute(
        """
        SELECT PaymentID, OrderID, Amount, PaymentMethod, PaymentType, PaymentDate, Signature
        FROM Payment
        """
    )
    rows = cur.fetchall()

    signed_count = 0
    for payment_id, order_id, amount, method, payment_type, payment_date, signature in rows:
        if signature:
            continue

        payload = serialize_payment(
            payment_id=payment_id,
            order_id=order_id,
            amount=float(amount),
            method=method,
            payment_type=payment_type,
            payment_date=payment_date,
        )
        new_signature = sign_payment(payload)
        signed_count += 1

        if not dry_run:
            cur.execute(
                """
                UPDATE Payment
                SET Signature = %s
                WHERE PaymentID = %s
                """,
                (new_signature, payment_id),
            )

    return signed_count


def secure_seed(dry_run: bool = False) -> dict:
    """
    Hash plain-text passwords and sign unsigned payment rows.

    Returns summary stats + mode ('DRY-RUN' or 'APPLIED').
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        customer_updated, customer_pwd = _secure_users(
            cur,
            table_name="Customer",
            id_col="CustomerID",
            dry_run=dry_run,
        )
        staff_updated, staff_pwd = _secure_users(
            cur,
            table_name="Staff",
            id_col="StaffID",
            dry_run=dry_run,
        )
        payment_signed = _secure_payments(cur, dry_run=dry_run)

        if dry_run:
            conn.rollback()
            mode = "DRY-RUN"
        else:
            conn.commit()
            mode = "APPLIED"

        return {
            "mode": mode,
            "customer_updated": customer_updated,
            "customer_pwd": customer_pwd,
            "staff_updated": staff_updated,
            "staff_pwd": staff_pwd,
            "payment_signed": payment_signed,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Secure already-seeded DB data.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing to database.",
    )
    args = parser.parse_args()

    result = secure_seed(dry_run=args.dry_run)
    mode = result["mode"]
    print(f"[{mode}] Customer rows updated: {result['customer_updated']}")
    print(f"[{mode}] Customer passwords hashed: {result['customer_pwd']}")
    print(f"[{mode}] Staff rows updated: {result['staff_updated']}")
    print(f"[{mode}] Staff passwords hashed: {result['staff_pwd']}")
    print(f"[{mode}] Payment signatures added: {result['payment_signed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
