# PDF text extraction prototype (2026-09-25)

The experimental `parsers/pdf_text.py` path extracts numbered references from
text-based PDFs and assigns a DOI only when a PDF hyperlink target matches the
characters of exactly one reference. It does not call Docker or GROBID. It is
**not connected to the application pipeline**: it does not yet parse title,
authors, seed metadata, or unnumbered reference lists. Image-only PDFs were
excluded at the user's request.

## Local comparison

The corpus contains 29 successfully GROBID-processed PDFs (the 27 text-based
new papers and two prior papers). Relative to the saved GROBID output:

| Measure | Result |
|---|---:|
| PDFs with a substantial numbered list | 11 / 29 |
| References extracted in those 11 PDFs | 845 |
| GROBID references in the same 11 | 805 |
| DOI links uniquely assigned to references | 163 |
| Assigned DOI strings exactly matching GROBID | 156 |
| PDF-link DOI strings absent from GROBID output | 7 |
| Wall time to scan the 29 PDFs, one local run | 22.3 s |
| Peak process working set, same Windows run | 168 MiB |

This run used pypdf 6.19.0 on Windows. The seven PDF-only DOI strings all come from one paper. Inspection shows that
GROBID appended trailing reference numbers or a year to the corresponding DOI
strings, while the PDF links contain the clean DOI; they are not necessarily
false positives. Conversely, this comparison cannot certify reference-level
precision against GROBID, because visual checks show GROBID itself misses
some numbered entries. The prototype merges two entries when a printed
number is absent from the text layer in the dynamic-switching paper.

The process working set is not directly comparable to `docker stats` (which
previously reported roughly 4-6 GiB for the GROBID container and may include
cache). It does establish that this specific local extraction pass is much
lighter than running that container.

Run the comparison with `python -m scripts.benchmark_pdf_text` after creating
`local-only/benchmark-grobid.json`. Install the new `pypdf` requirement first.
The local benchmark PDFs and GROBID JSON are deliberately ignored by Git.

## What still blocks a production replacement

- Eighteen of the 29 PDFs do not have a supported numbered bibliography.
- A DOI link does not supply a title, authors, or year. The current Crossref
  scorer gives title 65% of its score and requires a 0.72 threshold, so raw
  unnumbered references cannot simply substitute for GROBID's structured
  records.
- No end-to-end Crossref/OpenAlex/Semantic Scholar ranking comparison has been
  run for this prototype.

## No-GROBID candidates to test next

1. **Crossref source-paper metadata.** A DOI lookup can return the publisher's
   reference list without local PDF parsing. The corpus result is below; a
   robust way to identify the seed DOI and a local fallback are still needed.
