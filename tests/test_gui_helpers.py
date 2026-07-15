import json
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from zeitshop_converter.core import (
    ConversionBatch,
    InventoryUpdateBatch,
    InventoryUpdateIssueRow,
    InventoryUpdateResult,
    Severity,
    ValidationIssue,
    WixRowResult,
)
from zeitshop_converter.gui import app as gui_app
from zeitshop_converter.io import ReportDescriptionRecord


class DummyVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class DummyWidget:
    def __init__(self) -> None:
        self.config: dict[str, str] = {}

    def configure(self, **kwargs: str) -> None:
        self.config.update(kwargs)

    def cget(self, key: str):
        return self.config.get(key)


def _sample_result(*, artikel_nr: str = "10", price: str = "10.50", cost: str = "5.00") -> WixRowResult:
    return WixRowResult(
        source_row=2,
        source={"Artikel Nr": artikel_nr},
        wix_row={
            "name": "Brand Sample",
            "brand": "Brand",
            "plainDescription": "Desc",
            "price": price,
            "cost": cost,
            "barcode": "REF-10",
        },
    )


def test_load_sv_ttk_returns_none_when_module_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(_name: str) -> ModuleType:
        raise ModuleNotFoundError("missing")

    monkeypatch.setattr(gui_app.importlib, "import_module", fake_import)

    assert gui_app._load_sv_ttk() is None


def test_load_sv_ttk_returns_loaded_module(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("sv_ttk")
    monkeypatch.setattr(gui_app.importlib, "import_module", lambda _name: module)

    assert gui_app._load_sv_ttk() is module


def test_load_settings_returns_defaults_for_missing_or_invalid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_app, "_SETTINGS_PATH", settings_path)

    assert gui_app._load_settings() == gui_app.GuiSettings()

    settings_path.write_text("{invalid", encoding="utf-8")
    assert gui_app._load_settings() == gui_app.GuiSettings()


def test_save_and_load_settings_round_trip_with_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_app, "_SETTINGS_PATH", settings_path)

    gui_app._save_settings(
        gui_app.GuiSettings(
            default_visible=False,
        )
    )

    loaded = gui_app._load_settings()

    assert loaded == gui_app.GuiSettings(
            default_visible=False,
    )


def test_build_options_uses_settings() -> None:
    fake_app = SimpleNamespace(
        settings=gui_app.GuiSettings(
            default_visible=False,
        )
    )

    options = gui_app.ConverterApp._build_options(fake_app)

    assert options.default_visible is False
    assert options.handle_prefix == "ds-"


def test_default_download_helpers_use_configured_and_source_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_app = SimpleNamespace(
        settings=gui_app.GuiSettings(),
        diamond_path=Path("/tmp/input.csv"),
        wix_export_path=Path("/tmp/catalog_products.csv"),
        mode_var=DummyVar("import"),
    )
    assert gui_app.ConverterApp._default_download_directory(fake_app) == Path("/tmp")
    assert gui_app.ConverterApp._default_wix_filename(fake_app) == "input_wix_import.csv"
    assert gui_app.ConverterApp._default_issue_filename(fake_app, Severity.ERROR) == "input_fehler.csv"
    assert gui_app.ConverterApp._default_issue_filename(fake_app, Severity.WARNING) == "input_warnungen.csv"
    assert gui_app.ConverterApp._default_issue_filename(fake_app) == "input_issues.csv"

    fake_app.diamond_path = None
    assert gui_app.ConverterApp._default_download_directory(fake_app) == Path.home()
    assert gui_app.ConverterApp._default_wix_filename(fake_app) == "wix_import.csv"

    fake_app.mode_var.set("update")
    assert gui_app.ConverterApp._default_download_directory(fake_app) == Path("/tmp")
    assert gui_app.ConverterApp._default_wix_filename(fake_app) == "catalog_products_inventory_update.csv"


