from __future__ import annotations

import sqlite3

import pandas as pd

from segav_core.ops_estadisticas import (
    calcular_evaluacion_ds67,
    calcular_registro_mensual_tasas,
    cotizacion_adicional_ds67,
    ensure_estadisticas_tables,
    periodos_evaluacion_ds67,
    tasa_invalideces_muertes_ds67,
)


def _monthly_rows(start: str, periods: int, workers: int, days: int) -> pd.DataFrame:
    months = pd.date_range(start=start, periods=periods, freq="MS")
    return pd.DataFrame(
        {
            "anio": months.year,
            "mes": months.month,
            "trabajadores_promedio": workers,
            "dias_perdidos": days,
        }
    )


def test_ds67_official_premium_boundaries():
    assert cotizacion_adicional_ds67(32) == 0.00
    assert cotizacion_adicional_ds67(33) == 0.34
    assert cotizacion_adicional_ds67(980) == 6.46
    assert cotizacion_adicional_ds67(981) == 6.80
    assert cotizacion_adicional_ds67(33, elevar_un_tramo=True) == 0.68


def test_ds67_disability_death_factor_boundaries():
    assert tasa_invalideces_muertes_ds67(0.10) == 0
    assert tasa_invalideces_muertes_ds67(0.11) == 35
    assert tasa_invalideces_muertes_ds67(2.70) == 350
    assert tasa_invalideces_muertes_ds67(2.71) == 385


def test_ds67_uses_three_july_june_periods():
    periods = periodos_evaluacion_ds67(2025, 3)
    assert [p["periodo"] for p in periods] == ["2024-2025", "2023-2024", "2022-2023"]
    assert str(periods[0]["inicio"]) == "2024-07-01"
    assert str(periods[-1]["fin"]) == "2023-06-30"


def test_ds67_calculation_uses_real_monthly_data_and_legal_rounding():
    stats = _monthly_rows("2022-07-01", 36, workers=10, days=1)
    result = calcular_evaluacion_ds67(stats, pd.DataFrame(), 2025, 3)

    assert result["meses_con_datos"] == 36
    assert result["tasa_promedio_temporal"] == 120
    assert result["tasa_invalideces_muertes"] == 0
    assert result["tasa_siniestralidad_total"] == 120
    assert result["cotizacion_adicional"] == 1.02
    assert result["cotizacion_total"] == 1.92


def test_ds67_simulation_can_reduce_days_without_removing_permanent_events():
    stats = _monthly_rows("2022-07-01", 36, workers=100, days=2)
    events = pd.DataFrame(
        [{
            "fecha_dictamen": "2024-08-15",
            "valor_ds67": 0.50,
            "computable": True,
        }]
    )
    simulated = calcular_evaluacion_ds67(
        stats,
        events,
        2025,
        3,
        dias_simulados={"2024-2025": 0, "2023-2024": 0, "2022-2023": 0},
    )

    assert simulated["tasa_promedio_temporal"] == 0
    assert simulated["promedio_factores"] == 0.17
    assert simulated["tasa_invalideces_muertes"] == 35
    assert simulated["cotizacion_adicional"] == 0.34


def test_ds67_monthly_rate_register_calculates_operational_rates():
    stats = pd.DataFrame(
        [{
            "anio": 2025,
            "mes": 1,
            "trabajadores_promedio": 10,
            "horas_hombre_trabajadas": 2000,
            "accidentes_con_tiempo_perdido": 1,
            "accidentes_sin_tiempo_perdido": 2,
            "dias_perdidos": 2,
            "enfermedades_profesionales": 0,
            "accidentes_trayecto": 1,
            "accidentes_fatales": 0,
        }]
    )

    register = calcular_registro_mensual_tasas(stats)

    assert register.iloc[0]["Periodo"] == "2025-01"
    assert register.iloc[0]["Tasa frecuencia"] == 500.0
    assert register.iloc[0]["Tasa gravedad"] == 1000.0
    assert register.iloc[0]["Tasa siniestralidad"] == 20.0
    assert register.iloc[0]["Tasa temporal DS 67"] == 20.0


def test_ds67_sqlite_schema_creates_configuration_and_event_tables():
    connection = sqlite3.connect(":memory:")

    def execute(sql, params=()):
        connection.execute(sql, params)
        connection.commit()

    ensure_estadisticas_tables(execute, "sqlite")
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "sgsst_estadisticas_mensuales" in tables
    assert "sgsst_ds67_config" in tables
    assert "sgsst_ds67_eventos" in tables
    config_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(sgsst_ds67_config)").fetchall()
    }
    assert "empresa_razon_social" in config_columns
    assert "mutualidad_nombre" in config_columns
    assert "numero_adherente" in config_columns
    assert "conexion_modo" in config_columns
    assert "api_endpoint" in config_columns
    assert "autorizacion_intercambio" in config_columns


def test_ds67_sqlite_schema_migrates_existing_configuration_table():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE sgsst_ds67_config (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_key TEXT NOT NULL DEFAULT '')"
    )
    connection.commit()

    def execute(sql, params=()):
        connection.execute(sql, params)
        connection.commit()

    ensure_estadisticas_tables(execute, "sqlite")
    config_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(sgsst_ds67_config)").fetchall()
    }

    assert "empresa_rut" in config_columns
    assert "fecha_adhesion" in config_columns
    assert "tasa_adicional_vigente" in config_columns
    assert "cotizaciones_al_dia" in config_columns
    assert "mutualidad_codigo" in config_columns
    assert "portal_mutual_url" in config_columns
    assert "credencial_ref" in config_columns
    assert "fecha_ultima_sincronizacion" in config_columns
