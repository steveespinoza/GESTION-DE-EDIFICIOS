from datetime import datetime
from decimal import Decimal
from io import BytesIO
from textwrap import wrap
from zoneinfo import ZoneInfo

from xlsxwriter import Workbook

from app.billing.metering import from_milli
from app.collections.service import money
from app.documents.period import period_charges
from app.documents.transparency import Transparency

MONEY = '#,##0.00;[Red](#,##0.00);"—"'
VOLUME = '#,##0.000;[Red](#,##0.000);"—"'
PRECISE = '#,##0.000000;[Red](#,##0.000000);"—"'


def period(item) -> str:
    return f"{item.billing_year}-{item.billing_month:02}"


class Export:
    def __init__(self, workbook):
        self.book = workbook
        base = {"font_name": "Arial", "font_size": 11, "valign": "top"}
        self.text = workbook.add_format({**base, "text_wrap": True})
        self.identifier = workbook.add_format(
            {**base, "text_wrap": True, "num_format": "@", "align": "left"}
        )
        self.title = workbook.add_format(
            {**base, "bold": True, "font_size": 17, "font_color": "#153C45"}
        )
        self.header = workbook.add_format(
            {
                **base,
                "bold": True,
                "bg_color": "#153C45",
                "font_color": "white",
                "text_wrap": True,
            }
        )
        self.label = workbook.add_format({**base, "bold": True, "text_wrap": True})
        self.number = workbook.add_format({**base, "num_format": MONEY})
        self.volume = workbook.add_format({**base, "num_format": VOLUME})
        self.precise = workbook.add_format({**base, "num_format": PRECISE})
        self.date = workbook.add_format(
            {**base, "num_format": "dd/mm/yyyy", "align": "left"}
        )
        self.timestamp = workbook.add_format(
            {**base, "num_format": "dd/mm/yyyy hh:mm", "align": "left"}
        )
        self.total = workbook.add_format(
            {**base, "bold": True, "num_format": MONEY, "bg_color": "#DEF0EC", "top": 1}
        )

    def sheet(self, name, title, note, widths):
        sheet = self.book.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.set_tab_color("#267B76")
        sheet.set_default_row(21)
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width, self.text)
        sheet.merge_range(0, 0, 0, len(widths) - 1, title, self.title)
        sheet.set_row(0, 32)
        if note:
            sheet.merge_range(2, 0, 3, len(widths) - 1, note, self.text)
        sheet.freeze_panes(6, 2 if len(widths) > 4 else 0)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.3, 0.3, 0.4, 0.4)
        sheet.set_footer("&LGestión de Edificios&R&P / &N")
        return sheet

    def headers(self, sheet, row, labels):
        sheet.write_row(row, 0, labels, self.header)
        sheet.set_row(row, 34)

    def fit_text(self, sheet, row, *texts):
        lines = max(
            sum(max(1, len(wrap(line, width=width))) for line in text.split("\n"))
            for text, width in texts
        )
        sheet.set_row(row, min(409, max(21, lines * 16)))

    def formula(self, sheet, row, col, expression, value, total=False, precise=False):
        style = self.total if total else self.precise if precise else self.number
        sheet.write_formula(row, col, expression, style, float(value))


