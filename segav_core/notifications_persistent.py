"""SEGAV ERP – Persistent Notifications.

Stores notifications in a database table so they survive page reloads
and are visible across sessions.  Supports per-user and broadcast
notifications with read/unread state.

Tables created by bootstrap:
    segav_notifications (id, cliente_key, user_id, username, category,
                         title, body, link_page, is_read, created_at)
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Callable

# Notification categories
CAT_USER_PENDING = "user_pending"       # New user awaiting approval
CAT_DOC_EXPIRED = "doc_expired"         # Document expired
CAT_DOC_UPLOADED = "doc_uploaded"       # New document uploaded
CAT_APPROVAL_REQ = "approval_request"  # Legal approval requested
CAT_SYSTEM = "system"                   # System/generic

CATEGORY_ICONS = {
    CAT_USER_PENDING: "👤",
    CAT_DOC_EXPIRED: "⚠️",
    CAT_DOC_UPLOADED: "📎",
    CAT_APPROVAL_REQ: "✅",
    CAT_SYSTEM: "🔔",
}

CATEGORY_LABELS = {
    CAT_USER_PENDING: "Usuario pendiente",
    CAT_DOC_EXPIRED: "Documento vencido",
    CAT_DOC_UPLOADED: "Documento cargado",
    CAT_APPROVAL_REQ: "Aprobación solicitada",
    CAT_SYSTEM: "Sistema",
}

CATEGORY_COLORS = {
    CAT_USER_PENDING: "#2563eb",
    CAT_DOC_EXPIRED: "#dc2626",
    CAT_DOC_UPLOADED: "#16a34a",
    CAT_APPROVAL_REQ: "#7c3aed",
    CAT_SYSTEM: "#475569",
}


def _inject_notification_css(st_module) -> None:
    if getattr(st_module, "_segav_notification_css_loaded", False):
        return
    st_module.markdown(
        """
        <style>
        .segav-notif-badge {
            border:1px solid rgba(220,38,38,.22);
            background:linear-gradient(135deg,rgba(254,242,242,.98),rgba(254,226,226,.92));
            border-radius:14px;
            padding:10px 12px;
            color:#991b1b;
            font-weight:900;
            text-align:center;
            box-shadow:0 12px 24px rgba(127,29,29,.12);
        }
        .segav-notif-card {
            border:1px solid rgba(148,163,184,.24);
            border-left:5px solid var(--notif-color, #475569);
            background:rgba(255,255,255,.88);
            border-radius:12px;
            padding:10px 11px;
            margin:8px 0 6px 0;
            box-shadow:0 8px 18px rgba(15,23,42,.08);
        }
        .segav-notif-card.read {
            opacity:.68;
            background:rgba(248,250,252,.72);
            border-left-color:#94a3b8;
        }
        .segav-notif-top {
            display:flex;
            gap:8px;
            align-items:flex-start;
            justify-content:space-between;
        }
        .segav-notif-title {
            color:#0f172a;
            font-size:.88rem;
            font-weight:900;
            line-height:1.2;
        }
        .segav-notif-meta {
            color:#64748b;
            font-size:.72rem;
            font-weight:800;
            text-transform:uppercase;
            letter-spacing:.03em;
            margin-top:3px;
        }
        .segav-notif-body {
            color:#475569;
            font-size:.78rem;
            line-height:1.35;
            margin-top:6px;
        }
        .segav-notif-dot {
            min-width:9px;
            height:9px;
            border-radius:50%;
            background:var(--notif-color, #475569);
            margin-top:4px;
            box-shadow:0 0 0 4px rgba(37,99,235,.10);
        }
        .segav-notif-empty {
            border:1px dashed rgba(148,163,184,.42);
            border-radius:12px;
            padding:12px;
            color:#64748b;
            text-align:center;
            background:rgba(248,250,252,.72);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    setattr(st_module, "_segav_notification_css_loaded", True)

# SQL for table creation (SQLite)
CREATE_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS segav_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_key TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    username TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'system',
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    link_page TEXT DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS segav_notifications (
    id SERIAL PRIMARY KEY,
    cliente_key TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    username TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'system',
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    link_page TEXT DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
"""

CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_segav_notif_user ON segav_notifications(user_id, is_read);"


def ensure_notifications_table(execute_fn: Callable, db_backend: str = "sqlite") -> None:
    """Create the notifications table if it doesn't exist."""
    try:
        sql = CREATE_TABLE_POSTGRES if db_backend == "postgres" else CREATE_TABLE_SQLITE
        execute_fn(sql)
        execute_fn(CREATE_INDEX)
    except Exception:
        pass  # Table may already exist


def send_notification(
    execute_fn: Callable,
    *,
    cliente_key: str = "",
    user_id: int | None = None,
    username: str = "",
    category: str = CAT_SYSTEM,
    title: str = "",
    body: str = "",
    link_page: str = "",
) -> None:
    """Insert a notification record."""
    if not title:
        return
    try:
        execute_fn(
            "INSERT INTO segav_notifications(cliente_key, user_id, username, category, title, body, link_page) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (str(cliente_key), user_id, str(username), category, title, body, link_page),
        )
    except Exception:
        pass


def get_unread_count(fetch_value_fn: Callable, user_id: int | None = None, is_superadmin: bool = False) -> int:
    """Return the number of unread notifications for a user."""
    try:
        if is_superadmin:
            # Superadmin sees all unread
            return int(fetch_value_fn(
                "SELECT COUNT(*) FROM segav_notifications WHERE is_read=0",
                (), default=0, fresh=True,
            ) or 0)
        if user_id:
            return int(fetch_value_fn(
                "SELECT COUNT(*) FROM segav_notifications WHERE is_read=0 AND (user_id=? OR user_id IS NULL)",
                (user_id,), default=0, fresh=True,
            ) or 0)
    except Exception:
        pass
    return 0


def get_notifications(
    fetch_df_fn: Callable,
    user_id: int | None = None,
    is_superadmin: bool = False,
    *,
    limit: int = 50,
    unread_only: bool = False,
):
    """Return recent notifications as a DataFrame."""
    try:
        where = "WHERE 1=1"
        params: list = []
        if not is_superadmin and user_id:
            where += " AND (user_id=? OR user_id IS NULL)"
            params.append(user_id)
        if unread_only:
            where += " AND is_read=0"
        params.append(limit)
        sql = f"SELECT * FROM segav_notifications {where} ORDER BY id DESC LIMIT ?"
        return fetch_df_fn(sql, tuple(params))
    except Exception:
        return None


def mark_as_read(execute_fn: Callable, notification_id: int) -> None:
    """Mark a single notification as read."""
    try:
        execute_fn("UPDATE segav_notifications SET is_read=1 WHERE id=?", (notification_id,))
    except Exception:
        pass


def mark_all_read(execute_fn: Callable, user_id: int | None = None, is_superadmin: bool = False) -> None:
    """Mark all notifications as read for a user or all (superadmin)."""
    try:
        if is_superadmin:
            execute_fn("UPDATE segav_notifications SET is_read=1 WHERE is_read=0")
        elif user_id:
            execute_fn(
                "UPDATE segav_notifications SET is_read=1 WHERE is_read=0 AND (user_id=? OR user_id IS NULL)",
                (user_id,),
            )
    except Exception:
        pass


def render_notification_badge(st_module, count: int) -> None:
    """Render a notification count badge in the sidebar."""
    _inject_notification_css(st_module)
    if count > 0:
        badge_text = str(count) if count < 100 else "99+"
        st_module.markdown(
            f'<div class="segav-notif-badge">🔔 {badge_text} notificación{"es" if count != 1 else ""} sin leer</div>',
            unsafe_allow_html=True,
        )


def render_notification_panel(st_module, fetch_df_fn, execute_fn, user_id, is_superadmin_flag, go_fn=None):
    """Render a full notification panel (for sidebar expander or page)."""
    st = st_module
    _inject_notification_css(st)
    df = get_notifications(fetch_df_fn, user_id, is_superadmin_flag, limit=30)
    if df is None or df.empty:
        st.markdown('<div class="segav-notif-empty">Sin notificaciones recientes.</div>', unsafe_allow_html=True)
        return

    unread_count = 0
    try:
        unread_count = int((df["is_read"].fillna(0).astype(int) == 0).sum())
    except Exception:
        unread_count = 0
    st.caption(f"{unread_count} sin leer · {len(df)} recientes")
    if unread_count and st.button("Marcar todo como leído", key="notif_mark_all_read", use_container_width=True):
        mark_all_read(execute_fn, user_id, is_superadmin_flag)
        st.rerun()

    for _, row in df.iterrows():
        nid = int(row.get("id", 0))
        cat = str(row.get("category", "system"))
        icon = CATEGORY_ICONS.get(cat, "🔔")
        color = CATEGORY_COLORS.get(cat, "#475569")
        label = CATEGORY_LABELS.get(cat, "Sistema")
        title = escape(str(row.get("title", "")))
        body = escape(str(row.get("body", "")))
        is_read = int(row.get("is_read", 0))
        link_page = str(row.get("link_page", ""))
        created = escape(str(row.get("created_at", ""))[:16])

        read_class = "read" if is_read else "unread"
        status = "Leída" if is_read else "Nueva"
        st.markdown(
            f'''
            <div class="segav-notif-card {read_class}" style="--notif-color:{color};">
              <div class="segav-notif-top">
                <div>
                  <div class="segav-notif-title">{icon} {title}</div>
                  <div class="segav-notif-meta">{escape(label)} · {status} · {created}</div>
                </div>
                <span class="segav-notif-dot"></span>
              </div>
              <div class="segav-notif-body">{body or "Sin detalle."}</div>
            </div>
            ''',
            unsafe_allow_html=True,
        )
        cols = st.columns([1, 1])
        if not is_read:
            with cols[0]:
                if st.button("Leída", key=f"notif_read_{nid}", use_container_width=True):
                    mark_as_read(execute_fn, nid)
                    st.rerun()
        if link_page and go_fn:
            with cols[1]:
                if st.button("Abrir", key=f"notif_go_{nid}", use_container_width=True, help=f"Ir a {link_page}"):
                    st.session_state["nav_page"] = link_page
                    st.rerun()