def test_report_progress_matches_search_and_sort_key() -> None:
    idle_calls: list[str] = []
    progressbar = DummyWidget()
    fake_app = SimpleNamespace(
        status_var=DummyVar(),
        progress_text_var=DummyVar(),
        progressbar=progressbar,
        update_idletasks=lambda: idle_calls.append("idle"),
        search_var=DummyVar("brand ref-10"),
        _preview_columns=(
            "artikel_nr",
            "name",
            "brand",
            "plain_description",
            "price",
            "inventory",
            "referenznummer",
        ),
        _preview_overrides={},
    )
    fake_app._base_value_for_column = lambda result, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, result, column
    )
    fake_app._value_for_column = lambda result, column: gui_app.ConverterApp._value_for_column(fake_app, result, column)

    gui_app.ConverterApp._report_progress(fake_app, "Konvertierung läuft")
    assert fake_app.status_var.get() == "Konvertierung läuft"
    assert fake_app.progress_text_var.get() == "Fortschritt: läuft"
    assert idle_calls == ["idle"]

    result = _sample_result()
    assert gui_app.ConverterApp._matches_search(fake_app, result) is True
    fake_app.search_var.set("missing")
    assert gui_app.ConverterApp._matches_search(fake_app, result) is False

    assert gui_app.ConverterApp._sort_key(fake_app, result, "price") == (0, Decimal("10.50"), "")
    assert gui_app.ConverterApp._sort_key(fake_app, result, "artikel_nr") == (0, Decimal("10"), "")
    bad = _sample_result(artikel_nr="A-1", price="oops")
    assert gui_app.ConverterApp._sort_key(fake_app, bad, "price") == (2, Decimal(0), "oops")


def test_value_for_column_prefers_override_and_export_rows_merge_visible_edits() -> None:
    result = WixRowResult(
        source_row=2,
        source={"Artikel Nr": "ART-1"},
        wix_row={
            "handle": "one",
            "fieldType": "PRODUCT",
            "name": "Original Name",
            "brand": "Brand",
            "plainDescription": "Desc",
            "price": "10.50",
            "cost": "5.00",
            "inventory": "2",
            "visible": "TRUE",
            "sku": "ART-1",
            "barcode": "REF-1",
        },
    )
    fake_app = SimpleNamespace(
        batch=ConversionBatch(header=["handle", "fieldType"], results=[result]),
        _preview_overrides={
            2: {
                "artikel_nr": "ART-9",
                "name": "Edited Name",
                "price": "11.75",
                "referenznummer": "REF-9",
            }
        },
    )
    fake_app._base_value_for_column = lambda current, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, current, column
    )
    fake_app._product_row_for_export = lambda current: gui_app.ConverterApp._product_row_for_export(fake_app, current)

    assert gui_app.ConverterApp._value_for_column(fake_app, result, "name") == "Edited Name"
    assert gui_app.ConverterApp._value_for_column(fake_app, result, "artikel_nr") == "ART-9"

    rows, errors = gui_app.ConverterApp._build_export_rows(fake_app)

    assert errors == []
    assert rows[0] == {
        "handle": "one",
        "fieldType": "PRODUCT",
        "name": "Edited Name",
        "brand": "Brand",
        "plainDescription": "Desc",
        "price": "11.75",
        "cost": "5.00",
        "inventory": "2",
        "visible": "TRUE",
        "sku": "ART-9",
        "barcode": "REF-9",
    }
    assert len(rows) == 1


def test_build_export_rows_rejects_invalid_edited_values() -> None:
    result = WixRowResult(
        source_row=3,
        source={"Artikel Nr": "ART-2"},
        wix_row={
            "handle": "two",
            "fieldType": "PRODUCT",
            "name": "Valid Name",
            "brand": "Brand",
            "plainDescription": "Desc",
            "price": "10.50",
            "cost": "5.00",
            "inventory": "2",
            "visible": "TRUE",
            "sku": "ART-2",
        },
    )
    fake_app = SimpleNamespace(
        batch=ConversionBatch(header=["handle", "fieldType"], results=[result]),
        _preview_overrides={3: {"price": "oops"}},
    )
    fake_app._base_value_for_column = lambda current, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, current, column
    )
    fake_app._product_row_for_export = lambda current: gui_app.ConverterApp._product_row_for_export(fake_app, current)

    rows, errors = gui_app.ConverterApp._build_export_rows(fake_app)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].field == "price"
    assert errors[0].message == "price must be numeric."


