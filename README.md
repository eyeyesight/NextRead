# NextRead

**[操作 Demo](DEMO.md)** · **[安裝與啟動](#windows-安裝與啟動)** · **[計分方式](#scoring-methodology)**

NextRead 是在本機執行的 Streamlit 工具。輸入論文 DOI 或標題後，它會從 Crossref 取得出版者提交的參考文獻清單，補上學術指標，並建議閱讀順序。也可以上傳 PDF，抽取參考文獻或局部比對清單。**Docker 不是必備**：不安裝也能取得閱讀建議；若希望從 PDF 盡量擷取完整清單，建議使用透過 Docker 執行的 GROBID。自動抽取的結果仍須與原文核對。

Reading Priority 回答一個具體問題：

> 在目前這篇論文引用的文獻中，接下來應該先讀哪一篇？

分數只用來比較同一次分析的文獻，不代表跨領域、跨清單通用的學術品質。

## 功能

- 從 Crossref 取得原始論文及出版者提交的參考文獻清單；清單可能缺漏，不能視為與 PDF 完全一致
- 選擇性上傳 PDF，從文字中辨識原始論文 DOI，或局部比對參考文獻 DOI；也可在進階設定中選用 GROBID
- 從 OpenAlex 取得經領域校正的影響力、作者、發表來源與主題資料
- 根據清單內文獻彼此的引用關係，計算 Local PageRank、Local In-Degree 和 Local Connectivity
- 使用 Semantic Scholar SPECTER2 embeddings 計算語意相似度
- 使用 Semantic Scholar 判斷原始論文對每篇參考文獻的引用是否具有影響力
- 根據可取得的證據，計算 0–100 的 Reading Priority 和 Evidence Coverage
- 提供欄位篩選、文獻細節、CSV 與 JSON 匯出
- 將 API 回應快取於本機 SQLite

## 專案定位與平台支援

NextRead 目前須從原始碼執行，尚未提供 Windows 安裝程式或單一執行檔。初次使用需要安裝 Python 與專案依賴套件；只有選用 GROBID 解析 PDF 時才需要 Docker。

| 平台 | 支援狀態 |
|---|---|
| Windows 10/11 | 主要開發與測試環境。完成初次安裝後，可用 `start-nextread.cmd` 啟動 |
| macOS | 預期可手動啟動核心程式；Windows 啟動器不適用，尚未正式測試 |
| Linux | 預期可手動啟動核心程式；Windows 啟動器不適用，尚未正式測試 |

macOS 與 Linux 僅提供 best-effort 支援，尚未承諾持續維護各平台差異。如遇到平台特有問題，歡迎提出 issue 或 pull request。

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

API Key 都是選填；未設定時，系統會嘗試使用各服務的公開額度。`.env` 不會上傳 GitHub，換電腦後須重新建立，不能把私人 Key 寫進 `.env.example`。申請方式與欄位用途請見「API 與本機設定」。

### 4. 檢查新電腦的設定與連線

安裝依賴套件並建立 `.env` 後，在專案資料夾執行：

```powershell
.\.venv\Scripts\python.exe -m scripts.check_setup
```

檢查會顯示 OpenAlex、Semantic Scholar 的 Key 是否載入、SJR 資料是否安裝，以及執行 NextRead 的 Python 能否連上 Crossref、OpenAlex 和 Semantic Scholar；它不會印出 Key 值。Key「已載入」不等於有效，服務回應 401／403 才需要檢查授權，429 則表示額度或節流問題。如果出現 Windows 拒絕連線（`WinError 10013`），請檢查該電腦對 `.venv\Scripts\python.exe` 的防火牆、防毒軟體或代理伺服器設定；補上 API Key 無法解除本機的 socket 權限限制。不要為了測試而關閉整台電腦的防火牆。

SJR CSV 也不隨 GitHub 專案下載，檢查顯示「未安裝」時，請依[「SJR 資料」](#sjr-資料)下載並匯入。缺少 Key 或 SJR 檔案不會阻止介面啟動，但相關指標可能無法取得；外部 API 不可用時也無法保證完整分析。

### 5. 啟動 NextRead

完成初次安裝後，執行 `start-nextread.cmd` 即可啟動 NextRead，並在預設瀏覽器開啟 <http://localhost:8501>。啟動器不會開啟 Docker。若要使用 GROBID，請自行開啟 Docker Desktop，並在專案資料夾執行 `docker compose up -d grobid`。勾選介面中的「使用 GROBID 解析 PDF」時，NextRead 只會檢查 Docker、GROBID 容器和 API 是否就緒；若尚未就緒，處理畫面提示的問題後，可按「重新檢查 GROBID」。Docker Compose 專案名稱固定為 `nextread`（Compose 不接受大寫），容器通常名為 `nextread-grobid-1`，不再隨資料夾名稱變動。

#### 已安裝舊版 GROBID 的使用者

先前從 `AcademicReferences` 資料夾啟動的容器，通常屬於 `academicreferences` 專案。更新程式碼不會自動改名、停止或刪除舊容器；只要它仍在執行，NextRead 就能辨識並使用。若想改用新名稱，先用 `docker compose ls` 確認舊專案名稱，再到本專案資料夾執行：

```powershell
docker compose -p academicreferences stop grobid
docker compose up -d grobid
```

這兩個指令會停止舊 GROBID 容器，再以 `nextread` 專案啟動新容器；不會執行 `down`，也不會刪除舊容器。如果舊專案名稱不是 `academicreferences`，請把第一行換成 `docker compose ls` 顯示的名稱。舊容器仍占用 8070 埠時，請勿直接啟動新容器。

也可以在 PowerShell 中手動執行：

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

如果自行設定了 `GROBID_URL`，也須自行啟動對應服務；NextRead 只檢查其 API，不會啟動 Docker 或容器。

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
python -m scripts.check_setup
streamlit run app.py
```

接著開啟 <http://localhost:8501>。若特定平台的 Docker image、Python wheel 或檔案權限發生問題，請留意：這些平台尚未完成相容性驗證。

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
| 僅解析 | 取得 Crossref 參考文獻清單或解析 PDF，不查詢外部指標 |
| 標準分析 | 加入 Crossref、OpenAlex、SJR 與局部引用網路 |
| 完整分析 | 加入 Semantic Scholar 語意相似度與具影響力引用關係 |

即使個別資料服務查詢失敗，已取得的結果仍會保留。系統會排除缺少資料的計分維度，並顯示警告。

## Scoring methodology

Reading Priority 包含六個計分維度：

$$
Score = 30I + 25N + 25S + 10H + 6A + 4V
$$

各維度分數會先轉換到 $[0,1]$。

| Component | Default weight | Evidence status | 計算原則 |
|---|---:|---|---|
| Field-normalized impact | 30% | Project baseline | 優先採用 OpenAlex citation-normalized percentile；若缺少資料，改用清單內的 FWCI percentile，最後才用 citation count percentile |
| Local citation network | 25% | Project baseline | 結合 Local In-Degree、Local PageRank 和 Local Connectivity |
| Semantic relevance | 25% | Project baseline | 計算原始論文與參考文獻的 SPECTER2 cosine similarity |
| Influential citation relationship | 10% | Project baseline | 使用 focal-paper → reference citation edge 的 `isInfluential` |
| Author influence | 6% | Project-derived | 使用所有已取得作者的 median 和 maximum h-index |
| Venue influence | 4% | Project-derived | 結合 source h-index 與 2-year mean citedness，以低權重反映發表來源的背景 |

`30 / 25 / 25 / 10 / 6 / 4` 是參考文獻訂出的專案基準權重。相關研究支持這些訊號及部分子權重的選擇，但六個維度的完整比例尚未經本專案的人工標記資料集驗證。

### Field-normalized impact

如果 OpenAlex 提供已校正領域、年份與文獻類型的 citation-normalized percentile，系統會直接使用該 $[0,1]$ 值。若缺少這項資料，則在目前的參考文獻清單中，將 FWCI 轉為百分位；最後才以 Citation Count 補足。

這個順序有助於降低領域引用密度、出版時間和極端引用次數對排序的影響。

### Influential citation relationship

Influential Citation 判斷的是一條有方向的引用關係：

```text
Seed paper → Reference
```

`true` 表示 Semantic Scholar 判定這條引用關係具有實質影響；`false` 表示已取得明確的否定結果；`unknown` 表示資料不足。

Semantic Scholar 的 paper-level `influentialCitationCount` 是這篇參考文獻在整體學術網路中收到的具影響力引用次數，不能代替目前這條引用關係的判定。

### Author influence

系統取得一篇文章所有已知作者的 h-index，算出中位數與最大值，再分別按目前的參考文獻清單標準化。

```math
\mathrm{AuthorScore}
= 0.6097 \times \mathrm{MedianH}_{\mathrm{norm}}
+ 0.3903 \times \mathrm{MaxH}_{\mathrm{norm}}
```

Jinadu et al. (2026) 給 median h-index 的權重為 `0.2918`，maximum h-index 為 `0.1868`。只在這兩項作者指標之間重新正規化，便得到本專案使用的 `0.6097 / 0.3903`。

Author Influence 不計入作者順位。介面另有 Author Metadata Coverage，可查看作者資料缺漏的程度。

### Missing metadata

缺少的資料標為 `unknown`，不計作零。

若可用維度集合為 $\mathcal{K}$，分數計算方式為：

$$
Score_{available} =
100 \times
\frac{\sum_{k\in\mathcal{K}} w_kx_k}
{\sum_{k\in\mathcal{K}} w_k}
$$

Evidence Coverage 是可用維度的權重占全部設定權重的比例。涵蓋率越低，代表分數依據的證據類型越少。

## 指標解讀

介面右上角的「指標說明」依 What、Principle、Why 和 How 介紹各欄位。主要指標包括：

- Local PageRank 與 Local In-Degree
- Semantic Similarity
- Influential Citation
- FWCI 與 Citation Count
- SJR Quartile 與 SJR Score
- Median Author h-index、Maximum Author h-index 與 Author Metadata Coverage
- Source h-index

## SJR 資料

Q1–Q4 取自 SCImago Journal Rank 官方匯出檔，不會由 Citation Count 或 Reading Priority 推算。

1. 前往 [SCImago journal ranking](https://www.scimagojr.com/journalrank.php) 下載 CSV
2. 在應用程式展開「進階設定」
3. 使用「手動更新 SJR 資料」驗證並安裝檔案

系統會先用 ISSN 配對，再比對正規化後的期刊名稱。預設檔案位置是 `data/sjr/scimagojr 2024.csv`，可用 `SJR_DATA_PATH` 更改。

若採用預設路徑，資料夾結構應為：

```text
NextRead/
└── data/
    └── sjr/
        └── scimagojr 2024.csv
```

請勿把 CSV 放在專案根目錄或上傳至 GitHub。每位使用者須自行下載，再透過「進階設定 → 手動更新 SJR 資料」安裝，或放到上述路徑。若檔名、年份或路徑不同，請在 `.env` 設定 `SJR_DATA_PATH`。

## API 與本機設定

計分權重寫在 `config/settings.yaml`；API 與檔案路徑則設定在 `.env`。

專案提供兩種用途不同的環境設定檔：

- `.env.example` 是上傳至 GitHub 的公開範本，只列出支援的設定名稱，請勿填入真實密鑰
- `.env` 存放個人的本機設定，可能包含 API Key，因此已由 `.gitignore` 排除

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

API 回應預設快取 30 天，內容保存在 `data/cache.db`。「重新查詢外部 API（不使用快取）」只影響這次分析：略過現有的 Crossref、OpenAlex 和 Semantic Scholar 快取，重新查詢已啟用的服務並更新快取。查詢可能較慢，也會消耗 API 額度；原有快取不會整批清除。畫面會顯示 OpenAlex 與 Semantic Scholar 是否啟用，以及各自的 API Key 是否載入，但不會顯示 Key 值。顯示「API Key 已載入」不代表 Key 已驗證有效；服務未啟用或結果命中快取時，也不會使用該 Key 發出新請求。Semantic Scholar 使用 `x-api-key` HTTP 標頭，不需額外執行授權流程；金鑰只存在各電腦自己的 `.env` 中，不會隨 GitHub 複製。

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

綜合型書目計量指標容易受到權重、指標之間的相關性和標準化方法影響。未來可建立人工標記的參考文獻重要性資料集，再用 nDCG、MAP 和 MRR 校準權重。

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
