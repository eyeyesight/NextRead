# NextRead

**[操作 Demo](DEMO.md)** · **[安裝與啟動](#windows-安裝與啟動)** · **[計分方式](#scoring-methodology)**

NextRead 是一套本機 Streamlit 工具。輸入論文 DOI 或標題即可從 Crossref 取得出版者提交的 references，補充學術指標並產生建議閱讀順序。PDF 可用於抽取或局部比對參考文獻。**Docker 完全選用**：不用安裝也能快速推薦；若要盡量取得與原論文相符的完整參考文獻，建議上傳 PDF 並選用由 Docker 執行的 GROBID。任何自動抽取結果仍需與原文核對。

Reading Priority 回答一個具體問題：

> 在目前這篇論文引用的文獻中，接下來應該先讀哪一篇？

分數代表同一次分析中的相對閱讀優先度，不代表跨領域或跨清單通用的學術品質。

## 功能

- 使用 Crossref 取得原始論文及出版者提交的 reference list；此清單可能缺漏，不能視為與 PDF 完全一致
- 選擇性上傳 PDF，以文字抽取辨識原始 DOI 或局部比對 DOI；GROBID 可在進階設定中選用
- 使用 OpenAlex 取得 field-normalized impact、作者、來源與主題資料
- 使用 reference set 內部的 citation links 計算 Local PageRank、Local In-Degree 與 Local Connectivity
- 使用 Semantic Scholar SPECTER2 embeddings 計算語意相似度
- 使用 Semantic Scholar 判斷 seed paper 指向各 reference 的 influential citation relationship
- 依可用證據計算 0–100 Reading Priority 與 Evidence Coverage
- 提供欄位篩選、文獻細節、CSV 與 JSON 匯出
- 將 API 回應快取於本機 SQLite

## 專案定位與平台支援

NextRead 目前是從原始碼執行的本機應用程式，不是已封裝的 Windows 安裝程式或單一執行檔。第一次使用前需安裝 Python 與 Python dependencies；只有選用 GROBID PDF 解析時才需要 Docker。

| 平台 | 支援狀態 |
|---|---|
| Windows 10/11 | 主要開發與驗證環境，提供 `start-nextread.cmd` 一鍵啟動器，但仍需先完成初次安裝 |
| macOS | 核心程式預期可以手動啟動，但 Windows 啟動器不適用，目前未正式測試 |
| Linux | 核心程式預期可以手動啟動，但 Windows 啟動器不適用，目前未正式測試 |

macOS 與 Linux 採 best-effort 支援，本專案不承諾持續維護各平台差異，若遇到平台特有問題，歡迎透過 issue 或 pull request 補充。

## Windows 安裝與啟動

需要先安裝：

- [Git](https://git-scm.com/download/win)
- Python 3.11 以上
- Docker Desktop 與 Docker Compose（僅選用 GROBID 時需要）

### 1. 下載專案

```powershell
git clone https://github.com/eyeyesight/NextRead.git
cd NextRead
```

### 2. 建立 Python 環境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 建立本機設定

```powershell
Copy-Item .env.example .env
notepad .env
```

API Key 均為選填，未設定時系統會嘗試使用各服務的公開存取額度，申請方式與各欄位用途請見「API 與本機設定」。

### 4. 啟動 NextRead

完成初次安裝後，可以直接執行 `start-nextread.cmd`。它只會啟動 NextRead 並在預設瀏覽器開啟 <http://localhost:8501>，不會啟動 Docker。若要使用 GROBID，請先自行啟動 Docker Desktop，再於本專案資料夾手動執行 `docker compose up -d grobid`。在介面的進階設定勾選「使用 GROBID 解析 PDF」時，NextRead 只會檢查 Docker 引擎、GROBID 容器與 API 是否就緒；未就緒時會顯示原因，待手動處理後可按「重新檢查 GROBID」。新的 Docker Compose 專案固定命名為 `nextread`（Compose 不接受大寫），容器通常顯示為 `nextread-grobid-1`，不再跟隨專案資料夾名稱。

#### 已安裝舊版 GROBID 的使用者

先前從 `AcademicReferences` 資料夾啟動的容器通常屬於 `academicreferences` 專案。更新程式碼後，舊容器**不會自動改名、停止或刪除**；NextRead 仍可辨識並使用執行中的舊容器。如果要改用新名稱，請先確認舊專案名稱（`docker compose ls`），再於本專案資料夾執行：

```powershell
docker compose -p academicreferences stop grobid
docker compose up -d grobid
```

這只會停止舊 GROBID 容器並以 `nextread` 專案啟動新容器；不會執行 `down` 或刪除舊容器。若舊專案名稱不是 `academicreferences`，請將第一行的名稱換成 `docker compose ls` 顯示的值。請勿在舊容器仍占用 8070 埠時直接啟動新容器。

也可以在 PowerShell 中手動執行：

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

若使用自訂 `GROBID_URL`，請自行啟動對應服務；NextRead 只檢查該服務的 API，不會啟動 Docker 或容器。

## macOS 與 Linux 手動啟動

macOS 與 Linux 可以使用下列流程；只有 GROBID 需要 Docker 與 Compose：

```bash
git clone https://github.com/eyeyesight/NextRead.git
cd NextRead
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
streamlit run app.py
```

開啟 <http://localhost:8501>，若 Docker image、Python wheel 或檔案權限在特定平台出現問題，請將其視為尚未驗證的平台相容性問題，而不是已承諾支援的發行環境。

## 分析流程

```text
Paper DOI or title
    ↓
Crossref publisher-deposited references
    ↓
Optional PDF DOI comparison or PDF reference extraction
    ↓
OpenAlex bibliometrics and local citation graph
    ↓
Optional Semantic Scholar enrichment
    ↓
Capability-aware ranking
    ↓
Reading Priority and Evidence Coverage
```

## 分析模式

| 模式 | 內容 |
|---|---|
| 僅解析 | 取得 Crossref references 或解析 PDF，不查詢外部指標 |
| 標準分析 | 加入 Crossref、OpenAlex、SJR 與局部引用網路 |
| 完整分析 | 加入 Semantic Scholar 語意相似度與具影響力引用關係 |

個別 provider 失敗時，系統保留已取得的結果，排除缺失維度，並顯示警告。

## Scoring methodology

Reading Priority 由六個維度組成：

$$
Score = 30I + 25N + 25S + 10H + 6A + 4V
$$

所有 component scores 會先轉換至 $[0,1]$。

| Component | Default weight | Evidence status | 計算原則 |
|---|---:|---|---|
| Field-normalized impact | 30% | Project baseline | 優先使用 OpenAlex citation-normalized percentile，其次使用 reference set 內的 FWCI percentile，再以 citation count percentile 補足 |
| Local citation network | 25% | Project baseline | 綜合 Local In-Degree、Local PageRank 與 Local Connectivity |
| Semantic relevance | 25% | Project baseline | 計算 seed paper 與 reference 的 SPECTER2 cosine similarity |
| Influential citation relationship | 10% | Project baseline | 使用 focal-paper → reference citation edge 的 `isInfluential` |
| Author influence | 6% | Project-derived | 使用全部可取得作者的 median 與 maximum h-index |
| Venue influence | 4% | Project-derived | 綜合 source h-index 與 2-year mean citedness，作為低權重的來源背景訊號 |

這組 `30 / 25 / 25 / 10 / 6 / 4` 權重是 literature-informed project baseline，文獻支持各類訊號的選擇與部分子權重，但完整六維比例尚未經本專案人工標記資料集驗證。

### Field-normalized impact

OpenAlex citation-normalized percentile 已控制領域、年份與 work type 時，系統直接使用該 $[0,1]$ 值，缺少 percentile 時，系統在目前 reference set 內對 FWCI 進行 percentile normalization，Citation Count 僅作為最後的 fallback。

這個順序降低 field citation density、publication age 與極端 citation values 對排序的影響。

### Influential citation relationship

Influential Citation 描述一條指定方向的 citation edge：

```text
Seed paper → Reference
```

`true` 代表 Semantic Scholar 判定這條引用關係具有實質影響，`false` 代表已取得明確的 negative evidence，`unknown` 代表系統缺少足夠資料。

Semantic Scholar 的 paper-level `influentialCitationCount` 描述 reference 在整體學術網路中收到的具影響力引用次數，系統不使用該數值代替 edge-level evidence。

### Author influence

系統取得一篇文章所有可用作者的 h-index，計算 raw median 與 raw maximum，再分別在目前 reference set 中標準化。

```math
\mathrm{AuthorScore}
= 0.6097 \times \mathrm{MedianH}_{\mathrm{norm}}
+ 0.3903 \times \mathrm{MaxH}_{\mathrm{norm}}
```

Jinadu et al. (2026) 發表的 author authority weights 為 median h-index `0.2918` 與 maximum h-index `0.1868`，只在這兩個 author signals 內重新正規化後，得到本專案使用的 `0.6097 / 0.3903`。

作者順位不參與 Author Influence，介面同時顯示 Author Metadata Coverage，讓缺失作者資料保持可見。

### Missing metadata

缺失資料以 `unknown` 表示，系統不將缺失值轉成零。

若可用維度集合為 $\mathcal{K}$，分數計算方式為：

$$
Score_{available} =
100 \times
\frac{\sum_{k\in\mathcal{K}} w_kx_k}
{\sum_{k\in\mathcal{K}} w_k}
$$

Evidence Coverage 等於可用維度權重除以全部設定權重，低 coverage 代表分數依賴較少類型的證據。

## 指標解讀

介面右上角的「指標說明」包含每個欄位的 What、Principle、Why 與 How，主要原始欄位包括：

- Local PageRank 與 Local In-Degree
- Semantic Similarity
- Influential Citation
- FWCI 與 Citation Count
- SJR Quartile 與 SJR Score
- Median Author h-index、Maximum Author h-index 與 Author Metadata Coverage
- Source h-index

## SJR 資料

Q1–Q4 來自 SCImago Journal Rank 官方匯出檔，系統不從 Citation Count 或 Reading Priority 推算 Quartile。

1. 前往 [SCImago journal ranking](https://www.scimagojr.com/journalrank.php) 下載 CSV
2. 在應用程式展開「進階設定」
3. 使用「手動更新 SJR 資料」驗證並安裝檔案

系統先依 ISSN 配對，再依正規化 journal title 配對，預設檔案位置為 `data/sjr/scimagojr 2024.csv`，`SJR_DATA_PATH` 可覆寫該位置。

若採用預設路徑，資料夾結構應為：

```text
NextRead/
└── data/
    └── sjr/
        └── scimagojr 2024.csv
```

CSV 不應放在專案根目錄，也不會上傳至 GitHub，每位使用者需自行下載，再透過「進階設定 → 手動更新 SJR 資料」安裝，或手動放到上述路徑，若檔名、年份或位置不同，請在 `.env` 中設定 `SJR_DATA_PATH`。

## API 與本機設定

Ranking weights 位於 `config/settings.yaml`，API 與路徑設定位於 `.env`。

專案同時保留兩個不同用途的環境設定檔：

- `.env.example` 是會上傳至 GitHub 的公開範本，只列出支援的設定名稱，不可填入真實密鑰
- `.env` 是每位使用者自己的本機設定，可能包含 API Key，因此已由 `.gitignore` 排除

首次安裝時建立 `.env`：

```powershell
Copy-Item .env.example .env
notepad .env
```

可用設定如下：

| 設定 | 如何取得 | 是否必要 |
|---|---|---|
| `CROSSREF_MAILTO` | 不需申請，填入自己的聯絡 Email 即可，Crossref 建議提供，以使用 polite pool | 選填但建議 |
| `OPENALEX_API_KEY` | 建立免費 [OpenAlex 帳號](https://openalex.org)，再前往 [Settings → API key](https://openalex.org/settings/api) 複製 Key | 選填，免費 Key 可提高使用額度 |
| `SEMANTIC_SCHOLAR_API_KEY` | 前往 [Semantic Scholar API](https://www.semanticscholar.org/product/api) 填寫 API Key 申請表，Key 會透過 Email 提供 | 選填，可降低匿名額度不穩定的影響 |
| `SJR_DATA_PATH` | SCImago CSV 的本機路徑，預設為 `data/sjr/scimagojr 2024.csv` | 使用 SJR 時必要 |
| `GROBID_URL` | GROBID 服務網址，使用本專案 Docker Compose 時維持預設值 | 保留預設值 |

```dotenv
CROSSREF_MAILTO=your-email@example.com
OPENALEX_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
SJR_DATA_PATH=data/sjr/scimagojr 2024.csv
GROBID_URL=http://localhost:8070
```

儲存 `.env` 後重新啟動 NextRead，不要將 `.env`、API Key 或其他憑證提交到 Git。

API 回應預設快取 30 天，`data/cache.db` 保存快取內容。分析頁面的「重新查詢外部 API（不使用快取）」只影響該次分析：略過現有 Crossref、OpenAlex、Semantic Scholar 回應，向已啟用的服務重新查詢並更新快取；可能較慢，也會消耗 API 額度，不會清空整個快取。畫面會顯示 OpenAlex 與 Semantic Scholar API Key 是否已載入、對應服務本次是否啟用；不會顯示 Key 值。API Key 狀態僅表示設定已載入，不代表 Key 已驗證有效。服務未啟用或命中快取時，不會用該 Key 發出新請求。

## 開發與驗證

```powershell
pytest -q
python -m compileall app.py core parsers providers resolvers graph storage
```

執行紀錄寫入 `logs/app.log`。

## Evidence status

目前 scoring model 的數值來源分成兩類：

| Value | Status |
|---:|---|
| `0.3531` venue prestige | Published value, Jinadu et al. (2026), Table 1 |
| `0.2918` median author h-index | Published value, Jinadu et al. (2026), Table 1 |
| `0.1868` maximum author h-index | Published value, Jinadu et al. (2026), Table 1 |
| `0.6097 / 0.3903` author subscore | Project-derived from the published author weights |
| `6% / 4%` author and venue split | Project-derived allocation within a project-defined 10% metadata block |
| `30 / 25 / 25 / 10 / 6 / 4` | Literature-informed project baseline |

Bibliometric composite indicators 對權重、相關指標與 normalization 方法敏感，後續版本可建立人工標記的 reference importance dataset，使用 nDCG、MAP 與 MRR 校準權重。

## References

- Forthmann, B., Doebler, P., & Mutz, R. (2024). Why summing up bibliometric indicators does not justify a composite indicator. *Scientometrics, 129*(12), 7475–7499. https://doi.org/10.1007/s11192-024-05194-x
- Hagen, N. T. (2010). Harmonic publication and citation counting: Sharing authorship credit equitably—not equally, geometrically or arithmetically. *Scientometrics, 84*(3), 785–793. https://doi.org/10.1007/s11192-009-0129-4
- Jinadu, U., Ghazvinian, P., Budathoki, A., Ampel, B. M., Sunderraman, R., & Ding, Y. (2026). *Authority bias in conversational search engines for academic paper recommendation* [Preprint]. arXiv. https://arxiv.org/abs/2609.00248
- OpenAlex. (2026, August 8). *Citations*. https://help.openalex.org/data/works/citations/
- Semantic Scholar. (n.d.). *Academic Graph API*. Retrieved September 18, 2026, from https://api.semanticscholar.org/api-docs/
- Zhang, Y., Wang, M., Gottwalt, F., Saberi, M., & Chang, E. (2019). Ranking scientific articles based on bibliometric networks with a weighting scheme. *Journal of Informetrics, 13*(2), 616–634. https://doi.org/10.1016/j.joi.2019.03.013
- Zhang, Y., Wang, M., Saberi, M., & Chang, E. (2020). Towards expert preference on academic article recommendation using bibliometric networks. In W. Lu & K. Q. Zhu (Eds.), *Trends and applications in knowledge discovery and data mining* (pp. 11–19). Springer. https://doi.org/10.1007/978-3-030-60470-7_2

## License

NextRead 採用 [MIT License](LICENSE)。
