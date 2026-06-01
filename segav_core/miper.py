"""Lógica del MIPER según la Guía del ISP (DS 44) — método del Valor Esperado
de la Pérdida (VEP).

VEP = Probabilidad × Consecuencia (rango 1–16, con escalas 1–4).
Solo lógica pura (sin Streamlit ni BD) para poder testearla.

Nota: las escalas y bandas siguen el método VEP de la Guía del ISP / INSHT.
La validación final del nivel de riesgo corresponde al profesional de
prevención de riesgos.
"""

from __future__ import annotations


# Tipos de riesgo según la guía del ISP
TIPOS_RIESGO = [
    "Seguridad",
    "Higiénico",
    "Músculo-esquelético",
    "Psicosocial",
]

# Enfoque de género (DS 44)
GENEROS = ["Ambos", "Hombre", "Mujer", "Otro"]

# Escala de Probabilidad (1–4)
PROBABILIDAD = {
    1: "Baja — muy poco probable, ocurre raras veces",
    2: "Media — podría ocurrir alguna vez",
    3: "Alta — probable, ocurre varias veces",
    4: "Muy alta — casi seguro que ocurre",
}

# Escala de Consecuencia / Severidad (1–4)
CONSECUENCIA = {
    1: "Ligeramente dañino — lesión leve sin baja",
    2: "Dañino — lesión con baja, daño reversible",
    3: "Extremadamente dañino — lesión grave o incapacidad",
    4: "Mortal o catastrófico — fatalidad",
}

# Jerarquía de medidas de control (orden obligatorio de prioridad, DS 44 / ISP)
JERARQUIA_CONTROLES = [
    "1) Eliminación del peligro",
    "2) Sustitución",
    "3) Controles de ingeniería",
    "4) Controles administrativos / señalización",
    "5) Equipos de protección personal (EPP) — última opción",
]


def vep(probabilidad: int, consecuencia: int) -> int:
    """Valor Esperado de la Pérdida = Probabilidad × Consecuencia."""
    try:
        p = max(1, min(4, int(probabilidad)))
        c = max(1, min(4, int(consecuencia)))
    except (TypeError, ValueError):
        return 1
    return p * c


def nivel(vep_valor: int) -> dict:
    """Clasifica el VEP (1–16) en nivel de riesgo, color y acción recomendada.

    Bandas según el método VEP de la guía:
      1–2 Trivial · 3–4 Tolerable · 5–8 Moderado · 9–12 Importante · 13–16 Intolerable
    """
    try:
        v = int(vep_valor)
    except (TypeError, ValueError):
        v = 1
    if v <= 2:
        return {"nivel": "Trivial", "color": "🟢", "tone": "success",
                "accion": "No requiere acción específica."}
    if v <= 4:
        return {"nivel": "Tolerable", "color": "🟢", "tone": "success",
                "accion": "No se necesita mejorar; considerar soluciones más rentables."}
    if v <= 8:
        return {"nivel": "Moderado", "color": "🟡", "tone": "warning",
                "accion": "Reducir el riesgo en un plazo determinado; implementar medidas preventivas."}
    if v <= 12:
        return {"nivel": "Importante", "color": "🟠", "tone": "warning",
                "accion": "No comenzar el trabajo hasta reducir el riesgo; puede requerir recursos considerables."}
    return {"nivel": "Intolerable", "color": "🔴", "tone": "danger",
            "accion": "No debe comenzar ni continuar el trabajo hasta reducir el riesgo."}


def evaluacion(probabilidad: int, consecuencia: int) -> dict:
    """Devuelve VEP + clasificación completa para una combinación P×C."""
    v = vep(probabilidad, consecuencia)
    info = nivel(v)
    info["vep"] = v
    return info
