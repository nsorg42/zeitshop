from pathlib import Path

import pytest

from zeitshop_converter.core import ConversionBatch, Severity, ValidationIssue, WixRowResult
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
    assert args.wix_image_path == "/zeitshop"
    assert args.export_embedded_images is False
    assert args.image_export_dir is None
    assert args.images_dir is None
    assert args.issues_output is None


def test_main_runs_gui_for_default_and_gui_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(main_module, "run_gui", lambda: calls.append("gui"))

    assert main_module.main([]) == 0
    assert main_module.main(["gui"]) == 0
    assert calls == ["gui", "gui"]


def test_main_dispatches_convert_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_run_convert", lambda args: 7)

    assert main_module.main(["convert", "--diamond", "input.csv", "--output", "out.csv"]) == 7


def test_run_convert_uses_environment_image_credentials(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    batch = ConversionBatch(
        header=["handle"],
        results=[WixRowResult(source_row=2, source={}, wix_row={"handle": "one"})],
    )
    captured: dict[str, object] = {}
    written: dict[str, object] = {}

    def fake_convert_diamond_file(*, diamond_csv, wix_template_csv, options, progress_callback):
        captured["diamond_csv"] = diamond_csv
        captured["wix_template_csv"] = wix_template_csv
        captured["options"] = options
        captured["progress_callback"] = progress_callback
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
    monkeypatch.setenv("ZEITSHOP_WIX_SITE_ID", "env-site")
    monkeypatch.setenv("ZEITSHOP_WIX_API_KEY", "env-key")

    args = _build_parser().parse_args(
        [
            "convert",
            "--diamond",
            "input.csv",
            "--output",
            "out.csv",
            "--issues-output",
            "issues.csv",
            "--images-dir",
            "images",
        ]
    )

    assert _run_convert(args) == 0
    assert captured["progress_callback"] is print
    options = captured["options"]
    assert options.image_migration.enabled is True
    assert options.image_migration.image_directory == "images"
    assert options.image_migration.export_embedded_images is False
    assert options.image_migration.export_directory == ""
    assert options.image_migration.wix_site_id == "env-site"
    assert options.image_migration.wix_api_key == "env-key"
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
