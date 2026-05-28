"""SEGAV ERP – Global Search.

Provides a cross-entity search that scans trabajadores, faenas,
mandantes, contratos and documents in a single query.  Results are
returned as a list of dicts with entity type, id, label and match
context.

Usage::

    from segav_core.search import global_search
    results = global_search(fetch_df, tenant_key, "García", allowed_mandante_ids=None)
"""

from __future__ import annotations

import re
from typing import Callable


def _like_pattern(term: str) -> str:
    """Escape and wrap a search term for SQL LIKE."""
    safe = term.replace("%", "").replace("_", "").strip()
    return f"%{safe}%"


def global_search(
    fetch_df: Callable,
    tenant_key: str,
    query: str,
    *,
    allowed_mandante_ids: list[int] | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Search across main entities and return unified results.

    Each result dict has keys:
        - entity: str  ("trabajador", "faena", "mandante", "doc_trabajador", "doc_empresa")
        - id: int
        - label: str   (display name / primary info)
        - detail: str  (secondary info / match context)
        - icon: str    (emoji)
    """
    if not query or not query.strip():
        return []

    term = query.strip()
    like = _like_pattern(term)
    results: list[dict] = []
    limit = max(5, max_results)

    # --- Trabajadores ---
    try:
        mand_filter = ""
        params: list = [tenant_key, like, like, like]
        if allowed_mandante_ids:
            ph = ",".join(["?"] * len(allowed_mandante_ids))
            mand_filter = f" AND EXISTS (SELECT 1 FROM asignaciones a2 JOIN faenas f2 ON f2.id=a2.faena_id WHERE a2.trabajador_id=t.id AND f2.mandante_id IN ({ph}))"
            params.extend(allowed_mandante_ids)
        params.append(limit)
        sql = f"""
            SELECT t.id, t.rut, t.nombres, t.apellidos, COALESCE(t.cargo,'') AS cargo
            FROM trabajadores t
            WHERE COALESCE(t.cliente_key,'')=?
              AND (t.rut LIKE ? OR LOWER(t.nombres||' '||t.apellidos) LIKE LOWER(?) OR LOWER(t.cargo) LIKE LOWER(?))
              {mand_filter}
            ORDER BY t.apellidos, t.nombres
            LIMIT ?
        """
        df = fetch_df(sql, tuple(params))
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                results.append({
                    "entity": "trabajador",
                    "id": int(r["id"]),
                    "label": f"{r['apellidos']}, {r['nombres']}",
                    "detail": f"RUT: {r['rut']} · Cargo: {r['cargo']}",
                    "icon": "👷",
                })
    except Exception:
        pass

    # --- Faenas ---
    try:
        params_f: list = [tenant_key, like, like]
        mand_filter_f = ""
        if allowed_mandante_ids:
            ph = ",".join(["?"] * len(allowed_mandante_ids))
            mand_filter_f = f" AND f.mandante_id IN ({ph})"
            params_f.extend(allowed_mandante_ids)
        params_f.append(limit)
        sql_f = f"""
            SELECT f.id, f.nombre, f.estado, COALESCE(f.direccion,'') AS direccion
            FROM faenas f
            WHERE COALESCE(f.cliente_key,'')=?
              AND (LOWER(f.nombre) LIKE LOWER(?) OR LOWER(COALESCE(f.direccion,'')) LIKE LOWER(?))
              {mand_filter_f}
            ORDER BY f.nombre
            LIMIT ?
        """
        df = fetch_df(sql_f, tuple(params_f))
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                results.append({
                    "entity": "faena",
                    "id": int(r["id"]),
                    "label": str(r["nombre"]),
                    "detail": f"Estado: {r['estado']} · {r['direccion']}",
                    "icon": "🛠️",
                })
    except Exception:
        pass

    # --- Mandantes ---
    try:
        params_m: list = [tenant_key, like, like, limit]
        sql_m = """
            SELECT m.id, m.nombre, COALESCE(m.rut,'') AS rut
            FROM mandantes m
            WHERE COALESCE(m.cliente_key,'')=?
              AND (LOWER(m.nombre) LIKE LOWER(?) OR m.rut LIKE ?)
            ORDER BY m.nombre
            LIMIT ?
        """
        df = fetch_df(sql_m, tuple(params_m))
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                results.append({
                    "entity": "mandante",
                    "id": int(r["id"]),
                    "label": str(r["nombre"]),
                    "detail": f"RUT: {r['rut']}",
                    "icon": "🏢",
                })
    except Exception:
        pass

    # --- Documentos trabajador ---
    try:
        params_d: list = [tenant_key, like, like, limit]
        sql_d = """
            SELECT td.id, td.nombre_archivo, td.doc_tipo, t.nombres, t.apellidos
            FROM trabajador_documentos td
            JOIN trabajadores t ON t.id = td.trabajador_id
            WHERE COALESCE(td.cliente_key,'')=?
              AND (LOWER(td.nombre_archivo) LIKE LOWER(?) OR LOWER(td.doc_tipo) LIKE LOWER(?))
            ORDER BY td.id DESC
            LIMIT ?
        """
        df = fetch_df(sql_d, tuple(params_d))
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                results.append({
                    "entity": "doc_trabajador",
                    "id": int(r["id"]),
                    "label": str(r["nombre_archivo"]),
                    "detail": f"Tipo: {r['doc_tipo']} · Trabajador: {r['apellidos']}, {r['nombres']}",
                    "icon": "📎",
                })
    except Exception:
        pass

    return results[:max_results]


def render_search_sidebar(st_module, fetch_df_fn: Callable, tenant_key: str, allowed_mandante_ids=None, go_fn=None):
    """Render a professional global search widget in the Streamlit sidebar."""
    st = st_module
    with st.expander("🔍 Búsqueda global", expanded=False):
        q = st.text_input(
            "Buscar",
            key="global_search_input",
            placeholder="RUT, nombre, faena, documento…",
            label_visibility="collapsed",
        )
        if q and len(q.strip()) >= 2:
            results = global_search(fetch_df_fn, tenant_key, q, allowed_mandante_ids=allowed_mandante_ids)
            if not results:
                st.markdown(
                    '<div style="text-align:center; padding:12px; opacity:0.5;">'
                    '🔍 Sin resultados para esta búsqueda</div>',
                    unsafe_allow_html=True,
                )
            else:
                # Group by entity type
                grouped = {}
                for r in results[:20]:
                    grouped.setdefault(r["entity"], []).append(r)

                entity_labels = {
                    "trabajador": ("👷 Trabajadores", "Trabajadores"),
                    "faena": ("🛠️ Faenas", "Faenas"),
                    "mandante": ("🏢 Mandantes", "Mandantes"),
                    "doc_trabajador": ("📎 Documentos", "Documentos Trabajador"),
                    "doc_empresa": ("🏛️ Docs Empresa", "Documentos Empresa (Faena)"),
                }

                for entity_type, items in grouped.items():
                    label_info = entity_labels.get(entity_type, ("📋 Otros", "Dashboard"))
                    category_label, nav_target = label_info

                    st.markdown(
                        f'<div style="font-size:0.75rem; font-weight:700; text-transform:uppercase; '
                        f'letter-spacing:0.06em; opacity:0.5; margin:8px 0 4px 0; '
                        f'border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:3px;">'
                        f'{category_label} ({len(items)})</div>',
                        unsafe_allow_html=True,
                    )

                    for r in items[:5]:
                        rid = r["id"]
                        if st.button(
                            f"{r['icon']} {r['label']}",
                            key=f"gsearch_{entity_type}_{rid}",
                            use_container_width=True,
                            help=r["detail"],
                        ):
                            st.session_state["nav_page"] = nav_target
                            if entity_type == "faena":
                                st.session_state["selected_faena_id"] = rid
                            elif entity_type == "trabajador":
                                st.session_state["_search_trabajador_id"] = rid
                            st.rerun()

                total = len(results)
                if total > 20:
                    st.caption(f"Mostrando 20 de {total} resultados")
        elif q and len(q.strip()) < 2:
            st.caption("Escribe al menos 2 caracteres")
