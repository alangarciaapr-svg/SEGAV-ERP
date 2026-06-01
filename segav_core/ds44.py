"""Lógica del DS 44 (Reglamento de Gestión Preventiva de los Riesgos Laborales).

Vigente desde el 1 de febrero de 2025; derogó los DS 40 y DS 54 de 1969.
Las exigencias escalan según el número de personas trabajadoras de la entidad.

Este módulo contiene SOLO lógica pura (sin Streamlit ni base de datos) para que
sea fácil de testear: dada una cantidad de trabajadores, devuelve el tramo
aplicable y la lista de elementos exigibles del sistema de gestión.
"""

from __future__ import annotations


# Estados posibles de cada elemento en la autoevaluación
ESTADOS_AUTOEVAL = ["Cumple", "En proceso", "No cumple", "No aplica"]


def worker_tier(n: int) -> dict:
    """Devuelve el tramo DS 44 según número de trabajadores.

    Tramos:
      - < 10        : micro
      - 10 a 25     : pequeña
      - 26 a 100    : mediana
      - > 100       : grande
    """
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    if n < 10:
        return {"key": "micro", "label": "Menos de 10 trabajadores", "rango": "1–9"}
    if n <= 25:
        return {"key": "pequena", "label": "Entre 10 y 25 trabajadores", "rango": "10–25"}
    if n <= 100:
        return {"key": "mediana", "label": "Entre 26 y 100 trabajadores", "rango": "26–100"}
    return {"key": "grande", "label": "Más de 100 trabajadores", "rango": "101+"}


def required_elements(n: int) -> list[dict]:
    """Lista de elementos exigibles del sistema de gestión según el tramo.

    Cada elemento: {key, nombre, norma, detalle, auto} donde `auto` indica si
    el sistema puede detectar su presencia automáticamente (True) o requiere
    verificación manual del usuario (False).
    """
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0

    elementos: list[dict] = [
        {"key": "politica_sst", "nombre": "Política de Seguridad y Salud en el Trabajo",
         "norma": "DS 44 Art. 4", "detalle": "Documento firmado por la dirección, difundido a los trabajadores.", "auto": False},
        {"key": "iper", "nombre": "Matriz de Identificación de Peligros y Evaluación de Riesgos (IPER/MIPER)",
         "norma": "DS 44", "detalle": "Identificación de peligros, evaluación de riesgos y medidas de control por cargo/proceso.", "auto": True},
        {"key": "pdtp", "nombre": "Programa de Trabajo Preventivo / Programa Anual",
         "norma": "DS 44", "detalle": "Actividades preventivas con responsables y plazos.", "auto": True},
        {"key": "capacitaciones", "nombre": "Programa Anual de Capacitaciones",
         "norma": "DS 44 / Ley 16.744", "detalle": "Plan de capacitación en SST con registro de asistencia.", "auto": True},
        {"key": "odi", "nombre": "Obligación de Informar los Riesgos (ODI / Derecho a Saber)",
         "norma": "DS 44 Art. 14", "detalle": "Informar riesgos a cada trabajador desde el primer contrato.", "auto": False},
        {"key": "mapas_riesgo", "nombre": "Mapas de riesgo del lugar de trabajo",
         "norma": "DS 44", "detalle": "Representación de los riesgos por área/faena.", "auto": False},
        {"key": "autoevaluacion", "nombre": "Autoevaluación / diagnóstico del sistema",
         "norma": "DS 44", "detalle": "Instrumento de autoevaluación periódica (esta misma pauta).", "auto": False},
    ]

    if n >= 10:
        elementos.append({
            "key": "riohs", "nombre": "Reglamento Interno de Orden, Higiene y Seguridad (RIOHS)",
            "norma": "Código del Trabajo Art. 153", "detalle": "Obligatorio desde 10 trabajadores; debe citar el DS 44 vigente.", "auto": True,
        })

    if 10 <= n <= 25:
        elementos.append({
            "key": "delegado_sst", "nombre": "Delegado de Seguridad y Salud en el Trabajo",
            "norma": "DS 44", "detalle": "En faenas de 10 a 25 trabajadores, en ausencia de Comité Paritario.", "auto": False,
        })

    if n >= 26:
        elementos.append({
            "key": "cphs", "nombre": "Comité Paritario de Higiene y Seguridad (CPHS)",
            "norma": "DS 44 Art. 54", "detalle": "Obligatorio desde 25 trabajadores.", "auto": True,
        })
        elementos.append({
            "key": "cphs_actas", "nombre": "Actas mensuales del CPHS",
            "norma": "DS 44", "detalle": "Sesiones mensuales documentadas en actas.", "auto": True,
        })

    if n > 100:
        elementos.append({
            "key": "depto_prevencion", "nombre": "Departamento de Prevención de Riesgos (Experto)",
            "norma": "DS 44", "detalle": "Obligatorio sobre 100 trabajadores, dirigido por un Experto en Prevención.", "auto": False,
        })

    return elementos


def summarize(estados: dict) -> dict:
    """Resume la autoevaluación.

    `estados`: {elemento_key: estado_str}. Los 'No aplica' se excluyen del
    porcentaje, igual que en una fiscalización. Devuelve conteos y % de avance,
    donde 'Cumple' vale 1, 'En proceso' vale 0.5 y 'No cumple' vale 0.
    """
    aplicables = 0
    puntaje = 0.0
    conteo = {"Cumple": 0, "En proceso": 0, "No cumple": 0, "No aplica": 0}
    for estado in estados.values():
        e = estado if estado in conteo else "No cumple"
        conteo[e] += 1
        if e == "No aplica":
            continue
        aplicables += 1
        if e == "Cumple":
            puntaje += 1.0
        elif e == "En proceso":
            puntaje += 0.5
    pct = int(round((puntaje / aplicables) * 100)) if aplicables > 0 else 0
    return {
        "aplicables": aplicables,
        "pct": pct,
        "cumple": conteo["Cumple"],
        "en_proceso": conteo["En proceso"],
        "no_cumple": conteo["No cumple"],
        "no_aplica": conteo["No aplica"],
        "faltantes": [k for k, v in estados.items() if v == "No cumple"],
    }
