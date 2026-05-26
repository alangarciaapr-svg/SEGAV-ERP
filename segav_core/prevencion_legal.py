"""SEGAV ERP – Prevención de Riesgos: Estadísticas y Cotización Adicional.

Módulo de cumplimiento legal chileno basado en:
- Ley 16.744: Seguro social contra accidentes del trabajo
- DS 594: Condiciones sanitarias y ambientales
- DS 44: Cotización adicional diferenciada

Fórmulas según estándares de mutualidades chilenas (ACHS, IST, Mutual de Seguridad).
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Callable
import streamlit as st


# ═══════════════════════════════════════════════════════════════════════════════
# TASAS DE ACCIDENTABILIDAD (fórmulas estándar Chile)
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_tasas(n_accidentes: int, dias_perdidos: int, n_trabajadores: int, horas_hombre: int) -> dict:
    """Calcula las 4 tasas estándar de accidentabilidad laboral.

    Returns dict with keys: tasa_accidentabilidad, tasa_siniestralidad,
    tasa_frecuencia, tasa_gravedad.
    """
    t = max(n_trabajadores, 1)
    h = max(horas_hombre, 1)
    return {
        "tasa_accidentabilidad": round((n_accidentes / t) * 100, 2),
        "tasa_siniestralidad": round((dias_perdidos / t) * 100, 2),
        "tasa_frecuencia": round((n_accidentes * 1_000_000) / h, 2),
        "tasa_gravedad": round((dias_perdidos * 1_000_000) / h, 2),
    }


def obtener_stats_periodo(fetch_df, fetch_value, anio: int) -> dict:
    """Obtiene estadísticas de accidentes/incidentes para un año."""
    try:
        inicio = f"{anio}-01-01"
        fin = f"{anio}-12-31"
        n_acc = int(fetch_value(
            "SELECT COUNT(*) FROM sgsst_incidentes WHERE tipo='ACCIDENTE' AND fecha>=? AND fecha<=?",
            (inicio, fin), default=0, fresh=True) or 0)
        n_acc_tp = int(fetch_value(
            "SELECT COUNT(*) FROM sgsst_incidentes WHERE tipo='ACCIDENTE' AND dias_perdidos>0 AND fecha>=? AND fecha<=?",
            (inicio, fin), default=0, fresh=True) or 0)
        dias_p = int(fetch_value(
            "SELECT COALESCE(SUM(dias_perdidos),0) FROM sgsst_incidentes WHERE fecha>=? AND fecha<=?",
            (inicio, fin), default=0, fresh=True) or 0)
        n_inc = int(fetch_value(
            "SELECT COUNT(*) FROM sgsst_incidentes WHERE tipo='INCIDENTE' AND fecha>=? AND fecha<=?",
            (inicio, fin), default=0, fresh=True) or 0)
        n_enf = int(fetch_value(
            "SELECT COUNT(*) FROM sgsst_incidentes WHERE tipo='ENFERMEDAD PROFESIONAL' AND fecha>=? AND fecha<=?",
            (inicio, fin), default=0, fresh=True) or 0)
        n_fatales = int(fetch_value(
            "SELECT COUNT(*) FROM sgsst_incidentes WHERE gravedad='FATAL' AND fecha>=? AND fecha<=?",
            (inicio, fin), default=0, fresh=True) or 0)
        n_trab = int(fetch_value(
            "SELECT COUNT(*) FROM trabajadores", default=0, fresh=True) or 0)
    except Exception:
        n_acc, n_acc_tp, dias_p, n_inc, n_enf, n_fatales, n_trab = 0, 0, 0, 0, 0, 0, 0

    return {
        "anio": anio,
        "accidentes_total": n_acc,
        "accidentes_con_tiempo_perdido": n_acc_tp,
        "dias_perdidos": dias_p,
        "incidentes": n_inc,
        "enfermedades_profesionales": n_enf,
        "fatales": n_fatales,
        "n_trabajadores": n_trab,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CUMPLIMIENTO POR LEY
# ═══════════════════════════════════════════════════════════════════════════════

def evaluar_cumplimiento_16744(fetch_value, fetch_df, n_trabajadores: int) -> list[dict]:
    """Evalúa cumplimiento de Ley 16.744 y retorna lista de requisitos con estado."""
    items = []

    # 1. CPHS (obligatorio >= 25 trabajadores)
    cphs_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_cphs", default=0) or 0)
    cphs_requerido = n_trabajadores >= 25
    items.append({
        "requisito": "Comité Paritario (CPHS)",
        "referencia": "Art. 66, Ley 16.744 / DS 54",
        "obligatorio": cphs_requerido,
        "cumple": cphs_count > 0 if cphs_requerido else True,
        "detalle": f"{'Constituido' if cphs_count > 0 else 'No constituido'} · {'Obligatorio (≥25 trab.)' if cphs_requerido else 'No obligatorio (<25 trab.)'}",
    })

    # 2. RIOHS (obligatorio >= 10 trabajadores)
    riohs_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_riohs", default=0) or 0)
    riohs_requerido = n_trabajadores >= 10
    items.append({
        "requisito": "Reglamento Interno (RIOHS)",
        "referencia": "Art. 67, Ley 16.744",
        "obligatorio": riohs_requerido,
        "cumple": riohs_count > 0 if riohs_requerido else True,
        "detalle": f"{'Registrado' if riohs_count > 0 else 'No registrado'} · {'Obligatorio (≥10 trab.)' if riohs_requerido else 'No obligatorio (<10 trab.)'}",
    })

    # 3. Derecho a Saber (ODI) - siempre obligatorio
    odi_count = int(fetch_value(
        "SELECT COUNT(*) FROM sgsst_capacitaciones WHERE LOWER(tipo) LIKE '%odi%' OR LOWER(tema) LIKE '%derecho a saber%' OR LOWER(tema) LIKE '%odi%'",
        default=0) or 0)
    items.append({
        "requisito": "Obligación de Informar (ODI / Derecho a Saber)",
        "referencia": "Art. 21, DS 40",
        "obligatorio": True,
        "cumple": odi_count > 0,
        "detalle": f"{odi_count} registro(s) de ODI",
    })

    # 4. Departamento de Prevención (obligatorio >= 100 trabajadores)
    dept_requerido = n_trabajadores >= 100
    # Check if empresa has prevention dept configured
    dept_ok = bool(fetch_value("SELECT 1 FROM sgsst_empresa WHERE depto_prevencion IS NOT NULL AND depto_prevencion != ''", default=None))
    items.append({
        "requisito": "Departamento de Prevención de Riesgos",
        "referencia": "Art. 66, Ley 16.744",
        "obligatorio": dept_requerido,
        "cumple": dept_ok if dept_requerido else True,
        "detalle": f"{'Configurado' if dept_ok else 'No configurado'} · {'Obligatorio (≥100 trab.)' if dept_requerido else 'No obligatorio (<100 trab.)'}",
    })

    # 5. Investigación de accidentes
    inc_total = int(fetch_value("SELECT COUNT(*) FROM sgsst_incidentes WHERE tipo='ACCIDENTE'", default=0) or 0)
    inc_cerrados = int(fetch_value("SELECT COUNT(*) FROM sgsst_incidentes WHERE tipo='ACCIDENTE' AND estado='CERRADO'", default=0) or 0)
    items.append({
        "requisito": "Investigación de accidentes",
        "referencia": "Art. 76, Ley 16.744",
        "obligatorio": True,
        "cumple": inc_total == 0 or inc_cerrados == inc_total,
        "detalle": f"{inc_cerrados}/{inc_total} accidentes investigados y cerrados" if inc_total > 0 else "Sin accidentes registrados",
    })

    # 6. Programa de Prevención
    prog_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_programa_anual", default=0) or 0)
    prog_abierto = int(fetch_value("SELECT COUNT(*) FROM sgsst_programa_anual WHERE estado != 'CERRADO'", default=0) or 0)
    items.append({
        "requisito": "Programa anual de prevención",
        "referencia": "Art. 66, Ley 16.744 / DS 40",
        "obligatorio": True,
        "cumple": prog_count > 0,
        "detalle": f"{prog_count} actividades programadas, {prog_abierto} pendientes" if prog_count > 0 else "Sin programa registrado",
    })

    return items


def evaluar_cumplimiento_ds594(fetch_value, fetch_df) -> list[dict]:
    """Evalúa cumplimiento de DS 594."""
    items = []

    # 1. Inspecciones periódicas
    insp_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_inspecciones", default=0) or 0)
    insp_abiertas = int(fetch_value("SELECT COUNT(*) FROM sgsst_inspecciones WHERE estado != 'CERRADO'", default=0) or 0)
    items.append({
        "requisito": "Inspecciones de condiciones sanitarias y ambientales",
        "referencia": "DS 594, Título II-IV",
        "obligatorio": True,
        "cumple": insp_count > 0 and insp_abiertas == 0,
        "detalle": f"{insp_count} inspecciones, {insp_abiertas} abiertas" if insp_count > 0 else "Sin inspecciones registradas",
    })

    # 2. Checklist DS 594
    ck_count = int(fetch_value("SELECT COUNT(DISTINCT fecha_inspeccion || inspector) FROM sgsst_checklist_ds594", default=0) or 0)
    items.append({
        "requisito": "Checklist de cumplimiento DS 594",
        "referencia": "DS 594, Arts. 3-21",
        "obligatorio": True,
        "cumple": ck_count > 0,
        "detalle": f"{ck_count} checklist(s) realizados" if ck_count > 0 else "Sin checklist realizados",
    })

    # 3. Vigilancia ambiental
    vig_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_vigilancia", default=0) or 0)
    items.append({
        "requisito": "Vigilancia ambiental y ocupacional",
        "referencia": "DS 594, Título V",
        "obligatorio": True,
        "cumple": vig_count > 0,
        "detalle": f"{vig_count} registro(s) de vigilancia" if vig_count > 0 else "Sin registros de vigilancia",
    })

    # 4. EPP
    epp_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_epp_entrega", default=0) or 0)
    items.append({
        "requisito": "Entrega y control de EPP",
        "referencia": "DS 594, Art. 53-54",
        "obligatorio": True,
        "cumple": epp_count > 0,
        "detalle": f"{epp_count} entrega(s) registradas" if epp_count > 0 else "Sin entregas de EPP registradas",
    })

    return items


def evaluar_cumplimiento_ds44(fetch_value, fetch_df, stats_anio: dict) -> list[dict]:
    """Evalúa cumplimiento de DS 44 (cotización adicional diferenciada)."""
    items = []

    # 1. Matriz de riesgos (MIPER)
    miper_count = int(fetch_value("SELECT COUNT(*) FROM sgsst_miper", default=0) or 0)
    miper_criticos = int(fetch_value("SELECT COUNT(*) FROM sgsst_miper WHERE nivel_riesgo IN ('ALTO','CRÍTICO') AND estado != 'CERRADO'", default=0) or 0)
    items.append({
        "requisito": "Identificación y evaluación de riesgos (MIPER)",
        "referencia": "DS 44, Art. 3",
        "obligatorio": True,
        "cumple": miper_count > 0 and miper_criticos == 0,
        "detalle": f"{miper_count} riesgos identificados, {miper_criticos} críticos/altos sin cerrar" if miper_count > 0 else "Sin matriz de riesgos",
    })

    # 2. Tasa de accidentabilidad
    ta = stats_anio.get("accidentes_con_tiempo_perdido", 0)
    n_t = max(stats_anio.get("n_trabajadores", 1), 1)
    tasa_acc = round((ta / n_t) * 100, 2)
    items.append({
        "requisito": "Tasa de accidentabilidad controlada",
        "referencia": "DS 44, Art. 5-6",
        "obligatorio": True,
        "cumple": tasa_acc < 6.0,  # Below industry average
        "detalle": f"Tasa actual: {tasa_acc}% {'(baja ✅)' if tasa_acc < 6.0 else '(alta ⚠️ — meta: <6%)'}",
    })

    # 3. Tasa de siniestralidad
    dp = stats_anio.get("dias_perdidos", 0)
    tasa_sin = round((dp / n_t) * 100, 2)
    items.append({
        "requisito": "Tasa de siniestralidad controlada",
        "referencia": "DS 44, Art. 5-6",
        "obligatorio": True,
        "cumple": tasa_sin < 100,
        "detalle": f"Tasa actual: {tasa_sin}% {'(controlada ✅)' if tasa_sin < 100 else '(alta ⚠️)'}",
    })

    # 4. SGSST implementado
    empresa_ok = bool(fetch_value("SELECT 1 FROM sgsst_empresa WHERE razon_social IS NOT NULL AND razon_social != ''", default=None))
    items.append({
        "requisito": "Sistema de Gestión de SST implementado",
        "referencia": "DS 44, Art. 12",
        "obligatorio": True,
        "cumple": empresa_ok,
        "detalle": "Ficha empresa configurada" if empresa_ok else "Ficha empresa sin configurar",
    })

    return items


# ═══════════════════════════════════════════════════════════════════════════════
# COTIZACIÓN ADICIONAL
# ═══════════════════════════════════════════════════════════════════════════════

# Tabla de cotización base por actividad económica (simplificada)
COTIZACION_BASE = 0.93  # %
COTIZACION_ADICIONAL_RANGOS = {
    "Sin riesgo adicional": 0.0,
    "Riesgo bajo (0.85%)": 0.85,
    "Riesgo medio-bajo (1.70%)": 1.70,
    "Riesgo medio (2.55%)": 2.55,
    "Riesgo medio-alto (2.55%)": 2.55,
    "Riesgo alto (3.40%)": 3.40,
}


def calcular_cotizacion(sueldo_imponible: float, tasa_base: float = COTIZACION_BASE, tasa_adicional: float = 0.0, n_trabajadores: int = 1) -> dict:
    """Calcula cotización mensual y anual."""
    tasa_total = tasa_base + tasa_adicional
    cotiz_mensual_unit = sueldo_imponible * (tasa_total / 100)
    cotiz_mensual_total = cotiz_mensual_unit * n_trabajadores
    return {
        "tasa_base": tasa_base,
        "tasa_adicional": tasa_adicional,
        "tasa_total": tasa_total,
        "cotiz_mensual_por_trabajador": round(cotiz_mensual_unit),
        "cotiz_mensual_total": round(cotiz_mensual_total),
        "cotiz_anual_total": round(cotiz_mensual_total * 12),
    }


def simular_reduccion(cotiz_actual: dict, nueva_tasa_adicional: float) -> dict:
    """Simula el ahorro al reducir la cotización adicional."""
    nueva = calcular_cotizacion(
        cotiz_actual.get("_sueldo_base", 500000),
        cotiz_actual["tasa_base"],
        nueva_tasa_adicional,
        cotiz_actual.get("_n_trabajadores", 1),
    )
    ahorro_mensual = cotiz_actual["cotiz_mensual_total"] - nueva["cotiz_mensual_total"]
    ahorro_anual = cotiz_actual["cotiz_anual_total"] - nueva["cotiz_anual_total"]
    return {
        **nueva,
        "ahorro_mensual": round(ahorro_mensual),
        "ahorro_anual": round(ahorro_anual),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RENDER TABS
# ═══════════════════════════════════════════════════════════════════════════════

def render_tab_estadisticas(st, K, fetch_df, fetch_value, company):
    """Tab de Estadísticas de Accidentabilidad."""
    st.markdown("### 📊 Estadísticas de Accidentabilidad")
    st.caption("Tasas según estándares de mutualidades chilenas (ACHS, IST, Mutual de Seguridad).")

    anio = st.selectbox("Año", list(range(date.today().year, date.today().year - 5, -1)), key=K("stats_anio"))
    stats = obtener_stats_periodo(fetch_df, fetch_value, anio)

    hh_default = stats["n_trabajadores"] * 2000
    hh = st.number_input("Horas hombre trabajadas (estimación)", min_value=0, value=hh_default, step=1000, key=K("stats_hh"),
                          help="Si no conoces el dato exacto, se estima como N° trabajadores × 2.000 horas/año")

    tasas = calcular_tasas(stats["accidentes_con_tiempo_perdido"], stats["dias_perdidos"], stats["n_trabajadores"], hh)

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tasa Accidentabilidad", f"{tasas['tasa_accidentabilidad']}%", help="(Acc. con tiempo perdido / N° trabajadores) × 100")
    c2.metric("Tasa Siniestralidad", f"{tasas['tasa_siniestralidad']}%", help="(Días perdidos / N° trabajadores) × 100")
    c3.metric("Tasa Frecuencia", f"{tasas['tasa_frecuencia']}", help="(N° accidentes × 1.000.000) / HH trabajadas")
    c4.metric("Tasa Gravedad", f"{tasas['tasa_gravedad']}", help="(Días perdidos × 1.000.000) / HH trabajadas")

    st.divider()

    # Detail table
    st.markdown("#### Detalle del período")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Accidentes totales", stats["accidentes_total"])
        st.metric("Con tiempo perdido", stats["accidentes_con_tiempo_perdido"])
        st.metric("Días perdidos", stats["dias_perdidos"])
    with col2:
        st.metric("Incidentes (sin lesión)", stats["incidentes"])
        st.metric("Enfermedades profesionales", stats["enfermedades_profesionales"])
        st.metric("Fatales", stats["fatales"])

    st.divider()

    # Interpretation
    st.markdown("#### Interpretación")
    if tasas["tasa_accidentabilidad"] == 0:
        st.success("✅ Sin accidentes con tiempo perdido en el período. Excelente gestión preventiva.")
    elif tasas["tasa_accidentabilidad"] < 3:
        st.success(f"✅ Tasa de accidentabilidad baja ({tasas['tasa_accidentabilidad']}%). Buena gestión.")
    elif tasas["tasa_accidentabilidad"] < 6:
        st.warning(f"⚠️ Tasa de accidentabilidad media ({tasas['tasa_accidentabilidad']}%). Revisar programa de prevención.")
    else:
        st.error(f"🔴 Tasa de accidentabilidad alta ({tasas['tasa_accidentabilidad']}%). Acción inmediata requerida.")

    return stats, tasas


def render_tab_cotizacion(st, K, fetch_value, stats_anio, company):
    """Tab de Cotización Adicional."""
    st.markdown("### 💰 Cotización Adicional Diferenciada")
    st.caption("Simulador según DS 67 / DS 44 para evaluar y reducir la cotización adicional de su empresa.")

    st.markdown("#### Datos actuales")
    col1, col2, col3 = st.columns(3)
    with col1:
        n_trab = st.number_input("N° trabajadores", min_value=1, value=max(stats_anio.get("n_trabajadores", 1), 1), step=1, key=K("cot_ntrab"))
    with col2:
        sueldo = st.number_input("Sueldo imponible promedio ($)", min_value=0, value=500000, step=50000, key=K("cot_sueldo"))
    with col3:
        tasa_add_actual = st.selectbox("Cotización adicional actual", list(COTIZACION_ADICIONAL_RANGOS.keys()), key=K("cot_tasa_actual"))

    tasa_adicional = COTIZACION_ADICIONAL_RANGOS[tasa_add_actual]
    cotiz = calcular_cotizacion(sueldo, COTIZACION_BASE, tasa_adicional, n_trab)
    cotiz["_sueldo_base"] = sueldo
    cotiz["_n_trabajadores"] = n_trab

    st.divider()
    st.markdown("#### Costo actual")
    c1, c2, c3 = st.columns(3)
    c1.metric("Tasa total", f"{cotiz['tasa_total']}%")
    c2.metric("Costo mensual empresa", f"${cotiz['cotiz_mensual_total']:,.0f}")
    c3.metric("Costo anual empresa", f"${cotiz['cotiz_anual_total']:,.0f}")

    st.divider()
    st.markdown("#### Simulación de reducción")
    st.caption("¿Cuánto ahorraría su empresa si reduce la cotización adicional?")

    tasa_meta = st.selectbox("Cotización adicional meta", list(COTIZACION_ADICIONAL_RANGOS.keys()), key=K("cot_tasa_meta"))
    tasa_meta_val = COTIZACION_ADICIONAL_RANGOS[tasa_meta]

    if tasa_meta_val < tasa_adicional:
        sim = simular_reduccion(cotiz, tasa_meta_val)
        c1, c2, c3 = st.columns(3)
        c1.metric("Nueva tasa total", f"{sim['tasa_total']}%", delta=f"-{tasa_adicional - tasa_meta_val:.2f}%")
        c2.metric("Ahorro mensual", f"${sim['ahorro_mensual']:,.0f}", delta="ahorro")
        c3.metric("Ahorro anual", f"${sim['ahorro_anual']:,.0f}", delta="ahorro")
        st.success(f"💰 Reducir de {tasa_adicional}% a {tasa_meta_val}% genera un ahorro anual de **${sim['ahorro_anual']:,.0f}**")
    elif tasa_meta_val == tasa_adicional:
        st.info("La tasa meta es igual a la actual. Seleccione una tasa menor para ver el ahorro.")
    else:
        st.warning("La tasa meta es mayor que la actual. Seleccione una tasa menor.")

    st.divider()
    st.markdown("#### ¿Cómo reducir la cotización adicional?")
    st.markdown("""
