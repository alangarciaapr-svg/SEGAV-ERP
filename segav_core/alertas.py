"""Lógica de alertas de vencimiento del SGSST (lógica pura, testeable).

Calcula, a partir de una fecha de referencia, el estado de vencimiento de un
ítem (vigente / por vencer / vencido) y agrupa alertas. No toca BD ni Streamlit.
"""

from __future__ import annotations

from datetime import date, datetime


def _to_date(value):
    """Convierte str/date/datetime a date; None si no se puede."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in ("none", "nan"):
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    # ISO con hora
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def estado_vencimiento(fecha_objetivo, hoy=None, dias_aviso: int = 30) -> dict:
    """Clasifica una fecha objetivo respecto a hoy.

    Devuelve {estado, dias, color, etiqueta} donde estado ∈
    {vigente, por_vencer, vencido, sin_fecha}. `dias` es la diferencia
    (negativo = vencido hace N días; positivo = faltan N días).
    """
    hoy = hoy or date.today()
    if isinstance(hoy, datetime):
        hoy = hoy.date()
    f = _to_date(fecha_objetivo)
    if f is None:
        return {"estado": "sin_fecha", "dias": None, "color": "⚪", "etiqueta": "Sin fecha"}
    dias = (f - hoy).days
    if dias < 0:
        return {"estado": "vencido", "dias": dias, "color": "🔴", "etiqueta": f"Vencido hace {abs(dias)} día(s)"}
    if dias <= dias_aviso:
        return {"estado": "por_vencer", "dias": dias, "color": "🟡", "etiqueta": f"Vence en {dias} día(s)"}
    return {"estado": "vigente", "dias": dias, "color": "🟢", "etiqueta": f"Vigente ({dias} días)"}


def revision_anual(fecha_ultima, hoy=None, dias_aviso: int = 30) -> dict:
    """Estado de una revisión anual (p. ej. MIPER): vence al cumplir 1 año.

    Devuelve la misma estructura que estado_vencimiento, calculando la fecha
    objetivo como fecha_ultima + 365 días.
    """
    f = _to_date(fecha_ultima)
    if f is None:
        return {"estado": "sin_fecha", "dias": None, "color": "⚪", "etiqueta": "Sin registro"}
    try:
        objetivo = f.replace(year=f.year + 1)
    except ValueError:
        # 29-feb -> 28-feb del año siguiente
        objetivo = f.replace(year=f.year + 1, day=28)
    return estado_vencimiento(objetivo, hoy=hoy, dias_aviso=dias_aviso)


def resumen_alertas(items: list[dict]) -> dict:
    """Resume una lista de alertas (cada una con clave 'estado').

    Devuelve conteos por estado y el total que requiere atención
    (vencido + por_vencer).
    """
    conteo = {"vigente": 0, "por_vencer": 0, "vencido": 0, "sin_fecha": 0}
    for it in items:
        e = str(it.get("estado") or "sin_fecha")
        if e not in conteo:
            e = "sin_fecha"
        conteo[e] += 1
    conteo["atencion"] = conteo["vencido"] + conteo["por_vencer"]
    conteo["total"] = sum(conteo[k] for k in ("vigente", "por_vencer", "vencido", "sin_fecha"))
    return conteo
