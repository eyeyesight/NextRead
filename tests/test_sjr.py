from core.models import ReferencePaper
from providers.sjr import SjrProvider


SJR_CSV = """Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile;H index;Categories
1;12345;Journal of Motor Learning;journal;1234-5678, 8765-4321;2,345;Q1;120;Neuroscience (Q1)
2;67890;Applied Driving Research;journal;1111-2222;0,456;Q3;25;Human Factors (Q3)
"""


def test_sjr_matches_issn_before_title(tmp_path):
    path = tmp_path / "scimagojr 2024.csv"
    path.write_text(SJR_CSV, encoding="utf-8")
    paper = ReferencePaper(source_name="Different title", source_issns=["12345678"])

    provider = SjrProvider(path)
    provider.enrich([paper])

    assert paper.sjr_quartile == "Q1"
    assert paper.sjr_score == 2.345
    assert paper.sjr_year == 2024
    assert paper.sjr_match_method == "issn"


def test_sjr_falls_back_to_normalized_source_title(tmp_path):
    path = tmp_path / "scimagojr 2024.csv"
    path.write_text(SJR_CSV, encoding="utf-8")
    paper = ReferencePaper(source_name="Applied Driving Research")

    SjrProvider(path).enrich([paper])

    assert paper.sjr_quartile == "Q3"
    assert paper.sjr_match_method == "title"


def test_sjr_year_comes_from_csv_header_not_storage_filename(tmp_path):
    path = tmp_path / "current-sjr.csv"
    content = SJR_CSV.replace("Categories\n", "Total Docs. (2025);Categories\n").replace(
        ";Neuroscience (Q1)\n", ";10;Neuroscience (Q1)\n"
    ).replace(";Human Factors (Q3)\n", ";20;Human Factors (Q3)\n")
    path.write_text(content, encoding="utf-8")

    provider = SjrProvider(path)

    assert provider.year == 2025
