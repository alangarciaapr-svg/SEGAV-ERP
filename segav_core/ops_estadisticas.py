"""SEGAV ERP – Estadísticas de Accidentabilidad y Cotización Adicional.

Cumplimiento normativo chileno:
- Ley 16.744: Seguro social contra accidentes del trabajo y enfermedades profesionales
- DS 594: Condiciones sanitarias y ambientales básicas en los lugares de trabajo
- DS 44: Reglamento sobre prevención de riesgos profesionales

Cálculo de tasas para reducción de cotización adicional según estándares
de mutualidades (ACHS, Mutual de Seguridad, IST).
"""
from __future__ import annotations

import streamlit as st

from segav_core.kpi_ui import segmented_progress
import pandas as pd
from datetime import date, datetime
from typing import Callable


# ── Tasas de cotización adicional por actividad económica ────────────
# Cotización base: 0.93% (todos los empleadores)
# Cotización adicional: 0% a 3.4% según actividad y siniestralidad
COTIZACION_BASE = 0.93
COTIZACION_ADICIONAL_MAX = 3.40

ACTIVIDADES_ECONOMICAS = {
    "Oficinas / Administración": 0.0,
    "Comercio / Retail": 0.85,
    "Transporte": 1.70,
    "Construcción liviana": 1.70,
    "Construcción pesada": 2.55,
    "Minería": 3.40,
    "Industria manufacturera": 1.70,
    "Agricultura / Forestal": 1.70,
    "Servicios de limpieza": 0.85,
    "Electricidad / Gas / Agua": 1.70,
    "Salud": 0.85,
    "Educación": 0.0,
}

# ── Requisitos legales por normativa ─────────────────────────────────
REQUISITOS_LEY_16744 = [
    {"id": "L1", "articulo": "Art. 66", "requisito": "Constitución y funcionamiento del CPHS (≥25 trabajadores)", "critico": True},
    {"id": "L2", "articulo": "Art. 66 bis", "requisito": "Sistema de Gestión de SST para empresas con faenas", "critico": True},
    {"id": "L3", "articulo": "Art. 67", "requisito": "Reglamento Interno de Higiene y Seguridad (RIOHS)", "critico": True},
    {"id": "L4", "articulo": "Art. 68", "requisito": "Obligación de informar los riesgos laborales (ODI)", "critico": True},
    {"id": "L5", "articulo": "Art. 71", "requisito": "Denuncia de accidentes del trabajo (DIAT) en 24 horas", "critico": True},
    {"id": "L6", "articulo": "Art. 72", "requisito": "Denuncia de enfermedad profesional (DIEP)", "critico": True},
    {"id": "L7", "articulo": "Art. 76", "requisito": "Investigación de accidentes graves e informe a SEREMI", "critico": True},
    {"id": "L8", "articulo": "Art. 65", "requisito": "Cotización adicional diferenciada por siniestralidad", "critico": False},
    {"id": "L9", "articulo": "Art. 21", "requisito": "Exámenes médicos ocupacionales", "critico": False},
    {"id": "L10", "articulo": "Art. 184 CT", "requisito": "Deber general de protección del empleador", "critico": True},
]

