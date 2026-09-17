
# 指標說明 Metrics Guide

---

## 排名 Rank

**What**
該文獻在目前這份 references 清單中的閱讀順位。

**Principle**
系統依 Reading Priority 由高至低排列候選文獻，最高者列為第 1 名，本專案也將 Priority Score 設為預設排序欄位。

**Why**
提供最直接的閱讀入口，讓使用者不必逐一比較所有指標。

**How**
排名第 1 代表這篇文獻在**目前這篇論文的 reference set 中**具有最高綜合閱讀優先度。排名具有清單相依性，換一篇 seed paper 後，reference network、候選文章與各項標準化結果都會改變，因此不同分析之間的 Rank 不適合直接比較。

---

# 閱讀優先度 Reading Priority

**What**
0–100 的綜合閱讀推薦分數，用來回答：

> 「在這篇論文引用的所有文獻中，我接下來應該先讀哪一篇？」

它綜合 field-normalized impact、局部 citation network、語意相關性、具影響力引用關係、作者影響力與來源影響力等不同訊號。

**Principle**
不同指標的原始尺度差異很大，因此系統先對各維度進行標準化。針對 Citation Count、h-index 等高度偏斜的資料，使用 percentile ranking 或 log transformation，再將各維度轉成可比較的標準尺度。各維度依設定權重加總，最後轉成 0–100。

當某個資料來源缺失時，該維度會從此次計算中移除，剩餘權重重新標準化。例如缺少 Semantic Similarity 時，系統仍會使用其他可取得的指標產生 Priority Score。

Evidence Coverage 顯示目前可用維度的權重占全部設定權重的比例。涵蓋率較低時，Reading Priority 依賴的證據類型較少。

目前的預設權重為 Field Impact 30%、Local Network Importance 25%、Semantic Relevance 25%、Influential Citation Relationship 10%、Author Impact 6% 與 Source Impact 4%。這組權重是 literature-informed project baseline，尚未經本專案資料集驗證為通用最佳值。

**Why**
單一指標只能回答特定問題。Citation Count 擅長找經典文章、Semantic Similarity 擅長找與目前論文接近的研究、Local PageRank 能找到這批 references 共同依賴的核心文獻。Reading Priority 將這些訊號整合成可直接使用的閱讀排序。

**How**
分數越高，代表系統綜合目前可取得的證據後，越建議優先閱讀。

例如兩篇同樣得到 85 分的文章，可能有完全不同的原因：一篇具有很高的 Local PageRank，另一篇可能具有很高的 Semantic Similarity 與 FWCI。因此需要搭配後方的 component metrics 判讀推薦原因。

Reading Priority 特別適合比較**同一次分析中的 references**。由於部分標準化是根據目前 reference set 進行，不同 seed paper 所產生的 80 分沒有固定的跨清單意義。

---

# Local PageRank

**What**
衡量一篇文章在**目前 reference citation network 中的結構中心性**。

這裡的 network 僅由上傳論文的 references 組成。假設 reference A 引用了 reference B，且 A、B 都存在於目前 reference set，系統建立：

$$
A \rightarrow B
$$

這些關係共同形成 local citation graph。

**Principle**
PageRank 使用遞迴方式傳遞節點的重要性，基本概念可以寫成：

$$
PR(i)=\frac{1-d}{N}
+d\sum_{j\rightarrow i}\frac{PR(j)}{L(j)}
$$

其中 \(N\) 是 network 中的文章數，\(L(j)\) 是文章 \(j\) 所連出的 citation 數量，\(d\) 是 damping factor。

因此，一篇文章的 PageRank 會受到兩件事影響：

1. 有多少篇文章引用它。
2. 引用它的文章本身在 network 中有多重要。

這種遞迴式權重傳遞正是 PageRank 與單純 citation counting 的主要差異。

**Why**
references 往往存在知識結構。一篇 foundational paper 可能被後續多篇 references 共同依賴，而另一篇文章可能只位於某個旁支。

Local PageRank 可以找出這批 references 裡的核心節點，因此很適合回答：

