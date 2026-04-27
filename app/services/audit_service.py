"""Helpers for writing audit records."""

from __future__ import annotations

import json
from uuid import uuid4


def insert_audit_log(
    cur,
    *,
    actor_id: str,
    actor_role: str,
    action: str,
    target_table: str,
    target_id: str,
    old_value=None,
    new_value=None,
) -> str:
    """Insert a single row into AuditLog and return its LogID."""
    log_id = f"LOG{uuid4().hex[:12].upper()}"
    old_text = json.dumps(old_value, ensure_ascii=False, default=str) if old_value is not None else None
    new_text = json.dumps(new_value, ensure_ascii=False, default=str) if new_value is not None else None

    cur.execute(
        """
        INSERT INTO AuditLog
            (LogID, ActorID, ActorRole, Action, TargetTable, TargetID, OldValue, NewValue)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (log_id, actor_id, actor_role, action, target_table, target_id, old_text, new_text),
    )
    return log_id