REQUISITOS_DS594 = [
    {"id": "D1", "articulo": "Art. 3-4", "requisito": "Condiciones generales de construcción y sanitarias del lugar de trabajo", "critico": True},
    {"id": "D2", "articulo": "Art. 5-8", "requisito": "Provisión de agua potable", "critico": True},
    {"id": "D3", "articulo": "Art. 9-11", "requisito": "Servicios higiénicos y vestuarios", "critico": True},
    {"id": "D4", "articulo": "Art. 12-13", "requisito": "Guardarropías y comedores", "critico": False},
    {"id": "D5", "articulo": "Art. 14-16", "requisito": "Ventilación", "critico": True},
    {"id": "D6", "articulo": "Art. 17-19", "requisito": "Condiciones ambientales: iluminación", "critico": True},
    {"id": "D7", "articulo": "Art. 32-37", "requisito": "Control de ruido ocupacional", "critico": True},
    {"id": "D8", "articulo": "Art. 38-41", "requisito": "Exposición a calor y frío", "critico": False},
    {"id": "D9", "articulo": "Art. 42-56", "requisito": "Contaminantes químicos (límites permisibles)", "critico": True},
    {"id": "D10", "articulo": "Art. 57-66", "requisito": "Agentes biológicos", "critico": False},
    {"id": "D11", "articulo": "Art. 53", "requisito": "Programa de vigilancia ambiental y personal", "critico": True},
    {"id": "D12", "articulo": "Art. 68-73", "requisito": "Radiaciones ionizantes y no ionizantes", "critico": False},
    {"id": "D13", "articulo": "Art. 44", "requisito": "Elementos de protección personal (EPP)", "critico": True},
    {"id": "D14", "articulo": "Art. 45-47", "requisito": "Prevención y protección contra incendios", "critico": True},
    {"id": "D15", "articulo": "Art. 48-52", "requisito": "Equipos de protección personal adecuados y certificados", "critico": True},
]

REQUISITOS_DS44 = [
    {"id": "R1", "articulo": "Art. 3", "requisito": "Departamento de Prevención de Riesgos (>100 trabajadores)", "critico": True},
    {"id": "R2", "articulo": "Art. 9-11", "requisito": "Experto en Prevención de Riesgos registrado", "critico": True},
    {"id": "R3", "articulo": "Art. 14-21", "requisito": "Reglamento Interno de Higiene y Seguridad (RIOHS) vigente", "critico": True},
    {"id": "R4", "articulo": "Art. 21", "requisito": "Obligación de Informar (ODI) a cada trabajador", "critico": True},
    {"id": "R5", "articulo": "Art. 22-25", "requisito": "Comité Paritario constituido y funcionando", "critico": True},
    {"id": "R6", "articulo": "Art. 3", "requisito": "Estadísticas de accidentabilidad actualizadas", "critico": True},
    {"id": "R7", "articulo": "Art. 3", "requisito": "Programa anual de prevención", "critico": True},
    {"id": "R8", "articulo": "Art. 3", "requisito": "Registro de capacitaciones en seguridad", "critico": False},
    {"id": "R9", "articulo": "Art. 3", "requisito": "Investigación de todos los accidentes", "critico": True},
    {"id": "R10", "articulo": "Art. 3", "requisito": "Control de contratistas y subcontratistas", "critico": False},
]

# ── Requisitos mutualidad para rebaja de cotización ──────────────────
REQUISITOS_MUTUALIDAD = [
    {"id": "M1", "area": "CPHS", "requisito": "CPHS constituido, con actas mensuales y reuniones al día", "peso": 15},
    {"id": "M2", "area": "RIOHS", "requisito": "RIOHS vigente, entregado a cada trabajador con acuse de recibo", "peso": 10},
    {"id": "M3", "area": "Programa", "requisito": "Programa anual de prevención aprobado y con avance ≥80%", "peso": 15},
    {"id": "M4", "area": "MIPER", "requisito": "Matriz de riesgos actualizada para cada faena", "peso": 10},
    {"id": "M5", "area": "Capacitación", "requisito": "Plan de capacitación ejecutado (ODI, emergencias, EPP)", "peso": 10},
    {"id": "M6", "area": "Estadísticas", "requisito": "Tasas de accidentabilidad por debajo del promedio del sector", "peso": 15},
    {"id": "M7", "area": "Inspecciones", "requisito": "Inspecciones DS 594 realizadas según programa", "peso": 10},
    {"id": "M8", "area": "Investigación", "requisito": "100% de accidentes investigados con medidas correctivas", "peso": 10},
    {"id": "M9", "area": "EPP", "requisito": "Registro de entrega de EPP a cada trabajador", "peso": 5},
]


