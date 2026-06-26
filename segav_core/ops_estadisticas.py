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
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable


# ── Tasas de cotización adicional por actividad económica ────────────
# El DS 67 determina la cotización adicional diferenciada. La tasa básica
# de la Ley 16.744 se muestra por separado y corresponde a 0,90%.
COTIZACION_BASE = 0.90

HHT_STANDARD_MUTUAL_180 = "Mutual estándar 180 h/mes"
HHT_STANDARD_LEGAL_CHILE = "Jornada legal Chile proporcional"
HHT_STANDARD_CUSTOM = "Personalizado"
HHT_STANDARD_OPTIONS = [HHT_STANDARD_MUTUAL_180, HHT_STANDARD_LEGAL_CHILE, HHT_STANDARD_CUSTOM]

DS67_COTIZACION_TABLA = [
    (32, 0.00), (64, 0.34), (96, 0.68), (128, 1.02), (160, 1.36),
    (192, 1.70), (224, 2.04), (272, 2.38), (320, 2.72), (368, 3.06),
    (416, 3.40), (464, 3.74), (512, 4.08), (560, 4.42), (630, 4.76),
    (700, 5.10), (770, 5.44), (840, 5.78), (910, 6.12), (980, 6.46),
    (None, 6.80),
]

DS67_INVALIDEZ_MUERTE_TABLA = [
    (0.10, 0), (0.30, 35), (0.50, 70), (0.70, 105), (0.90, 140),
    (1.20, 175), (1.50, 210), (1.80, 245), (2.10, 280),
    (2.40, 315), (2.70, 350), (None, 385),
]