def test_build_export_rows_rewrites_duplicate_barcodes_after_edit() -> None:
    first = WixRowResult(
        source_row=4,
        source={"Artikel Nr": "ART-4"},
        wix_row={
            "handle": "four",
            "fieldType": "PRODUCT",
            "name": "First",
            "brand": "Brand",
            "plainDescription": "Desc",
            "price": "10.50",
            "cost": "5.00",
            "inventory": "2",
            "visible": "TRUE",
            "sku": "ART-4",
            "barcode": "REF-4",
        },
    )
    second = WixRowResult(
        source_row=5,
        source={"Artikel Nr": "ART-5"},
        wix_row={
            "handle": "five",
            "fieldType": "PRODUCT",
            "name": "Second",
            "brand": "Brand",
            "plainDescription": "Desc",
            "price": "10.50",
            "cost": "5.00",
            "inventory": "2",
            "visible": "TRUE",
            "sku": "ART-5",
            "barcode": "REF-5",
        },
    )
    fake_app = SimpleNamespace(
        batch=ConversionBatch(header=["handle", "fieldType"], results=[first, second]),
        _preview_overrides={5: {"referenznummer": "REF-4"}},
    )
    fake_app._base_value_for_column = lambda current, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, current, column
    )
    fake_app._product_row_for_export = lambda current: gui_app.ConverterApp._product_row_for_export(fake_app, current)

    rows, errors = gui_app.ConverterApp._build_export_rows(fake_app)

    assert errors == []
    assert len(rows) == 2
    assert rows[0]["barcode"] == "ART-4"
    assert rows[1]["barcode"] == "ART-5"


def test_apply_report_descriptions_matches_by_article_and_reference() -> None:
    first = WixRowResult(
        source_row=4,
        source={"Artikel Nr": "ART-4", "Referenz": "REF-4"},
        wix_row={"plainDescription": "", "barcode": "REF-4"},
    )
    second = WixRowResult(
        source_row=5,
        source={"Artikel Nr": "ART-5", "Referenz": "REF-5"},
        wix_row={"plainDescription": "", "barcode": "REF-5"},
    )
    fake_app = SimpleNamespace(
        batch=ConversionBatch(header=[], results=[first, second]),
        _preview_overrides={},
    )
    fake_app._base_value_for_column = lambda current, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, current, column
    )
    fake_app._value_for_column = lambda current, column: gui_app.ConverterApp._value_for_column(
        fake_app, current, column
    )
    fake_app._store_preview_override = lambda current, column, value: gui_app.ConverterApp._store_preview_override(
        fake_app, current, column, value
    )

    matched = gui_app.ConverterApp._apply_report_descriptions(
        fake_app,
        [
            ReportDescriptionRecord(
                source_row=10,
                artikel_nr="ART-4",
                referenz="",
                beschreibung="Specs 4",
            ),
            ReportDescriptionRecord(
                source_row=11,
                artikel_nr="",
                referenz="REF-5",
                beschreibung="Specs 5",
            ),
        ],
    )

    assert matched == 2
    assert fake_app._preview_overrides == {
        4: {"plain_description": "Specs 4"},
        5: {"plain_description": "Specs 5"},
    }