# ── CREATE TABLE SQL ─────────────────────────────────────────────────
CREATE_ESTADISTICAS_PG = """
CREATE TABLE IF NOT EXISTS sgsst_estadisticas_mensuales (
    id BIGSERIAL PRIMARY KEY,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    trabajadores_promedio INTEGER DEFAULT 0,
    horas_hombre_trabajadas NUMERIC DEFAULT 0,
    accidentes_con_tiempo_perdido INTEGER DEFAULT 0,
    accidentes_sin_tiempo_perdido INTEGER DEFAULT 0,
    dias_perdidos INTEGER DEFAULT 0,
    enfermedades_profesionales INTEGER DEFAULT 0,
    accidentes_trayecto INTEGER DEFAULT 0,
    accidentes_fatales INTEGER DEFAULT 0,
    cliente_key TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(anio, mes, cliente_key)
);
"""

CREATE_ESTADISTICAS_SQLITE = """
CREATE TABLE IF NOT EXISTS sgsst_estadisticas_mensuales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    trabajadores_promedio INTEGER DEFAULT 0,
    horas_hombre_trabajadas REAL DEFAULT 0,
    accidentes_con_tiempo_perdido INTEGER DEFAULT 0,
    accidentes_sin_tiempo_perdido INTEGER DEFAULT 0,
    dias_perdidos INTEGER DEFAULT 0,
    enfermedades_profesionales INTEGER DEFAULT 0,
    accidentes_trayecto INTEGER DEFAULT 0,
    accidentes_fatales INTEGER DEFAULT 0,
    cliente_key TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(anio, mes, cliente_key)
);
"""

CREATE_CUMPLIMIENTO_PG = """
CREATE TABLE IF NOT EXISTS sgsst_cumplimiento_legal (
    id BIGSERIAL PRIMARY KEY,
    normativa TEXT NOT NULL,
    requisito_id TEXT NOT NULL,
    cumple BOOLEAN DEFAULT FALSE,
    evidencia TEXT DEFAULT '',
    responsable TEXT DEFAULT '',
    fecha_verificacion TEXT,
    observacion TEXT DEFAULT '',
    cliente_key TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(normativa, requisito_id, cliente_key)
);
"""

CREATE_CUMPLIMIENTO_SQLITE = """
CREATE TABLE IF NOT EXISTS sgsst_cumplimiento_legal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normativa TEXT NOT NULL,
    requisito_id TEXT NOT NULL,
    cumple INTEGER DEFAULT 0,
    evidencia TEXT DEFAULT '',
    responsable TEXT DEFAULT '',
    fecha_verificacion TEXT,
    observacion TEXT DEFAULT '',
    cliente_key TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(normativa, requisito_id, cliente_key)
);
"""


def ensure_estadisticas_tables(execute_fn, db_backend="postgres"):
    """Create statistics and compliance tables."""
    try:
        if db_backend == "postgres":
            execute_fn(CREATE_ESTADISTICAS_PG)
            execute_fn(CREATE_CUMPLIMIENTO_PG)
        else:
            execute_fn(CREATE_ESTADISTICAS_SQLITE)
            execute_fn(CREATE_CUMPLIMIENTO_SQLITE)
    except Exception:
        pass


