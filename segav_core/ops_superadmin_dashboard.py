"""SEGAV ERP – SuperAdmin Dashboard.

Dashboard exclusivo para el superadmin con visión global de la aplicación:
- Resumen de empresas, usuarios, faenas, trabajadores
- Estado del sistema
- Actividad reciente
- Alertas y pendientes
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, date


def render_superadmin_dashboard(
    *,
    fetch_df,
    fetch_value,
    execute,
    ui_header,
):
    """Render the SuperAdmin dashboard with app-wide metrics."""

    ui_header("Panel de Control — SuperAdmin", "Visión global de SEGAV ERP: empresas, usuarios, sistema y actividad.")

    # ── Gather all metrics ──────────────────────────────────────────
    def _safe_int(sql, params=(), default=0):
        try:
            return int(fetch_value(sql, params, default=default, fresh=True) or default)
        except Exception:
            return default

    def _safe_df(sql, params=()):
        try:
            df = fetch_df(sql, params)
            return df if df is not None and not df.empty else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    # Counts
    n_empresas = _safe_int("SELECT COUNT(*) FROM segav_clientes")
    n_users = _safe_int("SELECT COUNT(*) FROM users")
    n_users_active = _safe_int("SELECT COUNT(*) FROM users WHERE is_active=1")
    n_users_pending = _safe_int("SELECT COUNT(*) FROM users WHERE approval_status='PENDIENTE'")
    n_faenas = _safe_int("SELECT COUNT(*) FROM faenas")
    n_faenas_activas = _safe_int("SELECT COUNT(*) FROM faenas WHERE estado='ACTIVA'")
    n_trabajadores = _safe_int("SELECT COUNT(*) FROM trabajadores")
    n_docs_trabajador = _safe_int("SELECT COUNT(*) FROM trabajador_documentos")
    n_docs_empresa = _safe_int("SELECT COUNT(*) FROM empresa_documentos")
    n_docs_faena = _safe_int("SELECT COUNT(*) FROM faena_empresa_documentos")
    n_total_docs = n_docs_trabajador + n_docs_empresa + n_docs_faena
    n_sessions = _safe_int("SELECT COUNT(*) FROM user_sessions")
    n_exports = _safe_int("SELECT COUNT(*) FROM export_historial")
    n_audit = _safe_int("SELECT COUNT(*) FROM segav_audit_log")
    n_notif_unread = _safe_int("SELECT COUNT(*) FROM segav_notifications WHERE is_read=0")

    # ── Row 1: Primary KPIs ─────────────────────────────────────────
    st.markdown("### 🏢 Resumen General")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Empresas", n_empresas, help="Total de empresas/clientes registrados")
    k2.metric("Usuarios", f"{n_users_active}/{n_users}", help="Activos / Total")
    k3.metric("Faenas", f"{n_faenas_activas}/{n_faenas}", help="Activas / Total")
    k4.metric("Trabajadores", n_trabajadores)
    k5.metric("Documentos", f"{n_total_docs:,}", help=f"Trabajador: {n_docs_trabajador} · Empresa: {n_docs_empresa} · Faena: {n_docs_faena}")

    # ── Row 2: Alerts ───────────────────────────────────────────────
    _alerts = []
    if n_users_pending > 0:
        _alerts.append(f"🟠 **{n_users_pending} usuario(s) pendientes** de aprobación")
    if n_notif_unread > 0:
        _alerts.append(f"🔔 **{n_notif_unread} notificación(es)** sin leer")
    n_docs_vencidos = _safe_int(
        "SELECT COUNT(*) FROM legal_doc_approvals WHERE legal_status='VENCIDO' AND renewal_status != 'RENOVADO'"
    )
    if n_docs_vencidos > 0:
        _alerts.append(f"🔴 **{n_docs_vencidos} documento(s) legales vencidos**")

    if _alerts:
        st.markdown("### ⚡ Alertas del Sistema")
        for a in _alerts:
            st.warning(a)
    else:
        st.success("✅ Sin alertas pendientes. Todo el sistema operando normalmente.")

    # ── Tabs ────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Empresas", "👥 Usuarios", "📈 Actividad", "🔧 Sistema"])

    # ── Tab 1: Empresas ─────────────────────────────────────────────
    with tab1:
        st.markdown("#### Empresas registradas")
        empresas_df = _safe_df("""
            SELECT c.cliente_key, c.cliente_nombre, c.vertical,
                   (SELECT COUNT(*) FROM faenas f WHERE COALESCE(f.cliente_key,'')=c.cliente_key) AS faenas,
                   (SELECT COUNT(*) FROM trabajadores t WHERE COALESCE(t.cliente_key,'')=c.cliente_key) AS trabajadores,
                   (SELECT COUNT(*) FROM trabajador_documentos d WHERE COALESCE(d.cliente_key,'')=c.cliente_key) AS documentos
            FROM segav_clientes c
            ORDER BY c.cliente_nombre
        """)
        if not empresas_df.empty:
            st.dataframe(
                empresas_df.rename(columns={
                    "cliente_key": "Clave", "cliente_nombre": "Empresa", "vertical": "Vertical",
                    "faenas": "Faenas", "trabajadores": "Trabajadores", "documentos": "Documentos",
                }),
                use_container_width=True, hide_index=True,
            )

            # Chart: docs per company
            if len(empresas_df) > 1:
                chart = empresas_df[["cliente_nombre", "faenas", "trabajadores", "documentos"]].copy()
                chart = chart.rename(columns={"cliente_nombre": "Empresa"}).set_index("Empresa")
                st.bar_chart(chart, use_container_width=True)
        else:
            st.info("No hay empresas registradas.")

    # ── Tab 2: Usuarios ─────────────────────────────────────────────
    with tab2:
        st.markdown("#### Usuarios del sistema")

        # KPIs
        u1, u2, u3, u4 = st.columns(4)
        n_superadmins = _safe_int("SELECT COUNT(*) FROM users WHERE role='SUPERADMIN'")
        n_admins = _safe_int("SELECT COUNT(*) FROM users WHERE role='ADMIN'")
        n_operadores = _safe_int("SELECT COUNT(*) FROM users WHERE role='OPERADOR'")
        n_lectores = _safe_int("SELECT COUNT(*) FROM users WHERE role='LECTOR'")
        u1.metric("SuperAdmin", n_superadmins)
        u2.metric("Admin", n_admins)
        u3.metric("Operador", n_operadores)
        u4.metric("Lector", n_lectores)

        # Pending approvals
        if n_users_pending > 0:
            st.markdown("##### 🟠 Usuarios pendientes de aprobación")
            pending_df = _safe_df(
                "SELECT username, role, full_name, approval_requested_at, requested_cliente_key FROM users WHERE approval_status='PENDIENTE' ORDER BY id DESC"
            )
            if not pending_df.empty:
                st.dataframe(pending_df.rename(columns={
                    "username": "Usuario", "role": "Rol", "full_name": "Nombre",
                    "approval_requested_at": "Solicitado", "requested_cliente_key": "Empresa",
                }), use_container_width=True, hide_index=True)

        # Active sessions
        st.markdown("##### 🟢 Sesiones activas")
        sessions_df = _safe_df("""
            SELECT s.username, s.role, s.cliente_key, s.last_seen_at
            FROM user_sessions s
            ORDER BY s.last_seen_at DESC
            LIMIT 20
        """)
        if not sessions_df.empty:
            st.dataframe(sessions_df.rename(columns={
                "username": "Usuario", "role": "Rol", "cliente_key": "Empresa", "last_seen_at": "Última actividad",
            }), use_container_width=True, hide_index=True)
        else:
            st.caption("No hay sesiones activas registradas.")

    # ── Tab 3: Actividad ────────────────────────────────────────────
    with tab3:
        st.markdown("#### Actividad reciente")

        a1, a2, a3 = st.columns(3)
        a1.metric("Acciones registradas", f"{n_audit:,}")
        a2.metric("Exportaciones", n_exports)
        a3.metric("Sesiones históricas", n_sessions)

        # Recent audit entries
        st.markdown("##### Últimas acciones")
        audit_df = _safe_df(
            "SELECT created_at, username, role_global, accion, entidad, detalle, cliente_key FROM segav_audit_log ORDER BY id DESC LIMIT 30"
        )
        if not audit_df.empty:
            st.dataframe(audit_df.rename(columns={
                "created_at": "Fecha", "username": "Usuario", "role_global": "Rol",
                "accion": "Acción", "entidad": "Entidad", "detalle": "Detalle", "cliente_key": "Empresa",
            }), use_container_width=True, hide_index=True)

        # Activity chart by month
        st.markdown("##### Acciones por mes (últimos 6 meses)")
        monthly_df = _safe_df("""
            SELECT
                SUBSTR(created_at, 1, 7) AS mes,
                COUNT(*) AS acciones
            FROM segav_audit_log
            GROUP BY SUBSTR(created_at, 1, 7)
            ORDER BY mes DESC
            LIMIT 6
        """)
        if not monthly_df.empty:
            chart_m = monthly_df.sort_values("mes").set_index("mes")
            st.bar_chart(chart_m, use_container_width=True)

    # ── Tab 4: Sistema ──────────────────────────────────────────────
    with tab4:
        st.markdown("#### Estado del sistema")

        s1, s2, s3 = st.columns(3)
        # Count tables
        n_tables = _safe_int("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
        s1.metric("Tablas en BD", n_tables)
        s2.metric("Notificaciones", n_notif_unread, help="Sin leer")

        # Storage info
        n_storage_docs = _safe_int(
            "SELECT COUNT(*) FROM trabajador_documentos WHERE bucket IS NOT NULL AND bucket != ''"
        )
        n_local_docs = n_docs_trabajador - n_storage_docs
        s3.metric("Docs en Storage", f"{n_storage_docs}/{n_docs_trabajador}", help=f"En línea: {n_storage_docs} · Local: {n_local_docs}")

        st.markdown("##### 📊 Distribución de documentos por estado")
        doc_status = pd.DataFrame({
            "Estado": ["✅ En línea (Storage)", "💾 Solo local"],
            "Cantidad": [n_storage_docs, n_local_docs],
        })
        st.dataframe(doc_status, use_container_width=True, hide_index=True)

        st.markdown("##### 🗄️ Tablas principales")
        tables_info = []
        for tbl_name in ["users", "segav_clientes", "faenas", "trabajadores", "trabajador_documentos",
                         "empresa_documentos", "faena_empresa_documentos", "asignaciones",
                         "export_historial", "segav_audit_log", "user_sessions", "segav_notifications"]:
            count = _safe_int(f"SELECT COUNT(*) FROM {tbl_name}")
            tables_info.append({"Tabla": tbl_name, "Registros": count})
        st.dataframe(pd.DataFrame(tables_info), use_container_width=True, hide_index=True)
