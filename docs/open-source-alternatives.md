# 從原文 PDF 取得參考文獻：開源工具調查（2026-09-26）

本調查只核對官方文件、專案原始碼與授權；沒有安裝下列候選工具，也沒有在本專案的 29 篇 PDF 上量測其辨識率、時間或記憶體。比較時須把「辨識來源論文本身」、「取得出版者提交的引用清單」和「讀取 PDF 末尾實際印出的參考文獻」分開。

## Zotero 到底能做什麼？

Zotero 內建的 **Retrieve PDF Metadata** 會用 PDF 前幾頁文字及線上服務辨識**這份 PDF 對應的論文**，建立 parent item。它不是一個把 PDF 末尾每筆 cited reference 匯出給本專案的功能。Zotero 官方對「從 PDF／文字檔中的現成 bibliography 匯入」的建議是用 DOI 等識別碼逐筆加入，或先用 AnyStyle 解析後匯入；Zotero 的「Create Bibliography」則是把**已在文獻庫的項目**排版為清單。[Zotero PDF 中繼資料說明](https://www.zotero.org/support/retrieve_pdf_metadata)、[匯入既有 bibliography 的官方說明](https://www.zotero.org/support/kb/importing_formatted_bibliographies)、[建立 bibliography 的官方說明](https://www.zotero.org/support/creating_bibliographies)。

但確實有**第三方** [Zotero Reference 外掛](https://github.com/MuiseDestiny/zotero-reference/tree/bootstrap)：它的說明列出預設的 PDF 解析來源，以及 ReadPaper、Crossref、Semantic Scholar、arXiv 等可切換來源；點刷新可取得目前 PDF 的參考文獻，亦可複製清單。這足以證明「在 Zotero 閱讀介面顯示／擷取 PDF references」有現成實作，但不同來源的清單仍須分別標示；切到 Crossref 時並不等於已核對 PDF。外掛是 [AGPL-3.0](https://github.com/MuiseDestiny/zotero-reference/blob/bootstrap/LICENSE)，而且為 Zotero 閱讀介面的外掛，不能直接視為 NextRead 的獨立 Python 函式庫或無介面服務。[外掛 README](https://github.com/MuiseDestiny/zotero-reference/tree/bootstrap#readme)。Zotero Desktop 有 [Windows 版本](https://www.zotero.org/support/kb/portable_zotero)，但這條路會要求使用者另外安裝／執行 Zotero 與外掛；本調查沒有驗證自動化 API、記憶體或 29 篇 PDF 的準確率。

## 候選工具

| 工具與來源 | 原文 PDF references | 整合與授權限制 | 對本專案的判斷 |
|---|---|---|---|
| 既有 **pypdf** 原型 | 已實作文字 PDF 的有編號清單與 DOI hyperlink 對齊；本地樣本有 11/29 篇可抽出 substantial numbered list | 已列在 `requirements.txt`，不用 Docker；它是文字擷取工具，PDF 不含語意層，掃描圖像亦需 OCR。[pypdf 官方說明](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)、[本專案量測](pdf-text-prototype.md) | 保留為快速本地核對路徑，但不能涵蓋未編號清單。22.3 秒／168 MiB 是當時 Windows **整批 29 篇**的單次測值，不能外推其他資料集。 |
| **AnyStyle / anystyle-cli** | `find` 可找 PDF 或文字中的 references；`parse` 把單筆字串拆成欄位，可輸出 CSL JSON、BibTeX 等。[CLI 官方 README](https://github.com/inukshuk/anystyle-cli) | Ruby gem；PDF 輸入另需 `pdftotext`；主程式和 CLI 為 [BSD 式授權](https://github.com/inukshuk/anystyle/blob/main/LICENSE)。Windows 可行性不能僅由 README 推定；上游 [歷史紀錄](https://github.com/inukshuk/anystyle/blob/main/HISTORY.md)稱底層 `wapiti-ruby` 支援 Windows，但本機安裝與整體資源尚未驗證。 | **最值得下一個實測**：可補未編號 reference boundary 和欄位解析，且本身授權較容易與 MIT 專案共存。若要隨程式散布 `pdftotext`，仍需另查該二進位版本及其授權義務。 |
| **refextract** | `extract_references_from_file` 從 PDF 得到 parsed references、原文 `raw_ref`；上游範例即顯示 DOI 等欄位。[上游 README](https://github.com/inspirehep/refextract) | Python，但依賴 `pdftotext`；專案標為 [GPLv2](https://github.com/inspirehep/refextract/blob/master/LICENSE)，定位在高能物理文章。Windows、CPU／RAM、跨學科品質未在此樣本驗證。 | 可當比較基準；若整合進 MIT 發行版，須先確認授權安排。 |
| **CERMINE** | 從 PDF 擷取 metadata、全文與 parsed references；單一 JAR 可輸出 JATS 或 BibTeX。[上游 README](https://github.com/CeON/CERMINE) | Java runtime／JAR，非 Docker 必需；[AGPL-3.0](https://github.com/CeON/CERMINE/blob/master/LICENSE)。本調查無 Windows 與資源量測。 | 功能完整的候選對照，但不宜直接作 MIT 專案的必備依賴，先做授權與資源評估。 |
| **GROBID**（現有基準） | 現行解析器，可抽結構化 bibliography；仍需用原文核對漏筆、拆筆等情形。[上游專案](https://github.com/grobidOrg/grobid) | 上游明說[原生 Windows 不支援，建議 Windows 用 Docker](https://github.com/grobidOrg/grobid/blob/master/doc/Frequently-asked-questions.md#windows-related-issues)。 | 作為選用的高品質解析路徑與實測基準。 |

`pdfplumber` 提供字詞座標及版面資訊，為 [MIT 授權](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt)，但本身不提供 bibliography 語意辨識；本專案先前的 hanging-indent 試驗在部分未編號 PDF 會大幅高估或低估。PyMuPDF 也只提供文字／版面基礎能力，採 [AGPL 或商業授權](https://github.com/pymupdf/PyMuPDF#licensing)。兩者都不能單靠「抽到文字」保證 refs 與原文逐筆一致。[pdfplumber 官方 README](https://github.com/jsvine/pdfplumber/blob/stable/README.md)、[本專案試驗](pdf-text-prototype.md)。

## 建議

1. **不要求原文一致時**：DOI／標題找到來源論文後，可用 Crossref 的出版者提交清單做快速推薦，但在 UI 和匯出中保留 `source=Crossref`、`pdf_verified=false`。Crossref 官方明說提交 references 並非必須，且清單取決於出版者資料。[Crossref references 說明](https://www.crossref.org/documentation/principles-practices/best-practices/references/)。
2. **要求與 PDF 一致時**：以 PDF 為核對依據，先試已存在的 pypdf 路徑；接著以 AnyStyle CLI 做 29 篇 corpus 的候選驗證。至少逐篇量測原文 reference boundary 的 precision／recall、文字與欄位對齊、DOI 辨識、最終排名變化、Windows 安裝、wall time、process peak memory。比較時保留每筆原文及來源，允許使用者檢查差異。單純 DOI 筆數相近不足以證明原文一致。[現有 prototype 的未涵蓋例子](pdf-text-prototype.md)。
3. **Zotero 的位置**：Zotero Reference 外掛適合人工檢視與產品交互參考；若想把它當自動擷取引擎，須另證實可呼叫的穩定介面、PDF 模式的逐筆輸出品質、授權及 Windows 資源需求。Zotero 官方內建 PDF metadata lookup 可輔助找 seed DOI，卻不能代替原文 bibliography 核對。[Zotero 官方說明](https://www.zotero.org/support/retrieve_pdf_metadata)、[外掛 README](https://github.com/MuiseDestiny/zotero-reference/tree/bootstrap#readme)。

以上授權欄是整合風險提示，不是法律結論；**沒有量測**的工具不能宣稱比目前 GROBID 更準或更省記憶體。
