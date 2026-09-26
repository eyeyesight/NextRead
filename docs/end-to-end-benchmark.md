# Crossref deposited references vs PDF/GROBID: offline end-to-end benchmark

Run date: 2026-09-26. Run `\.venv\Scripts\python.exe -m scripts.benchmark_end_to_end` from the repository root. The script emits machine-readable JSON with totals and per-paper results. It reads ignored local files `local-only/benchmark-grobid.json`, `local-only/benchmark-crossref.json`, `data/cache.db`, and the local SJR CSV. It makes **no HTTP calls** and writes no data. One Windows run took 0.95 seconds after startup; this is cached computation time, not PDF parsing or online lookup time.

## Cohort and method

The source corpus has 29 text PDFs processed by GROBID, with two image-only PDFs excluded. Crossref deposited nonempty reference lists for 25 of those 29. This benchmark compares those same 25 PDFs. The source DOI is supplied from the saved Crossref capture; this tests reference identification and recommendation, **not** the success rate of source DOI discovery. Four PDFs without a deposited list cannot enter a two-path comparison and require another source of references.

The baseline is each saved GROBID reference, then the project's `CrossrefResolver`. The alternative is each Crossref-deposited source-paper reference, mapped into `ReferencePaper` with the same fields currently used by `CrossrefResolver.source_work`, then the same resolver. The saved Crossref capture retained DOI, article title, author, year, and unstructured text, but omitted some deposited fields such as journal title; this limits the alternative's DOI-free matching compared with a fresh, full Crossref response. DOI-bearing records are accepted as exact DOI by the project's resolver. DOI-free references are searched only in the preexisting Crossref query cache; uncached searches return an empty response. Both paths use the same cached OpenAlex and Semantic Scholar enrichment, local SJR data, citation-graph builder, `rank_papers`, and configured weights. A missing provider response stays missing. No live lookup fills cache gaps. The script does not incorporate the experimental PDF-text parser.

To compare cited works before resolution, the script pairs records one-to-one by normalized DOI, then by normalized title similarity at least 95/100 with compatible year (within one year when both years exist). Conflicting nonempty DOIs cannot be matched by title. This is a **conservative matching proxy**, not human-verified precision or recall: sparse titles and reference formatting can hide true matches, while a near-identical title can still occasionally be ambiguous. GROBID is a comparator, not a ground truth transcript of each PDF; Crossref counts can differ because of publisher omissions or different reference granularity.

## Reference identification

| Measure across 25 PDFs | PDF/GROBID path | Crossref deposited path |
|---|---:|---:|
| Input reference records | 1,582 | 1,619 |
| Records with DOI after the cached resolver | 855 | 1,383 |
| Records with a rank score from cached providers | 173 | 165 |

Before resolution, 665 pairs matched by DOI and another 227 by title, totaling **892 one-to-one matched cited works**. After cached resolution, 790 pairs matched by DOI and 182 additional pairs by title, totaling 972. Some title-only pairs gained DOI assignments, so the lower title-only subtotal does not by itself imply citations were lost. These numbers say much more than DOI totals but do **not** establish which path correctly transcribed the PDF.

Eleven of the 25 papers have identical record counts, but count equality is weak evidence of citation equality. For example, `2023_SJMSS_SMRNeurofeedbackGolf.pdf` has 60 records in each path and only four conservative raw matches. Conversely, `2022_PsychSportExerc_FunctionSpecificNeurofeedbackGolf.pdf` has 67 records in each and 66 raw matches. `Guo et al. ... Micro-action ... .pdf` also has 74 records in each, but only six raw matches because its GROBID records have few usable raw DOIs/titles; cached resolution raises matching substantially. Count equality must not be presented as a fidelity guarantee.

## Recommendation results and coverage

The full top-k comparison takes each route's scored, DOI-identified candidates in its own ranking. The shared-set comparison filters each already-scored ranking to DOIs appearing in both and then compares the top-k within that common set. Scores still reflect each route's full candidate pool and local citation graph; filtering does not recompute scores. Spearman correlation uses relative ranks of the common DOI set. These comparisons are defined only where enough rankable records exist.

| Source paper | Rankable GROBID / Crossref | Shared ranked DOIs | Full top 5 overlap | Full top 10 overlap | Shared-set top 10 overlap | Shared-set Spearman |
|---|---:|---:|---:|---:|---:|---:|
| Guo micro-action, 2024 | 66 / 64 | 64 | 5/5 | 10/10 | 10/10 | 0.9999 |
| Jolly, 2021 | 54 / 45 | 45 | 4/5 | 10/10 | 10/10 | 0.9920 |
| Rito Lima et al., 2020 | 39 / 38 | 38 | 5/5 | 9/10 | 9/10 | 0.9980 |

For Rito Lima, the GROBID-path full top ten contains DOI `10.3389/fncom.2015.00027`, absent from the Crossref candidate set; the Crossref-path top ten instead contains `10.1007/bf00318203`. Even after filtering to shared DOIs, top-ten overlap remains 9/10 (`10.1109/tnsre.2017.2699598` versus `10.1007/bf00318203` at the boundary), showing that the different full candidate pools also change scores and ranks. Across these three papers, full top-ten agreement is 29/30 placements. They are the **only three** papers where both paths have at least ten rankable candidates in the existing cache. Eleven papers have at least one scored item in both paths, 12 have none in either, and two have scored items only in the Crossref path. The other 22 papers do not support a meaningful top-ten equivalence claim. Mean shared-set Spearman across papers with at least two shared ranked DOIs is 0.999, heavily influenced by small two-item comparisons; the three full-rank examples above are more informative.

The cached enrichment coverage is the limiting factor. Relative to all input records, feature values were available as follows:

| Score dimension | PDF/GROBID | Crossref |
|---|---:|---:|
| Field impact | 173 / 1,582 | 165 / 1,619 |
| Local network | 173 / 1,582 | 165 / 1,619 |
| Semantic relevance | 77 / 1,582 | 72 / 1,619 |
| Influential citation | 82 / 1,582 | 75 / 1,619 |
| Author impact | 171 / 1,582 | 163 / 1,619 |
| Source impact | 142 / 1,582 | 135 / 1,619 |

The cache reported 155 Crossref, 1,359 OpenAlex, and 339 Semantic Scholar hits, and 942, 2,347, and 1,940 misses respectively (provider lookups, not unique papers). Because the cache largely reflects prior analyses of the three well-covered papers, the apparent top-ten stability should not be generalized to the other 22. The benchmark uses cached provider responses without TTL filtering, so it is a fixed offline snapshot rather than a current-data evaluation.

## Decision supported by this benchmark

Crossref's deposited list yields many more immediately DOI-identified references and can support quick recommendations for papers with deposited references. It cannot certify that the references match the source PDF. The observed ranking agreement is encouraging on the three cache-rich papers, but the benchmark does not establish general recommendation parity. To evaluate that claim, collect complete provider data for a representative sample, manually adjudicate cited-work identity and PDF boundaries, and rerun both paths on the same snapshot. Users who need source-faithful references still need PDF validation or PDF-based extraction.
