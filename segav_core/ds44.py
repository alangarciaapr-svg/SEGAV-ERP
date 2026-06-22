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


# Campos clave de la ficha de empresa para el dashboard de inicio.
# (clave_en_bd, etiqueta_visible)
COMPANY_PROFILE_FIELDS = [
    ("razon_social", "Razón social"),
    ("rut", "RUT"),
    ("direccion", "Dirección"),
    ("comuna", "Comuna"),
    ("region", "Región"),
    ("actividad", "Actividad / rubro"),
    ("ciiu", "Código de actividad (CIIU)"),
    ("organismo_admin", "Organismo administrador (mutualidad)"),
    ("representantes", "Representante legal"),
    ("prevencionista", "Prevencionista / Experto"),
    ("telefono", "Teléfono"),
    ("email", "Email de contacto"),
    ("canal_denuncias", "Canal de denuncias"),
    ("politica_version", "Política SST (versión)"),
    ("politica_fecha", "Política SST (fecha)"),
]


def company_profile_status(company: dict | None) -> dict:
    """Evalúa qué tan completa está la ficha de empresa.

    Devuelve {pct, total, completos, filled (list (key,label,valor)),
    missing (list (key,label))}. Un campo cuenta como completo si tiene un
    valor no vacío (distinto de '', None, '0' para numéricos no aplica aquí).
    """
    company = company or {}
    filled = []
    missing = []
    for key, label in COMPANY_PROFILE_FIELDS:
        val = company.get(key)
        sval = "" if val is None else str(val).strip()
        if sval and sval.lower() not in ("none", "nan"):
            filled.append((key, label, sval))
        else:
            missing.append((key, label))
    total = len(COMPANY_PROFILE_FIELDS)
    completos = len(filled)
    pct = int(round((completos / total) * 100)) if total else 0
    return {"pct": pct, "total": total, "completos": completos, "filled": filled, "missing": missing}


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
         "norma": "DS 44 Arts. 22 y 64", "detalle": "Compromiso de la entidad empleadora con la protección, el cumplimiento normativo y la mejora continua.", "auto": False},
        {"key": "iper", "nombre": "Matriz de Identificación de Peligros y Evaluación de Riesgos (IPER/MIPER)",
         "norma": "DS 44 Art. 7", "detalle": "Identificación de peligros y evaluación de riesgos por proceso, tarea y puesto de trabajo, con enfoque de género.", "auto": True},
        {"key": "pdtp", "nombre": "Programa de Trabajo Preventivo / Programa Anual",
         "norma": "DS 44 Arts. 8 y 14", "detalle": "Medidas preventivas y correctivas con responsables, plazos, control y evaluación anual.", "auto": True},
        {"key": "capacitaciones", "nombre": "Programa Anual de Capacitaciones",
         "norma": "DS 44 Art. 16", "detalle": "Capacitación preventiva de al menos 8 horas, con periodicidad máxima de dos años y registro de asistencia.", "auto": True},
        {"key": "odi", "nombre": "Obligación de Informar los Riesgos (ODI / Derecho a Saber)",
         "norma": "DS 44 Art. 15", "detalle": "Información previa al inicio de labores y cada vez que cambien procesos, tecnologías, materiales o sustancias.", "auto": False},
        {"key": "mapas_riesgo", "nombre": "Mapas de riesgo del lugar de trabajo",
         "norma": "DS 44 Art. 62", "detalle": "Representación visible de los principales riesgos en cada centro o lugar de trabajo.", "auto": False},
        {"key": "autoevaluacion", "nombre": "Autoevaluación / diagnóstico del sistema",
         "norma": "DS 44 Arts. 14 y 64", "detalle": "Diagnóstico periódico y evaluación anual del programa para sostener la mejora continua.", "auto": False},
        {"key": "riohs", "nombre": "Reglamento Interno de Higiene y Seguridad",
         "norma": "DS 44 Arts. 56 a 61", "detalle": "Toda entidad empleadora debe mantenerlo vigente, entregarlo gratuitamente y revisarlo al menos una vez al año.", "auto": True},
    ]

    if 10 <= n <= 25:
        elementos.append({
            "key": "delegado_sst", "nombre": "Delegado de Seguridad y Salud en el Trabajo",
            "norma": "DS 44 Art. 66", "detalle": "En cada centro de trabajo con 10 a 25 personas, cuando no funcione un Comité Paritario.", "auto": False,
        })

    if n >= 26:
        elementos.append({
            "key": "cphs", "nombre": "Comité Paritario de Higiene y Seguridad (CPHS)",
            "norma": "DS 44 Art. 23 / Ley 16.744 Art. 66", "detalle": "Obligatorio en la empresa, sucursal, agencia o centro de trabajo con más de 25 personas.", "auto": True,
        })
        elementos.append({
            "key": "cphs_actas", "nombre": "Actas mensuales del CPHS",
            "norma": "DS 44", "detalle": "Funcionamiento y acuerdos del Comité documentados mediante actas.", "auto": True,
        })

    if n > 100:
        elementos.append({
            "key": "depto_prevencion", "nombre": "Departamento de Prevención de Riesgos (Experto)",
            "norma": "DS 44 Art. 50 / Ley 16.744 Art. 66", "detalle": "Obligatorio con más de 100 personas trabajadoras y dirigido por un experto.", "auto": False,
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
