from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from xlsxwriter import Workbook
from xlsxwriter.utility import xl_col_to_name

from app.billing.metering import from_milli
from app.collections.service import money
from app.documents.excel import Export
from app.documents.monthly import MonthlyReport


def render_monthly(data: MonthlyReport) -> bytes:
    output = BytesIO()
    report = data.summary
    units = {unit.unit_id: unit for unit in report.units}
    services = {service.invoice_id: service for service in report.services}
    with Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        book.set_properties(
            {"title": "Excel mensual del edificio", "author": "Gestión de Edificios"}
        )
        export = Export(book)
        consolidated = export.sheet(
            "Consolidado",
            "CONSOLIDADO MENSUAL DEL EDIFICIO",
            "Importes vigentes al descargar, incluidos movimientos posteriores al mes. Aplicado al mes no es efectivo recibido en el mes. El pendiente excluye cargos posteriores; no duplica arrastres ni descuenta otra vez el crédito actual.",
            [15, 32] + [20] * len(services) + [21] * 7 + [27],
        )
        matrix = export.sheet(
            "Matriz de servicios",
            "MATRIZ DE SERVICIOS DEL MES",
            "Fuente: facturas, reparto original, ajustes y aplicaciones netas del periodo. El divisor es la cantidad de unidades incluidas en cada factura. Las cuotas teóricas no reemplazan los céntimos asignados; los ajustes no reescriben el reparto original.",
            [30, 19, 15, 15, 20, 16, 18, 18, 18, 22, 22, 22, 20, 20, 20, 20, 20],
        )
        detail = export.sheet(
            "Detalle",
            "CONSUMOS Y CARGOS POR UNIDAD Y SERVICIO",
            "Fuente: cargos, lecturas y reparto guardados al emitir; ajustes y aplicaciones netas actuales. Sin lectura significa que el servicio es lineal. En reinicios confirmados, el consumo incluye el ciclo completo del medidor. Importes en soles y lecturas en m³.",
            [15, 32, 30, 19, 19, 19, 21, 21, 21, 21, 21, 21, 21, 21],
        )
        export.headers(
            detail,
            5,
            [
                "Unidad",
                "Propietario actual",
                "Servicio",
                "Lectura anterior m³",
                "Lectura actual m³",
                "Consumo propio m³",
                "Propio asignado S/",
                "Común asignado S/",
                "Cuota lineal S/",
                "Cargo original S/",
                "Ajustes S/",
                "Cargo vigente S/",
                "Aplicado neto S/",
                "Pendiente S/",
            ],
        )
        for row, item in enumerate(data.charges, 6):
            n = row + 1
            unit = units[item.charge.unit_id]
            service = services[item.invoice.id]
            detail.write(row, 0, unit.unit_number, export.identifier)
            detail.write_row(row, 1, [unit.owner_name, service.service])
            original = money(item.charge.amount_cents)
            if item.reading is not None:
                for col, value in enumerate(
                    (
                        item.reading.previous_milli,
                        item.reading.current_milli,
                        item.reading.consumption_milli,
                    ),
                    3,
                ):
                    detail.write_number(row, col, from_milli(value), export.volume)
                common = money(item.charge.common_cents)
                detail.write_number(row, 6, original - common, export.number)
                detail.write_number(row, 7, common, export.number)
            else:
                detail.write_number(row, 8, original, export.number)
            export.formula(detail, row, 9, f"=SUM(G{n}:I{n})", original)
            detail.write_number(row, 10, money(item.adjustment), export.number)
            export.formula(
                detail,
                row,
                11,
                f"=ROUND(SUM(J{n}:K{n}),2)",
                original + money(item.adjustment),
            )
            detail.write_number(row, 12, money(item.applied), export.number)
            export.formula(
                detail,
                row,
                13,
                f"=ROUND(L{n}-M{n},2)",
                original + money(item.adjustment - item.applied),
            )
            detail.write_string(row, 14, str(unit.unit_id))
            detail.write_string(row, 15, str(item.invoice.id))
            export.fit_text(
                detail,
                row,
                (unit.unit_number, 12),
                (unit.owner_name, 26),
                (service.service, 24),
            )
        detail.set_column(14, 15, 38, None, {"hidden": True})
        detail.write_row(
            5, 14, ["Unidad de origen", "Factura de origen"], export.header
        )
        last = 6 + len(data.charges)
        detail.autofilter(5, 0, last - 1, 15)
        detail.repeat_rows(5)
        detail.print_area(0, 0, last - 1, 13)
        detail.set_zoom(85)

        # Keys stay as text in hidden columns: filters and sorting preserve joins,
        # including identifiers such as 001 versus 1 and literal wildcard names.
        amount_range = f"'Detalle'!$L$7:$L${last}"
        applied_range = f"'Detalle'!$M$7:$M${last}"
        original_range = f"'Detalle'!$J$7:$J${last}"
        adjustment_range = f"'Detalle'!$K$7:$K${last}"
        invoice_range = f"'Detalle'!$P$7:$P${last}"
        unit_range = f"'Detalle'!$O$7:$O${last}"
        export.headers(
            matrix,
            5,
            [
                "Servicio",
                "Reparto",
                "Inicio",
                "Fin",
                "Proveedor S/",
                "Unidades del reparto",
                "Volumen proveedor m³",
                "Consumo propio total m³",
                "Volumen común m³",
                "Tarifa teórica S/m³",
                "Cuota lineal teórica S/",
                "Cuota común teórica S/",
                "Ajustes S/",
                "Cargos vigentes S/",
                "Aplicado neto S/",
                "Pendiente S/",
                "Diferencia de reparto S/",
            ],
        )
        matrix.set_row(5, 64)
        for row, service in enumerate(report.services, 6):
            n = row + 1
            items = [
                item for item in data.charges if item.invoice.id == service.invoice_id
            ]
            invoice = items[0].invoice
            metered = invoice.total_volume_milli is not None
            matrix.write_row(
                row, 0, [service.service, "Medido" if metered else "Lineal"]
            )
            matrix.write_datetime(row, 2, invoice.start_date, export.date)
            matrix.write_datetime(row, 3, invoice.end_date, export.date)
            matrix.write_number(row, 4, service.provider_amount, export.number)
            matrix.write_number(row, 5, len(items))
            matrix.write_string(row, 17, str(invoice.id))
            if metered:
                volume = from_milli(invoice.total_volume_milli)
                consumption = sum(
                    (from_milli(item.reading.consumption_milli) for item in items),
                    Decimal(0),
                )
                common = volume - consumption
                rate = service.provider_amount / volume
                matrix.write_number(row, 6, volume, export.volume)
                matrix.write_formula(
                    row,
                    7,
                    f"=SUMIFS('Detalle'!$F$7:$F${last},{invoice_range},$R{n})",
                    export.volume,
                    float(consumption),
                )
                matrix.write_formula(
                    row, 8, f"=ROUND(G{n}-H{n},3)", export.volume, float(common)
                )
                export.formula(matrix, row, 9, f"=E{n}/G{n}", rate, precise=True)
                export.formula(
                    matrix,
                    row,
                    11,
                    f"=I{n}*J{n}/F{n}",
                    common * rate / len(items),
                    precise=True,
                )
            else:
                export.formula(
                    matrix,
                    row,
                    10,
                    f"=E{n}/F{n}",
                    service.provider_amount / len(items),
                    precise=True,
                )
            for col, source, value in (
                (12, adjustment_range, service.adjustment),
                (13, amount_range, service.amount),
                (14, applied_range, service.applied),
            ):
                export.formula(
                    matrix, row, col, f"=SUMIFS({source},{invoice_range},$R{n})", value
                )
            export.formula(matrix, row, 15, f"=ROUND(N{n}-O{n},2)", service.balance)
            export.formula(
                matrix,
                row,
                16,
                f"=ROUND(SUMIFS({original_range},{invoice_range},$R{n})-E{n},2)",
                service.amount - service.adjustment - service.provider_amount,
            )
            export.fit_text(matrix, row, (service.service, 24))
        matrix.set_column(17, 17, 38, None, {"hidden": True})
        matrix.write(5, 17, "Factura de origen", export.header)
        matrix.autofilter(5, 0, 5 + len(services), 17)
        matrix.repeat_rows(5)
        matrix.print_area(0, 0, 6 + len(services), 16)
        matrix.set_zoom(80)
        matrix_total = 6 + len(services)
        matrix.write(matrix_total, 0, "TOTAL", export.label)
        for col, value in (
            (4, sum(s.provider_amount for s in report.services)),
            (12, sum(s.adjustment for s in report.services)),
            (13, report.totals.current_amount),
            (14, report.totals.current_applied),
            (15, report.totals.current_balance),
            (16, Decimal(0)),
        ):
            letter = xl_col_to_name(col)
            export.formula(
                matrix,
                matrix_total,
                col,
                f"=SUM({letter}7:{letter}{matrix_total})",
                value,
                total=True,
            )

        count = len(services)
        first_total = 2 + count
        hidden = first_total + 8
        key_col = xl_col_to_name(hidden)
        consolidated.set_column(hidden, hidden, 38, None, {"hidden": True})
        consolidated.merge_range(
            1, 0, 1, hidden - 1, report.building_name, export.label
        )
        consolidated.write(4, 0, "Periodo", export.label)
        consolidated.write_datetime(
            4,
            1,
            report.as_of.replace(
                year=report.billing_year, month=report.billing_month, day=1
            ),
            book.add_format(
                {"font_name": "Arial", "font_size": 11, "num_format": "mm/yyyy"}
            ),
        )
        consolidated.write(5, 0, "Vencimiento", export.label)
        if report.due_date:
            consolidated.write_datetime(5, 1, report.due_date, export.date)
        else:
            consolidated.write(5, 1, "Sin vencimiento")
        consolidated.write(6, 0, "Evaluación Lima", export.label)
        consolidated.write_datetime(6, 1, report.as_of, export.date)
        consolidated.write(4, 2, "Generado en Lima", export.label)
        consolidated.merge_range(4, 3, 4, 5, "")
        consolidated.write_datetime(
            4,
            3,
            report.generated_at.astimezone(ZoneInfo("America/Lima")).replace(
                tzinfo=None
            ),
            export.timestamp,
        )
        export.headers(
            consolidated,
            8,
            ["Unidad", "Propietario actual"]
            + [s.service + " S/" for s in report.services]
            + [
                "Cargos del mes S/",
                "Aplicado al mes S/",
                "Pendiente del mes S/",
                "Pendiente anterior S/",
                "Pendiente total S/",
                "De ese total, vencido S/",
                "Crédito actual S/",
                "Participación en el mes",
            ],
        )
        consolidated.set_row(8, 64)
        consolidated.write(8, hidden, "Unidad de origen", export.header)
        consolidated.set_row(7, None, None, {"hidden": True})
        for col, service in enumerate(report.services, 2):
            consolidated.write_string(7, col, str(service.invoice_id))
        for row, unit in enumerate(report.units, 9):
            n = row + 1
            consolidated.write(row, 0, unit.unit_number, export.identifier)
            consolidated.write(row, 1, unit.owner_name)
            consolidated.write_string(row, hidden, str(unit.unit_id))
            for col, service in enumerate(report.services, 2):
                matching = [
                    item
                    for item in data.charges
                    if item.charge.unit_id == unit.unit_id
                    and item.invoice.id == service.invoice_id
                ]
                if matching:
                    reference = f"{xl_col_to_name(col)}$8"
                    export.formula(
                        consolidated,
                        row,
                        col,
                        f"=SUMIFS({amount_range},{unit_range},${key_col}{n},{invoice_range},{reference})",
                        money(matching[0].charge.amount_cents + matching[0].adjustment),
                    )

            def cell(offset, number=n):
                return f"{xl_col_to_name(first_total + offset)}{number}"

            export.formula(
                consolidated,
                row,
                first_total,
                f"=SUM(C{n}:{xl_col_to_name(first_total - 1)}{n})",
                unit.current_amount,
            )
            export.formula(
                consolidated,
                row,
                first_total + 1,
                f"=SUMIFS({applied_range},{unit_range},${key_col}{n})",
                unit.current_applied,
            )
            export.formula(
                consolidated,
                row,
                first_total + 2,
                f"=ROUND({cell(0)}-{cell(1)},2)",
                unit.current_balance,
            )
            consolidated.write_number(
                row, first_total + 3, unit.previous_balance, export.number
            )
            export.formula(
                consolidated,
                row,
                first_total + 4,
                f"=ROUND(SUM({cell(2)}:{cell(3)}),2)",
                unit.total_pending,
            )
            consolidated.write_number(
                row, first_total + 5, unit.overdue_balance, export.number
            )
            consolidated.write_number(row, first_total + 6, unit.credit, export.number)
            consolidated.write(
                row,
                first_total + 7,
                "Con cargos" if unit.has_current_charges else "Sin cargos del periodo",
            )
            export.fit_text(
                consolidated, row, (unit.unit_number, 12), (unit.owner_name, 26)
            )
        total_row = 9 + len(report.units)
        consolidated.write(total_row, 0, "TOTAL", export.label)
        totals = report.totals
        values = [s.amount for s in report.services] + [
            totals.current_amount,
            totals.current_applied,
            totals.current_balance,
            totals.previous_balance,
            totals.total_pending,
            totals.overdue_balance,
            totals.credit,
        ]
        for col, value in enumerate(values, 2):
            letter = xl_col_to_name(col)
            export.formula(
                consolidated,
                total_row,
                col,
                f"=SUM({letter}10:{letter}{total_row})",
                value,
                total=True,
            )
        consolidated.autofilter(8, 0, total_row - 1, hidden)
        consolidated.freeze_panes(9, 2)
        consolidated.repeat_rows(8)
        consolidated.print_area(0, 0, total_row, hidden - 1)
        consolidated.set_zoom(85)
        for sheet in (matrix, detail):
            sheet.merge_range(1, 0, 1, 5, "")
            sheet.write_formula(
                1,
                0,
                "='Consolidado'!A2&\" · \"&TEXT('Consolidado'!B5,\"mm/yyyy\")",
                export.label,
                f"{report.building_name} · {report.billing_month:02}/{report.billing_year}",
            )
        for sheet in (consolidated, matrix, detail):
            sheet.set_print_scale(100)
            sheet.repeat_columns(0, 1)
    return output.getvalue()