def test_apply_report_descriptions_prepends_description_to_existing_availability() -> None:
    result = WixRowResult(
        source_row=4,
        source={"Artikel Nr": "ART-4", "Referenz": "REF-4"},
        wix_row={
            "plainDescription": "Verfügbar in der Bijouterie am Bogen in Bremgarten AG",
            "barcode": "REF-4",
        },
    )
    fake_app = SimpleNamespace(
        batch=ConversionBatch(header=[], results=[result]),
        _preview_overrides={},
    )
    fake_app._base_value_for_column = lambda current, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, current, column
    )
    fake_app._value_for_column = lambda current, column: gui_app.ConverterApp._value_for_column(
        fake_app, current, column
    )
    fake_app._store_preview_override = lambda current, column, value: gui_app.ConverterApp._store_preview_override(
        fake_app, current, column, value
    )

    matched = gui_app.ConverterApp._apply_report_descriptions(
        fake_app,
        [
            ReportDescriptionRecord(
                source_row=10,
                artikel_nr="ART-4",
                referenz="",
                beschreibung="Specs 4",
            ),
        ],
    )

    assert matched == 1
    assert fake_app._preview_overrides == {
        4: {
            "plain_description": "Specs 4\nVerfügbar in der Bijouterie am Bogen in Bremgarten AG"
        }
    }


def test_build_export_rows_returns_update_rows_in_update_mode() -> None:
    update_batch = InventoryUpdateBatch(
        header=["sku", "inventory"],
        rows=[{"sku": "A1", "inventory": "3"}],
        results=[
            InventoryUpdateResult(
                source_row=2,
                wix_row={"sku": "A1", "inventory": "3", "name": "Alpha"},
                original_inventory="1",
                updated_inventory="3",
                matched=True,
                changed=True,
            )
        ],
    )
    fake_app = SimpleNamespace(
        mode_var=DummyVar("update"),
        update_batch=update_batch,
    )

    rows, errors = gui_app.ConverterApp._build_export_rows(fake_app)

    assert rows == [{"sku": "A1", "inventory": "3"}]
    assert errors == []


def test_build_export_rows_blocks_update_rows_with_safety_errors() -> None:
    update_batch = InventoryUpdateBatch(
        header=["sku", "inventory"],
        rows=[{"sku": "A1", "inventory": "3"}],
        results=[],
        issue_rows=[
            InventoryUpdateIssueRow(
                source_row=0,
                source={"Datei": "Wix-Export", "Marke": "Missing"},
                kind="safety",
                issues=[
                    ValidationIssue(
                        source_row=0,
                        field="brand",
                        severity=Severity.ERROR,
                        message="Wix-Export enthält keine Produktzeile für Marke 'Missing'.",
                    )
                ],
            )
        ],
    )
    fake_app = SimpleNamespace(
        mode_var=DummyVar("update"),
        update_batch=update_batch,
    )

    rows, errors = gui_app.ConverterApp._build_export_rows(fake_app)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].field == "brand"


def test_update_preview_values_include_brand_and_zero_status() -> None:
    result = InventoryUpdateResult(
        source_row=2,
        wix_row={"sku": "A1", "name": "Alpha", "brand": "Brand", "inventory": "0"},
        original_inventory="4",
        updated_inventory="0",
        matched=False,
        changed=True,
        set_to_zero=True,
    )
    fake_app = SimpleNamespace(mode_var=DummyVar("update"))

    assert gui_app.ConverterApp._base_value_for_column(fake_app, result, "brand") == "Brand"
    assert (
        gui_app.ConverterApp._base_value_for_column(fake_app, result, "status")
        == "Auf 0 gesetzt"
    )


def test_update_preview_values_label_unmanaged_wix_rows() -> None:
    result = InventoryUpdateResult(
        source_row=3,
        wix_row={
            "sku": "X1",
            "name": "External",
            "brand": "Additional Import",
            "inventory": "5",
        },
        original_inventory="5",
        updated_inventory="5",
        matched=False,
        changed=False,
        source_kind="wix_unmanaged",
    )
    fake_app = SimpleNamespace(mode_var=DummyVar("update"))

    assert (
        gui_app.ConverterApp._base_value_for_column(fake_app, result, "status")
        == "Nicht verwaltet"
    )


