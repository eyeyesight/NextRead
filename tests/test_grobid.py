from types import SimpleNamespace

import pytest

from parsers.grobid import GrobidClient, parse_tei


TEI_XML = """<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt><title>Seed paper</title></titleStmt>
      <publicationStmt><date when="2025"/></publicationStmt>
      <sourceDesc><biblStruct><analytic><author><persName><forename>Ada</forename><surname>Lovelace</surname></persName></author></analytic><idno type="DOI">10.1000/seed</idno></biblStruct></sourceDesc>
    </fileDesc>
    <profileDesc><abstract><p>Seed abstract.</p></abstract></profileDesc>
  </teiHeader>
  <text><back><div><listBibl>
    <biblStruct>
      <analytic><title>Referenced paper</title><author><persName><forename>Grace</forename><surname>Hopper</surname></persName></author></analytic>
      <monogr><title>Journal</title><imprint><date when="2020"/><biblScope unit="volume">4</biblScope><biblScope unit="page" from="1" to="9"/></imprint></monogr>
      <idno type="DOI">https://doi.org/10.1000/ref.</idno><note type="raw_reference">Hopper. Referenced paper. 2020.</note>
    </biblStruct>
  </listBibl></div></back></text>
</TEI>"""


def test_parse_tei_extracts_seed_and_reference():
    seed, references = parse_tei(TEI_XML)
    assert seed.title == "Seed paper"
    assert seed.doi == "10.1000/seed"
    assert seed.year == 2025
    assert len(references) == 1
    assert references[0].title == "Referenced paper"
    assert references[0].doi == "10.1000/ref"
    assert references[0].authors == ["Grace Hopper"]
    assert references[0].pages == "1-9"
    assert references[0].resolution_status == "exact_doi"


def test_empty_fulltext_retries_reference_only_endpoint(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    empty = TEI_XML.split("  <text>")[0] + "</TEI>"
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["data"]))
        return SimpleNamespace(text=empty if len(calls) == 1 else TEI_XML,
                               raise_for_status=lambda: None)

    monkeypatch.setattr("parsers.grobid.requests.post", post)
    seed, refs = GrobidClient("http://localhost:8070").process_pdf(pdf)

    assert seed.title == "Seed paper"
    assert len(refs) == 1
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["processFulltextDocument", "processReferences"]
    assert all(data["consolidateCitations"] == "0" for _, data in calls)


def test_grobid_empty_in_both_endpoints_is_not_success(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    empty = TEI_XML.split("  <text>")[0] + "</TEI>"
    monkeypatch.setattr("parsers.grobid.requests.post", lambda *args, **kwargs:
                        SimpleNamespace(text=empty, raise_for_status=lambda: None))

    with pytest.raises(ValueError, match="GROBID.*參考文獻"):
        GrobidClient("http://localhost:8070").process_pdf(pdf)


def test_successful_grobid_does_not_send_pdf_twice(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(text=TEI_XML, raise_for_status=lambda: None)

    monkeypatch.setattr("parsers.grobid.requests.post", post)
    _, refs = GrobidClient("http://localhost:8070").process_pdf(pdf)
    assert len(refs) == 1
    assert len(calls) == 1