def render_transparency(data: Transparency) -> bytes:
    output = BytesIO()
    with Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        book.set_properties(
            {"title": "Transparencia por unidad", "author": "Gestión de Edificios"}
        )
        export = Export(book)
        statement = data.statement
        selected = f"{data.year}-{data.month:02}"
        current, earlier = period_charges(statement, data.year, data.month)
        charges = [c for c in statement.charges if period(c) <= selected]
        summary = export.sheet(
            "Resumen", "TRANSPARENCIA POR UNIDAD", "", [43, 23, 23, 23]
        )
        for row, label, value in (
            (2, "Edificio", statement.building_name),
            (3, "Unidad", f"N.º {statement.unit_number}"),
            (4, "Periodo de cargos", selected),
        ):
            summary.write(row, 0, label, export.label)
            summary.merge_range(
                row, 1, row, 3, value, export.identifier if row == 3 else export.text
            )
        summary.write(5, 0, "Vencimientos al (Lima)", export.label)
        summary.write_datetime(5, 1, statement.as_of, export.date)
        summary.write(6, 0, "Generado en Lima", export.label)
        summary.write_datetime(
            6,
            1,
            datetime.now(ZoneInfo("America/Lima")).replace(tzinfo=None),
            export.timestamp,
        )
        export.headers(summary, 8, ["Concepto", "Importe (S/)"])
        for row in range(9, 16):
            summary.set_row(row, 32)

        sheet = export.sheet(
            "Cargos",
            "CARGOS Y SALDOS VIGENTES",
            "Fuente: cargos, ajustes y aplicaciones del estado de cuenta. Incluye los cargos hasta el periodo elegido, incluso los anteriores ya pagados. No se suman otra vez los arrastres.",
            [15, 26, 18, 18, 18, 18, 18, 17, 18],
        )
        export.headers(
            sheet,
            5,
            [
                "Periodo",
                "Servicio",
                "Original S/",
                "Ajustes S/",
                "Vigente S/",
                "Aplicado S/",
                "Pendiente S/",
                "Vencimiento",
                "Estado al consultar",
            ],
        )
        for row, charge in enumerate(charges, 6):
            n = row + 1
            sheet.write_row(row, 0, [period(charge), charge.service])
            sheet.write_number(row, 2, charge.original_amount, export.number)
            sheet.write_number(row, 3, charge.adjustment, export.number)
            export.formula(sheet, row, 4, f"=ROUND(C{n}+D{n},2)", charge.amount)
            sheet.write_number(row, 5, charge.applied, export.number)
            export.formula(sheet, row, 6, f"=ROUND(E{n}-F{n},2)", charge.balance)
            if charge.due_date:
                sheet.write_datetime(row, 7, charge.due_date, export.date)
            sheet.write(
                row,
                8,
                "Pagado"
                if charge.balance == 0
                else "Vencido"
                if charge.overdue
                else "Pendiente",
            )
            sheet.write_comment(row, 1, f"Cargo de origen: {charge.id}")
            export.fit_text(sheet, row, (charge.service, 21))
        end = len(charges) + 6
        sheet.autofilter(5, 0, end - 1, 8)
        sheet.repeat_rows(5)
        for row, label, expression, value in (
            (
                9,
                "Cargos del periodo",
                f"=SUMIF('Cargos'!A7:A{end},B5,'Cargos'!E7:E{end})",
                sum(c.amount for c in current),
            ),
            (
                10,
                "Aplicado al periodo",
                f"=SUMIF('Cargos'!A7:A{end},B5,'Cargos'!F7:F{end})",
                sum(c.applied for c in current),
            ),
            (
                11,
                "Pendiente del periodo",
                "=ROUND(B10-B11,2)",
                sum(c.balance for c in current),
            ),
            (
                12,
                "Pendiente anterior",
                f"=SUMIF('Cargos'!A7:A{end},\"<\"&B5,'Cargos'!G7:G{end})",
                sum(c.balance for c in earlier),
            ),
            (
                13,
                "TOTAL PENDIENTE HASTA EL PERIODO",
                "=SUM(B12:B13)",
                sum(c.balance for c in current + earlier),
            ),
            (
                14,
                "De ese pendiente, vencido",
                f"=SUMIF('Cargos'!I7:I{end},\"Vencido\",'Cargos'!G7:G{end})",
                sum(c.balance for c in current + earlier if c.overdue),
            ),
        ):
            summary.write(row, 0, label, export.label)
            export.formula(summary, row, 1, expression, value, total=row == 13)

        repartition_sheet(export, data)
        credit_formula = payments_sheet(export, data)
        summary.write(
            15, 0, "Crédito disponible hoy (todos los periodos)", export.label
        )
        if credit_formula:
            export.formula(summary, 15, 1, credit_formula, statement.credit)
        else:
            summary.write_number(15, 1, 0, export.number)
        for row, note in enumerate(
            [
                "Consulta del estado actual: no reconstruye el saldo que existía al cierre de ese mes. Los pagos y ajustes posteriores ya están reflejados.",
                "El pendiente incluye cargos del periodo elegido y saldos anteriores. Excluye cargos posteriores. El crédito se muestra separado y no se descuenta de nuevo.",
                "El reparto explica solo los cargos del periodo elegido. Los agregados del edificio permiten comprobar el criterio sin revelar datos de otras unidades.",
                "Importes en soles (S/), lecturas en m³. Fuente: registros del sistema al generar esta descarga. Las fórmulas permiten seguir los cálculos; editar este archivo no modifica el sistema.",
            ],
            18,
        ):
            summary.merge_range(row, 0, row, 3, note, export.text)
            summary.set_row(row, 36)
        adjustments_sheet(export, data)
        summary.freeze_panes(0, 0)
    return output.getvalue()


