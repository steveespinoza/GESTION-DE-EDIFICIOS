from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.documents.schemas import ReceiptSnapshot

FONT_DIR = Path(reportlab.__file__).parent / "fonts"
RENDER_LOCK = Lock()
pdfmetrics.registerFont(TTFont("ReceiptSans", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("ReceiptSansBold", str(FONT_DIR / "VeraBd.ttf")))
pdfmetrics.registerFontFamily(
    "ReceiptSans", normal="ReceiptSans", bold="ReceiptSansBold"
)
GREEN = colors.HexColor("#15382e")
LIGHT = colors.HexColor("#edf3ef")
MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
BODY = ParagraphStyle(
    "ReceiptBody", fontName="ReceiptSans", fontSize=9, leading=13, spaceAfter=5
)
SMALL = ParagraphStyle("ReceiptSmall", parent=BODY, fontSize=8, leading=11)
NUMBER = ParagraphStyle("ReceiptNumber", parent=SMALL, alignment=TA_RIGHT)
HEADING = ParagraphStyle(
    "ReceiptHeading",
    parent=BODY,
    fontName="ReceiptSansBold",
    fontSize=12,
    leading=16,
    spaceBefore=15,
    spaceAfter=8,
    keepWithNext=False,
)


def period(item) -> str:
    return f"{MONTHS[item.billing_month - 1]} de {item.billing_year}"


def money(value) -> str:
    return "S/ " + format(value, ".2f").replace(".", ",")


def paragraph(text, style=BODY):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def data_table(headers, rows, widths):
    table = Table(
        [[paragraph(header, SMALL) for header in headers], *rows],
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, GREEN),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d9e2dc")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def render_receipt(snapshot: ReceiptSnapshot) -> bytes:
    # ReportLab's registered TTFont objects must not build two PDFs at once.
    with RENDER_LOCK:
        return _render_receipt(snapshot)


def _render_receipt(snapshot: ReceiptSnapshot) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=72,
        bottomMargin=48,
        title=f"Recibo {period(snapshot)} - Unidad {snapshot.unit_number}",
        author="Gestión de Edificios",
        pageCompression=1,
    )
    width = A4[0] - 84
    story = [paragraph(f"RECIBO DE COBRANZA · {period(snapshot)}", HEADING)]

    def section(title):
        story.append(CondPageBreak(100))
        story.append(paragraph(title, HEADING))

    total_style = ParagraphStyle(
        "ReceiptTotal",
        parent=NUMBER,
        fontName="ReceiptSansBold",
        fontSize=13,
        leading=18,
        textColor=GREEN,
    )
    total = Table(
        [
            [
                paragraph("Total pendiente hasta este periodo"),
                paragraph(money(snapshot.total_pending), total_style),
            ]
        ],
        colWidths=[width - 200, 200],
        hAlign="LEFT",
    )
    total.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story += [total, Spacer(1, 10)]
    issued = snapshot.issued_at.astimezone(ZoneInfo("America/Lima")).strftime(
        "%d/%m/%Y %H:%M"
    )
    metadata = [
        ("Edificio", snapshot.building_name),
        ("Unidad", snapshot.unit_number),
        ("Propietario", snapshot.owner_name),
        ("Área", f"{snapshot.area_sqm:.2f} m²"),
        ("Emisión (Lima)", issued),
        (
            "Vencimiento del periodo",
            snapshot.due_date.strftime("%d/%m/%Y")
            if snapshot.due_date
            else "Sin vencimiento definido",
        ),
        ("Versión", str(snapshot.version)),
        ("Emitido por", snapshot.issued_by),
    ]
    if snapshot.address:
        metadata.insert(1, ("Dirección", snapshot.address))
    story.append(
        data_table(
            ["Datos del recibo", ""],
            [[paragraph(label, SMALL), paragraph(value)] for label, value in metadata],
            [145, width - 145],
        )
    )
    story.append(
        paragraph(
            "Saldos vigentes al emitir para este periodo y los anteriores. Las versiones emitidas conservan sus importes y su vencimiento.",
            SMALL,
        )
    )
    section("Cargos del periodo")
    charge_rows = []
    for charge in snapshot.charges:
        description = [charge.service]
        if charge.consumption is not None:
            description += [
                f"Lecturas: {charge.previous_reading:.3f} a {charge.current_reading:.3f} m³",
                f"Consumo propio: {charge.consumption:.3f} m³",
                f"Común original: {money(charge.original_common_amount)}",
            ]
        if charge.adjustment != 0:
            description.append(
                f"Original: {money(charge.original_amount)}; ajuste: {money(charge.adjustment)}"
            )
        charge_rows.append(
            [
                paragraph("\n".join(description), SMALL),
                paragraph(money(charge.amount), NUMBER),
                paragraph(money(charge.applied), NUMBER),
                paragraph(money(charge.balance), NUMBER),
            ]
        )
    story.append(
        data_table(
            ["Servicio y detalle", "Cargo vigente", "Aplicado", "Pendiente"],
            charge_rows,
            [width - 282, 94, 94, 94],
        )
    )
    if snapshot.previous_charges:
        section("Saldo anterior pendiente")
        story.append(
            paragraph(
                "Cada saldo mantiene su periodo y fecha de origen. Los arrastres ya están incluidos una sola vez.",
                SMALL,
            )
        )
        story.append(
            data_table(
                ["Origen", "Vencimiento", "Pendiente"],
                [
                    [
                        paragraph(f"{charge.service}\n{period(charge)}", SMALL),
                        paragraph(
                            charge.due_date.strftime("%d/%m/%Y")
                            if charge.due_date
                            else "Sin vencimiento",
                            SMALL,
                        ),
                        paragraph(money(charge.balance), NUMBER),
                    ]
                    for charge in snapshot.previous_charges
                ],
                [width - 210, 116, 94],
            )
        )
    section("Resumen")
    summary = [
        ("Cargos vigentes del periodo", snapshot.current_amount),
        ("Aplicado a cargos del periodo", snapshot.current_applied),
        ("Pendiente del periodo", snapshot.current_balance),
        ("Saldo anterior pendiente", snapshot.previous_balance),
        ("Total pendiente hasta este periodo", snapshot.total_pending),
        ("De ese pendiente, vencido al emitir", snapshot.overdue_balance),
        ("Crédito disponible de la unidad", snapshot.credit),
    ]
    story.append(
        data_table(
            ["Concepto", "Importe"],
            [
                [paragraph(label), paragraph(money(value), NUMBER)]
                for label, value in summary
            ],
            [width - 120, 120],
        )
    )
    story.append(
        paragraph(
            "El crédito se aplica automáticamente en el sistema. El saldo pendiente ya considera sus aplicaciones; el crédito disponible se muestra por separado.",
            SMALL,
        )
    )
    if snapshot.payments:
        section("Pagos aplicados hasta este periodo")
        story.append(
            data_table(
                ["Fecha y referencia", "Recibido", "Aplicado hasta el periodo"],
                [
                    [
                        paragraph(
                            f"{payment.received_on.strftime('%d/%m/%Y')}\n{payment.reference or 'Sin referencia'}",
                            SMALL,
                        ),
                        paragraph(money(payment.amount), NUMBER),
                        paragraph(money(payment.applied), NUMBER),
                    ]
                    for payment in snapshot.payments
                ],
                [width - 218, 100, 118],
            )
        )
        story.append(
            paragraph(
                "El monto recibido puede cubrir también cargos de periodos posteriores. La columna aplicada muestra únicamente cargos hasta el periodo de este recibo.",
                SMALL,
            )
        )
    section("Instrucciones de pago")
    payment = snapshot.payment_instructions
    instructions = [
        ("Banco", payment.bank_name),
        ("Titular", payment.account_holder),
        ("Cuenta", payment.account_number),
        ("CCI", payment.cci),
        ("Contacto", payment.contact_email),
    ]
    present = [(label, value) for label, value in instructions if value]
    if present:
        story.append(
            data_table(
                ["Dato", "Información"],
                [
                    [paragraph(label, SMALL), paragraph(value)]
                    for label, value in present
                ],
                [100, width - 100],
            )
        )
    else:
        story.append(
            paragraph("El edificio todavía no tiene instrucciones de pago registradas.")
        )
    story += [
        Spacer(1, 8),
        paragraph(f"Motivo de emisión: {snapshot.reason}", SMALL),
        paragraph(f"Identificador: {snapshot.receipt_id}", SMALL),
    ]

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(GREEN)
        canvas.rect(0, A4[1] - 48, A4[0], 48, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("ReceiptSansBold", 12)
        canvas.drawString(42, A4[1] - 30, "Gestión de Edificios")
        canvas.setFillColor(GREEN)
        canvas.setFont("ReceiptSans", 8)
        canvas.drawString(42, 26, f"Recibo de cobranza · Versión {snapshot.version}")
        canvas.drawRightString(A4[0] - 42, 26, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
