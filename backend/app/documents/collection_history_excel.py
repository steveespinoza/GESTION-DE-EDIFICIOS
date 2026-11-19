from datetime import date
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from xlsxwriter import Workbook

from app.documents.collection_history import CollectionHistory
from app.documents.excel import Export


def render_collection_history(data: CollectionHistory) -> bytes:
    output = BytesIO()
    board = data.overview
    periods = sorted({(row.billing_year, row.billing_month) for row in board.rows})
    rows = {
        (row.unit_id, row.billing_year, row.billing_month): row for row in board.rows
    }
    total_row = 6 + len(data.units)
    timestamp = data.generated_at.astimezone(ZoneInfo("America/Lima")).replace(
        tzinfo=None
    )
    with Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        book.set_properties(
            {"title": "Histórico de cobranzas", "author": "Gestión de Edificios"}
        )
        export = Export(book)
        summary = export.sheet(
            "Resumen",
            "HISTÓRICO DE COBRANZAS",
            "Estado vigente al descargar, no cierre histórico. Los periodos corresponden a cargos registrados, incluidos meses futuros si existen. Las aplicaciones no son efectivo recibido en ese mes. El resumen suma solo pendientes propios de cada periodo; el crédito actual no se descuenta otra vez.",
            [22, 32, 24, 28, 25, 25],
        )
        summary.merge_range(1, 0, 1, 5, board.building_name, export.label)
        summary.write(4, 0, "Evaluación en Lima", export.label)
        summary.write_datetime(4, 1, board.as_of, export.date)
        summary.write(4, 3, "Generado en Lima", export.label)
        summary.merge_range(4, 4, 4, 5, "")
        summary.write_datetime(4, 4, timestamp, export.timestamp)
        summary.write(5, 0, "Pendiente actual S/", export.label)
        summary.write(5, 3, "Crédito actual separado S/", export.label)
        summary.set_row(5, 34)
        export.headers(
            summary,
            8,
            [
                "Periodo del cargo",
                "Unidades con cargos",
                "Cargos vigentes S/",
                "Aplicado neto S/",
                "Pendiente propio S/",
                "De ese pendiente, vencido S/",
            ],
        )
        summary.set_row(8, 50)
        credits = [unit for unit in data.units if unit.credit > 0]
        credit_header = 13 + len(periods)
        if credits:
            export.headers(
                summary,
                credit_header,
                ["Unidad", "Propietario actual", "Crédito disponible actual S/"],
            )
            summary.set_row(credit_header, 50)
            for row, unit in enumerate(credits, credit_header + 1):
                summary.write(row, 0, unit.number, export.identifier)
                summary.write(row, 1, unit.owner)
                summary.write_number(row, 2, unit.credit, export.number)
                export.fit_text(summary, row, (unit.number, 18), (unit.owner, 26))
            export.formula(
                summary,
                5,
                4,
                f"=SUM(C{credit_header + 2}:C{credit_header + 1 + len(credits)})",
                sum((unit.credit for unit in credits), Decimal(0)),
            )
        else:
            summary.merge_range(
                credit_header,
                0,
                credit_header,
                5,
                "Sin crédito disponible actual.",
                export.text,
            )
            summary.write_number(5, 4, 0, export.number)

        sheets = {}
        for year, month in reversed(periods):
            name = f"Periodo {year}-{month:02}"
            sheet = export.sheet(
                name,
                f"COBRANZAS · {year}-{month:02}",
                "Importes actuales de los cargos de este periodo. Pendiente anterior suma saldos de periodos previos y no se suma otra vez al resumen. Los pagos y ajustes posteriores ya están reflejados. Las unidades sin cargos del mes conservan su pendiente anterior. El crédito disponible figura solo en Resumen.",
                [15, 32, 23, 23, 23, 23, 23, 23, 19, 23, 28],
            )
            sheets[(year, month)] = sheet
            sheet.merge_range(1, 0, 1, 10, board.building_name, export.label)
            sheet.write(4, 0, "Fecha en Lima", export.label)
            sheet.write_datetime(4, 1, board.as_of, export.date)
            sheet.write(4, 3, "Generado en Lima", export.label)
            sheet.merge_range(4, 4, 4, 5, "")
            sheet.write_datetime(4, 4, timestamp, export.timestamp)
            export.headers(
                sheet,
                5,
                [
                    "Unidad",
                    "Propietario actual",
                    "Cargos del periodo S/",
                    "Aplicado al periodo S/",
                    "Pendiente propio S/",
                    "Pendiente anterior S/",
                    "Pendiente hasta periodo S/",
                    "Propio vencido S/",
                    "Vencimiento del periodo",
                    "Estado del periodo",
                    "Participación",
                ],
            )
            sheet.set_row(5, 64)
            sheet.write(5, 11, "Unidad de origen", export.header)
            sheet.set_column(11, 11, 38, None, {"hidden": True})
            sheet.freeze_panes(6, 2)
            sheet.autofilter(5, 0, total_row - 1, 11)
            sheet.repeat_rows(5)
            sheet.repeat_columns(0, 1)
            sheet.print_area(0, 0, total_row, 10)
            sheet.set_print_scale(100)
            sheet.set_zoom(85)

        previous_sheet = None
        previous_balances = {unit.id: Decimal(0) for unit in data.units}
        for year, month in periods:
            sheet = sheets[(year, month)]
            for index, unit in enumerate(data.units, 6):
                n = index + 1
                row = rows.get((unit.id, year, month))
                amount, applied, balance, overdue = (
                    (row.amount, row.applied, row.balance, row.overdue_balance)
                    if row
                    else (Decimal(0),) * 4
                )
                previous = previous_balances[unit.id]
                sheet.write(index, 0, unit.number, export.identifier)
                sheet.write(index, 1, unit.owner)
                sheet.write_number(index, 2, amount, export.number)
                sheet.write_number(index, 3, applied, export.number)
                export.formula(sheet, index, 4, f"=ROUND(C{n}-D{n},2)", balance)
                if previous_sheet:
                    export.formula(
                        sheet,
                        index,
                        5,
                        f"=SUMIFS('{previous_sheet}'!$G$7:$G${total_row},'{previous_sheet}'!$L$7:$L${total_row},$L{n})",
                        previous,
                    )
                else:
                    sheet.write_number(index, 5, 0, export.number)
                export.formula(
                    sheet, index, 6, f"=ROUND(SUM(E{n}:F{n}),2)", previous + balance
                )
                sheet.write_number(index, 7, overdue, export.number)
                if row and row.due_date:
                    sheet.write_datetime(index, 8, row.due_date, export.date)
                else:
                    sheet.write(index, 8, "Sin vencimiento" if row else "Sin cargos")
                state = (
                    "Sin cargos"
                    if row is None
                    else "Pagado"
                    if balance == 0
                    else "Vencido"
                    if overdue
                    else "Por vencer"
                    if row.due_date
                    else "Sin vencimiento"
                )
                sheet.write(index, 9, state)
                sheet.write(
                    index, 10, "Con cargos" if row else "Sin cargos del periodo"
                )
                sheet.write_string(index, 11, str(unit.id))
                export.fit_text(sheet, index, (unit.number, 12), (unit.owner, 26))
                previous_balances[unit.id] += balance
            sheet.write(total_row, 0, "TOTAL", export.label)
            selected = [
                row
                for row in board.rows
                if (row.billing_year, row.billing_month) == (year, month)
            ]
            current_balance = sum((row.balance for row in selected), Decimal(0))
            cumulative = sum(previous_balances.values(), Decimal(0))
            values = [
                sum((row.amount for row in selected), Decimal(0)),
                sum((row.applied for row in selected), Decimal(0)),
                current_balance,
                cumulative - current_balance,
                cumulative,
                sum((row.overdue_balance for row in selected), Decimal(0)),
            ]
            for col, value in enumerate(values, 2):
                letter = chr(ord("A") + col)
                export.formula(
                    sheet,
                    total_row,
                    col,
                    f"=SUM({letter}7:{letter}{total_row})",
                    value,
                    total=True,
                )
            previous_sheet = f"Periodo {year}-{month:02}"

        for index, (year, month) in enumerate(reversed(periods), 9):
            name = f"Periodo {year}-{month:02}"
            selected = [
                row
                for row in board.rows
                if (row.billing_year, row.billing_month) == (year, month)
            ]
            period_style = book.add_format(
                {"font_name": "Arial", "font_size": 11, "num_format": "yyyy-mm"}
            )
            summary.write_datetime(index, 0, date(year, month, 1), period_style)
            summary.write_number(index, 1, len(selected))
            for col, source, field in (
                (2, "C", "amount"),
                (3, "D", "applied"),
                (4, "E", "balance"),
                (5, "H", "overdue_balance"),
            ):
                export.formula(
                    summary,
                    index,
                    col,
                    f"='{name}'!{source}{total_row + 1}",
                    sum((getattr(row, field) for row in selected), Decimal(0)),
                )
        final = 9 + len(periods)
        summary.write(final, 0, "TOTAL SIN DUPLICAR", export.label)
        summary.set_row(final, 34)
        for col in range(2, 6):
            letter = chr(ord("A") + col)
            field = ("amount", "applied", "balance", "overdue_balance")[col - 2]
            export.formula(
                summary,
                final,
                col,
                f"=SUM({letter}10:{letter}{final})",
                sum((getattr(row, field) for row in board.rows), Decimal(0)),
                total=True,
            )
        export.formula(summary, 5, 1, f"=E{final + 1}", board.balance)
        summary.autofilter(8, 0, final - 1, 5)
        summary.freeze_panes(9, 1)
        summary.repeat_rows(8)
        summary.print_area(0, 0, credit_header + max(1, len(credits)), 5)
        summary.set_print_scale(100)
    return output.getvalue()
