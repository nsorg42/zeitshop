import json
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from zeitshop_converter.core import ConversionBatch, ImageMigrationOptions, Severity, ValidationIssue, WixRowResult
from zeitshop_converter.gui import app as gui_app


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
            handle_prefix="custom-",
            default_visible=False,
            output_dir="/tmp/out",
            image_migration_enabled=True,
            image_directory="/tmp/images",
            export_embedded_images=True,
            export_directory="/tmp/exported",
            wix_site_id="site-1",
            wix_api_key="secret",
            wix_image_path="/media/path",
        )
    )

    loaded = gui_app._load_settings()

    assert loaded == gui_app.GuiSettings(
        handle_prefix="custom-",
        default_visible=False,
        output_dir="/tmp/out",
        image_migration_enabled=True,
        image_directory="/tmp/images",
        export_embedded_images=True,
        export_directory="/tmp/exported",
        wix_site_id="site-1",
        wix_api_key="secret",
        wix_image_path="/media/path",
    )

    settings_path.write_text(
        json.dumps({"handle_prefix": " ", "wix_image_path": " "}),
        encoding="utf-8",
    )
    loaded = gui_app._load_settings()
    assert loaded.handle_prefix == "ds-"
    assert loaded.wix_image_path == "/zeitshop"


def test_build_options_uses_environment_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_app = SimpleNamespace(
        settings=gui_app.GuiSettings(
            handle_prefix="hp-",
            default_visible=False,
            image_migration_enabled=True,
            image_directory="/images",
            export_embedded_images=True,
            export_directory="/exports",
            wix_site_id="",
            wix_api_key="stored-key",
            wix_image_path="/target",
        )
    )
    monkeypatch.setenv("ZEITSHOP_WIX_SITE_ID", "env-site")
    monkeypatch.setenv("ZEITSHOP_WIX_API_KEY", "env-key")

    options = gui_app.ConverterApp._build_options(fake_app)

    assert options.default_visible is False
    assert options.handle_prefix == "hp-"
    assert options.image_migration == ImageMigrationOptions(
        enabled=True,
        image_directory="",
        export_embedded_images=True,
        export_directory="/exports",
        wix_site_id="env-site",
        wix_api_key="stored-key",
        wix_file_path="/target",
    )


def test_default_download_helpers_use_configured_and_source_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_app = SimpleNamespace(
        settings=gui_app.GuiSettings(output_dir="~/exports"),
        diamond_path=Path("/tmp/input.csv"),
    )
    assert gui_app.ConverterApp._default_download_directory(fake_app) == Path("~/exports").expanduser()
    assert gui_app.ConverterApp._default_wix_filename(fake_app) == "input_wix_import.csv"
    assert gui_app.ConverterApp._default_issue_filename(fake_app, Severity.ERROR) == "input_fehler.csv"
    assert gui_app.ConverterApp._default_issue_filename(fake_app, Severity.WARNING) == "input_warnungen.csv"
    assert gui_app.ConverterApp._default_issue_filename(fake_app) == "input_issues.csv"

    fake_app.settings.output_dir = ""
    assert gui_app.ConverterApp._default_download_directory(fake_app) == Path("/tmp")

    fake_app.diamond_path = None
    assert gui_app.ConverterApp._default_download_directory(fake_app) == Path.home()
    assert gui_app.ConverterApp._default_wix_filename(fake_app) == "wix_import.csv"


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
            "cost",
            "referenznummer",
        ),
        _preview_overrides={},
    )
    fake_app._base_value_for_column = lambda result, column: gui_app.ConverterApp._base_value_for_column(
        fake_app, result, column
    )
    fake_app._value_for_column = lambda result, column: gui_app.ConverterApp._value_for_column(fake_app, result, column)

    gui_app.ConverterApp._report_progress(fake_app, "Bilder 2/5: Working")
    assert fake_app.status_var.get() == "Bilder 2/5: Working"
    assert fake_app.progress_text_var.get() == "Fortschritt: 2/5"
    assert progressbar.config["maximum"] == 5
    assert progressbar.config["value"] == 2
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
        media_rows=[{"handle": "one", "fieldType": "MEDIA", "media": "https://example.com/pic.jpg"}],
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
    assert rows[1] == {"handle": "one", "fieldType": "MEDIA", "media": "https://example.com/pic.jpg"}


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
        RuntimeError("Internet nötig um Bilder automatisch hochzuladen"),
    )

    assert fake_app._conversion_running is False
    assert fake_app.status_var.get() == "Internet nötig um Bilder automatisch hochzuladen"
    assert fake_app.progressbar.config["value"] == 0
    assert fake_app.progress_text_var.get() == ""
    assert shown == [
        ("Konvertierung fehlgeschlagen", "Internet nötig um Bilder automatisch hochzuladen")
    ]


def test_run_conversion_blocks_offline_wix_uploads_before_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_app.messagebox, "showerror", lambda title, message: shown.append((title, message)))
    monkeypatch.setattr(
        gui_app,
        "ensure_wix_upload_connectivity",
        lambda: (_ for _ in ()).throw(
            gui_app.WixUploadConnectivityError("Internet nötig um Bilder automatisch hochzuladen")
        ),
    )

    fake_app = SimpleNamespace(
        diamond_path=Path("/tmp/input.xlsx"),
        _conversion_running=False,
        _build_options=lambda: gui_app.ConversionOptions(
            image_migration=gui_app.ImageMigrationOptions(
                enabled=True,
                wix_site_id="site-1",
                wix_api_key="api-1",
            )
        ),
        _ensure_wix_upload_connectivity=lambda options: gui_app.ConverterApp._ensure_wix_upload_connectivity(
            fake_app,
            options,
        ),
        status_var=DummyVar(),
        progressbar=DummyWidget(),
        progress_text_var=DummyVar("Fortschritt: läuft"),
    )

    gui_app.ConverterApp._run_conversion(fake_app)

    assert fake_app._conversion_running is False
    assert fake_app.status_var.get() == "Internet nötig um Bilder automatisch hochzuladen"
    assert fake_app.progressbar.config["value"] == 0
    assert fake_app.progress_text_var.get() == ""
    assert shown == [
        ("Konvertierung fehlgeschlagen", "Internet nötig um Bilder automatisch hochzuladen")
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
