from pathlib import Path

import pytest

from parsers.pdf_text import (
    doi_from_uri,
    extract_numbered_references,
    numbered_references,
    seed_doi_candidates,
    seed_doi_from_pdf,
    title_matches_first_page,
    unique_seed_doi,
    verified_seed_doi,
)


def test_doi_from_uri_handles_pdf_link_targets():
    assert doi_from_uri("https://doi.org/10.1016/j.jesp.2017.09.004") == "10.1016/j.jesp.2017.09.004"
    assert doi_from_uri("https://example.org/?doi=10.1038%2Fs41598-022-06161-3&x=1") == "10.1038/s41598-022-06161-3"
    assert doi_from_uri("https://example.org/other") is None


def test_unique_seed_doi_uses_only_unambiguous_canonical_links():
    assert unique_seed_doi([
        "https://doi.org/10.3389/fpsyg.2024.1349918",
        "https://www.frontiersin.org/articles/10.3389/fpsyg.2024.1349918/full",
    ]) == "10.3389/fpsyg.2024.1349918"
    assert unique_seed_doi([
        "https://doi.org/10.1000/a",
        "https://doi.org/10.1000/b",
    ]) is None


def test_seed_doi_candidates_include_page_text_and_unique_canonical_link():
    text = "Article DOI: 10.1000/source Supplement: 10.1000/supplement"
    assert seed_doi_candidates(text, ["https://doi.org/10.1000/source"]) == [
        "10.1000/source", "10.1000/supplement"
    ]


def test_title_verification_rejects_incidental_doi_and_short_titles():
    page = "Journal of Science\nA Long and Distinctive Article Title About Human Attention\nJane Doe"
    assert title_matches_first_page("A Long and Distinctive Article Title About Human Attention", page)
    assert not title_matches_first_page("An Unrelated Review of Human Behavior and Emotions", page)
    assert not title_matches_first_page("Human Attention", page)


def test_verified_seed_doi_rejects_wrong_crossref_title(tmp_path):
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    pdf = tmp_path / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as stream:
        writer.write(stream)
    assert verified_seed_doi(pdf, lambda _: "Wrong Article Title from Another Source") is None


def test_numbered_references_keep_wrapped_lines_together():
    text = "References\n1. A. Author. First title\ncontinued title. doi: 10.1000/first\n2. B. Author. Second title\ncontinued.\n"
    refs = numbered_references(text)
    assert len(refs) == 2
    assert refs[0].startswith("1. A. Author")
    assert "continued title" in refs[0]
    assert refs[1].startswith("2. B. Author")


def test_numbered_references_accept_brackets_and_small_pdf_marker_gaps():
    text = "[1] First citation\n[2] Second citation\n[4] Fourth citation\n[5] Fifth citation\n1) Appendix item\n"
    refs = numbered_references(text)
    assert len(refs) == 4
    assert refs[-1].startswith("[5] Fifth citation")
    assert "Appendix item" not in refs[-1]


def test_numbered_references_do_not_treat_split_doi_as_marker():
    text = "\n".join(f"{number}. Citation {number}" for number in range(1, 14))
    text += "\n10. 3389/ fnhum. 2020. 00243\n14. Next citation\n"
    refs = numbered_references(text)
    assert len(refs) == 14
    assert "10. 3389" in refs[12]


def test_local_scirep_pdf_recovers_numbered_references_and_linked_dois():
    pytest.importorskip("pypdf")
    pdf = Path("local-only/papers/2022_SciRep_BrainConnectivityGolfSkill.pdf")
    if not pdf.exists():
        pytest.skip("Local benchmark PDF is not distributed with the repository")
    refs = extract_numbered_references(pdf)
    assert len(refs) == 47
    assert sum(bool(ref.doi) for ref in refs) == 38
    assert "10.1016/j.jesp.2017.09.004" in {ref.doi for ref in refs}


def test_local_frontiers_pdf_has_seed_doi_link_when_grobid_missed_it():
    pytest.importorskip("pypdf")
    pdf = Path("local-only/papers/2024_FrontPsychol_SelfEfficacyFrontalThetaGolf.pdf")
    if not pdf.exists():
        pytest.skip("Local benchmark PDF is not distributed with the repository")
    assert seed_doi_from_pdf(pdf) == "10.3389/fpsyg.2024.1349918"
