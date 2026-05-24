from zeitshop_converter import conversion
from zeitshop_converter.core import ConversionBatch, ConversionOptions, ImageArchiveOptions


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
    monkeypatch.setattr(
        conversion,
        "attach_archive_media_rows",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    options = ConversionOptions(handle_prefix="hp-")
    result = conversion.convert_diamond_file("input.csv", "template.csv", options=options)

    assert result is batch
    assert captured == {
        "records": records,
        "template_header": header,
        "options": options,
    }


def test_convert_diamond_file_attaches_archive_media_rows_when_enabled(monkeypatch) -> None:
    batch = ConversionBatch(header=["handle", "media"], results=[])
    attached: dict[str, object] = {}

    monkeypatch.setattr(conversion, "read_diamond_file", lambda path: [])
    monkeypatch.setattr(conversion, "load_template_header", lambda path: ["handle", "media"])
    monkeypatch.setattr(conversion, "convert_records", lambda **kwargs: batch)

    def fake_attach_archive_media_rows(*, batch, options, progress_callback):
        attached["batch"] = batch
        attached["options"] = options
        attached["progress_callback"] = progress_callback

    monkeypatch.setattr(conversion, "attach_archive_media_rows", fake_attach_archive_media_rows)

    options = ConversionOptions(
        image_archive=ImageArchiveOptions(enabled=True, manifest_path="manifest.csv"),
    )
    callback = lambda message: None

    result = conversion.convert_diamond_file("input.csv", options=options, progress_callback=callback)

    assert result is batch
    assert attached == {
        "batch": batch,
        "options": options.image_archive,
        "progress_callback": callback,
    }