> 「如果我希望先理解這整組文獻的知識骨架，應該先讀哪篇？」

**How**
數值越高，代表該文章在目前 reference network 中越核心。

PageRank 的絕對數值會受到 network 大小、citation structure 與演算法參數影響，因此主要看**同一份 reference set 內的相對大小與排名**。

---

# Local In-Degree

**What**
目前 reference set 中，有多少篇其他文章引用了這篇文章。

**Principle**
在 local citation graph 中，每一條：

$$
A\rightarrow B
$$

代表 A 引用 B。

B 每收到一條這類 incoming edge，Local In-Degree 就增加 1。專案目前的定義即為「reference set 中引用此文獻的文章數」。

**Why**
它是最直接、最容易理解的 local network 指標，可以快速辨識這批 references 共同依賴哪些研究。

**How**
例如：

**Local In-Degree = 7**

代表目前上傳論文的 references 中，有 **7 篇其他 reference 引用了這篇文章**。

`0` 只代表目前這一組 references 中沒有其他文章引用它。全球 Citation Count 仍可能非常高。

Local In-Degree 與 Local PageRank 搭配閱讀最有價值：

**In-Degree** 告訴你「有多少篇引用它」；
**PageRank** 進一步考慮「引用它的那些文章本身有多核心」。

---

# Semantic Similarity

**What**
衡量某篇 reference 與目前上傳論文在研究內容上的語意相似程度。

**Principle**
本專案使用 Semantic Scholar 提供的 **SPECTER2 scientific-document embedding**。SPECTER2 將科學文獻的 title 與 abstract 表示為高維向量，其訓練過程包含 citation relationships，並針對 scientific-document representation 進行訓練。

系統取得：

$$
\vec{S}=\text{Seed paper embedding}
$$

與

$$
\vec{R}=\text{Reference embedding}
$$

再計算 cosine similarity：

$$
Similarity=
\frac{\vec S\cdot \vec R}
{\|\vec S\|\|\vec R\|}
$$

這正是目前專案規格所定義的 SPECTER2 similarity 計算方式。

**Why**
一篇 reference 很有名、citation 很高，仍可能只負責支持某個背景概念或方法。Semantic Similarity 可以直接評估這篇 reference 與目前正在閱讀的論文在概念空間中的距離。

因此它特別適合尋找：

> 「如果我想沿著目前這篇 paper 的研究問題繼續往下讀，哪些 references 最接近？」

**How**
數值越高，代表兩篇文章在模型建立的 scientific semantic space 中越接近。

若介面顯示 `0–1`，越接近 1 代表越相似；若介面將其轉成 `0–100`，只是將相同數值線性放大方便閱讀。

Semantic Similarity 描述內容鄰近程度，沒有評估研究品質、證據強度或兩篇文章的結論是否一致。它也不應被當成機率，例如 `0.82` 不代表「82% 相同」。

---

# Influential Citation

**What**
Semantic Scholar 對目前 seed paper 引用該 reference 的關係判定。

欄位使用 `是`、`否`、`無資料` 三種狀態。

**Principle**
Semantic Scholar 使用 machine-learning model 分析 citation context。模型使用 citation 的出現次數、位置與所在 section 等訊號，判斷 cited work 對 citing work 的重要程度。

本欄位描述一條特定方向的 citation edge：

$$
Seed\ paper \rightarrow Reference
$$

**Why**
這個關係可協助辨識 seed paper 實際採用、延伸或高度依賴的 reference。

Paper-level `influentialCitationCount` 描述該 reference 在整體文獻網路中收到的具影響力引用次數。它屬於 global paper impact。系統不使用該數值代替目前這條 citation edge 的判定。

**How**
`是` 表示 Semantic Scholar 將目前引用關係判定為 highly influential citation。

`否` 表示系統取得明確的 negative evidence。

`無資料` 表示引用關係或 citation context coverage 不足。系統會將該維度排除，並以其餘可用權重重新計算 Reading Priority。

---

# FWCI — Field-Weighted Citation Impact

