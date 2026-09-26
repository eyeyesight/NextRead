"""Experimental, local-only evidence extraction from text-based PDFs.

This does not replace GROBID: unnumbered bibliographies and bibliographic
field parsing are deliberately outside this module's scope.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from rapidfuzz.fuzz import partial_ratio

from core.models import ReferencePaper
from parsers.grobid import DOI_RE, normalize_doi

HEADING = re.compile(r"(?im)^\s*(references|bibliography|works cited|literature cited)\s*$")
NUMBER = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+[^\d\s]")


def doi_from_uri(uri: str) -> str | None:
    return normalize_doi(unquote(uri))


def unique_seed_doi(uris: list[str]) -> str | None:
    """Trust first-page DOI resolver links only when they identify one work."""
    candidates = set()
    for uri in uris:
        parsed = urlparse(uri)
        if parsed.netloc.lower() in {"doi.org", "www.doi.org", "dx.doi.org"}:
            if doi := normalize_doi(unquote(parsed.path)):
                candidates.add(doi)
    return next(iter(candidates)) if len(candidates) == 1 else None


def seed_doi_from_pdf(pdf_path: str | Path) -> str | None:
    from pypdf import PdfReader

    page = PdfReader(pdf_path).pages[0]
    uris = []
    for annotation in page.get("/Annots", []):
        action = annotation.get_object().get("/A") or {}
        if uri := action.get("/URI"):
            uris.append(str(uri))
    return unique_seed_doi(uris)


def seed_doi_candidates(first_page_text: str, uris: list[str]) -> list[str]:
    """Order local first-page clues; candidates still require title verification."""
    candidates = []
    if linked := unique_seed_doi(uris):
        candidates.append(linked)
    for match in DOI_RE.finditer(first_page_text):
        doi = normalize_doi(match.group(0))
        if doi and doi not in candidates:
            candidates.append(doi)
    return candidates


def title_matches_first_page(title: str, first_page_text: str, threshold: float = 85) -> bool:
    """Reject incidental reference/supplement DOIs using the source paper's title."""
    def words(value: str) -> str:
        return " ".join(re.findall(r"[\w]+", value.casefold()))

    normalized_title = words(title)
    if len(normalized_title) < 25 or len(normalized_title.split()) < 4:
        return False
    return partial_ratio(normalized_title, words(first_page_text)) >= threshold


def verified_seed_doi(pdf_path: str | Path, lookup_title) -> str | None:
    """Resolve local DOI clues via a title lookup; never trust a bare DOI alone.

    ``lookup_title`` accepts a DOI and returns its source title or None. This
    callback keeps the experimental PDF extractor independent of network I/O.
    """
    from pypdf import PdfReader

    page = PdfReader(pdf_path).pages[0]
    text = page.extract_text() or ""
    uris = []
    for annotation in page.get("/Annots", []):
        action = annotation.get_object().get("/A") or {}
        if uri := action.get("/URI"):
            uris.append(str(uri))
    for doi in seed_doi_candidates(text, uris):
        title = lookup_title(doi)
        if title and title_matches_first_page(title, text):
            return doi
    return None


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def numbered_references(text: str) -> list[str]:
    """Split an already ordered bibliography on consecutive numeric markers."""
    references: list[str] = []
    current: list[str] = []
    previous = 0
    for line in text.splitlines():
        match = NUMBER.match(line)
        number = int(match.group(1) or match.group(2)) if match else None
        if number == 1 and not current:
            current = [line.strip()]
            previous = 1
        elif number is not None and current and previous < number <= previous + 3:
            if current:
                references.append(" ".join(current))
            current = [line.strip()]
            previous = number
        elif number is not None and current and number <= previous:
            break
        elif current:
            current.append(line.strip())
    if current:
        references.append(" ".join(current))
    return references


def extract_numbered_references(pdf_path: str | Path) -> list[ReferencePaper]:
    """Extract numbered references and DOI links, or reject unsupported PDFs.

    A DOI is attached only when its characters occur in exactly one numbered
    reference. Ambiguous links are ignored rather than assigned incorrectly.
    """
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    headings = [(index, match.end()) for index, page in enumerate(pages) for match in HEADING.finditer(page)]
    if not headings:
        raise ValueError("No bibliography heading found")
    first_page, offset = headings[-1]
    text = "\n".join([pages[first_page][offset:]] + pages[first_page + 1 :])
    raw_references = numbered_references(text)
    if len(raw_references) < 10:
        raise ValueError("No substantial numbered reference list found")

    links: set[str] = set()
    for page in reader.pages[first_page:]:
        for annotation in page.get("/Annots", []):
            action = annotation.get_object().get("/A") or {}
            uri = action.get("/URI")
            if uri and (doi := doi_from_uri(str(uri))):
                links.add(doi)

    compact_references = [_compact(raw) for raw in raw_references]
    assigned: dict[int, set[str]] = {}
    for doi in links:
        token = _compact(doi)
        matches = [index for index, raw in enumerate(compact_references) if token in raw]
        if len(matches) == 1:
            assigned.setdefault(matches[0], set()).add(doi)

    papers = []
    for index, raw in enumerate(raw_references):
        candidates = assigned.get(index, set())
        doi = next(iter(candidates)) if len(candidates) == 1 else None
        papers.append(ReferencePaper(raw_reference=raw, doi=doi))
    return papers