def repartition_sheet(export: Export, data: Transparency):
    sheet = export.sheet(
        "Reparto",
        "CÓMO SE REPARTE CADA SERVICIO",
        "Fuente: factura del proveedor, cargos emitidos y lecturas. Se usa la cantidad de cargos de esa factura, aunque el edificio tenga ahora más unidades. Los ajustes posteriores se detallan en Cargos y Ajustes.",
        [46, 24, 22, 22],
    )
    charge_details = {c.id: c for c in data.statement.charges}
    row = 5
    for item in data.repartitions:
        charge = charge_details[item.charge.id]
        invoice = item.invoice
        metered = invoice.total_volume_milli is not None
        sheet.merge_range(row, 0, row, 3, charge.service, export.header)
        sheet.write_comment(row, 0, f"Factura: {invoice.id}\nCargo: {charge.id}")
        labels = [
            (
                "Cobertura del proveedor",
                f"{invoice.start_date:%d/%m/%Y} — {invoice.end_date:%d/%m/%Y}",
            ),
            (
                "Criterio",
                "Consumo propio + parte común" if metered else "Partes iguales",
            ),
            ("Total original del proveedor S/", money(invoice.total_cents)),
            ("Unidades incluidas al emitir", item.unit_count),
        ]
        for offset, (label, value) in enumerate(labels, 1):
            sheet.write(row + offset, 0, label, export.label)
            if offset < 3:
                sheet.merge_range(row + offset, 1, row + offset, 3, value, export.text)
            else:
                sheet.write(
                    row + offset, 1, value, export.number if offset == 3 else None
                )
        total, count = f"B{row + 4}", f"B{row + 5}"
        if not metered:
            ideal = money(invoice.total_cents) / item.unit_count
            sheet.write(row + 5, 0, "Cuota teórica sin redondear S/", export.label)
            export.formula(sheet, row + 5, 1, f"={total}/{count}", ideal, precise=True)
            sheet.write(row + 6, 0, "Cargo original asignado S/", export.label)
            sheet.write_number(row + 6, 1, charge.original_amount, export.number)
            sheet.write(row + 7, 0, "Diferencia de redondeo S/", export.label)
            export.formula(
                sheet,
                row + 7,
                1,
                f"=B{row + 7}-B{row + 6}",
                charge.original_amount - ideal,
                precise=True,
            )
            note_row = row + 9
            note = "Los céntimos restantes se asignan por número de unidad e identificador. La suma de los cargos originales de la factura coincide con el total del proveedor."
        else:
            volume = from_milli(invoice.total_volume_milli)
            consumed = from_milli(item.total_consumption_milli)
            own = charge.consumption
            common = money(item.charge.common_cents)
            labels = [
                ("Volumen total del proveedor m³", volume),
                ("Consumo individual agregado m³", consumed),
                ("Volumen común del edificio m³", volume - consumed),
                ("Lectura anterior de esta unidad m³", from_milli(item.previous_milli)),
                ("Lectura actual de esta unidad m³", from_milli(item.current_milli)),
                ("Consumo de esta unidad m³", own),
            ]
            for offset, (label, value) in enumerate(labels, 5):
                sheet.write(row + offset, 0, label, export.label)
                if offset == 7:
                    sheet.write_formula(
                        row + offset,
                        1,
                        f"=B{row + 6}-B{row + 7}",
                        export.volume,
                        float(value),
                    )
                else:
                    sheet.write_number(row + offset, 1, value, export.volume)
            own_ideal = money(invoice.total_cents) * own / volume
            common_ideal = (
                money(invoice.total_cents)
                * (volume - consumed)
                / volume
                / item.unit_count
            )
            for offset, label, expression, value in (
                (
                    11,
                    "Parte propia teórica S/",
                    f"={total}*B{row + 11}/B{row + 6}",
                    own_ideal,
                ),
                (
                    12,
                    "Parte común teórica por unidad S/",
                    f"={total}*B{row + 8}/B{row + 6}/{count}",
                    common_ideal,
                ),
            ):
                sheet.write(row + offset, 0, label, export.label)
                export.formula(sheet, row + offset, 1, expression, value, precise=True)
            for offset, label, value in (
                (13, "Parte propia asignada S/", charge.original_amount - common),
                (14, "Parte común asignada S/", common),
            ):
                sheet.write(row + offset, 0, label, export.label)
                sheet.write_number(row + offset, 1, value, export.number)
            sheet.write(row + 15, 0, "Cargo original asignado S/", export.label)
            export.formula(
                sheet,
                row + 15,
                1,
                f"=SUM(B{row + 14}:B{row + 15})",
                charge.original_amount,
            )
            sheet.write(row + 16, 0, "Diferencia de redondeo S/", export.label)
            export.formula(
                sheet,
                row + 16,
                1,
                f"=B{row + 16}-SUM(B{row + 12}:B{row + 13})",
                charge.original_amount - own_ideal - common_ideal,
                precise=True,
            )
            note_row = row + 18
            note = "Los céntimos se distribuyen entre las partes propias y comunes según el mayor residuo fraccionario; los empates siguen el orden de emisión. Un reinicio confirmado usa un límite de 100 000 m³. El consumo registrado ya incorpora ese reinicio."
        sheet.merge_range(note_row, 0, note_row + 1, 3, note, export.text)
        row = note_row + 4
    sheet.freeze_panes(5, 0)