# ── Calculation functions ────────────────────────────────────────────
def calcular_tasas(df_stats: pd.DataFrame) -> dict:
    """Calculate accident rates from monthly statistics."""
    if df_stats is None or df_stats.empty:
        return {
            "tasa_frecuencia": 0, "tasa_gravedad": 0, "tasa_siniestralidad": 0,
            "total_accidentes": 0, "total_dias_perdidos": 0, "total_hht": 0,
            "promedio_trabajadores": 0, "accidentes_fatales": 0,
        }
    total_acc = int(df_stats["accidentes_con_tiempo_perdido"].sum())
    total_dias = int(df_stats["dias_perdidos"].sum())
    total_hht = float(df_stats["horas_hombre_trabajadas"].sum())
    prom_trab = float(df_stats["trabajadores_promedio"].mean())
    fatales = int(df_stats.get("accidentes_fatales", pd.Series([0])).sum())

    tf = (total_acc * 1_000_000 / total_hht) if total_hht > 0 else 0
    tg = (total_dias * 1_000_000 / total_hht) if total_hht > 0 else 0
    ts = (total_dias * 100 / prom_trab) if prom_trab > 0 else 0

    return {
        "tasa_frecuencia": round(tf, 2),
        "tasa_gravedad": round(tg, 2),
        "tasa_siniestralidad": round(ts, 2),
        "total_accidentes": total_acc,
        "total_dias_perdidos": total_dias,
        "total_hht": round(total_hht),
        "promedio_trabajadores": round(prom_trab),
        "accidentes_fatales": fatales,
    }


def estimar_cotizacion_adicional(actividad: str, tasa_siniestralidad: float) -> dict:
    """Estimate additional premium based on activity and accident rate."""
    base_adicional = ACTIVIDADES_ECONOMICAS.get(actividad, 0.85)

    # Lógica de rebaja/recargo según DS 67 (simplificada)
    if tasa_siniestralidad == 0:
        factor = 0.0  # Rebaja máxima
        estado = "🟢 Rebaja máxima"
    elif tasa_siniestralidad < 50:
        factor = 0.4
        estado = "🟢 Rebaja parcial"
    elif tasa_siniestralidad < 100:
        factor = 0.7
        estado = "🟡 Rebaja menor"
    elif tasa_siniestralidad < 150:
        factor = 1.0
        estado = "🟡 Sin variación"
    elif tasa_siniestralidad < 250:
        factor = 1.3
        estado = "🟠 Recargo leve"
    else:
        factor = 1.7
        estado = "🔴 Recargo máximo"

    cotizacion_adicional = round(base_adicional * factor, 2)
    cotizacion_total = round(COTIZACION_BASE + cotizacion_adicional, 2)
    ahorro_potencial = round(base_adicional - cotizacion_adicional, 2) if cotizacion_adicional < base_adicional else 0

    return {
        "cotizacion_base": COTIZACION_BASE,
        "adicional_actividad": base_adicional,
        "factor_siniestralidad": factor,
        "cotizacion_adicional": cotizacion_adicional,
        "cotizacion_total": cotizacion_total,
        "estado": estado,
        "ahorro_potencial": ahorro_potencial,
    }


