from zeitshop_converter import conversion
from zeitshop_converter.core import ConversionBatch, ConversionOptions


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

    options = ConversionOptions(handle_prefix="hp-")
    result = conversion.convert_diamond_file("input.csv", "template.csv", options=options)

    assert result is batch
    assert captured == {
        "records": records,
        "template_header": header,
        "options": options,
    }
