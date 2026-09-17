from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from core.models import ReferencePaper, SeedPaper

TEI = {"tei": "http://www.tei-c.org/ns/1.0"}
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI_RE.search(value.strip())
    return match.group(0).rstrip(".,;)").lower() if match else None


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join(part.strip() for part in element.itertext() if part.strip())
    return value or None


def _year(value: str | None) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", value or "")
    return int(match.group(0)) if match else None


def _scope_value(element: ET.Element) -> str | None:
    value = _text(element)
    if value:
        return value
    start, end = element.get("from"), element.get("to")
    if start and end:
        return f"{start}-{end}"
    return start or end


class GrobidClient:
    def __init__(self, base_url: str, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/isalive", timeout=3)
            return response.ok
        except requests.RequestException:
            return False

    def process_pdf(self, pdf_path: str | Path) -> tuple[SeedPaper, list[ReferencePaper]]:
        with Path(pdf_path).open("rb") as pdf:
            response = requests.post(
                f"{self.base_url}/api/processFulltextDocument",
                files={"input": (Path(pdf_path).name, pdf, "application/pdf")},
                data={"consolidateHeader": "0", "consolidateCitations": "0", "includeRawCitations": "1"},
                timeout=self.timeout,
            )
        response.raise_for_status()
        return parse_tei(response.text)


def parse_tei(xml_text: str) -> tuple[SeedPaper, list[ReferencePaper]]:
    root = ET.fromstring(xml_text)
    header = root.find(".//tei:teiHeader", TEI)
    title_node = header.find(".//tei:titleStmt/tei:title", TEI) if header is not None else None
    author_nodes = header.findall(".//tei:sourceDesc//tei:author", TEI) if header is not None else []
    seed_authors = [_text(node) for node in author_nodes]
    idno_nodes = header.findall(".//tei:idno", TEI) if header is not None else []
    seed_doi = next((normalize_doi(_text(node)) for node in idno_nodes if (node.get("type") or "").lower() == "doi"), None)
    date_node = header.find(".//tei:publicationStmt/tei:date", TEI) if header is not None else None
    if date_node is None and header is not None:
        date_node = header.find(".//tei:sourceDesc//tei:imprint/tei:date", TEI)
    abstract_node = root.find(".//tei:profileDesc/tei:abstract", TEI)
    seed = SeedPaper(
        title=_text(title_node),
        doi=seed_doi,
        authors=[value for value in seed_authors if value],
        abstract=_text(abstract_node),
        year=_year(date_node.get("when") if date_node is not None else None),
    )

    references: list[ReferencePaper] = []
    for item in root.findall(".//tei:listBibl/tei:biblStruct", TEI):
        analytic = item.find("tei:analytic", TEI)
        monogr = item.find("tei:monogr", TEI)
        title = _text(analytic.find("tei:title", TEI)) if analytic is not None else None
        if not title and monogr is not None:
            title = _text(monogr.find("tei:title", TEI))
        authors = item.findall("tei:analytic/tei:author", TEI) or item.findall("tei:monogr/tei:author", TEI)
        source = _text(monogr.find("tei:title", TEI)) if monogr is not None else None
        imprint = monogr.find("tei:imprint", TEI) if monogr is not None else None
        scopes = imprint.findall("tei:biblScope", TEI) if imprint is not None else []
        scope_map = {(scope.get("unit") or scope.get("type") or ""): _scope_value(scope) for scope in scopes}
        date = imprint.find("tei:date", TEI) if imprint is not None else None
        raw = _text(item.find("tei:note[@type='raw_reference']", TEI)) or _text(item) or ""
        dois = item.findall(".//tei:idno", TEI)
        doi = next((normalize_doi(_text(node)) for node in dois if (node.get("type") or "").lower() == "doi"), None)
        doi = doi or normalize_doi(raw)
        references.append(
            ReferencePaper(
                raw_reference=raw,
                title=title,
                doi=doi,
                year=_year(date.get("when") if date is not None else raw),
                authors=[value for node in authors if (value := _text(node))],
                source_name=source,
                volume=scope_map.get("volume"),
                issue=scope_map.get("issue"),
                pages=scope_map.get("page") or scope_map.get("pp"),
                resolution_status="exact_doi" if doi else "unresolved",
                resolution_confidence=1.0 if doi else None,
            )
        )
    return seed, references