2. **PyMuPDF + a citation parser.** PyMuPDF provides fast local text extraction,
   positional blocks, and links, and can sort text by position. It does not by
   itself label author/title/source fields. See the
   [text extraction guide](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
   and [performance notes](https://pymupdf.readthedocs.io/en/latest/about-performance.html).
   It is [AGPL/commercially licensed](https://github.com/pymupdf/PyMuPDF#licensing),
   so do not add it to this MIT project without a licensing decision. A local
   installation attempt stalled during download; no corpus result is claimed.
3. **AnyStyle CLI for bibliography finding and field parsing.** Its `find`
   command accepts PDF or text, and `parse` produces structured references;
   PDF input requires `pdftotext`, and the local CLI requires Ruby. Its upstream
   documentation describes a small feature dictionary, but the total Windows
   runtime footprint and accuracy on this corpus have **not** been measured.
   See [AnyStyle](https://github.com/inukshuk/anystyle) and
   [AnyStyle CLI](https://github.com/inukshuk/anystyle-cli).

Before selecting a route, benchmark all text-based papers for
reference boundaries, DOI and title precision, end-to-end resolution, elapsed
time, and peak resident memory. Do not infer parity from DOI coverage alone.

## Follow-up: layout heuristic and Crossref metadata

A `pdfplumber` hanging-indent trial produced reference counts within three of
GROBID for six unnumbered papers, but badly over- or under-counted several
others. It is not a safe generic fallback. The scratch benchmark is
`local-only/benchmark_hanging_indent.py`.

Crossref's public `/works/{doi}` metadata was then tested against the same 29
text-based PDFs. The **automatic-DOI-input cohort** used 21 seed DOIs from the
saved GROBID baseline and three more recovered from unique `doi.org` links on
the PDFs' first pages. This is a test of Crossref's reference-list coverage,
**not** proof that all 24 seed DOIs can be found without GROBID.

| Crossref measure, automatic-DOI-input cohort | Result |
|---|---:|
| PDFs with a seed DOI supplied to Crossref | 24 / 29 |
| PDFs with a nonempty Crossref reference list | 23 / 29 |
| Reference records returned | 1,515 |
| Reference records with DOI | 1,297 |
| Unique reference DOIs, summed by PDF | 1,296 |
| Reference records with `article-title` | 690 |
| Reference records with neither DOI nor title | 134 |
| GROBID records / unique DOIs on the same 24 PDFs | 1,535 / 730 |
| DOI strings matching between Crossref and GROBID | 665 |

Title-based manual searches found source DOIs for four more PDFs. Two 1980s
papers have Crossref records but **no deposited references**. The 1985 Science
paper and the Guo micro-action paper have 30 and 74 Crossref reference records,
respectively. Including these four manually identified DOIs yields 25/29 PDFs
with a nonempty Crossref reference list and 1,619 records, but that is an
**assisted upper bound**, not an automatic-parser result. The textbook has no
single bibliography; the `lme4` paper has a DOI but no Crossref reference list.

For ten of the eleven previously inspected numbered PDFs, Crossref's record
count equals the visible final reference number; Jolly has 61 Crossref records
versus 63 visible numbered entries. Record granularity can also differ: the
1985 Science paper visibly has 26 numbered *references and notes* while
Crossref provides 30 cited-work records, because one printed entry can contain
multiple works. GROBID reported 24 entries on that PDF.

Crossref metadata is very promising for DOI-bearing recent papers and requires
no Docker or local model. It is online-only, publisher-dependent, and often
lacks titles for individual references. The current application pipeline and
ranking have **not** been switched or benchmarked end-to-end. The read-only
scratch capture is `local-only/benchmark_crossref_metadata.py`, with its cached
output in ignored `local-only/benchmark-crossref.json`. Crossref documents
[`/works/{doi}` and `query.bibliographic`](https://github.com/CrossRef/rest-api-doc).

## Follow-up: find the source DOI without GROBID (2026-09-26)

The earlier 24-paper cohort was assisted by GROBID for 21 DOIs. A new
first-page-only extractor now discovers DOI candidates from PDF text or an
unambiguous `doi.org` link, then checks the candidate's Crossref title against
the first-page text. The offline test uses the saved Crossref cache **only as a
candidate DOI-to-title lookup**; expected DOIs are not passed to the extractor.
On the 29 text PDFs it found 24 correct seed DOIs, zero wrong, and left five
unresolved (four articles plus a textbook). A specificity check matched each
of the 28 known source titles against every *other* first page: zero matches
in 756 cross-paper pairs at the current threshold. This corpus check does not
establish a general false-positive rate.

For the four remaining articles, a separate live `query.bibliographic` trial
searched Crossref with either a plausible PDF metadata title or the first two
content lines after the page header. Among the top three results for each,
only one passed the title check, and all four selected DOIs matched the saved
answer. The first two queries succeeded, the third initially received HTTP
429, and the final two succeeded on a later, delayed retry. Thus **28/29 source
DOIs were recoverable in this corpus without GROBID output**, but this is two
experimental passes rather than one integrated production algorithm. The
remaining PDF is a multilevel-analysis textbook with no single article DOI.

Using these 28 correct source DOIs as input to the *previously cached*
Crossref `/works/{doi}` responses yields nonempty deposited reference lists
for 25/29 PDFs, with 1,619 records and 1,383 DOI-bearing records. This is an
upper bound for a fully automatic app flow, not an end-to-end resolution score:
the four title-search results have not been wired into the app, publisher
reference lists may be incomplete, and record-level titles are often absent.

Reproduce the offline candidate test with
`python -m scripts.benchmark_seed_doi`. The four live title-search probes are
in `python -m scripts.benchmark_title_lookup`; avoid repeating them needlessly
because Crossref can rate-limit requests. Neither script uses Docker. The
current production pipeline still uses GROBID.
