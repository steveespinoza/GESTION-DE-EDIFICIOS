from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import CondPageBreak, SimpleDocTemplate, Spacer, TableStyle

from app.documents.consolidation import Consolidation
from app.documents.pdf import (
    GREEN,
    HEADING,
    LIGHT,
    RENDER_LOCK,
    SMALL,
    data_table,
    paragraph,
    period,
)

NUMBER = ParagraphStyle(
    "ConsolidatedNumber", parent=SMALL, fontSize=8, leading=11, alignment=TA_RIGHT
)
BOLD_NUMBER = ParagraphStyle(
    "ConsolidatedTotal", parent=NUMBER, fontName="ReceiptSansBold"
)


def format_amount(value):
    return format(value, ",.2f").translate(str.maketrans({",": ".", ".": ","}))


def amount(value, *, bold=False):
    return paragraph(format_amount(value), BOLD_NUMBER if bold else NUMBER)


def render_consolidation(report: Consolidation) -> bytes:
    # Share the font lock with individual receipts: TTFont is process-global.
    with RENDER_LOCK:
        return _render_consolidation(report)


def _render_consolidation(report: Consolidation) -> bytes:
    output = BytesIO()
    size = landscape(A4)
    document = SimpleDocTemplate(
        output,
        pagesize=size,
        leftMargin=36,
        rightMargin=36,
        topMargin=67,
        bottomMargin=44,
        title=f"Consolidado mensual - {period(report)}",
        author="Gestión de Edificios",
        pageCompression=1,
    )
    width = size[0] - 72
    totals = report.totals
    story = [
        paragraph(f"CONSOLIDADO MENSUAL · {period(report)}", HEADING),
        paragraph(report.building_name, HEADING),
    ]
    if report.address:
        story.append(paragraph(report.address))
    due_date = (
        report.due_date.strftime("%d/%m/%Y") if report.due_date else "Sin vencimiento"
    )
    generated = report.generated_at.astimezone(ZoneInfo("America/Lima"))
    story += [
        paragraph(
            f"Vencimiento del mes: {due_date} · Vencimientos evaluados al {report.as_of:%d/%m/%Y} (Lima).",
            SMALL,
        ),
        paragraph(
            f"Generado el {generated:%d/%m/%Y a las %H:%M} (Lima) · {len(report.units)} unidades registradas.",
            SMALL,
        ),
        paragraph(
            "Estado vigente al descargar. Incluye pagos y ajustes posteriores al mes elegido; no es un cierre histórico. Todos los importes están expresados en soles (S/).",
            SMALL,
        ),
    ]
    overview = data_table(
        [
            "Pendiente hasta el periodo S/",
            "De ese pendiente, vencido S/",
            "Crédito disponible hoy S/",
        ],
        [
            [
                amount(totals.total_pending, bold=True),
                amount(totals.overdue_balance),
                amount(totals.credit),
            ]
        ],
        [width / 3] * 3,
    )
    story += [
        overview,
        paragraph(
            "El crédito corresponde a todos los periodos y se muestra por separado. El pendiente ya considera sus aplicaciones; no se vuelve a descontar ni se duplican los arrastres.",
            SMALL,
        ),
    ]

    story += [CondPageBreak(110), paragraph("Facturas y cargos del mes", HEADING)]
    service_rows = [
        [
            paragraph(item.service, SMALL),
            amount(item.provider_amount),
            amount(item.adjustment),
            amount(item.amount),
            amount(item.applied),
            amount(item.balance),
        ]
        for item in report.services
    ]
    service_rows.append(
        [
            paragraph("TOTAL DEL MES", SMALL),
            amount(sum(s.provider_amount for s in report.services), bold=True),
            amount(sum(s.adjustment for s in report.services)),
            amount(totals.current_amount, bold=True),
            amount(totals.current_applied),
            amount(totals.current_balance, bold=True),
        ]
    )
    services = data_table(
        [
            "Servicio",
            "Proveedor S/",
            "Ajustes S/",
            "Cargos vigentes S/",
            "Aplicado al mes S/",
            "Pendiente del mes S/",
        ],
        service_rows,
        [width - 5 * 105] + [105] * 5,
    )
    services.setStyle(TableStyle([("BACKGROUND", (0, -1), (-1, -1), LIGHT)]))
    story += [
        services,
        paragraph(
            "Proveedor conserva el importe original de cada factura. Los ajustes corresponden a los cargos de las unidades. Aplicado al mes es la aplicación neta a esos cargos, independientemente de la fecha de recepción del pago.",
            SMALL,
        ),
    ]

    story += [CondPageBreak(120), paragraph("Cargos y saldos por unidad", HEADING)]
    unit_rows = []
    for unit in report.units:
        label = f"Unidad {unit.unit_number}\n{unit.owner_name}"
        if not unit.has_current_charges:
            label += "\nSin cargos del mes"
        unit_rows.append(
            [
                paragraph(label, SMALL),
                amount(unit.current_amount),
                amount(unit.current_applied),
                amount(unit.current_balance),
                amount(unit.previous_balance),
                amount(unit.total_pending, bold=True),
                amount(unit.overdue_balance),
                amount(unit.credit),
            ]
        )
    unit_rows.append(
        [
            paragraph("TOTAL DEL EDIFICIO", SMALL),
            amount(totals.current_amount, bold=True),
            amount(totals.current_applied),
            amount(totals.current_balance),
            amount(totals.previous_balance),
            amount(totals.total_pending, bold=True),
            amount(totals.overdue_balance),
            amount(totals.credit),
        ]
    )
    fields = (
        "current_amount",
        "current_applied",
        "current_balance",
        "previous_balance",
        "total_pending",
        "overdue_balance",
        "credit",
    )
    widths = [
        max(
            80,
            max(
                stringWidth(format_amount(getattr(item, field)), "ReceiptSansBold", 8)
                for item in [*report.units, totals]
            )
            + 16,
        )
        for field in fields
    ]
    units = data_table(
        [
            "Unidad y propietario actual",
            "Cargos del mes S/",
            "Aplicado al mes S/",
            "Pendiente del mes S/",
            "Pendiente anterior S/",
            "Total pendiente S/",
            "De ese total, vencido S/",
            "Crédito actual S/",
        ],
        unit_rows,
        [width - sum(widths), *widths],
    )
    units.setStyle(TableStyle([("BACKGROUND", (0, -1), (-1, -1), LIGHT)]))
    story += [
        units,
        Spacer(1, 9),
        paragraph(
            "El pendiente anterior es el saldo actual de los cargos anteriores al mes elegido. El total excluye cargos posteriores. Las unidades sin cargos del mes también se incluyen, con sus saldos anteriores y crédito actual.",
            SMALL,
        ),
        paragraph(
            "Cada cargo mantiene su vencimiento de origen. Sin fecha no cuenta como vencido; una fecha vence al terminar ese día en Lima. Fuente: facturas, cargos, ajustes, aplicaciones y crédito del estado de cuenta al generar la descarga.",
            SMALL,
        ),
    ]

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(GREEN)
        canvas.rect(0, size[1] - 43, size[0], 43, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("ReceiptSansBold", 12)
        canvas.drawString(36, size[1] - 27, "Gestión de Edificios")
        canvas.setFont("ReceiptSans", 9)
        canvas.drawRightString(size[0] - 36, size[1] - 27, period(report))
        canvas.setFillColor(GREEN)
        canvas.setFont("ReceiptSans", 8)
        canvas.drawString(36, 24, "Consolidado mensual · Uso administrativo")
        canvas.drawRightString(size[0] - 36, 24, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