# ── Render functions ─────────────────────────────────────────────────
def render_tab_estadisticas(st, fetch_df, fetch_value, execute, K, cliente_key=""):
    """Tab: Estadísticas de accidentabilidad."""
    st.markdown("### 📊 Estadísticas de Accidentabilidad")
    st.caption("Registro mensual de horas trabajadas, accidentes y días perdidos. Las tasas se calculan automáticamente según fórmulas oficiales.")

    today = date.today()
    c1, c2 = st.columns(2)
    with c1:
        anio = st.number_input("Año", min_value=2020, max_value=2030, value=today.year, key=K("est_anio"))
    with c2:
        mes = st.number_input("Mes", min_value=1, max_value=12, value=today.month, key=K("est_mes"))

    # Check if record exists
    existing = fetch_value(
        "SELECT id FROM sgsst_estadisticas_mensuales WHERE anio=? AND mes=? AND COALESCE(cliente_key,'')=?",
        (int(anio), int(mes), str(cliente_key)), default=None, fresh=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        trab_prom = st.number_input("Trabajadores promedio", min_value=0, value=0, key=K("est_trab"))
        acc_ctp = st.number_input("Accidentes con tiempo perdido", min_value=0, value=0, key=K("est_acc_ctp"))
    with c2:
        hht = st.number_input("Horas hombre trabajadas", min_value=0, value=0, step=100, key=K("est_hht"))
        acc_stp = st.number_input("Accidentes sin tiempo perdido", min_value=0, value=0, key=K("est_acc_stp"))
    with c3:
        dias = st.number_input("Días perdidos", min_value=0, value=0, key=K("est_dias"))
        enf_prof = st.number_input("Enfermedades profesionales", min_value=0, value=0, key=K("est_enf"))
    with c4:
        acc_tray = st.number_input("Accidentes de trayecto", min_value=0, value=0, key=K("est_tray"))
        acc_fat = st.number_input("Accidentes fatales", min_value=0, value=0, key=K("est_fat"))

    _btn_label = "Actualizar registro" if existing else "Guardar registro"
    if st.button(f"💾 {_btn_label}", key=K("est_save"), type="primary", use_container_width=True):
        now = datetime.now().isoformat(timespec="seconds")
        if existing:
            execute(
                "UPDATE sgsst_estadisticas_mensuales SET trabajadores_promedio=?, horas_hombre_trabajadas=?, accidentes_con_tiempo_perdido=?, accidentes_sin_tiempo_perdido=?, dias_perdidos=?, enfermedades_profesionales=?, accidentes_trayecto=?, accidentes_fatales=? WHERE anio=? AND mes=? AND COALESCE(cliente_key,'')=?",
                (trab_prom, hht, acc_ctp, acc_stp, dias, enf_prof, acc_tray, acc_fat, int(anio), int(mes), str(cliente_key)),
            )
        else:
            execute(
                "INSERT INTO sgsst_estadisticas_mensuales(anio,mes,trabajadores_promedio,horas_hombre_trabajadas,accidentes_con_tiempo_perdido,accidentes_sin_tiempo_perdido,dias_perdidos,enfermedades_profesionales,accidentes_trayecto,accidentes_fatales,cliente_key) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (int(anio), int(mes), trab_prom, hht, acc_ctp, acc_stp, dias, enf_prof, acc_tray, acc_fat, str(cliente_key)),
            )
        st.success(f"Estadísticas de {anio}-{mes:02d} guardadas.")
        st.rerun()

    # ── Show annual summary ──
    st.divider()
    st.markdown(f"#### Resumen anual {anio}")
    df_year = fetch_df(
        "SELECT * FROM sgsst_estadisticas_mensuales WHERE anio=? AND COALESCE(cliente_key,'')=? ORDER BY mes",
        (int(anio), str(cliente_key)),
    )
    if df_year is not None and not df_year.empty:
        tasas = calcular_tasas(df_year)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Tasa de Frecuencia", f"{tasas['tasa_frecuencia']}", help="(Acc. c/tiempo perdido × 1.000.000) / HHT")
        m2.metric("Tasa de Gravedad", f"{tasas['tasa_gravedad']}", help="(Días perdidos × 1.000.000) / HHT")
        m3.metric("Tasa de Siniestralidad", f"{tasas['tasa_siniestralidad']}", help="(Días perdidos × 100) / Promedio trabajadores")
        m4.metric("Accidentes fatales", str(tasas['accidentes_fatales']))

        # Chart
        chart_df = df_year[["mes", "accidentes_con_tiempo_perdido", "dias_perdidos"]].copy()
        chart_df = chart_df.rename(columns={"accidentes_con_tiempo_perdido": "Accidentes", "dias_perdidos": "Días perdidos"})
        chart_df["mes"] = chart_df["mes"].apply(lambda x: f"{int(x):02d}")
        st.bar_chart(chart_df.set_index("mes"), use_container_width=True)

        st.dataframe(df_year[["mes", "trabajadores_promedio", "horas_hombre_trabajadas", "accidentes_con_tiempo_perdido", "dias_perdidos"]].rename(columns={
            "mes": "Mes", "trabajadores_promedio": "Trabajadores", "horas_hombre_trabajadas": "HHT",
            "accidentes_con_tiempo_perdido": "Acc. CTP", "dias_perdidos": "Días perdidos",
        }), use_container_width=True, hide_index=True)
    else:
        st.info("No hay estadísticas registradas para este año. Ingresa los datos mensuales arriba.")


def render_tab_cotizacion(st, fetch_df, fetch_value, K, cliente_key="", company=None):
    """Tab: Simulador de cotización adicional."""
    st.markdown("### 💰 Simulador de Cotización Adicional")
    st.caption("Calcula tu cotización adicional según DS 67 y estima el ahorro potencial al reducir accidentabilidad.")

    actividad = st.selectbox(
        "Actividad económica principal",
        list(ACTIVIDADES_ECONOMICAS.keys()),
        key=K("cot_actividad"),
    )
    anio = st.number_input("Año de referencia", min_value=2020, max_value=2030, value=date.today().year, key=K("cot_anio"))

    df_year = fetch_df(
        "SELECT * FROM sgsst_estadisticas_mensuales WHERE anio=? AND COALESCE(cliente_key,'')=? ORDER BY mes",
        (int(anio), str(cliente_key)),
    )
    tasas = calcular_tasas(df_year)
    cot = estimar_cotizacion_adicional(actividad, tasas["tasa_siniestralidad"])

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Cotización base", f"{cot['cotizacion_base']}%")
    c2.metric("Cotización adicional", f"{cot['cotizacion_adicional']}%", delta=f"{cot['estado']}")
    c3.metric("Total a pagar", f"{cot['cotizacion_total']}%")

    if cot["ahorro_potencial"] > 0:
        st.success(f"🎯 Ahorro actual respecto a tu actividad: **{cot['ahorro_potencial']}%** de la remuneración imponible")
    elif cot["cotizacion_adicional"] > cot["adicional_actividad"]:
        st.error(f"⚠️ Recargo por siniestralidad: estás pagando **{cot['cotizacion_adicional'] - cot['adicional_actividad']:.2f}%** más que tu base")

    st.divider()
    st.markdown("#### 📋 ¿Cómo reducir la cotización adicional?")
    st.markdown("""
La cotización adicional se revisa cada 2 años según el DS 67. Para obtener rebaja necesitas demostrar a tu mutualidad:

1. **Tasas por debajo del promedio** de tu actividad económica
2. **SGSST implementado** con evidencia documentada
3. **CPHS funcionando** con actas al día
4. **Programa de prevención** ejecutado ≥80%
5. **100% de accidentes investigados** con medidas correctivas
6. **Capacitaciones al día** (ODI, emergencias, EPP)
7. **Inspecciones DS 594** realizadas según programa
8. **RIOHS vigente** y entregado a cada trabajador
""")

    # Simulation table
    st.markdown("#### 📊 Simulación de escenarios")
    scenarios = []
    for label, ts_val in [("Sin accidentes", 0), ("Bajo (TS<50)", 25), ("Medio (TS<100)", 75), ("Alto (TS<150)", 125), ("Crítico (TS≥250)", 300)]:
        c = estimar_cotizacion_adicional(actividad, ts_val)
        scenarios.append({"Escenario": label, "Tasa Siniestralidad": ts_val, "Cot. Adicional": f"{c['cotizacion_adicional']}%", "Total": f"{c['cotizacion_total']}%", "Estado": c["estado"]})
    st.dataframe(pd.DataFrame(scenarios), use_container_width=True, hide_index=True)


def render_tab_cumplimiento_legal(st, fetch_df, fetch_value, execute, K, cliente_key=""):
    """Tab: Cumplimiento legal por normativa."""
    st.markdown("### ⚖️ Cumplimiento Legal")
    st.caption("Evalúa el cumplimiento de tu empresa según Ley 16.744, DS 594 y DS 44. Marca cada requisito y registra la evidencia.")

    norma_tab = st.radio(
        "Normativa",
        ["Ley 16.744", "DS 594", "DS 44", "Requisitos Mutualidad"],
        horizontal=True,
        key=K("cl_norma"),
    )

    if norma_tab == "Ley 16.744":
        requisitos = REQUISITOS_LEY_16744
        norma_key = "ley16744"
    elif norma_tab == "DS 594":
        requisitos = REQUISITOS_DS594
        norma_key = "ds594"
    elif norma_tab == "DS 44":
        requisitos = REQUISITOS_DS44
        norma_key = "ds44"
    else:
        requisitos = REQUISITOS_MUTUALIDAD
        norma_key = "mutualidad"

    # Load existing compliance data
    existing_df = fetch_df(
        "SELECT requisito_id, cumple, evidencia, responsable, observacion FROM sgsst_cumplimiento_legal WHERE normativa=? AND COALESCE(cliente_key,'')=?",
        (norma_key, str(cliente_key)),
    )
    existing_map = {}
    if existing_df is not None and not existing_df.empty:
        for _, r in existing_df.iterrows():
            existing_map[r["requisito_id"]] = r

    total = len(requisitos)
    cumple_count = 0
    updates = []

    for req in requisitos:
        rid = req["id"]
        prev = existing_map.get(rid, {})
        is_critico = req.get("critico", False)
        peso = req.get("peso", 0)
        prefix = "🔴 " if is_critico else ""
        peso_label = f" (peso: {peso}%)" if peso > 0 else ""

        with st.expander(f"{prefix}{req.get('articulo', rid)} — {req['requisito']}{peso_label}", expanded=False):
            c1, c2 = st.columns([1, 2])
            with c1:
                cumple = st.checkbox("Cumple", value=bool(prev.get("cumple", 0)), key=K(f"cl_{norma_key}_{rid}_c"))
                if cumple:
                    cumple_count += 1
                responsable = st.text_input("Responsable", value=str(prev.get("responsable", "")), key=K(f"cl_{norma_key}_{rid}_r"))
            with c2:
                evidencia = st.text_input("Evidencia / documento", value=str(prev.get("evidencia", "")), key=K(f"cl_{norma_key}_{rid}_e"), placeholder="Ej: Acta CPHS mayo 2025")
                observacion = st.text_input("Observación", value=str(prev.get("observacion", "")), key=K(f"cl_{norma_key}_{rid}_o"))

            updates.append((norma_key, rid, cumple, evidencia, responsable, observacion))

    # Score
    pct = int((cumple_count / total) * 100) if total > 0 else 0
    color = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")
    st.markdown(f"#### {color} Cumplimiento {norma_tab}: {cumple_count}/{total} ({pct}%)")
    segmented_progress(pct, label="Score estadístico")

    if st.button(f"💾 Guardar cumplimiento {norma_tab}", key=K(f"cl_save_{norma_key}"), type="primary", use_container_width=True):
        now = datetime.now().isoformat(timespec="seconds")
        saved = 0
        for norma, rid, cumple, evidencia, responsable, observacion in updates:
            try:
                # Upsert
                existing_id = fetch_value(
                    "SELECT id FROM sgsst_cumplimiento_legal WHERE normativa=? AND requisito_id=? AND COALESCE(cliente_key,'')=?",
                    (norma, rid, str(cliente_key)), default=None, fresh=True,
                )
                if existing_id:
                    execute(
                        "UPDATE sgsst_cumplimiento_legal SET cumple=?, evidencia=?, responsable=?, observacion=?, updated_at=? WHERE id=?",
                        (1 if cumple else 0, evidencia.strip(), responsable.strip(), observacion.strip(), now, int(existing_id)),
                    )
                else:
                    execute(
                        "INSERT INTO sgsst_cumplimiento_legal(normativa, requisito_id, cumple, evidencia, responsable, observacion, cliente_key, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (norma, rid, 1 if cumple else 0, evidencia.strip(), responsable.strip(), observacion.strip(), str(cliente_key), now),
                    )
                saved += 1
            except Exception:
                pass
        st.success(f"Cumplimiento {norma_tab} guardado: {saved} requisitos actualizados.")
        st.rerun()
