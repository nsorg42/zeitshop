from pathlib import Path

from zeitshop_converter import conversion
from zeitshop_converter.core import ConversionBatch, ConversionOptions, ImageMigrationOptions


def test_convert_diamond_file_delegates_reader_template_and_pipeline(monkeypatch) -> None:
    records = ["records"]
    header = ["handle"]
    batch = ConversionBatch(header=header, results=[])
    captured: dict[str, object] = {}

    monkeypatch.setattr(conversion, "read_diamond_file", lambda path: records)
    monkeypatch.setattr(conversion, "load_template_header", lambda path: header)

    def fake_convert_records(*, records, template_header, options):
        captured["records"] = records
        captured["template_header"] = template_header
        captured["options"] = options
        return batch

    monkeypatch.setattr(conversion, "convert_records", fake_convert_records)
    monkeypatch.setattr(conversion, "attach_media_rows", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))

    options = ConversionOptions(handle_prefix="hp-")
    result = conversion.convert_diamond_file("input.csv", "template.csv", options=options)

    assert result is batch
    assert captured == {
        "records": records,
        "template_header": header,
        "options": options,
    }


def test_convert_diamond_file_attaches_media_rows_when_enabled(monkeypatch) -> None:
    batch = ConversionBatch(header=["handle", "media"], results=[])
    attached: dict[str, object] = {}

    monkeypatch.setattr(conversion, "read_diamond_file", lambda path: [])
    monkeypatch.setattr(conversion, "load_template_header", lambda path: ["handle", "media"])
    monkeypatch.setattr(conversion, "convert_records", lambda **kwargs: batch)

    def fake_attach_media_rows(*, batch, options, source_file, progress_callback):
        attached["batch"] = batch
        attached["options"] = options
        attached["source_file"] = source_file
        attached["progress_callback"] = progress_callback

    monkeypatch.setattr(conversion, "attach_media_rows", fake_attach_media_rows)

    options = ConversionOptions(
        image_migration=ImageMigrationOptions(enabled=True, image_directory="images"),
    )
    callback = lambda message: None

    result = conversion.convert_diamond_file("input.csv", options=options, progress_callback=callback)

    assert result is batch
    assert attached == {
        "batch": batch,
        "options": options.image_migration,
        "source_file": "input.csv",
        "progress_callback": callback,
    }


def test_convert_diamond_file_writes_mapping_when_export_is_enabled(monkeypatch) -> None:
    records = ["records"]
    batch = ConversionBatch(header=["handle"], results=[])
    captured: dict[str, object] = {}

    def fake_read_diamond_file(path, extract_embedded_images=False, image_export_dir=None):
        captured["path"] = path
        captured["extract_embedded_images"] = extract_embedded_images
        captured["image_export_dir"] = image_export_dir
        return records

    monkeypatch.setattr(conversion, "read_diamond_file", fake_read_diamond_file)
    monkeypatch.setattr(conversion, "load_template_header", lambda path: ["handle"])
    monkeypatch.setattr(conversion, "convert_records", lambda **kwargs: batch)
    monkeypatch.setattr(
        conversion,
        "default_xlsx_image_mapping_path",
        lambda source_path, output_dir=None: f"/tmp/{Path(str(source_path)).stem}_image_mapping.csv",
    )
    monkeypatch.setattr(
        conversion,
        "write_image_mapping_csv",
        lambda path, rows: captured.update({"mapping_path": path, "mapping_records": rows}) or 1,
    )
    monkeypatch.setattr(conversion, "attach_media_rows", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))

    options = ConversionOptions(
        image_migration=ImageMigrationOptions(
            enabled=False,
            export_embedded_images=True,
            export_directory="exports",
        ),
    )

    result = conversion.convert_diamond_file("input.xlsx", options=options)

    assert result is batch
    assert captured == {
        "path": "input.xlsx",
        "extract_embedded_images": True,
        "image_export_dir": "exports",
        "mapping_path": "/tmp/input_image_mapping.csv",
        "mapping_records": records,
    }