def payments_sheet(export: Export, data: Transparency) -> str | None:
    sheet = export.sheet(
        "Pagos",
        "PAGOS Y SUS APLICACIONES",
        "Fuente: pagos confirmados de esta unidad, aplicaciones y liberaciones por ajustes. Incluye todos sus pagos y aplicaciones actuales para conciliar monto recibido = aplicado hasta el periodo + aplicado después + crédito disponible.",
        [22, 30, 18, 22, 22, 18, 20, 38, 38],
    )
    export.headers(
        sheet,
        5,
        [
            "Fecha recibida",
            "Referencia",
            "Recibido S/",
            "Aplicado hasta periodo S/",
            "Aplicado después S/",
            "Crédito actual S/",
            "Diferencia S/",
        ],
    )
    payments = data.statement.payments
    applications = [
        (payment, app) for payment in payments for app in payment.applications
    ]
    start = 10 + len(payments)
    export.headers(
        sheet,
        start - 1,
        [
            "Aplicado en Lima",
            "Referencia del pago",
            "Periodo del cargo",
            "Servicio",
            "Aplicación original S/",
            "Liberado S/",
            "Aplicación vigente S/",
            "Cargo de origen",
            "Pago de origen",
        ],
    )
    for row, (payment, application) in enumerate(applications, start):
        n = row + 1
        sheet.write_datetime(
            row,
            0,
            application.applied_at.astimezone(ZoneInfo("America/Lima")).replace(
                tzinfo=None
            ),
            export.timestamp,
        )
        sheet.write_row(
            row,
            1,
            [
                payment.reference or "Sin referencia",
                period(application),
                application.service,
            ],
        )
        sheet.write_number(row, 4, application.amount, export.number)
        sheet.write_number(row, 5, application.released, export.number)
        export.formula(sheet, row, 6, f"=ROUND(E{n}-F{n},2)", application.net_amount)
        sheet.write_row(row, 7, [str(application.charge_id), str(payment.id)])
        export.fit_text(
            sheet,
            row,
            (payment.reference or "Sin referencia", 25),
            (application.service, 18),
        )
    for row, payment in enumerate(payments, 6):
        n = row + 1
        sheet.write_datetime(row, 0, payment.received_on, export.date)
        sheet.write(row, 1, payment.reference or "Sin referencia")
        export.fit_text(sheet, row, (payment.reference or "Sin referencia", 25))
        sheet.write_number(row, 2, payment.amount, export.number)
        for col, comparison in ((3, "<="), (4, ">")):
            applied = sum(
                (
                    a.net_amount
                    for a in payment.applications
                    if (period(a) <= f"{data.year}-{data.month:02}") == (col == 3)
                ),
                Decimal(0),
            )
            if applications:
                last = start + len(applications)
                formula = f'=SUMIFS(G{start + 1}:G{last},I{start + 1}:I{last},"{payment.id}",C{start + 1}:C{last},"{comparison}"&\'Resumen\'!B5)'
                export.formula(sheet, row, col, formula, applied)
            else:
                sheet.write_number(row, col, 0, export.number)
        sheet.write_number(row, 5, payment.credit, export.number)
        export.formula(
            sheet,
            row,
            6,
            f"=ROUND(C{n}-SUM(D{n}:F{n}),2)",
            payment.amount
            - sum((a.net_amount for a in payment.applications), Decimal(0))
            - payment.credit,
        )
    if payments:
        sheet.autofilter(5, 0, len(payments) + 5, 6)
        return f"=SUM('Pagos'!F7:F{len(payments) + 6})"
    sheet.write(6, 0, "Sin pagos registrados.")
    return None


