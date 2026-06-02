"""Generador del Expediente de Fiscalización SGSST (PDF).

Reúne ficha de empresa, tramo y autoevaluación DS 44, MIPER, alertas e
inventario de evidencias en un PDF listo para entregar a la DT, Mutual,
MINSAL o empresa mandante.

La función principal recibe datos ya recopilados (dicts y listas) para no
acoplarse a la BD; el ensamblado de datos se hace en la capa de UI.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO


def build_expediente_pdf(*, empresa: dict, tramo: dict, autoeval: list[dict],
                         miper: list[dict], alertas: list[dict],
                         evidencias: list[dict], generado_por: str = "") -> bytes:
    """Construye el expediente en PDF y devuelve los bytes.

    empresa: dict con datos de la ficha.
    tramo: {label, rango} del DS 44.
    autoeval: [{nombre, norma, estado}].
    miper: [{faena, tipo, peligro, riesgo, nivel, estado}].
    alertas: [{tipo, ref, etiqueta}].
    evidencias: [{modulo, referencia, nombre_archivo, created_at}].
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        title="Expediente de Fiscalización SGSST",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13,
                        textColor=colors.HexColor("#1e3a8a"), spaceBefore=14, spaceAfter=6)
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=8, textColor=colors.grey)

    INDIGO = colors.HexColor("#3730a3")
    HEADER_BG = colors.HexColor("#e0e7ff")

    def _p(text, style=normal):
        return Paragraph(str(text if text not in (None, "") else "—"), style)

    def _table(rows, col_widths=None, header=True):
        t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, 0), INDIGO),
            ]
        t.setStyle(TableStyle(style))
        return t

    story = []
    # Portada / cabecera
    story.append(_p("Expediente de Fiscalización SGSST", h1))
    story.append(_p(f"<b>{empresa.get('razon_social') or 'Empresa'}</b> · RUT {empresa.get('rut') or '—'}", normal))
    story.append(_p(f"Generado el {datetime.now().strftime('%d-%m-%Y %H:%M')}" + (f" por {generado_por}" if generado_por else ""), small))
    story.append(_p("Documento de apoyo. La validez del cumplimiento debe ser confirmada por un experto en prevención de riesgos.", small))
    story.append(Spacer(1, 8))

    # 1. Identificación de la empresa
    story.append(_p("1. Identificación de la empresa", h2))
    emp_rows = [
        ["Campo", "Dato"],
        ["Razón social", empresa.get("razon_social") or "—"],
        ["RUT", empresa.get("rut") or "—"],
        ["Dirección", empresa.get("direccion") or "—"],
        ["Comuna / Región", f"{empresa.get('comuna') or '—'} / {empresa.get('region') or '—'}"],
        ["Teléfono / Email", f"{empresa.get('telefono') or '—'} / {empresa.get('email') or '—'}"],
        ["Actividad / CIIU", f"{empresa.get('actividad') or '—'} / {empresa.get('ciiu') or '—'}"],
        ["Organismo administrador", empresa.get("organismo_admin") or "—"],
        ["Representante legal", empresa.get("representantes") or "—"],
        ["Prevencionista / Experto", empresa.get("prevencionista") or "—"],
        ["Tramo DS 44", f"{tramo.get('label','—')} ({tramo.get('rango','—')})"],
    ]
    story.append(_table([[_p(c) for c in r] for r in emp_rows], col_widths=[5 * cm, 11 * cm]))

    # 2. Autoevaluación DS 44
    story.append(_p("2. Autoevaluación DS 44", h2))
    if autoeval:
        rows = [["Elemento", "Norma", "Estado"]]
        for a in autoeval:
            rows.append([a.get("nombre", ""), a.get("norma", ""), a.get("estado", "")])
        story.append(_table([[_p(c) for c in r] for r in rows], col_widths=[8.5 * cm, 4 * cm, 3.5 * cm]))
    else:
        story.append(_p("Sin autoevaluación registrada."))

    # 3. MIPER
    story.append(PageBreak())
    story.append(_p("3. Matriz de Identificación de Peligros y Evaluación de Riesgos (MIPER)", h2))
    if miper:
        rows = [["Faena", "Tipo", "Peligro", "Riesgo", "Nivel", "Estado"]]
        for m in miper:
            rows.append([m.get("faena", ""), m.get("tipo", ""), m.get("peligro", ""),
                         m.get("riesgo", ""), m.get("nivel", ""), m.get("estado", "")])
        story.append(_table([[_p(c) for c in r] for r in rows],
                            col_widths=[2.6 * cm, 2.4 * cm, 3.6 * cm, 3.6 * cm, 2.2 * cm, 1.6 * cm]))
    else:
        story.append(_p("Sin riesgos registrados en la MIPER."))

    # 4. Alertas de vencimiento
    story.append(_p("4. Alertas de vencimiento", h2))
    if alertas:
        rows = [["Tipo", "Referencia", "Estado"]]
        for al in alertas:
            rows.append([al.get("tipo", ""), al.get("ref", ""), al.get("etiqueta", "")])
        story.append(_table([[_p(c) for c in r] for r in rows], col_widths=[5 * cm, 7 * cm, 4 * cm]))
    else:
        story.append(_p("Sin vencimientos próximos ni vencidos."))

    # 5. Inventario de evidencias
    story.append(_p("5. Inventario de evidencias", h2))
    if evidencias:
        rows = [["Módulo", "Referencia", "Archivo", "Fecha"]]
        for e in evidencias:
            rows.append([e.get("modulo", ""), e.get("referencia", ""),
                         e.get("nombre_archivo", ""), str(e.get("created_at", ""))[:16]])
        story.append(_table([[_p(c) for c in r] for r in rows],
                            col_widths=[4 * cm, 4.5 * cm, 5 * cm, 2.5 * cm]))
        story.append(Spacer(1, 4))
        story.append(_p(f"Total de evidencias respaldadas: {len(evidencias)}.", small))
    else:
        story.append(_p("Sin evidencias registradas."))

    doc.build(story)
    return buf.getvalue()
