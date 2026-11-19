from decimal import Decimal
from io import BytesIO
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from test_charge_adjustments import workspace as adjustment_workspace
from test_collections import ledger as metered_ledger
from test_collections import payment_data

ledger = metered_ledger
workspace = adjustment_workspace
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class Spreadsheet:
    def __init__(self, response, filename_prefix="transparencia"):
        assert response.status_code == 200, (
            response.text[:500] if response.status_code != 200 else ""
        )
        assert (
            response.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith(
            f'attachment; filename="{filename_prefix}-'
        )
        self.zip = ZipFile(BytesIO(response.content))
        strings = ET.fromstring(self.zip.read("xl/sharedStrings.xml"))
        self.strings = ["".join(s.itertext()) for s in strings]
        workbook = ET.fromstring(self.zip.read("xl/workbook.xml"))
        self.sheets = {
            sheet.attrib["name"]: ET.fromstring(
                self.zip.read(f"xl/worksheets/sheet{index}.xml")
            )
            for index, sheet in enumerate(workbook.find("s:sheets", NS), 1)
        }

    def cell(self, sheet, address):
        return self.sheets[sheet].find(f'.//s:c[@r="{address}"]', NS)

    def value(self, sheet, address):
        cell = self.cell(sheet, address)
        if cell is None:
            return None
        value = cell.findtext("s:v", namespaces=NS)
        return (
            self.strings[int(value)]
            if cell.attrib.get("t") == "s"
            else Decimal(value)
            if value is not None
            else None
        )

    def formula(self, sheet, address):
        return self.cell(sheet, address).findtext("s:f", namespaces=NS)


def endpoint(ledger, *, owner=False, index=0):
    paths, units, _ = ledger
    return (
        f"/api/owner/properties/{units[index]}/transparency.xlsx"
        if owner
        else f"{paths[index]}/units/{units[index]}/transparency.xlsx"
    )


def download(client, path, year=2027, month=1):
    return client.get(path, params={"billing_year": year, "billing_month": month})


def test_export_reconciles_statement_and_metered_repartition_without_storage(
    admin, ledger, session_header
):
    paths, units, _ = ledger
    assert (
        admin.post(
            f"{paths[0]}/units/{units[0]}/payments",
            json=payment_data(),
            headers=session_header,
        ).status_code
        == 201
    )
    book = Spreadsheet(download(admin, endpoint(ledger)))
    assert list(book.sheets) == ["Resumen", "Cargos", "Reparto", "Pagos", "Ajustes"]
    assert [book.value("Resumen", f"B{row}") for row in range(10, 17)] == [
        50,
        0,
        50,
        40,
        90,
        0,
        0,
    ]
    assert book.value("Resumen", "B4") == "N.º 001"
    assert book.value("Resumen", "B5") == "2027-01"
    assert (
        book.value("Resumen", "B6") > 45000
    )  # A real Excel date, not a formatted string.
    assert book.formula("Resumen", "B14") == "SUM(B12:B13)"
    assert book.formula("Cargos", "G7") == "ROUND(E7-F7,2)"
    assert [
        book.value("Reparto", f"B{row}")
        for row in (9, 10, 11, 12, 13, 14, 15, 16, 21, 22)
    ] == [50, 1, 1, 1, 0, 1, 2, 1, 50, 0]
    assert book.value("Pagos", "G7") == 0
    assert not any(
        "externalLink" in path or "vbaProject" in path for path in book.zip.namelist()
    )


def test_export_scopes_both_roles_two_owners_and_two_buildings(
    admin, sign_in, ledger, session_header
):
    paths, units, _ = ledger
    path = endpoint(ledger)
    assert download(admin, path).status_code == 200
    assert (
        download(admin, f"{paths[1]}/units/{units[0]}/transparency.xlsx").status_code
        == 404
    )
    assert sign_in("test-owner").status_code == 200
    own = endpoint(ledger, owner=True)
    book = Spreadsheet(download(admin, own))
    assert book.value("Resumen", "B3") == "Cedros"
    assert download(admin, path).status_code == 403
    assert download(admin, endpoint(ledger, owner=True, index=1)).status_code == 404
    assert (
        download(
            admin, f"/api/owner/properties/{uuid4()}/transparency.xlsx"
        ).status_code
        == 404
    )
    assert sign_in("second-owner").status_code == 200
    assert download(admin, own).status_code == 404
    assert download(admin, endpoint(ledger, owner=True, index=1)).status_code == 409
    assert admin.post("/api/auth/logout", headers=session_header).status_code == 204
    assert download(admin, own).status_code == 401


@pytest.mark.parametrize(
    "query",
    [
        "billing_year=2019&billing_month=1",
        "billing_year=10000&billing_month=1",
        "billing_year=2027&billing_month=0",
        "billing_year=2027&billing_month=13",
        "billing_year=2027&billing_month=x",
        "billing_month=1",
        "billing_year=2027",
    ],
)
def test_export_validates_period(admin, ledger, query):
    assert admin.get(f"{endpoint(ledger)}?{query}").status_code == 422


def test_empty_period_does_not_create_document(admin, ledger):
    response = download(admin, endpoint(ledger), month=8)
    assert response.status_code == 409
    assert "no tiene cargos" in response.json()["detail"]


def test_adjustments_releases_and_future_applications_reconcile(admin, workspace):
    first = workspace.issue()
    workspace.pay("110.00")
    response, _, _ = workspace.adjust(first, "90.00", reason="Reducir cargo pagado")
    assert response.status_code == 201
    workspace.issue("50.00", year=2027, month=1)
    path = f"{workspace.paths[0]}/units/{workspace.units[0]}/transparency.xlsx"
    book = Spreadsheet(download(admin, path, year=2026, month=12))
    assert [book.value("Resumen", f"B{row}") for row in range(10, 17)] == [
        90,
        90,
        0,
        0,
        0,
        0,
        0,
    ]
    assert [book.value("Cargos", f"{col}7") for col in "CDEFG"] == [100, -10, 90, 90, 0]
    assert [book.value("Pagos", f"{col}7") for col in "CDEFG"] == [110, 90, 20, 0, 0]
    assert book.value("Ajustes", "F7") == -10
    assert book.value("Ajustes", "H7") == "Reducir cargo pagado"
    assert book.value("Reparto", "B12") == 100  # Original allocation remains unchanged.
    later = Spreadsheet(download(admin, path))
    assert later.value("Resumen", "B14") == 30
    assert later.value("Resumen", "B13") == 0


def test_credit_is_current_and_not_subtracted_again(admin, workspace):
    invoice = workspace.issue()
    workspace.pay("110.00")
    response, _, _ = workspace.adjust(invoice, "90.00")
    assert response.status_code == 201
    book = Spreadsheet(
        download(
            admin,
            f"{workspace.paths[0]}/units/{workspace.units[0]}/transparency.xlsx",
            year=2026,
            month=12,
        )
    )
    assert book.value("Resumen", "B14") == 0
    assert book.value("Resumen", "B16") == 20
    assert [book.value("Pagos", f"{col}7") for col in "CDEFG"] == [110, 90, 0, 20, 0]


def test_linear_and_metered_rounding_use_original_unit_count_and_hide_other_units(
    admin, ledger, session_header
):
    paths, _, _ = ledger
    owners = {a["username"]: a["id"] for a in admin.get("/api/admin/owners").json()}

    def post(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    building = post(
        "/api/admin/buildings", {"name": "Transparencia sintética", "total_units": 4}
    )
    path = f"/api/admin/buildings/{building['id']}"
    units = [
        post(
            f"{path}/units",
            {
                "number": number,
                "area_sqm": "40.00",
                "owner": {
                    "kind": "existing",
                    "id": owners["test-owner" if index == 0 else "second-owner"],
                },
            },
        )
        for index, number in enumerate(("001", "SECRETO-002", "SECRETO-003"))
    ]
    for name, kind, amount, extra in (
        ("Cuota", "LINEAR", "100.00", {}),
        (
            "Agua",
            "METERED",
            "90.00",
            {
                "total_volume": "10.000",
                "readings": [
                    {
                        "unit_id": unit["id"],
                        "previous_reading": "0",
                        "current_reading": str(index + 1),
                    }
                    for index, unit in enumerate(units)
                ],
            },
        ),
    ):
        category = post(f"{path}/services", {"name": name, "calculation_type": kind})
        post(
            f"{path}/invoices",
            {
                "category_id": category["id"],
                "billing_year": 2027,
                "billing_month": 1,
                "start_date": "2027-01-01",
                "end_date": "2027-01-25",
                "total_amount": amount,
                **extra,
            },
        )
    post(
        f"{path}/units",
        {
            "number": "POSTERIOR-004",
            "area_sqm": "40.00",
            "owner": {"kind": "existing", "id": owners["second-owner"]},
        },
    )
    book = Spreadsheet(
        download(admin, f"{path}/units/{units[0]['id']}/transparency.xlsx")
    )
    assert not any(
        secret in text
        for text in book.strings
        for secret in ("SECRETO", "POSTERIOR", "second-owner", "Segunda cuenta")
    )
    blocks = [
        row
        for row in range(6, 80)
        if book.value("Reparto", f"A{row}") in ("Cuota", "Agua")
    ]
    for row in blocks:
        assert book.value("Reparto", f"B{row + 4}") == 3
        if book.value("Reparto", f"A{row}") == "Cuota":
            assert book.value("Reparto", f"B{row + 6}") == Decimal("33.34")
            assert abs(
                book.value("Reparto", f"B{row + 7}") - Decimal("0.00666666666667")
            ) < Decimal("0.000000001")
        else:
            assert (
                book.value("Reparto", f"B{row + 6}") == 6
            )  # Only a building aggregate.
            assert book.value("Reparto", f"B{row + 7}") == 4
            assert book.value("Reparto", f"B{row + 13}") == 9
            assert book.value("Reparto", f"B{row + 14}") == 12
            assert book.value("Reparto", f"B{row + 15}") == 21
    assert len(blocks) == 2
    assert (
        download(
            admin, f"{paths[0]}/units/{units[0]['id']}/transparency.xlsx"
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "text",
    [
        '=HYPERLINK("https://example.com","ejecutar")',
        "+SUM(1,2)",
        "-1+2",
        "@SUM(1,2)",
        "https://example.com",
    ],
)
def test_user_supplied_text_stays_text_without_active_links(admin, workspace, text):
    workspace.issue()
    workspace.post(
        f"{workspace.paths[0]}/units/{workspace.units[0]}/payments",
        payment_data(amount="1.00", reference=text),
    )
    book = Spreadsheet(
        download(
            admin,
            f"{workspace.paths[0]}/units/{workspace.units[0]}/transparency.xlsx",
            year=2026,
            month=12,
        )
    )
    assert book.value("Pagos", "B7") == text
    assert book.formula("Pagos", "B7") is None
    assert book.sheets["Pagos"].find("s:hyperlinks", NS) is None


def test_large_amounts_and_long_reasons_remain_readable(admin, workspace):
    invoice = workspace.issue()
    workspace.pay("1.00")
    reason = "Á" * 500
    response, _, _ = workspace.adjust(invoice, "9999999999.99", reason=reason)
    assert response.status_code == 201
    book = Spreadsheet(
        download(
            admin,
            f"{workspace.paths[0]}/units/{workspace.units[0]}/transparency.xlsx",
            year=2026,
            month=12,
        )
    )
    assert book.value("Resumen", "B14") == Decimal("9999999998.99")
    assert book.value("Ajustes", "H7") == reason
    row = book.sheets["Ajustes"].find('.//s:row[@r="7"]', NS)
    assert float(row.attrib["ht"]) >= 150


def test_meter_rollover_exports_recorded_consumption(admin, ledger, session_header):
    paths, units, _ = ledger
    category = admin.post(
        f"{paths[0]}/services",
        json={"name": "Medidor reiniciado", "calculation_type": "METERED"},
        headers=session_header,
    ).json()
    response = admin.post(
        f"{paths[0]}/invoices",
        json={
            "category_id": category["id"],
            "billing_year": 2027,
            "billing_month": 2,
            "start_date": "2027-02-01",
            "end_date": "2027-02-25",
            "total_amount": "70.00",
            "total_volume": "1.000",
            "readings": [
                {
                    "unit_id": units[0],
                    "previous_reading": "99999.500",
                    "current_reading": "0.500",
                    "rollover_confirmed": True,
                }
            ],
        },
        headers=session_header,
    )
    assert response.status_code == 201, response.text
    book = Spreadsheet(download(admin, endpoint(ledger), month=2))
    assert [book.value("Reparto", f"B{row}") for row in (14, 15, 16, 21)] == [
        Decimal("99999.5"),
        Decimal("0.5"),
        1,
        70,
    ]
