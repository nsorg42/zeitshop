from pathlib import Path

import pytest

from zeitshop_converter.core import (
    ConversionBatch,
    InventoryUpdateBatch,
    InventoryUpdateResult,
    Severity,
    ValidationIssue,
    WixRowResult,
)
from zeitshop_converter.main import _build_parser, _run_convert
from zeitshop_converter import main as main_module


def test_cli_issue_export_includes_warning_only_rows(tmp_path: Path) -> None:
    diamond_csv = tmp_path / "diamond.csv"
    diamond_csv.write_text(
        "Artikel Nr;Referenz;Marke;Produktlinie;Kurzbeschreibung;Menge;Einstand;Verkauf\n"
        "AB;R1;Brand;Line;Item One;1;5;10\n"
        "A/B;R2;Brand;Line;Item Two;2;6;11\n",
        encoding="utf-8",
    )

    output_csv = tmp_path / "wix.csv"
    issue_csv = tmp_path / "issues.csv"
    parser = _build_parser()
    args = parser.parse_args(
        [
            "convert",
            "--diamond",
            str(diamond_csv),
            "--output",
            str(output_csv),
            "--issues-output",
            str(issue_csv),
        ]
    )

    assert _run_convert(args) == 0
    assert issue_csv.exists()

    rows = issue_csv.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert "Doppelter Handle erkannt." in rows[1]


def test_build_parser_sets_expected_defaults() -> None:
    args = _build_parser().parse_args(["convert", "--diamond", "input.csv", "--output", "out.csv"])

    assert args.inventory_mode == "numeric"
    assert args.handle_prefix == "ds-"
    assert args.issues_output is None


def test_build_parser_accepts_update_command_and_alias() -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            "update",
            "--wix-export",
            "catalog_products.csv",
            "--diamond",
            "lager.csv",
            "--output",
            "updated.csv",
        ]
    )
    alias_args = parser.parse_args(
        [
            "update-inventory",
            "--wix-export",
            "catalog_products.csv",
            "--diamond",
            "lager.csv",
            "--output",
            "updated.csv",
        ]
    )

    assert args.command == "update"
    assert args.wix_export == "catalog_products.csv"
    assert args.diamond == "lager.csv"
    assert args.output == "updated.csv"
    assert alias_args.command == "update-inventory"


def test_main_runs_gui_for_default_and_gui_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(main_module, "run_gui", lambda: calls.append("gui"))

    assert main_module.main([]) == 0
    assert main_module.main(["gui"]) == 0
    assert calls == ["gui", "gui"]


def test_main_dispatches_convert_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_run_convert", lambda args: 7)

    assert main_module.main(["convert", "--diamond", "input.csv", "--output", "out.csv"]) == 7


def test_main_dispatches_update_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_run_update", lambda args: 8)

    assert (
        main_module.main(
            [
                "update",
                "--wix-export",
                "catalog_products.csv",
                "--diamond",
                "lager.csv",
                "--output",
                "updated.csv",
            ]
        )
        == 8
    )


def test_run_convert_writes_outputs(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    batch = ConversionBatch(
        header=["handle"],
        results=[WixRowResult(source_row=2, source={}, wix_row={"handle": "one"})],
    )
    captured: dict[str, object] = {}
    written: dict[str, object] = {}

    def fake_convert_diamond_file(*, diamond_csv, wix_template_csv, options):
        captured["diamond_csv"] = diamond_csv
        captured["wix_template_csv"] = wix_template_csv
        captured["options"] = options
        return batch

    def fake_write_wix_csv(path, header, rows):
        written["wix"] = (path, list(header), list(rows))
        return len(rows)

    def fake_write_error_csv(path, rows):
        written["issues"] = (path, list(rows))
        return len(rows)

    monkeypatch.setattr(main_module, "convert_diamond_file", fake_convert_diamond_file)
    monkeypatch.setattr(main_module, "write_wix_csv", fake_write_wix_csv)
    monkeypatch.setattr(main_module, "write_error_csv", fake_write_error_csv)

    args = _build_parser().parse_args(
        [
            "convert",
            "--diamond",
            "input.csv",
            "--output",
            "out.csv",
            "--issues-output",
            "issues.csv",
        ]
    )

    assert _run_convert(args) == 0
    assert captured["diamond_csv"] == "input.csv"
    assert written["wix"] == ("out.csv", ["handle"], [{"handle": "one"}])
    assert written["issues"] == ("issues.csv", [])
    assert "Valid products: 1" in capsys.readouterr().out


def test_run_convert_skips_issue_writer_without_issues_output(monkeypatch: pytest.MonkeyPatch) -> None:
    batch = ConversionBatch(
        header=["handle"],
        results=[
            WixRowResult(
                source_row=2,
                source={},
                wix_row={"handle": "one"},
                issues=[ValidationIssue(source_row=2, field="brand", severity=Severity.WARNING, message="warn")],
            )
        ],
    )

    monkeypatch.setattr(main_module, "convert_diamond_file", lambda **kwargs: batch)
    monkeypatch.setattr(main_module, "write_wix_csv", lambda path, header, rows: len(rows))
    monkeypatch.setattr(
        main_module,
        "write_error_csv",
        lambda path, rows: (_ for _ in ()).throw(AssertionError("issue writer should not run")),
    )

    args = _build_parser().parse_args(["convert", "--diamond", "input.csv", "--output", "out.csv"])
    assert _run_convert(args) == 0


def test_run_update_writes_updated_wix_export(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    batch = InventoryUpdateBatch(
        header=["sku", "inventory"],
        rows=[{"sku": "A1", "inventory": "3"}],
        results=[
            InventoryUpdateResult(
                source_row=2,
                wix_row={"sku": "A1", "inventory": "3"},
                original_inventory="1",
                updated_inventory="3",
                matched=True,
                changed=True,
            )
        ],
    )
    captured: dict[str, object] = {}
    written: dict[str, object] = {}

    def fake_build_inventory_update_batch(*, wix_export_csv, diamond_csv):
        captured["wix_export_csv"] = wix_export_csv
        captured["diamond_csv"] = diamond_csv
        return batch

    def fake_write_wix_csv(path, header, rows):
        written["wix"] = (path, list(header), list(rows))
        return len(rows)

    monkeypatch.setattr(
        main_module,
        "build_inventory_update_batch",
        fake_build_inventory_update_batch,
    )
    monkeypatch.setattr(main_module, "write_wix_csv", fake_write_wix_csv)

    args = _build_parser().parse_args(
        [
            "update",
            "--wix-export",
            "catalog_products.csv",
            "--diamond",
            "lager.csv",
            "--output",
            "updated.csv",
        ]
    )

    assert main_module._run_update(args) == 0
    assert captured == {
        "wix_export_csv": "catalog_products.csv",
        "diamond_csv": "lager.csv",
    }
    assert written["wix"] == (
        "updated.csv",
        ["sku", "inventory"],
        [{"sku": "A1", "inventory": "3"}],
    )
    output = capsys.readouterr().out
    assert "Matched products: 1" in output
    assert "Changed products: 1" in output