**What**
經過研究領域、出版年份與文獻類型校正後的 citation impact。

本專案的 FWCI 來源為 **OpenAlex**。

**Principle**
OpenAlex 的核心公式：

$$
FWCI=
\frac{\text{Citations Received}}
{\text{Citations Expected}}
$$

其中實際 citations 計算文章出版年及其後三年的 citation；Expected Citations 則由相同出版年份、文獻類型與 OpenAlex Subfield 的文章計算平均值。

因此 FWCI 建立了一個標準化基準：

$$
FWCI=1
$$

代表與同類文章的世界平均相當。

**Why**
不同領域有非常不同的 citation culture，新舊文章也有不同的 citation 累積時間。

FWCI 能降低這些因素造成的偏差，因此特別適合發現：

* 年份較新但成長很快的文章
* citation culture 較低領域中的重要研究
* 在同年代、同類型文獻中特別突出的文章

**How**

**FWCI = 1.0**
約等於同類文章平均。

**FWCI = 2.0**
約為同類文章預期 citation 的兩倍。

**FWCI = 0.5**
約為同類文章預期 citation 的一半。

因此 FWCI 很適合和 Citation Count 同時看：

**Citation Count** 提供累積影響規模；
**FWCI** 提供相對於同類研究的表現。

OpenAlex、Scopus/SciVal 等資料庫可能產生不同 FWCI，原因包括 corpus coverage、field classification 與 publication-date definition 的差異。OpenAlex 官方也特別說明了這些差異。

---

# Citation Count

**What**
一篇文章目前累積收到的 citation 數量。

本專案主要使用 OpenAlex 的 `cited_by_count`。

**Principle**
OpenAlex 從各篇文章的 reference list 建立 scholarly citation graph。Reference 會先透過 DOI 等 identifier 進行匹配，缺少 DOI 時再利用 bibliographic metadata 辨識。當 A 的 reference 成功匹配到 B，B 的 Citation Count 就增加一筆 citation。

**Why**
Citation Count 是最直觀的 scholarly impact 訊號之一。

高 citation 的文章常代表它長期被研究社群使用、討論或引用，因此很適合尋找：

* 經典研究
* foundational paper
* 廣泛使用的方法
* 高度受到學界關注的工作

**How**
數值越高，代表累積 citation 越多。

解讀時應同時考慮：

出版時間越久，通常越有時間累積 citation；不同 field 的 citation density 差距也很大；review article 等文獻類型通常具有不同的 citation pattern。

因此本專案同時保留 FWCI，讓使用者同時看到「總量」與「經校正後的相對影響力」。

不同學術資料庫的 Citation Count 也可能不同，因為各資料庫收錄與 reference matching 的範圍不同。

---

# SJR Quartile

**What**
SCImago Journal Rank 將期刊依學科分類後所產生的 **Q1–Q4 期刊分區**。

**Principle**
SCImago 在每個 subject category 與年度中，以 SJR 排序期刊，再將排序結果切成四個區段：

**Q1**：最高的 25%
**Q2**：25–50%
**Q3**：50–75%
**Q4**：最低的 25%

這是 SCImago 官方採用的 quartile 定義。

同一份期刊可能同時屬於多個 subject categories，因此各 category 可以具有不同 Quartile。本專案若顯示 **Best Quartile**，代表該期刊在所屬分類中取得的最高 Quartile。SCImago 也將 Best Quartile 與其對應 category 分開記錄。

**Why**
SJR Quartile 提供非常快速的 journal-level quality context。

當 references 數量很多時，Q1/Q2 能協助使用者迅速辨識發表來源在其學科中的相對位置，因此適合作為初步瀏覽訊號。

**How**

$$
Q1 > Q2 > Q3 > Q4
$$

Q1 表示該 journal 在相應學科分類中的 SJR 位居前 25%。

若顯示的是 Best Quartile，Q1 代表該 journal 至少有一個收錄 category 位於 Q1。跨學科期刊尤其需要留意這一點。