def test_update_report_descriptions_apply_only_to_new_rows() -> None:
    new_result = InventoryUpdateResult(
        source_row=8,
        wix_row={
            "sku": "A2",
            "barcode": "R2",
            "plainDescription": "Referenz: R2",
        },
        original_inventory="",
        updated_inventory="2",
        matched=False,
        changed=True,
        is_new_product=True,
        source_kind="diamond",
    )
    existing_result = InventoryUpdateResult(
        source_row=2,
        wix_row={
            "sku": "A1",
            "barcode": "R1",
            "plainDescription": "Existing",
        },
        original_inventory="1",
        updated_inventory="1",
        matched=True,
        changed=False,
    )
    fake_app = SimpleNamespace(
        mode_var=DummyVar("update"),
        update_batch=InventoryUpdateBatch(
            header=[],
            rows=[existing_result.wix_row, new_result.wix_row],
            results=[new_result, existing_result],
        ),
    )

    matched = gui_app.ConverterApp._apply_report_descriptions_to_new_update_rows(
        fake_app,
        [
            ReportDescriptionRecord(
                source_row=10,
                artikel_nr="A1",
                referenz="R1",
                beschreibung="Should not apply",
            ),
            ReportDescriptionRecord(
                source_row=11,
                artikel_nr="A2",
                referenz="R2",
                beschreibung="New long description",
            ),
        ],
    )

    assert matched == 1
    assert existing_result.wix_row["plainDescription"] == "Existing"
    assert new_result.wix_row["plainDescription"] == (
        "New long description\nReferenz: R2"
    )


def test_finish_inventory_update_success_blocks_download_when_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_app.messagebox, "showerror", lambda title, message: shown.append((title, message)))

    update_batch = InventoryUpdateBatch(
        header=["sku", "inventory"],
        rows=[{"sku": "A1", "inventory": "3"}],
        results=[],
        issue_rows=[
            InventoryUpdateIssueRow(
                source_row=0,
                source={"Datei": "Wix-Export", "Marke": "Missing"},
                kind="safety",
                issues=[
                    ValidationIssue(
                        source_row=0,
                        field="brand",
                        severity=Severity.ERROR,
                        message="missing",
                    )
                ],
            )
        ],
    )
    fake_app = SimpleNamespace(
        _conversion_running=True,
        configure=lambda **kwargs: None,
        _close_cell_editor=lambda save: None,
        _preview_overrides={},
        batch=object(),
        update_batch=None,
        progressbar=DummyWidget(),
        progress_text_var=DummyVar(),
        _render_preview=lambda: None,
        download_wix_button=DummyWidget(),
        download_issue_button=DummyWidget(),
        add_description_button=DummyWidget(),
        status_var=DummyVar(),
    )
    fake_app.progressbar.config["maximum"] = "1"

    gui_app.ConverterApp._finish_inventory_update_success(fake_app, update_batch)

    assert fake_app.download_wix_button.config["state"] == "disabled"
    assert fake_app.download_issue_button.config["state"] == "normal"
    assert fake_app.status_var.get() == "Bestandsupdate blockiert: Markenprüfung fehlgeschlagen."
    assert shown and shown[0][0] == "Sicherheitsprüfung fehlgeschlagen"
    assert "- missing" in shown[0][1]


def test_format_update_blocking_details_limits_error_messages() -> None:
    update_batch = InventoryUpdateBatch(
        header=[],
        rows=[],
        results=[],
        issue_rows=[
            InventoryUpdateIssueRow(
                source_row=index,
                source={},
                kind="safety",
                issues=[
                    ValidationIssue(
                        source_row=index,
                        field="brand",
                        severity=Severity.ERROR,
                        message=f"Fehler {index}",
                    )
                ],
            )
            for index in range(1, 5)
        ],
    )
    fake_app = SimpleNamespace()

    details = gui_app.ConverterApp._format_update_blocking_details(
        fake_app,
        update_batch,
    )

    assert "Fehler 1" in details
    assert "Fehler 3" in details
    assert "Fehler 4" not in details
    assert "und 1 weitere Fehler" in details


