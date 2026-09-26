# 從原文 PDF 取得參考文獻：開源工具調查（2026-09-26）

這份調查只查閱官方文件、專案原始碼和授權資訊。下列候選工具尚未安裝，也沒有用本專案的 29 篇 PDF 測試辨識率、耗時或記憶體用量。比較前須先分清三件事：辨識 PDF 對應哪篇論文、取得出版者提交的引用清單，以及讀取 PDF 中實際印出的參考文獻。

## Zotero 到底能做什麼？

Zotero 內建的 **Retrieve PDF Metadata** 會利用 PDF 前幾頁的文字和線上服務，辨識**這份 PDF 對應的論文**，並建立 parent item；它不會把 PDF 末尾的每筆參考文獻匯出給 NextRead。若要匯入 PDF 或文字檔中已有的 bibliography，Zotero 官方建議用 DOI 等識別碼逐筆新增，或先用 AnyStyle 解析。「Create Bibliography」則是把**文獻庫中已有的項目**排成清單。[Zotero PDF 中繼資料說明](https://www.zotero.org/support/retrieve_pdf_metadata)、[匯入既有 bibliography 的官方說明](https://www.zotero.org/support/kb/importing_formatted_bibliographies)、[建立 bibliography 的官方說明](https://www.zotero.org/support/creating_bibliographies)。

**第三方** [Zotero Reference 外掛](https://github.com/MuiseDestiny/zotero-reference/tree/bootstrap)則提供另一條路：其說明列出預設的 PDF 解析來源，也可切換 ReadPaper、Crossref、Semantic Scholar、arXiv 等來源；重新整理後，可在閱讀介面查看或複製目前 PDF 的參考文獻。這表示 Zotero 已有顯示或擷取 PDF 參考文獻的外掛，但每種來源仍須分別標示；使用 Crossref 清單並不等於核對過 PDF。外掛採 [AGPL-3.0](https://github.com/MuiseDestiny/zotero-reference/blob/bootstrap/LICENSE)，依附於 Zotero 閱讀介面，不能直接當成 NextRead 可呼叫的 Python 函式庫或無介面服務。[外掛 README](https://github.com/MuiseDestiny/zotero-reference/tree/bootstrap#readme)。Zotero Desktop 有 [Windows 版本](https://www.zotero.org/support/kb/portable_zotero)，但使用者須另外安裝並執行 Zotero 和外掛。本調查尚未驗證其自動化 API、記憶體用量，或在 29 篇 PDF 上的準確率。

## 候選工具

| 工具與來源 | 原文 PDF references | 整合與授權限制 | 對本專案的判斷 |
|---|---|---|---|
| 既有 **pypdf** 原型 | 已能抽取文字型 PDF 中有編號的清單，並對齊 DOI 超連結；本地樣本有 11/29 篇抽出具規模的編號清單 | 已列在 `requirements.txt`，不用 Docker。它只能抽取文字，不理解 PDF 的語意結構；掃描型 PDF 還需要 OCR。[pypdf 官方說明](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)、[本專案量測](pdf-text-prototype.md) | 保留作為快速本地核對方式，但無法涵蓋未編號清單。22.3 秒／168 MiB 是當時在 Windows 上**一次處理整批 29 篇**的測值，不能外推至其他資料集。 |
| **AnyStyle / anystyle-cli** | `find` 可尋找 PDF 或文字中的參考文獻；`parse` 可把單筆引文拆成欄位，輸出 CSL JSON、BibTeX 等格式。[CLI 官方 README](https://github.com/inukshuk/anystyle-cli) | Ruby gem；處理 PDF 另需 `pdftotext`。主程式和 CLI 採 [BSD 式授權](https://github.com/inukshuk/anystyle/blob/main/LICENSE)。不能只憑 README 判定 Windows 可用；上游 [歷史紀錄](https://github.com/inukshuk/anystyle/blob/main/HISTORY.md)雖稱底層 `wapiti-ruby` 支援 Windows，本機安裝和資源用量仍未驗證。 | **下一個值得實測的候選**：可能補足未編號清單的分筆與欄位解析，授權也較容易與 MIT 專案並用。若要隨程式提供 `pdftotext`，還須確認所用二進位版本的授權義務。 |
| **refextract** | `extract_references_from_file` 可從 PDF 取得解析後的參考文獻及原文 `raw_ref`；上游範例也顯示 DOI 等欄位。[上游 README](https://github.com/inspirehep/refextract) | Python 套件，但依賴 `pdftotext`；專案標示為 [GPLv2](https://github.com/inspirehep/refextract/blob/master/LICENSE)，主要面向高能物理文章。這批樣本尚未驗證 Windows 相容性、CPU／RAM 用量或跨學科品質。 | 可作比較基準；若要納入 MIT 發行版，須先確認授權安排。 |
| **CERMINE** | 可從 PDF 擷取中繼資料、全文和解析後的參考文獻；單一 JAR 可輸出 JATS 或 BibTeX。[上游 README](https://github.com/CeON/CERMINE) | 需要 Java runtime／JAR，不一定要 Docker；採 [AGPL-3.0](https://github.com/CeON/CERMINE/blob/master/LICENSE)。本調查未測 Windows 相容性和資源用量。 | 可作功能較完整的對照，但在加入 MIT 專案作為必備依賴前，應先評估授權與資源需求。 |
| **GROBID**（現有基準） | 目前的解析器，可抽取結構化參考文獻；漏筆或錯誤分筆仍須對照原文。[上游專案](https://github.com/grobidOrg/grobid) | 上游說明[不支援原生 Windows，建議在 Windows 使用 Docker](https://github.com/grobidOrg/grobid/blob/master/doc/Frequently-asked-questions.md#windows-related-issues)。 | 保留為選用的解析方式與實測基準。 |

`pdfplumber` 可取得字詞座標與版面資訊，採 [MIT 授權](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt)，但不會自行辨識參考文獻。本專案先前試過用懸掛縮排辨識分筆，在部分未編號 PDF 上明顯高估或低估。PyMuPDF 同樣主要提供文字與版面資料，採 [AGPL 或商業授權](https://github.com/pymupdf/PyMuPDF#licensing)。兩者都不能僅憑「抽到文字」保證清單與原文逐筆一致。[pdfplumber 官方 README](https://github.com/jsvine/pdfplumber/blob/stable/README.md)、[本專案試驗](pdf-text-prototype.md)。

## 建議

1. **不要求與原文完全一致時**：找到論文 DOI 或標題後，可用 Crossref 的出版者提交清單快速推薦，但介面與匯出資料仍應標示 `source=Crossref`、`pdf_verified=false`。Crossref 明確說明：出版者並非一定會提交參考文獻，清單內容取決於其提交資料。[Crossref references 說明](https://www.crossref.org/documentation/principles-practices/best-practices/references/)。
2. **要求與 PDF 一致時**：以 PDF 為核對依據，先測現有的 pypdf 路徑，再用 29 篇樣本驗證 AnyStyle CLI。至少應逐篇量測參考文獻分筆的 precision／recall、文字與欄位對齊、DOI 辨識、最終排名變化、Windows 安裝、耗時及程序記憶體峰值。比較時保留每筆原文與資料來源，供使用者核對差異。DOI 筆數接近，不足以證明兩份清單相同。[現有原型尚未涵蓋的例子](pdf-text-prototype.md)。
3. **Zotero 的用途**：Zotero Reference 外掛適合人工檢視，也可作為介面設計參考。若要把它用作自動擷取引擎，還須驗證穩定的呼叫介面、PDF 模式的逐筆輸出、授權及 Windows 資源需求。Zotero 內建的 PDF 中繼資料辨識可協助尋找原始論文 DOI，不能代替與 PDF 內參考文獻逐筆核對。[Zotero 官方說明](https://www.zotero.org/support/retrieve_pdf_metadata)、[外掛 README](https://github.com/MuiseDestiny/zotero-reference/tree/bootstrap#readme)。

表中的授權資訊只提示整合風險，並非法律結論。工具尚未經過量測，就不能宣稱比目前的 GROBID 更準確或更省記憶體。