Para solicitar rebaja de la cotización adicional ante su mutualidad, debe demostrar:

1. **Tasa de accidentabilidad** por debajo del promedio de su actividad económica
2. **Sistema de Gestión SST** implementado y documentado
3. **CPHS** constituido y funcionando (≥25 trabajadores)
4. **RIOHS** vigente y difundido (≥10 trabajadores)
5. **Programa de prevención** anual ejecutado
6. **Capacitaciones** al día (ODI, uso EPP, procedimientos)
7. **Inspecciones DS 594** periódicas realizadas
8. **Investigación de accidentes** completa (100% cerrados)
9. **MIPER** actualizado sin riesgos críticos abiertos
10. **Estadísticas de accidentabilidad** documentadas

Revise el tab **📋 Cumplimiento Legal** para ver el estado de cada requisito.
    """)


def render_tab_cumplimiento_legal(st, K, fetch_value, fetch_df, stats_anio, company, n_trabajadores):
    """Tab de Cumplimiento Legal por normativa."""
    st.markdown("### 📋 Cumplimiento Legal — Ley 16.744 · DS 594 · DS 44")
    st.caption("Estado de cumplimiento por cada normativa aplicable.")

    items_16744 = evaluar_cumplimiento_16744(fetch_value, fetch_df, n_trabajadores)
    items_ds594 = evaluar_cumplimiento_ds594(fetch_value, fetch_df)
    items_ds44 = evaluar_cumplimiento_ds44(fetch_value, fetch_df, stats_anio)

    def _render_law_section(title, ref, items):
        cumple = sum(1 for i in items if i["cumple"])
        total_oblig = sum(1 for i in items if i["obligatorio"])
        pct = int((cumple / max(total_oblig, 1)) * 100)
        color = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")

        with st.expander(f"{color} **{title}** — {cumple}/{total_oblig} requisitos ({pct}%)", expanded=False):
            st.caption(ref)
            st.progress(pct / 100)
            for item in items:
                icon = "✅" if item["cumple"] else ("⚠️" if not item["obligatorio"] else "❌")
                oblig = "OBLIGATORIO" if item["obligatorio"] else "RECOMENDADO"
                st.markdown(
                    f'{icon} **{item["requisito"]}** · `{item["referencia"]}` · {oblig}\n\n'
                    f'   {item["detalle"]}'
                )
                st.markdown("---")
        return pct

    pct1 = _render_law_section(
        "Ley 16.744 — Seguro contra accidentes del trabajo",
        "Seguro social obligatorio, CPHS, RIOHS, Departamento de Prevención, ODI",
        items_16744,
    )
    pct2 = _render_law_section(
        "DS 594 — Condiciones sanitarias y ambientales",
        "Inspecciones, checklist, vigilancia ambiental, EPP",
        items_ds594,
    )
    pct3 = _render_law_section(
        "DS 44 — Cotización adicional diferenciada",
        "Evaluación de riesgos, tasas de accidentabilidad, SGSST",
        items_ds44,
    )

    st.divider()
    pct_global = int((pct1 + pct2 + pct3) / 3)
    color_g = "🟢" if pct_global >= 80 else ("🟡" if pct_global >= 50 else "🔴")
    st.markdown(f"### {color_g} Cumplimiento legal global: {pct_global}%")
    st.progress(pct_global / 100)

    if pct_global >= 80:
        st.success("Su empresa tiene un buen nivel de cumplimiento. Puede solicitar rebaja de cotización adicional ante su mutualidad.")
    elif pct_global >= 50:
        st.warning("Cumplimiento parcial. Revise los ítems pendientes antes de solicitar rebaja.")
    else:
        st.error("Cumplimiento insuficiente. Priorice los requisitos obligatorios marcados con ❌.")