def adjustments_sheet(export: Export, data: Transparency):
    sheet = export.sheet(
        "Ajustes",
        "HISTORIAL DE AJUSTES DE LA UNIDAD",
        "Fuente: diferencias auditadas sobre los cargos hasta el periodo elegido. El cargo original conserva el reparto del proveedor. Las liberaciones de aplicaciones se detallan en Pagos.",
        [15, 26, 12, 18, 18, 18, 20, 65],
    )
    export.headers(
        sheet,
        5,
        [
            "Periodo",
            "Servicio",
            "Revisión",
            "Anterior S/",
            "Revisado S/",
            "Diferencia S/",
            "Registrado en Lima",
            "Motivo",
        ],
    )
    adjustments = [
        a
        for a in data.statement.adjustments
        if period(a) <= f"{data.year}-{data.month:02}"
    ]
    for row, adjustment in enumerate(adjustments, 6):
        sheet.write_row(
            row, 0, [period(adjustment), adjustment.service, adjustment.revision]
        )
        sheet.write_number(row, 3, adjustment.previous_amount, export.number)
        sheet.write_number(row, 4, adjustment.new_amount, export.number)
        export.formula(
            sheet, row, 5, f"=ROUND(E{row + 1}-D{row + 1},2)", adjustment.difference
        )
        sheet.write_datetime(
            row,
            6,
            adjustment.recorded_at.astimezone(ZoneInfo("America/Lima")).replace(
                tzinfo=None
            ),
            export.timestamp,
        )
        sheet.write(row, 7, adjustment.reason)
        export.fit_text(sheet, row, (adjustment.reason, 54), (adjustment.service, 21))
    if adjustments:
        sheet.autofilter(5, 0, len(adjustments) + 5, 7)
    else:
        sheet.write(6, 0, "Sin ajustes en estos cargos.")