DS67_EVENTOS = {
    "Invalidez de 15,0% a 25,0%": ("INVALIDEZ", 0.25),
    "Invalidez de 27,5% a 37,5%": ("INVALIDEZ", 0.50),
    "Invalidez de 40,0% a 65,0%": ("INVALIDEZ", 1.00),
    "Invalidez de 70,0% o más": ("INVALIDEZ", 1.50),
    "Gran invalidez": ("GRAN INVALIDEZ", 2.00),
    "Muerte": ("MUERTE", 2.50),
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

REQUISITOS_DS67 = [
    {"id": "S1", "articulo": "Art. 2 letras c-i", "requisito": "Nómina mensual de trabajadores y días perdidos por cada período anual julio-junio", "critico": True},
    {"id": "S2", "articulo": "Arts. 2 letras j-k y 3", "requisito": "Registro de invalideces y muertes computables respaldado por dictámenes", "critico": True},
    {"id": "S3", "articulo": "Art. 7", "requisito": "Antigüedad mínima de dos períodos anuales consecutivos", "critico": True},
    {"id": "S4", "articulo": "Art. 8", "requisito": "Cotizaciones de la Ley 16.744 al día", "critico": True},
    {"id": "S5", "articulo": "Art. 8", "requisito": "SG-SST en funcionamiento durante el último período anual y acreditado oportunamente", "critico": True},
    {"id": "S6", "articulo": "Arts. 10-12", "requisito": "Antecedentes y resolución del organismo administrador revisados y archivados", "critico": False},
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

CREATE_DS67_CONFIG_PG = """
CREATE TABLE IF NOT EXISTS sgsst_ds67_config (
    id BIGSERIAL PRIMARY KEY,
    cliente_key TEXT NOT NULL DEFAULT '',
    empresa_razon_social TEXT DEFAULT '',
    empresa_rut TEXT DEFAULT '',
    empresa_actividad TEXT DEFAULT '',
    empresa_ciiu TEXT DEFAULT '',
    empresa_contacto_ds67 TEXT DEFAULT '',
    fecha_adhesion TEXT,
    tasa_adicional_vigente NUMERIC DEFAULT 0,
    remuneracion_imponible_mensual NUMERIC DEFAULT 0,
    mutualidad_nombre TEXT DEFAULT '',
    mutualidad_codigo TEXT DEFAULT '',
    numero_adherente TEXT DEFAULT '',
    sucursal_mutual TEXT DEFAULT '',
    ejecutivo_mutual TEXT DEFAULT '',
    correo_mutual TEXT DEFAULT '',
    telefono_mutual TEXT DEFAULT '',
    portal_mutual_url TEXT DEFAULT '',
    conexion_modo TEXT DEFAULT 'Manual controlado',
    conexion_estado TEXT DEFAULT 'PENDIENTE',
    api_endpoint TEXT DEFAULT '',
    credencial_ref TEXT DEFAULT '',
    autorizacion_intercambio BOOLEAN DEFAULT FALSE,
    fecha_ultima_sincronizacion TEXT,
    ultima_resolucion_tasa TEXT DEFAULT '',
    notas_conexion TEXT DEFAULT '',
    cotizaciones_al_dia BOOLEAN DEFAULT FALSE,
    sgsst_acreditado BOOLEAN DEFAULT FALSE,
    muerte_prevenible_confirmada BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(cliente_key)
);
"""

CREATE_DS67_CONFIG_SQLITE = """
CREATE TABLE IF NOT EXISTS sgsst_ds67_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_key TEXT NOT NULL DEFAULT '',
    empresa_razon_social TEXT DEFAULT '',
    empresa_rut TEXT DEFAULT '',
    empresa_actividad TEXT DEFAULT '',
    empresa_ciiu TEXT DEFAULT '',
    empresa_contacto_ds67 TEXT DEFAULT '',
    fecha_adhesion TEXT,
    tasa_adicional_vigente REAL DEFAULT 0,
    remuneracion_imponible_mensual REAL DEFAULT 0,
    mutualidad_nombre TEXT DEFAULT '',
    mutualidad_codigo TEXT DEFAULT '',
    numero_adherente TEXT DEFAULT '',
    sucursal_mutual TEXT DEFAULT '',
    ejecutivo_mutual TEXT DEFAULT '',
    correo_mutual TEXT DEFAULT '',
    telefono_mutual TEXT DEFAULT '',
    portal_mutual_url TEXT DEFAULT '',
    conexion_modo TEXT DEFAULT 'Manual controlado',
    conexion_estado TEXT DEFAULT 'PENDIENTE',
    api_endpoint TEXT DEFAULT '',
    credencial_ref TEXT DEFAULT '',
    autorizacion_intercambio INTEGER DEFAULT 0,
    fecha_ultima_sincronizacion TEXT,
    ultima_resolucion_tasa TEXT DEFAULT '',
    notas_conexion TEXT DEFAULT '',
    cotizaciones_al_dia INTEGER DEFAULT 0,
    sgsst_acreditado INTEGER DEFAULT 0,
    muerte_prevenible_confirmada INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(cliente_key)
);
"""

DS67_CONFIG_EXTRA_COLUMNS = [
    ("fecha_adhesion", "TEXT", "TEXT"),
    ("tasa_adicional_vigente", "NUMERIC DEFAULT 0", "REAL DEFAULT 0"),
    ("remuneracion_imponible_mensual", "NUMERIC DEFAULT 0", "REAL DEFAULT 0"),
    ("cotizaciones_al_dia", "BOOLEAN DEFAULT FALSE", "INTEGER DEFAULT 0"),
    ("sgsst_acreditado", "BOOLEAN DEFAULT FALSE", "INTEGER DEFAULT 0"),
    ("muerte_prevenible_confirmada", "BOOLEAN DEFAULT FALSE", "INTEGER DEFAULT 0"),
    ("updated_at", "TIMESTAMPTZ", "TEXT"),
    ("empresa_razon_social", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("empresa_rut", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("empresa_actividad", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("empresa_ciiu", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("empresa_contacto_ds67", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("mutualidad_nombre", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("mutualidad_codigo", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("numero_adherente", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("sucursal_mutual", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("ejecutivo_mutual", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("correo_mutual", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("telefono_mutual", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("portal_mutual_url", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("conexion_modo", "TEXT DEFAULT 'Manual controlado'", "TEXT DEFAULT 'Manual controlado'"),
    ("conexion_estado", "TEXT DEFAULT 'PENDIENTE'", "TEXT DEFAULT 'PENDIENTE'"),
    ("api_endpoint", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("credencial_ref", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("autorizacion_intercambio", "BOOLEAN DEFAULT FALSE", "INTEGER DEFAULT 0"),
    ("fecha_ultima_sincronizacion", "TEXT", "TEXT"),
    ("ultima_resolucion_tasa", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
    ("notas_conexion", "TEXT DEFAULT ''", "TEXT DEFAULT ''"),
]

CREATE_DS67_EVENTOS_PG = """
CREATE TABLE IF NOT EXISTS sgsst_ds67_eventos (
    id BIGSERIAL PRIMARY KEY,
    fecha_dictamen TEXT NOT NULL,
    categoria TEXT NOT NULL,
    tipo TEXT NOT NULL,
    valor_ds67 NUMERIC NOT NULL,
    computable BOOLEAN DEFAULT TRUE,
    detalle TEXT DEFAULT '',
    cliente_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);
"""

CREATE_DS67_EVENTOS_SQLITE = """
CREATE TABLE IF NOT EXISTS sgsst_ds67_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_dictamen TEXT NOT NULL,
    categoria TEXT NOT NULL,
    tipo TEXT NOT NULL,
    valor_ds67 REAL NOT NULL,
    computable INTEGER DEFAULT 1,
    detalle TEXT DEFAULT '',
    cliente_key TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
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
            execute_fn(CREATE_DS67_CONFIG_PG)
            _ensure_ds67_config_columns(execute_fn, db_backend)
            execute_fn(CREATE_DS67_EVENTOS_PG)
            execute_fn("CREATE INDEX IF NOT EXISTS idx_ds67_eventos_cliente_fecha ON sgsst_ds67_eventos(cliente_key, fecha_dictamen)")
            execute_fn(CREATE_CUMPLIMIENTO_PG)
        else:
            execute_fn(CREATE_ESTADISTICAS_SQLITE)
            execute_fn(CREATE_DS67_CONFIG_SQLITE)
            _ensure_ds67_config_columns(execute_fn, db_backend)
            execute_fn(CREATE_DS67_EVENTOS_SQLITE)
            execute_fn("CREATE INDEX IF NOT EXISTS idx_ds67_eventos_cliente_fecha ON sgsst_ds67_eventos(cliente_key, fecha_dictamen)")
            execute_fn(CREATE_CUMPLIMIENTO_SQLITE)
    except Exception:
        pass


def _ensure_ds67_config_columns(execute_fn, db_backend="postgres"):
    """Backfill DS67 configuration columns in databases created by older versions."""
    for column, pg_definition, sqlite_definition in DS67_CONFIG_EXTRA_COLUMNS:
        try:
            if db_backend == "postgres":
                execute_fn(f"ALTER TABLE IF EXISTS sgsst_ds67_config ADD COLUMN IF NOT EXISTS {column} {pg_definition}")
            else:
                execute_fn(f"ALTER TABLE sgsst_ds67_config ADD COLUMN {column} {sqlite_definition}")
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


def calcular_registro_mensual_tasas(df_stats: pd.DataFrame) -> pd.DataFrame:
    """Return the monthly rate register used by accidentability and DS 67 views."""
    columns = [
        "Periodo", "Trabajadores", "HHT", "Acc. CTP", "Acc. STP",
        "Días perdidos", "Enf. profesionales", "Trayecto", "Fatales",
        "Tasa frecuencia", "Tasa gravedad", "Tasa siniestralidad", "Tasa temporal DS 67",
    ]
    if df_stats is None or df_stats.empty:
        return pd.DataFrame(columns=columns)

    work = df_stats.copy()
    numeric_defaults = {
        "anio": 0,
        "mes": 0,
        "trabajadores_promedio": 0,
        "horas_hombre_trabajadas": 0,
        "accidentes_con_tiempo_perdido": 0,
        "accidentes_sin_tiempo_perdido": 0,
        "dias_perdidos": 0,
        "enfermedades_profesionales": 0,
        "accidentes_trayecto": 0,
        "accidentes_fatales": 0,
    }
    for col, default in numeric_defaults.items():
        if col not in work.columns:
            work[col] = default
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(default)

    rows = []
    for _, row in work.sort_values(["anio", "mes"]).iterrows():
        workers = float(row["trabajadores_promedio"])
        hht = float(row["horas_hombre_trabajadas"])
        acc_ctp = float(row["accidentes_con_tiempo_perdido"])
        dias = float(row["dias_perdidos"])
        tasa_frecuencia = _round_half_up(acc_ctp * 1_000_000 / hht, 2) if hht > 0 else 0.0
        tasa_gravedad = _round_half_up(dias * 1_000_000 / hht, 2) if hht > 0 else 0.0
        tasa_siniestralidad = _round_half_up(dias * 100 / workers, 2) if workers > 0 else 0.0
        rows.append({
            "Periodo": f"{int(row['anio'])}-{int(row['mes']):02d}",
            "Trabajadores": int(workers),
            "HHT": int(hht),
            "Acc. CTP": int(row["accidentes_con_tiempo_perdido"]),
            "Acc. STP": int(row["accidentes_sin_tiempo_perdido"]),
            "Días perdidos": int(dias),
            "Enf. profesionales": int(row["enfermedades_profesionales"]),
            "Trayecto": int(row["accidentes_trayecto"]),
            "Fatales": int(row["accidentes_fatales"]),
            "Tasa frecuencia": tasa_frecuencia,
            "Tasa gravedad": tasa_gravedad,
            "Tasa siniestralidad": tasa_siniestralidad,
            "Tasa temporal DS 67": tasa_siniestralidad,
        })
    return pd.DataFrame(rows, columns=columns)


def _round_half_up(value: float, decimals: int = 0) -> float:
    """Apply the decimal rounding rule used by article 2 of DS 67."""
    quant = Decimal("1") if decimals == 0 else Decimal("1." + ("0" * decimals))
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def _weekly_hours_chile_for_day(day: date) -> float:
    """Legal ordinary weekly hours in Chile for the date, following Ley 21.561 schedule."""
    if day >= date(2028, 4, 26):
        return 40.0
    if day >= date(2026, 4, 26):
        return 42.0
    if day >= date(2024, 4, 26):
        return 44.0
    return 45.0


def horas_hombre_mensuales_estandar(
    trabajadores: int | float,
    anio: int,
    mes: int,
    standard: str = HHT_STANDARD_MUTUAL_180,
    horas_persona_mes: int | float | None = None,
) -> int:
    """Estimate monthly man-hours from workforce and the selected mutuality/working-hour standard."""
    workers = max(0.0, float(trabajadores or 0))
    standard = str(standard or HHT_STANDARD_MUTUAL_180)
    if workers <= 0:
        return 0
    if standard == HHT_STANDARD_CUSTOM:
        per_worker = max(0.0, float(horas_persona_mes or 0))
    elif standard == HHT_STANDARD_LEGAL_CHILE:
        start = date(int(anio), int(mes), 1)
        end = date(int(anio) + (1 if int(mes) == 12 else 0), 1 if int(mes) == 12 else int(mes) + 1, 1)
        per_worker = 0.0
        day = start
        while day < end:
            per_worker += _weekly_hours_chile_for_day(day) / 7
            day += timedelta(days=1)
    else:
        per_worker = 180.0
    return int(_round_half_up(workers * per_worker, 0))


def cotizacion_adicional_ds67(tasa_siniestralidad_total: float, elevar_un_tramo: bool = False) -> float:
    """Map the total accident rate to the official article 5 premium table."""
    tasa = max(0, int(_round_half_up(tasa_siniestralidad_total, 0)))
    index = len(DS67_COTIZACION_TABLA) - 1
    for idx, (limite, _cotizacion) in enumerate(DS67_COTIZACION_TABLA):
        if limite is None or tasa <= limite:
            index = idx
            break
    if elevar_un_tramo and index < len(DS67_COTIZACION_TABLA) - 1:
        index += 1
    return float(DS67_COTIZACION_TABLA[index][1])


def tasa_invalideces_muertes_ds67(promedio_factores: float) -> int:
    """Map the average disability/death factor to the article 2(j) rate."""
    factor = max(0.0, _round_half_up(promedio_factores, 2))
    for limite, tasa in DS67_INVALIDEZ_MUERTE_TABLA:
        if limite is None or factor <= limite:
            return int(tasa)
    return 385


def periodos_evaluacion_ds67(anio_evaluacion: int, cantidad: int = 3) -> list[dict]:
    """Return the two or three annual July-June periods evaluated by DS 67."""
    cantidad = 2 if int(cantidad) == 2 else 3
    periodos = []
    for offset in range(cantidad):
        fin_anio = int(anio_evaluacion) - offset
        inicio = date(fin_anio - 1, 7, 1)
        fin = date(fin_anio, 6, 30)
        periodos.append({
            "periodo": f"{inicio.year}-{fin.year}",
            "inicio": inicio,
            "fin": fin,
        })
    return periodos


def calcular_evaluacion_ds67(
    df_stats: pd.DataFrame,
    df_eventos: pd.DataFrame,
    anio_evaluacion: int,
    cantidad_periodos: int = 3,
    dias_simulados: dict[str, int] | None = None,
    elevar_por_muerte_prevenible: bool = False,
) -> dict:
    """Calculate the DS 67 estimate from monthly payroll and permanent events."""
    stats = df_stats.copy() if df_stats is not None else pd.DataFrame()
    eventos = df_eventos.copy() if df_eventos is not None else pd.DataFrame()
    dias_simulados = dias_simulados or {}

    if not stats.empty:
        stats["anio"] = pd.to_numeric(stats.get("anio"), errors="coerce")
        stats["mes"] = pd.to_numeric(stats.get("mes"), errors="coerce")
        stats["trabajadores_promedio"] = pd.to_numeric(stats.get("trabajadores_promedio"), errors="coerce").fillna(0)
        stats["dias_perdidos"] = pd.to_numeric(stats.get("dias_perdidos"), errors="coerce").fillna(0)
        stats["fecha_mes"] = pd.to_datetime(
            dict(year=stats["anio"], month=stats["mes"], day=1), errors="coerce"
        )

    if not eventos.empty:
        eventos["fecha_evento"] = pd.to_datetime(eventos.get("fecha_dictamen"), errors="coerce")
        eventos["valor_ds67"] = pd.to_numeric(eventos.get("valor_ds67"), errors="coerce").fillna(0)
        computables = eventos["computable"] if "computable" in eventos.columns else pd.Series(True, index=eventos.index)
        eventos["es_computable"] = computables.apply(
            lambda value: str(value).strip().lower() not in {"0", "false", "no", "none", ""}
        )

    detalle_periodos = []
    for periodo in periodos_evaluacion_ds67(anio_evaluacion, cantidad_periodos):
        inicio_ts = pd.Timestamp(periodo["inicio"])
        fin_ts = pd.Timestamp(periodo["fin"])
        if stats.empty:
            mensual = pd.DataFrame()
        else:
            mensual = stats[(stats["fecha_mes"] >= inicio_ts) & (stats["fecha_mes"] <= fin_ts)]

        meses = int(mensual[["anio", "mes"]].drop_duplicates().shape[0]) if not mensual.empty else 0
        promedio_trabajadores = _round_half_up(float(mensual["trabajadores_promedio"].sum()) / 12, 2) if not mensual.empty else 0.0
        dias_reales = int(max(0, mensual["dias_perdidos"].sum())) if not mensual.empty else 0
        dias_usados = int(max(0, dias_simulados.get(periodo["periodo"], dias_reales)))
        tasa_temporal = _round_half_up((dias_usados * 100 / promedio_trabajadores), 2) if promedio_trabajadores > 0 else 0.0

        if eventos.empty:
            eventos_periodo = pd.DataFrame()
        else:
            eventos_periodo = eventos[
                (eventos["fecha_evento"] >= inicio_ts)
                & (eventos["fecha_evento"] <= fin_ts)
                & eventos["es_computable"]
            ]
        valor_eventos = float(eventos_periodo["valor_ds67"].sum()) if not eventos_periodo.empty else 0.0
        factor_invalidez = _round_half_up((valor_eventos * 100 / promedio_trabajadores), 2) if promedio_trabajadores > 0 else 0.0

        detalle_periodos.append({
            "periodo": periodo["periodo"],
            "inicio": periodo["inicio"],
            "fin": periodo["fin"],
            "meses_con_datos": meses,
            "promedio_trabajadores": promedio_trabajadores,
            "dias_perdidos_reales": dias_reales,
            "dias_perdidos_usados": dias_usados,
            "tasa_temporal": tasa_temporal,
            "valor_invalideces_muertes": _round_half_up(valor_eventos, 2),
            "factor_invalideces_muertes": factor_invalidez,
        })

    divisor = len(detalle_periodos) or 1
    tasa_promedio_temporal = int(_round_half_up(sum(p["tasa_temporal"] for p in detalle_periodos) / divisor, 0))
    promedio_factores = _round_half_up(sum(p["factor_invalideces_muertes"] for p in detalle_periodos) / divisor, 2)
    tasa_invalideces_muertes = tasa_invalideces_muertes_ds67(promedio_factores)
    tasa_total = int(tasa_promedio_temporal + tasa_invalideces_muertes)
    cotizacion_adicional = cotizacion_adicional_ds67(tasa_total, elevar_por_muerte_prevenible)

    return {
        "periodos": detalle_periodos,
        "tasa_promedio_temporal": tasa_promedio_temporal,
        "promedio_factores": promedio_factores,
        "tasa_invalideces_muertes": tasa_invalideces_muertes,
        "tasa_siniestralidad_total": tasa_total,
        "cotizacion_adicional": cotizacion_adicional,
        "cotizacion_base": COTIZACION_BASE,
        "cotizacion_total": _round_half_up(COTIZACION_BASE + cotizacion_adicional, 2),
        "meses_con_datos": sum(p["meses_con_datos"] for p in detalle_periodos),
        "meses_requeridos": len(detalle_periodos) * 12,
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

    existing_df = fetch_df(
        "SELECT * FROM sgsst_estadisticas_mensuales WHERE anio=? AND mes=? AND COALESCE(cliente_key,'')=?",
        (int(anio), int(mes), str(cliente_key)),
    )
    existing_row = existing_df.iloc[0].to_dict() if existing_df is not None and not existing_df.empty else {}
    existing = existing_row.get("id")

    def _int_or_zero(value):
        try:
            return int(float(value)) if pd.notna(value) else 0
        except (TypeError, ValueError):
            return 0

    # If the official monthly record is still empty, use operational events as a
    # suggestion. The user can reconcile these values with the mutuality record.
    suggested = {}
    if not existing:
        month_start = date(int(anio), int(mes), 1)
        month_end = date(int(anio) + (1 if int(mes) == 12 else 0), 1 if int(mes) == 12 else int(mes) + 1, 1)
        suggested_df = fetch_df(
            """
            SELECT
                SUM(CASE WHEN tipo='ACCIDENTE DEL TRABAJO' AND COALESCE(dias_perdidos,0)>0 THEN 1 ELSE 0 END) AS accidentes_ctp,
                SUM(CASE WHEN tipo='ACCIDENTE DEL TRABAJO' AND COALESCE(dias_perdidos,0)=0 THEN 1 ELSE 0 END) AS accidentes_stp,
                SUM(CASE WHEN tipo IN ('ACCIDENTE DEL TRABAJO','ENFERMEDAD PROFESIONAL') THEN COALESCE(dias_perdidos,0) ELSE 0 END) AS dias_perdidos,
                SUM(CASE WHEN tipo='ENFERMEDAD PROFESIONAL' THEN 1 ELSE 0 END) AS enfermedades,
                SUM(CASE WHEN tipo='ACCIDENTE DE TRAYECTO' THEN 1 ELSE 0 END) AS trayectos
            FROM sgsst_incidentes
            WHERE fecha>=? AND fecha<? AND COALESCE(cliente_key,'')=?
            """,
            (month_start.isoformat(), month_end.isoformat(), str(cliente_key)),
        )
        if suggested_df is not None and not suggested_df.empty:
            suggested = suggested_df.iloc[0].to_dict()

    defaults = {
        "trabajadores_promedio": _int_or_zero(existing_row.get("trabajadores_promedio")),
        "horas_hombre_trabajadas": _int_or_zero(existing_row.get("horas_hombre_trabajadas")),
        "accidentes_con_tiempo_perdido": _int_or_zero(existing_row.get("accidentes_con_tiempo_perdido", suggested.get("accidentes_ctp"))),
        "accidentes_sin_tiempo_perdido": _int_or_zero(existing_row.get("accidentes_sin_tiempo_perdido", suggested.get("accidentes_stp"))),
        "dias_perdidos": _int_or_zero(existing_row.get("dias_perdidos", suggested.get("dias_perdidos"))),
        "enfermedades_profesionales": _int_or_zero(existing_row.get("enfermedades_profesionales", suggested.get("enfermedades"))),
        "accidentes_trayecto": _int_or_zero(existing_row.get("accidentes_trayecto", suggested.get("trayectos"))),
        "accidentes_fatales": _int_or_zero(existing_row.get("accidentes_fatales")),
    }

    if suggested and not existing:
        st.caption("Valores sugeridos desde Accidentes e incidentes. Confírmalos con el registro del organismo administrador antes de guardar.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        trab_prom = st.number_input("Trabajadores con cotización o subsidio", min_value=0, value=defaults["trabajadores_promedio"], key=K(f"est_trab_{int(anio)}_{int(mes)}"), help="Número de personas con remuneración imponible o subsidio durante el mes.")
        acc_ctp = st.number_input("Accidentes del trabajo con tiempo perdido", min_value=0, value=defaults["accidentes_con_tiempo_perdido"], key=K(f"est_acc_ctp_{int(anio)}_{int(mes)}"))
    with c2:
        auto_hht = st.checkbox(
            "Calcular HHT automático",
            value=not bool(defaults["horas_hombre_trabajadas"]),
            key=K(f"est_hht_auto_{int(anio)}_{int(mes)}"),
        )
        hht_standard = st.selectbox(
            "Estándar HHT",
            HHT_STANDARD_OPTIONS,
            index=0,
            key=K(f"est_hht_standard_{int(anio)}_{int(mes)}"),
            disabled=not auto_hht,
        )
        custom_hours = 180
        if auto_hht and hht_standard == HHT_STANDARD_CUSTOM:
            custom_hours = st.number_input(
                "Horas por trabajador/mes",
                min_value=0,
                value=180,
                step=1,
                key=K(f"est_hht_custom_{int(anio)}_{int(mes)}"),
            )
        hht_calculadas = horas_hombre_mensuales_estandar(trab_prom, int(anio), int(mes), hht_standard, custom_hours)
        if auto_hht:
            hht = hht_calculadas
            st.metric("Horas hombre calculadas", f"{hht:,.0f}")
        else:
            hht = st.number_input(
                "Horas hombre trabajadas",
                min_value=0,
                value=defaults["horas_hombre_trabajadas"],
                step=100,
                key=K(f"est_hht_{int(anio)}_{int(mes)}"),
                help="Usa horas reales informadas por la empresa o mutualidad.",
            )
        acc_stp = st.number_input("Accidentes del trabajo sin tiempo perdido", min_value=0, value=defaults["accidentes_sin_tiempo_perdido"], key=K(f"est_acc_stp_{int(anio)}_{int(mes)}"))
    with c3:
        dias = st.number_input("Días perdidos computables DS 67", min_value=0, value=defaults["dias_perdidos"], key=K(f"est_dias_{int(anio)}_{int(mes)}"), help="Días con incapacidad temporal por accidente del trabajo o enfermedad profesional. Excluye trayecto y eventos de otra entidad empleadora.")
        enf_prof = st.number_input("Enfermedades profesionales", min_value=0, value=defaults["enfermedades_profesionales"], key=K(f"est_enf_{int(anio)}_{int(mes)}"))
    with c4:
        acc_tray = st.number_input("Accidentes de trayecto (no computables)", min_value=0, value=defaults["accidentes_trayecto"], key=K(f"est_tray_{int(anio)}_{int(mes)}"))
        acc_fat = st.number_input("Accidentes fatales", min_value=0, value=defaults["accidentes_fatales"], key=K(f"est_fat_{int(anio)}_{int(mes)}"))

    _btn_label = "Actualizar registro" if existing else "Guardar registro"
    if st.button(f"💾 {_btn_label}", key=K(f"est_save_{int(anio)}_{int(mes)}"), type="primary", use_container_width=True):
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


def _render_ds67_monthly_registry(st, fetch_df, execute, K, cliente_key: str, periodos: list[dict], stats_df: pd.DataFrame):
    """Monthly DS 67 register embedded in the cotization workflow."""
    st.markdown("#### Registro mensual de tasas")
    st.caption(
        "Ingresa cada mes la dotación, horas trabajadas, accidentes y días perdidos. "
        "La tabla calcula automáticamente las tasas y alimenta la simulación DS 67."
    )

    if not periodos:
        st.info("Selecciona un proceso de evaluación para cargar meses DS 67.")
        return

    def _int_or_zero(value):
        try:
            return int(float(value)) if pd.notna(value) else 0
        except (TypeError, ValueError):
            return 0

    period_labels = [p["periodo"] for p in periodos]
    selected_label = st.selectbox(
        "Período anual julio-junio",
        period_labels,
        index=0,
        key=K("ds67_reg_periodo"),
        help="El DS 67 evalúa períodos anuales de julio a junio.",
    )
    selected_period = next((p for p in periodos if p["periodo"] == selected_label), periodos[0])
    month_range = pd.date_range(selected_period["inicio"], selected_period["fin"], freq="MS")
    month_options = [f"{m.year}-{m.month:02d}" for m in month_range]
    current_month = f"{date.today().year}-{date.today().month:02d}"
    month_index = month_options.index(current_month) if current_month in month_options else len(month_options) - 1
    selected_month = st.selectbox("Mes a registrar", month_options, index=month_index, key=K("ds67_reg_mes"))
    anio, mes = [int(part) for part in selected_month.split("-")]

    existing_df = fetch_df(
        "SELECT * FROM sgsst_estadisticas_mensuales WHERE anio=? AND mes=? AND COALESCE(cliente_key,'')=?",
        (int(anio), int(mes), str(cliente_key)),
    )
    existing_row = existing_df.iloc[0].to_dict() if existing_df is not None and not existing_df.empty else {}
    existing = existing_row.get("id")

    suggested = {}
    if not existing:
        month_start = date(int(anio), int(mes), 1)
        month_end = date(int(anio) + (1 if int(mes) == 12 else 0), 1 if int(mes) == 12 else int(mes) + 1, 1)
        suggested_df = fetch_df(
            """
            SELECT
                SUM(CASE WHEN tipo='ACCIDENTE DEL TRABAJO' AND COALESCE(dias_perdidos,0)>0 THEN 1 ELSE 0 END) AS accidentes_ctp,
                SUM(CASE WHEN tipo='ACCIDENTE DEL TRABAJO' AND COALESCE(dias_perdidos,0)=0 THEN 1 ELSE 0 END) AS accidentes_stp,
                SUM(CASE WHEN tipo IN ('ACCIDENTE DEL TRABAJO','ENFERMEDAD PROFESIONAL') THEN COALESCE(dias_perdidos,0) ELSE 0 END) AS dias_perdidos,
                SUM(CASE WHEN tipo='ENFERMEDAD PROFESIONAL' THEN 1 ELSE 0 END) AS enfermedades,
                SUM(CASE WHEN tipo='ACCIDENTE DE TRAYECTO' THEN 1 ELSE 0 END) AS trayectos
            FROM sgsst_incidentes
            WHERE fecha>=? AND fecha<? AND COALESCE(cliente_key,'')=?
            """,
            (month_start.isoformat(), month_end.isoformat(), str(cliente_key)),
        )
        if suggested_df is not None and not suggested_df.empty:
            suggested = suggested_df.iloc[0].to_dict()

    defaults = {
        "trabajadores_promedio": _int_or_zero(existing_row.get("trabajadores_promedio")),
        "horas_hombre_trabajadas": _int_or_zero(existing_row.get("horas_hombre_trabajadas")),
        "accidentes_con_tiempo_perdido": _int_or_zero(existing_row.get("accidentes_con_tiempo_perdido", suggested.get("accidentes_ctp"))),
        "accidentes_sin_tiempo_perdido": _int_or_zero(existing_row.get("accidentes_sin_tiempo_perdido", suggested.get("accidentes_stp"))),
        "dias_perdidos": _int_or_zero(existing_row.get("dias_perdidos", suggested.get("dias_perdidos"))),
        "enfermedades_profesionales": _int_or_zero(existing_row.get("enfermedades_profesionales", suggested.get("enfermedades"))),
        "accidentes_trayecto": _int_or_zero(existing_row.get("accidentes_trayecto", suggested.get("trayectos"))),
        "accidentes_fatales": _int_or_zero(existing_row.get("accidentes_fatales")),
    }

    with st.container(border=True):
        if suggested and not existing:
            st.caption("Valores sugeridos desde incidentes internos. Antes de guardar, concílialos con el certificado o nómina mensual de la mutualidad.")

        f1, f2, f3, f4 = st.columns(4)
        with f1:
            trab_prom = st.number_input("Trabajadores cotizados", min_value=0, value=defaults["trabajadores_promedio"], key=K(f"ds67_m_trab_{anio}_{mes}"))
            acc_ctp = st.number_input("Acc. con tiempo perdido", min_value=0, value=defaults["accidentes_con_tiempo_perdido"], key=K(f"ds67_m_acc_ctp_{anio}_{mes}"))
        with f2:
            auto_hht = st.checkbox(
                "Calcular HHT automático",
                value=not bool(defaults["horas_hombre_trabajadas"]),
                key=K(f"ds67_m_hht_auto_{anio}_{mes}"),
            )
            hht_standard = st.selectbox(
                "Estándar HHT",
                HHT_STANDARD_OPTIONS,
                index=0,
                key=K(f"ds67_m_hht_standard_{anio}_{mes}"),
                disabled=not auto_hht,
            )
            custom_hours = 180
            if auto_hht and hht_standard == HHT_STANDARD_CUSTOM:
                custom_hours = st.number_input(
                    "Horas por trabajador/mes",
                    min_value=0,
                    value=180,
                    step=1,
                    key=K(f"ds67_m_hht_custom_{anio}_{mes}"),
                )
            hht_calculadas = horas_hombre_mensuales_estandar(trab_prom, int(anio), int(mes), hht_standard, custom_hours)
            if auto_hht:
                hht = hht_calculadas
                st.metric("Horas hombre calculadas", f"{hht:,.0f}")
            else:
                hht = st.number_input(
                    "Horas hombre trabajadas",
                    min_value=0,
                    value=defaults["horas_hombre_trabajadas"],
                    step=100,
                    key=K(f"ds67_m_hht_{anio}_{mes}"),
                    help="Usa horas reales informadas por la empresa o mutualidad.",
                )
            acc_stp = st.number_input("Acc. sin tiempo perdido", min_value=0, value=defaults["accidentes_sin_tiempo_perdido"], key=K(f"ds67_m_acc_stp_{anio}_{mes}"))
        with f3:
            dias = st.number_input("Días perdidos DS 67", min_value=0, value=defaults["dias_perdidos"], key=K(f"ds67_m_dias_{anio}_{mes}"))
            enf_prof = st.number_input("Enfermedades profesionales", min_value=0, value=defaults["enfermedades_profesionales"], key=K(f"ds67_m_enf_{anio}_{mes}"))
        with f4:
            acc_tray = st.number_input("Trayecto no computable", min_value=0, value=defaults["accidentes_trayecto"], key=K(f"ds67_m_tray_{anio}_{mes}"))
            acc_fat = st.number_input("Accidentes fatales", min_value=0, value=defaults["accidentes_fatales"], key=K(f"ds67_m_fat_{anio}_{mes}"))

        tasa_frecuencia = _round_half_up(float(acc_ctp) * 1_000_000 / float(hht), 2) if float(hht) > 0 else 0.0
        tasa_gravedad = _round_half_up(float(dias) * 1_000_000 / float(hht), 2) if float(hht) > 0 else 0.0
        tasa_siniestralidad = _round_half_up(float(dias) * 100 / float(trab_prom), 2) if float(trab_prom) > 0 else 0.0
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Tasa frecuencia", tasa_frecuencia)
        p2.metric("Tasa gravedad", tasa_gravedad)
        p3.metric("Tasa siniestralidad", tasa_siniestralidad)
        p4.metric("Tasa temporal DS 67", tasa_siniestralidad)

        _btn_label = "Actualizar mes" if existing else "Guardar mes"
        if st.button(f"Guardar registro mensual: {selected_month}", key=K(f"ds67_m_save_{anio}_{mes}"), type="primary", use_container_width=True):
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
            st.success(f"{_btn_label}: {selected_month}.")
            st.rerun()

    registro_df = calcular_registro_mensual_tasas(stats_df)
    if registro_df.empty:
        st.info("Aún no hay meses registrados para el proceso seleccionado.")
        return

    meses_cargados = int(registro_df.shape[0])
    total_dias = int(registro_df["Días perdidos"].sum())
    total_acc_ctp = int(registro_df["Acc. CTP"].sum())
    promedio_trab = _round_half_up(float(registro_df["Trabajadores"].sum()) / max(1, meses_cargados), 2)
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Meses cargados", f"{meses_cargados}/12")
    r2.metric("Promedio trabajadores", promedio_trab)
    r3.metric("Acc. CTP período", total_acc_ctp)
    r4.metric("Días perdidos período", total_dias)

    st.dataframe(registro_df, use_container_width=True, hide_index=True)


def render_tab_cotizacion(st, fetch_df, fetch_value, execute, K, cliente_key="", company=None):
    """Tab: DS 67 simulator based on actual company records."""
    company = company or {}
    st.markdown("### 💰 Evaluación y simulación DS 67")
    st.caption(
        "Estimación de la cotización adicional diferenciada con datos mensuales reales. "
        "La tasa definitiva siempre es fijada por el organismo administrador o la autoridad competente."
    )
    st.markdown(
        "[Texto oficial DS 67](https://www.bcn.cl/leychile/navegar?idNorma=159800) · "
        "[Cálculo SUSESO](https://www.suseso.cl/613/w3-article-480660.html)"
    )

    def _as_bool(value) -> bool:
        return str(value).strip().lower() not in {"0", "false", "no", "none", ""}

    def _as_date(value, fallback: date) -> date:
        parsed = pd.to_datetime(value, errors="coerce")
        return parsed.date() if pd.notna(parsed) else fallback

    cfg_df = fetch_df(
        "SELECT * FROM sgsst_ds67_config WHERE COALESCE(cliente_key,'')=?",
        (str(cliente_key),),
    )
    cfg = cfg_df.iloc[0].to_dict() if cfg_df is not None and not cfg_df.empty else {}
    default_adhesion = date(max(2000, date.today().year - 5), 1, 1)

    next_process = date.today().year if date.today().year % 2 == 1 else date.today().year + 1
    process_years = list(range(2021, max(next_process + 5, 2030), 2))
    process_index = process_years.index(next_process) if next_process in process_years else len(process_years) - 1

    def _cfg_text(name: str, fallback: str = "") -> str:
        value = cfg.get(name)
        if value is None or str(value).strip().lower() in {"nan", "none"}:
            return str(fallback or "")
        text = str(value).strip()
        return text if text else str(fallback or "")

    def _option_index(options: list[str], value: str, default: int = 0) -> int:
        try:
            return options.index(str(value or ""))
        except ValueError:
            return default

    empresa_razon_default = _cfg_text("empresa_razon_social", company.get("razon_social") or "")
    empresa_rut_default = _cfg_text("empresa_rut", company.get("rut") or "")
    empresa_actividad_default = _cfg_text("empresa_actividad", company.get("actividad") or "")
    empresa_ciiu_default = _cfg_text("empresa_ciiu", company.get("ciiu") or "")
    empresa_contacto_default = _cfg_text("empresa_contacto_ds67", company.get("prevencionista") or "")
    mutualidad_default = _cfg_text("mutualidad_nombre", company.get("organismo_admin") or "")

    st.markdown("#### Empresa y mutualidad")
    with st.container(border=True):
        st.caption("Base de datos para preparar el proceso DS 67, conciliar antecedentes con la mutualidad adherida y simular la rebaja de cotización adicional.")

        e1, e2, e3 = st.columns([1.4, 0.8, 1])
        with e1:
            empresa_razon_social = st.text_input(
                "Razón social evaluada",
                value=empresa_razon_default,
                key=K("ds67_empresa_razon"),
                placeholder="SOCIEDAD / EMPRESA",
            )
            empresa_actividad = st.text_input(
                "Actividad económica",
                value=empresa_actividad_default,
                key=K("ds67_empresa_actividad"),
                placeholder="Ej: Forestal, servicios, transporte",
            )
        with e2:
            empresa_rut = st.text_input(
                "RUT empresa",
                value=empresa_rut_default,
                key=K("ds67_empresa_rut"),
                placeholder="12.345.678-5",
            )
            empresa_ciiu = st.text_input(
                "CIIU / código actividad",
                value=empresa_ciiu_default,
                key=K("ds67_empresa_ciiu"),
                placeholder="Opcional",
            )
        with e3:
            empresa_contacto_ds67 = st.text_input(
                "Responsable interno DS 67",
                value=empresa_contacto_default,
                key=K("ds67_empresa_contacto"),
                placeholder="Prevencionista / RRHH / Gerencia",
            )
            numero_adherente = st.text_input(
                "N° adherente / afiliación",
                value=_cfg_text("numero_adherente"),
                key=K("ds67_numero_adherente"),
                placeholder="Código entregado por la mutualidad",
            )

        mutualidad_options = ["Mutual de Seguridad", "ACHS", "IST", "ISL", "Otra / por definir"]
        if mutualidad_default and mutualidad_default not in mutualidad_options:
            mutualidad_options.insert(0, mutualidad_default)
        m1, m2, m3 = st.columns([1, 1, 1])
        with m1:
            mutualidad_seleccion = st.selectbox(
                "Mutualidad / organismo administrador",
                mutualidad_options,
                index=_option_index(mutualidad_options, mutualidad_default),
                key=K("ds67_mutualidad_nombre"),
            )
            if mutualidad_seleccion == "Otra / por definir":
                mutualidad_nombre = st.text_input(
                    "Nombre de la mutualidad",
                    value="" if mutualidad_default in mutualidad_options else mutualidad_default,
                    key=K("ds67_mutualidad_otra"),
                    placeholder="Nombre organismo administrador",
                )
            else:
                mutualidad_nombre = mutualidad_seleccion
            mutualidad_codigo = st.text_input(
                "Código / convenio mutualidad",
                value=_cfg_text("mutualidad_codigo"),
                key=K("ds67_mutualidad_codigo"),
                placeholder="Opcional",
            )
        with m2:
            sucursal_mutual = st.text_input(
                "Sucursal o agencia",
                value=_cfg_text("sucursal_mutual"),
                key=K("ds67_sucursal_mutual"),
                placeholder="Ej: Osorno, Puerto Montt",
            )
            ejecutivo_mutual = st.text_input(
                "Ejecutivo mutualidad",
                value=_cfg_text("ejecutivo_mutual"),
                key=K("ds67_ejecutivo_mutual"),
                placeholder="Nombre contacto",
            )
        with m3:
            correo_mutual = st.text_input(
                "Correo mutualidad",
                value=_cfg_text("correo_mutual"),
                key=K("ds67_correo_mutual"),
                placeholder="contacto@mutualidad.cl",
            )
            telefono_mutual = st.text_input(
                "Teléfono mutualidad",
                value=_cfg_text("telefono_mutual"),
                key=K("ds67_telefono_mutual"),
                placeholder="+56 9 ...",
            )

        c1, c2, c3 = st.columns([1, 1, 1])
        conexion_modos = ["Manual controlado", "Portal mutualidad", "Archivo conciliado", "API directa", "Pendiente"]
        conexion_estados = ["PENDIENTE", "DATOS INCOMPLETOS", "CONFIGURADA", "AUTORIZADA", "SINCRONIZADA", "OBSERVADA"]
        with c1:
            conexion_modo = st.selectbox(
                "Modo de conexión",
                conexion_modos,
                index=_option_index(conexion_modos, _cfg_text("conexion_modo", "Manual controlado")),
                key=K("ds67_conexion_modo"),
                help="La API directa requiere endpoint, autorización y referencia de credencial. No se guarda una clave secreta en texto plano.",
            )
            conexion_estado = st.selectbox(
                "Estado gestión mutualidad",
                conexion_estados,
                index=_option_index(conexion_estados, _cfg_text("conexion_estado", "PENDIENTE")),
                key=K("ds67_conexion_estado"),
            )
        with c2:
            portal_mutual_url = st.text_input(
                "Portal mutualidad",
                value=_cfg_text("portal_mutual_url"),
                key=K("ds67_portal_mutual"),
                placeholder="https://...",
            )
            api_endpoint = st.text_input(
                "Endpoint API / integración",
                value=_cfg_text("api_endpoint"),
                key=K("ds67_api_endpoint"),
                placeholder="https://api.mutualidad.cl/...",
            )
        with c3:
            credencial_ref = st.text_input(
                "Referencia credencial",
                value=_cfg_text("credencial_ref"),
                key=K("ds67_credencial_ref"),
                placeholder="Ej: secrets.MUTUAL_DS67_TOKEN",
                help="Guarda solo el alias o referencia. La clave real debe quedar en un gestor seguro o Streamlit Secrets.",
            )
            autorizacion_intercambio = st.checkbox(
                "Autorización de intercambio de datos vigente",
                value=_as_bool(cfg.get("autorizacion_intercambio")),
                key=K("ds67_autorizacion_intercambio"),
            )

        s1, s2, s3 = st.columns([1, 1, 1])
        with s1:
            registrar_sync = st.checkbox(
                "Registrar última sincronización",
                value=bool(_cfg_text("fecha_ultima_sincronizacion")),
                key=K("ds67_registrar_sync"),
            )
            if registrar_sync:
                fecha_ultima_sync = st.date_input(
                    "Fecha última sincronización",
                    value=_as_date(cfg.get("fecha_ultima_sincronizacion"), date.today()),
                    key=K("ds67_ultima_sync"),
                )
                fecha_ultima_sync_value = fecha_ultima_sync.isoformat()
            else:
                fecha_ultima_sync_value = ""
        with s2:
            ultima_resolucion_tasa = st.text_input(
                "Resolución / carta tasa",
                value=_cfg_text("ultima_resolucion_tasa"),
                key=K("ds67_resolucion_tasa"),
                placeholder="Ej: Resolución proceso 2025",
            )
        with s3:
            notas_conexion = st.text_area(
                "Notas de conexión",
                value=_cfg_text("notas_conexion"),
                key=K("ds67_notas_conexion"),
                height=88,
                placeholder="Pendientes, credenciales, fecha solicitada, observaciones de la mutualidad",
            )

        empresa_ok = all(str(v or "").strip() for v in [empresa_razon_social, empresa_rut, empresa_actividad])
        mutualidad_ok = bool(str(mutualidad_nombre or "").strip()) and bool(str(numero_adherente or "").strip())
        api_ok = conexion_modo != "API directa" or (bool(str(api_endpoint or "").strip()) and bool(str(credencial_ref or "").strip()))
        conexion_lista = mutualidad_ok and bool(autorizacion_intercambio) and api_ok
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Ficha empresa", "Completa" if empresa_ok else "Pendiente")
        k2.metric("Mutualidad", "Identificada" if mutualidad_ok else "Pendiente")
        k3.metric("Conexión", "Lista" if conexion_lista else "Por completar")
        k4.metric("Estado", conexion_estado)

        if st.button("Validar configuración mutualidad", use_container_width=True, key=K("ds67_validar_conexion")):
            faltantes = []
            if not empresa_ok:
                faltantes.append("razón social, RUT o actividad")
            if not mutualidad_ok:
                faltantes.append("mutualidad y N° adherente")
            if conexion_modo == "API directa" and not api_ok:
                faltantes.append("endpoint API y referencia de credencial")
            if not autorizacion_intercambio:
                faltantes.append("autorización de intercambio de datos")
            if faltantes:
                st.warning("Configuración incompleta: falta " + ", ".join(faltantes) + ".")
            else:
                st.success("Configuración lista para conciliar antecedentes DS 67 con la mutualidad adherida.")

    st.markdown("#### Evaluación DS 67")
    c1, c2, c3 = st.columns(3)
    with c1:
        anio_evaluacion = st.selectbox("Proceso de evaluación", process_years, index=process_index, key=K("ds67_anio"))
        fecha_adhesion = st.date_input(
            "Fecha de adhesión al Seguro Ley 16.744",
            value=_as_date(cfg.get("fecha_adhesion"), default_adhesion),
            key=K("ds67_adhesion"),
        )
    with c2:
        tasa_vigente = st.number_input(
            "Cotización adicional vigente (%)",
            min_value=0.0, max_value=6.8, value=float(cfg.get("tasa_adicional_vigente") or 0), step=0.01,
            key=K("ds67_tasa_vigente"),
        )
        remuneracion_imponible = st.number_input(
            "Remuneración imponible mensual total ($)",
            min_value=0, value=int(float(cfg.get("remuneracion_imponible_mensual") or 0)), step=100000,
            key=K("ds67_remuneracion"),
        )
    with c3:
        cotizaciones_al_dia = st.checkbox(
            "Cotizaciones Ley 16.744 al día",
            value=_as_bool(cfg.get("cotizaciones_al_dia")), key=K("ds67_cotizaciones_ok"),
        )
        sgsst_acreditado = st.checkbox(
            "SG-SST acreditado durante el último período anual",
            value=_as_bool(cfg.get("sgsst_acreditado")), key=K("ds67_sgsst_ok"),
        )
        muerte_prevenible = st.checkbox(
            "El organismo confirmó muerte atribuible a falta de medidas preventivas",
            value=_as_bool(cfg.get("muerte_prevenible_confirmada")), key=K("ds67_muerte_prevenible"),
            help="Art. 5 DS 67: eleva la cotización al tramo inmediatamente superior cuando la investigación del organismo administrador así lo concluye.",
        )

    if st.button("Guardar datos DS 67 y mutualidad", type="primary", use_container_width=True, key=K("ds67_save_config")):
        now = datetime.now().isoformat(timespec="seconds")
        payload = {
            "empresa_razon_social": str(empresa_razon_social or "").strip(),
            "empresa_rut": str(empresa_rut or "").strip(),
            "empresa_actividad": str(empresa_actividad or "").strip(),
            "empresa_ciiu": str(empresa_ciiu or "").strip(),
            "empresa_contacto_ds67": str(empresa_contacto_ds67 or "").strip(),
            "fecha_adhesion": fecha_adhesion.isoformat(),
            "tasa_adicional_vigente": float(tasa_vigente),
            "remuneracion_imponible_mensual": int(remuneracion_imponible),
            "mutualidad_nombre": str(mutualidad_nombre or "").strip(),
            "mutualidad_codigo": str(mutualidad_codigo or "").strip(),
            "numero_adherente": str(numero_adherente or "").strip(),
            "sucursal_mutual": str(sucursal_mutual or "").strip(),
            "ejecutivo_mutual": str(ejecutivo_mutual or "").strip(),
            "correo_mutual": str(correo_mutual or "").strip(),
            "telefono_mutual": str(telefono_mutual or "").strip(),
            "portal_mutual_url": str(portal_mutual_url or "").strip(),
            "conexion_modo": str(conexion_modo or "").strip(),
            "conexion_estado": str(conexion_estado or "").strip(),
            "api_endpoint": str(api_endpoint or "").strip(),
            "credencial_ref": str(credencial_ref or "").strip(),
            "autorizacion_intercambio": bool(autorizacion_intercambio),
            "fecha_ultima_sincronizacion": str(fecha_ultima_sync_value or "").strip(),
            "ultima_resolucion_tasa": str(ultima_resolucion_tasa or "").strip(),
            "notas_conexion": str(notas_conexion or "").strip(),
            "cotizaciones_al_dia": bool(cotizaciones_al_dia),
            "sgsst_acreditado": bool(sgsst_acreditado),
            "muerte_prevenible_confirmada": bool(muerte_prevenible),
            "updated_at": now,
        }
        columns = list(payload.keys())
        values = tuple(payload[col] for col in columns)
        if cfg.get("id"):
            set_clause = ", ".join(f"{col}=?" for col in columns)
            execute(
                f"UPDATE sgsst_ds67_config SET {set_clause} WHERE id=? AND COALESCE(cliente_key,'')=?",
                values + (int(cfg["id"]), str(cliente_key)),
            )
        else:
            insert_cols = ["cliente_key"] + columns
            placeholders = ",".join("?" for _ in insert_cols)
            execute(
                f"INSERT INTO sgsst_ds67_config ({','.join(insert_cols)}) VALUES({placeholders})",
                (str(cliente_key),) + values,
            )
        st.success("Datos DS 67 y conexión con mutualidad guardados.")
        st.rerun()

    corte_evaluacion = date(int(anio_evaluacion), 7, 1)
    if fecha_adhesion <= date(int(anio_evaluacion) - 3, 7, 1):
        cantidad_periodos = 3
        antiguedad_suficiente = True
    elif fecha_adhesion <= date(int(anio_evaluacion) - 2, 7, 1):
        cantidad_periodos = 2
        antiguedad_suficiente = True
    else:
        cantidad_periodos = 2
        antiguedad_suficiente = False

    periodos = periodos_evaluacion_ds67(int(anio_evaluacion), cantidad_periodos)
    inicio_datos = min(p["inicio"] for p in periodos)
    fin_datos = max(p["fin"] for p in periodos)
    stats_df = fetch_df(
        """SELECT * FROM sgsst_estadisticas_mensuales
           WHERE COALESCE(cliente_key,'')=?
             AND ((anio>? OR (anio=? AND mes>=7)) AND (anio<? OR (anio=? AND mes<=6)))
           ORDER BY anio, mes""",
        (str(cliente_key), inicio_datos.year, inicio_datos.year, fin_datos.year, fin_datos.year),
    )
    eventos_df = fetch_df(
        """SELECT id, fecha_dictamen, categoria, tipo, valor_ds67, computable, detalle
           FROM sgsst_ds67_eventos
           WHERE COALESCE(cliente_key,'')=? AND fecha_dictamen>=? AND fecha_dictamen<=?
           ORDER BY fecha_dictamen DESC, id DESC""",
        (str(cliente_key), inicio_datos.isoformat(), fin_datos.isoformat()),
    )

    st.divider()
    _render_ds67_monthly_registry(st, fetch_df, execute, K, str(cliente_key), periodos, stats_df)

    st.divider()
    st.markdown("#### Invalideces y muertes computables")
    with st.expander("Registrar o revisar eventos permanentes", expanded=eventos_df is None or eventos_df.empty):
        if eventos_df is not None and not eventos_df.empty:
            show_events = eventos_df.copy()
            show_events["computable"] = show_events["computable"].apply(lambda value: "Sí" if _as_bool(value) else "No")
            st.dataframe(show_events.rename(columns={
                "fecha_dictamen": "Fecha", "categoria": "Categoría", "tipo": "Tipo",
                "valor_ds67": "Valor DS 67", "computable": "Computable", "detalle": "Detalle",
            }), use_container_width=True, hide_index=True)

        e1, e2 = st.columns(2)
        with e1:
            evento_fecha = st.date_input("Fecha de dictamen o muerte", value=date.today(), key=K("ds67_evento_fecha"))
            evento_categoria = st.selectbox("Categoría DS 67", list(DS67_EVENTOS.keys()), key=K("ds67_evento_categoria"))
        with e2:
            evento_computable = st.checkbox("Incluir en esta evaluación", value=True, key=K("ds67_evento_computable"))
            evento_detalle = st.text_input("Referencia / resolución", key=K("ds67_evento_detalle"))
        if st.button("Agregar evento DS 67", use_container_width=True, key=K("ds67_add_evento")):
            tipo_evento, valor_evento = DS67_EVENTOS[evento_categoria]
            execute(
                """INSERT INTO sgsst_ds67_eventos
                   (fecha_dictamen, categoria, tipo, valor_ds67, computable, detalle, cliente_key, created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (evento_fecha.isoformat(), evento_categoria, tipo_evento, float(valor_evento), bool(evento_computable), evento_detalle.strip(), str(cliente_key), datetime.now().isoformat(timespec="seconds")),
            )
            st.success("Evento DS 67 registrado.")
            st.rerun()

        if eventos_df is not None and not eventos_df.empty:
            delete_id = st.selectbox(
                "Evento a eliminar",
                eventos_df["id"].tolist(),
                format_func=lambda value: f"#{int(value)} · {eventos_df[eventos_df['id']==value].iloc[0]['categoria']} · {eventos_df[eventos_df['id']==value].iloc[0]['fecha_dictamen']}",
                key=K("ds67_delete_id"),
            )
            confirm_delete = st.checkbox("Confirmar eliminación", key=K("ds67_confirm_delete"))
            if st.button("Eliminar evento", disabled=not confirm_delete, key=K("ds67_delete_evento")):
                execute("DELETE FROM sgsst_ds67_eventos WHERE id=? AND COALESCE(cliente_key,'')=?", (int(delete_id), str(cliente_key)))
                st.success("Evento eliminado.")
                st.rerun()

    resultado_real = calcular_evaluacion_ds67(
        stats_df, eventos_df, int(anio_evaluacion), cantidad_periodos,
        elevar_por_muerte_prevenible=bool(muerte_prevenible),
    )
    datos_completos = resultado_real["meses_con_datos"] == resultado_real["meses_requeridos"]
    acceso_rebaja = antiguedad_suficiente and cotizaciones_al_dia and sgsst_acreditado

    st.markdown("#### Resultado con datos registrados")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Tasa temporal promedio", str(resultado_real["tasa_promedio_temporal"]))
    r2.metric("Tasa invalideces / muertes", str(resultado_real["tasa_invalideces_muertes"]))
    r3.metric("Siniestralidad total", str(resultado_real["tasa_siniestralidad_total"]))
    r4.metric("Cotización adicional estimada", f"{resultado_real['cotizacion_adicional']:.2f}%")

    detalle_df = pd.DataFrame(resultado_real["periodos"])
    if not detalle_df.empty:
        st.dataframe(detalle_df.rename(columns={
            "periodo": "Período anual", "inicio": "Desde", "fin": "Hasta",
            "meses_con_datos": "Meses cargados", "promedio_trabajadores": "Promedio trabajadores",
            "dias_perdidos_reales": "Días reales", "dias_perdidos_usados": "Días usados",
            "tasa_temporal": "Tasa temporal", "valor_invalideces_muertes": "Valor inv./muertes",
            "factor_invalideces_muertes": "Factor inv./muertes",
        }), use_container_width=True, hide_index=True)

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Antigüedad evaluable", "Sí" if antiguedad_suficiente else "No")
    e2.metric("Cobertura mensual", f"{resultado_real['meses_con_datos']}/{resultado_real['meses_requeridos']}")
    e3.metric("Cotizaciones al día", "Sí" if cotizaciones_al_dia else "No")
    e4.metric("SG-SST acreditado", "Sí" if sgsst_acreditado else "No")

    if not antiguedad_suficiente:
        st.warning("La entidad no completa dos períodos anuales consecutivos al 1 de julio; el DS 67 indica mantener la tasa vigente.")
    elif not datos_completos:
        st.warning("La estimación está incompleta: faltan meses del período de evaluación. Los meses sin registro se muestran como cero, pero no deben interpretarse como ausencia de siniestros.")
    if resultado_real["cotizacion_adicional"] < float(tasa_vigente) and not acceso_rebaja:
        st.warning("Existe una rebaja estadística potencial, pero no es exigible mientras falten cotizaciones al día o la acreditación del SG-SST.")

    diferencia_real = float(tasa_vigente) - resultado_real["cotizacion_adicional"]
    ahorro_mensual_real = max(0.0, diferencia_real) * float(remuneracion_imponible) / 100
    if diferencia_real > 0:
        st.success(f"Rebaja potencial frente a la tasa vigente: **{diferencia_real:.2f} puntos** · ahorro mensual estimado **${ahorro_mensual_real:,.0f}**.")
    elif diferencia_real < 0:
        st.error(f"Recargo potencial frente a la tasa vigente: **{abs(diferencia_real):.2f} puntos**.")
    else:
        st.info("La estimación mantiene la tasa adicional vigente.")

    st.divider()
    st.markdown("#### Escenario de rebaja")
    st.caption("Modifica los días perdidos totales esperados por período. Las invalideces y muertes registradas se mantienen porque no pueden eliminarse de la evaluación.")
    dias_simulados = {}
    sim_cols = st.columns(len(resultado_real["periodos"]))
    for idx, periodo in enumerate(resultado_real["periodos"]):
        with sim_cols[idx]:
            dias_simulados[periodo["periodo"]] = st.number_input(
                f"Días {periodo['periodo']}", min_value=0,
                value=int(periodo["dias_perdidos_reales"]), step=1,
                key=K(f"ds67_sim_dias_{periodo['periodo']}"),
            )

    resultado_simulado = calcular_evaluacion_ds67(
        stats_df, eventos_df, int(anio_evaluacion), cantidad_periodos,
        dias_simulados=dias_simulados,
        elevar_por_muerte_prevenible=bool(muerte_prevenible),
    )
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Siniestralidad simulada", str(resultado_simulado["tasa_siniestralidad_total"]))
    s2.metric("Adicional simulada", f"{resultado_simulado['cotizacion_adicional']:.2f}%")
    s3.metric("Total Ley 16.744", f"{resultado_simulado['cotizacion_total']:.2f}%", help="0,90% básico más la cotización adicional DS 67.")
    ahorro_simulado = max(0.0, float(tasa_vigente) - resultado_simulado["cotizacion_adicional"]) * float(remuneracion_imponible) / 100
    s4.metric("Ahorro mensual", f"${ahorro_simulado:,.0f}")

    tabla_tramos = []
    minimo = 0
    for limite, tasa in DS67_COTIZACION_TABLA:
        rango = f"{minimo} a {limite}" if limite is not None else f"{minimo} y más"
        tabla_tramos.append({"Tasa de siniestralidad total": rango, "Cotización adicional": f"{tasa:.2f}%"})
        minimo = int(limite) + 1 if limite is not None else minimo
    with st.expander("Tabla oficial de conversión DS 67"):
        st.dataframe(pd.DataFrame(tabla_tramos), use_container_width=True, hide_index=True)


def render_tab_cumplimiento_legal(st, fetch_df, fetch_value, execute, K, cliente_key=""):
    """Tab: diagnóstico normativo del SG-SST."""
    st.markdown("### ⚖️ Diagnóstico normativo")
    st.caption("Evalúa el cumplimiento de tu empresa según Ley 16.744, DS 44, DS 594 y DS 67. Marca cada requisito y registra la evidencia.")

    norma_tab = st.radio(
        "Normativa",
        ["Ley 16.744", "DS 594", "DS 44", "DS 67", "Requisitos Mutualidad"],
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
    elif norma_tab == "DS 67":
        requisitos = REQUISITOS_DS67
        norma_key = "ds67"
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
