from parsers.grobid import parse_tei


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
