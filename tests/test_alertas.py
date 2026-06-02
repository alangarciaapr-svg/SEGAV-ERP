"""Tests de la lógica de alertas de vencimiento."""

from datetime import date

from segav_core import alertas


HOY = date(2026, 6, 1)


def test_vencido():
    r = alertas.estado_vencimiento("2026-05-01", hoy=HOY)
    assert r["estado"] == "vencido"
    assert r["dias"] == -31
    assert r["color"] == "🔴"


def test_por_vencer():
    r = alertas.estado_vencimiento("2026-06-20", hoy=HOY, dias_aviso=30)
    assert r["estado"] == "por_vencer"
    assert r["dias"] == 19


def test_vigente():
    r = alertas.estado_vencimiento("2026-12-01", hoy=HOY)
    assert r["estado"] == "vigente"


def test_sin_fecha():
    assert alertas.estado_vencimiento(None, hoy=HOY)["estado"] == "sin_fecha"
    assert alertas.estado_vencimiento("nan", hoy=HOY)["estado"] == "sin_fecha"
    assert alertas.estado_vencimiento("", hoy=HOY)["estado"] == "sin_fecha"


def test_formatos_fecha():
    assert alertas.estado_vencimiento("01-12-2026", hoy=HOY)["estado"] == "vigente"
    assert alertas.estado_vencimiento("2026-12-01T10:00:00", hoy=HOY)["estado"] == "vigente"


def test_revision_anual():
    # última revisión hace casi un año -> por vencer
    r = alertas.revision_anual("2025-06-20", hoy=HOY)
    assert r["estado"] == "por_vencer"
    # última revisión hace más de un año -> vencida
    r2 = alertas.revision_anual("2025-01-01", hoy=HOY)
    assert r2["estado"] == "vencido"


def test_resumen():
    items = [
        {"estado": "vigente"}, {"estado": "vencido"},
        {"estado": "por_vencer"}, {"estado": "por_vencer"},
        {"estado": "sin_fecha"},
    ]
    r = alertas.resumen_alertas(items)
    assert r["vigente"] == 1
    assert r["vencido"] == 1
    assert r["por_vencer"] == 2
    assert r["atencion"] == 3
    assert r["total"] == 5