def test_download_issue_csv_uses_update_issue_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "issues.csv"
    written: dict[str, object] = {}
    messages: list[tuple[str, str]] = []
    issue_row = InventoryUpdateIssueRow(
        source_row=3,
        source={"Artikel Nr": "A2"},
        kind="unmatched_diamond",
        issues=[
            ValidationIssue(
                source_row=3,
                field="Artikel Nr",
                severity=Severity.WARNING,
                message="not matched",
            )
        ],
    )
    update_batch = InventoryUpdateBatch(
        header=["sku", "inventory"],
        rows=[],
        results=[],
        issue_rows=[issue_row],
    )
    fake_app = SimpleNamespace(
        mode_var=DummyVar("update"),
        update_batch=update_batch,
        _close_cell_editor=lambda save: None,
        _default_download_directory=lambda: tmp_path,
        _default_issue_filename=lambda severity=None: "issues.csv",
    )

    monkeypatch.setattr(gui_app.filedialog, "asksaveasfilename", lambda **kwargs: str(target))
    monkeypatch.setattr(gui_app.messagebox, "showinfo", lambda title, message: messages.append((title, message)))

    def fake_write_issue_csv(path, issue_rows):
        written["path"] = path
        written["rows"] = list(issue_rows)
        return len(written["rows"])

    monkeypatch.setattr(gui_app, "write_issue_csv", fake_write_issue_csv)

    gui_app.ConverterApp._download_issue_csv(fake_app, severity=Severity.WARNING)

    assert written == {"path": str(target), "rows": [issue_row]}
    assert messages == [("Export", "Bericht gespeichert: issues.csv")]


def test_finish_conversion_error_shows_exception_message(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_app.messagebox, "showerror", lambda title, message: shown.append((title, message)))

    fake_app = SimpleNamespace(
        _conversion_running=True,
        configure=lambda **kwargs: None,
        status_var=DummyVar(),
        progressbar=DummyWidget(),
        progress_text_var=DummyVar("Fortschritt: läuft"),
    )

    gui_app.ConverterApp._finish_conversion_error(
        fake_app,
        RuntimeError("Fehler bei der Konvertierung"),
    )

    assert fake_app._conversion_running is False
    assert fake_app.status_var.get() == "Fehler bei der Konvertierung"
    assert fake_app.progressbar.config["value"] == 0
    assert fake_app.progress_text_var.get() == ""
    assert shown == [
        ("Konvertierung fehlgeschlagen", "Fehler bei der Konvertierung")
    ]


def test_update_summary_metrics_and_open_issue_report(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_app.messagebox, "showinfo", lambda title, message: messages.append((title, message)))

    warning_result = WixRowResult(
        source_row=3,
        source={},
        wix_row={},
        issues=[ValidationIssue(source_row=3, field="brand", severity=Severity.WARNING, message="warn")],
    )
    error_result = WixRowResult(
        source_row=4,
        source={},
        wix_row={},
        issues=[ValidationIssue(source_row=4, field="price", severity=Severity.ERROR, message="bad")],
    )
    fake_app = SimpleNamespace(
        batch=ConversionBatch(header=[], results=[warning_result, error_result]),
        summary_total_var=DummyVar(),
        summary_valid_var=DummyVar(),
        error_link=DummyWidget(),
        warning_link=DummyWidget(),
    )

    gui_app.ConverterApp._update_summary_metrics(fake_app)
    assert fake_app.summary_total_var.get() == "2"
    assert fake_app.summary_valid_var.get() == "1"
    assert fake_app.error_link.config["text"] == "Fehler: 1"
    assert fake_app.warning_link.config["text"] == "Warnungen: 1"

    downloads: list[Severity] = []
    fake_app._download_issue_csv = lambda severity=None: downloads.append(severity)
    gui_app.ConverterApp._open_issue_report(fake_app, Severity.WARNING)
    assert downloads == [Severity.WARNING]

    fake_app.batch = None
    gui_app.ConverterApp._open_issue_report(fake_app, Severity.ERROR)
    assert messages[-1] == ("Hinweis", "Noch keine Konvertierung vorhanden.")


def test_run_gui_creates_app_and_starts_mainloop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeApp:
        def mainloop(self) -> None:
            calls.append("mainloop")

    monkeypatch.setattr(gui_app, "ConverterApp", FakeApp)

    gui_app.run_gui()

    assert calls == ["mainloop"]