Quartile 是 **journal-level information**。文章本身的 scholarly impact 可以再由 FWCI、Citation Count、Influential Citation Count 等 article-level 指標補充判讀。

---

# SJR Score — SCImago Journal Rank

**What**
衡量 academic journal citation prestige 的數值型指標。

Quartile 提供分區，SJR Score 則提供更細緻的連續數值。

**Principle**
SJR 以 journal citation network 為基礎，採用類似 PageRank 的 prestige propagation 概念。來自較具 prestige journal 的 citation 會傳遞較高權重，因此各 citation 對最終分數的貢獻並不完全相同。SCImago 的方法會反覆計算 journal 間的 prestige transfer，直到結果收斂，再依 journal 的 publication volume 標準化為平均 article prestige。

現行 SJR methodology 使用三年 publication window，SJR2 進一步利用 co-citation profile 的 cosine similarity，讓主題關係較接近的 citation 關係傳遞較多 prestige。

概念上可以理解成：

> **這本 journal 發表的平均文章，從整體 scholarly citation network 中獲得多少 prestige。**

**Why**
Quartile 會把大量 journal 壓縮成四個群組。例如兩本 journal 都可能是 Q1，但實際 SJR Score 差距很大。

因此 SJR Score 可以：

* 區分同 Quartile 內不同期刊
* 提供較細緻的 journal prestige 訊號
* 補充 Citation Count 無法表達的 citation-source prestige

**How**
數值越高，代表 journal 在 SCImago citation network 中取得較高的平均 prestige。

SJR Score 最適合搭配同年度資料解讀，也應考慮 journal 所屬 subject category。它是 journal-level metric，因此主要提供 publication venue 的背景資訊。

---

# Median Author h-index 與 Maximum Author h-index

**What**
該文章所有可取得作者 h-index 的中位數與最大值。

**Principle**
一位作者的 h-index 等於最大的 \(h\)，使其至少有 \(h\) 篇文章各自獲得至少 \(h\) 次 citation。

例如：

$$
h=20
$$

代表該作者至少有 **20 篇文章，每篇至少得到 20 次 citation**。

OpenAlex 將 h-index 作為 Author `summary_stats` 中的 bibliometric indicator。系統會排除缺失值，並另外記錄 Author Metadata Coverage。

**Why**
h-index 同時納入 scholarly output 與 citation impact，因此可以提供作者長期研究影響力的背景。

Median Author h-index 描述整個作者團隊的一般學術資歷。Maximum Author h-index 保留團隊中高影響力作者的訊號。作者順位不參與 Author Impact 計算。

**How**
系統先在目前 reference set 中分別標準化每篇文章的 median h-index 與 maximum h-index，再計算：

$$
Author\ Impact =
0.6097 \times MedianH_{norm}
+ 0.3903 \times MaxH_{norm}
$$

`0.6097 / 0.3903` 是根據 Jinadu et al. (2026) 發表的 `0.2918 / 0.1868` 重新正規化後得到的 project-derived values。

h-index 受到 career length、field citation culture 與資料庫 coverage 影響。Author Impact 在總分中占 6%，用於提供低權重的 authority context。

---

# Source h-index

**What**
發表來源（通常為 journal）的 h-index。

**Principle**
計算方法和作者 h-index 相同，只是將分析單位改成這個 source 所發表的所有 works。

例如：

$$
Source\ h=100
$$

代表該 source 至少有 **100 篇文章，每篇至少獲得 100 次 citation**。

OpenAlex 的 Source `summary_stats` 直接提供 h-index。

**Why**
Source h-index 提供 journal 長期累積 scholarly impact 的資訊。

SJR 著重 prestige-weighted citation network 與特定時間窗口；Source h-index 則呈現 publication source 長時間累積出的高被引作品規模，因此兩者可以互補。

**How**
數值越高，代表該 source 歷史上擁有更多持續受到大量引用的文章。

Source h-index 會受到 journal 成立時間、publication volume、field citation density 與 OpenAlex coverage 影響，因此適合當作 journal background signal。

---
