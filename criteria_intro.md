
# 指標說明 Metrics Guide

---

## 排名 Rank

**What**
這篇文獻在目前參考文獻清單中的閱讀順位。

**Principle**
系統依 Reading Priority 由高到低排列文獻，分數最高者排第 1 名。表格也預設按 Priority Score 排序。

**Why**
讓你先看到值得閱讀的文獻，不必逐項比較所有指標。

**How**
排名第 1，表示這篇文獻在**目前論文的參考文獻清單中**有最高的綜合閱讀優先度。換一篇原始論文，候選文獻、引用網路和標準化結果都可能改變；不同分析的排名不宜直接比較。

---

# 閱讀優先度 Reading Priority

**What**
0–100 的綜合閱讀推薦分數，用來回答：

> 「在這篇論文引用的所有文獻中，我接下來應該先讀哪一篇？」

分數結合經領域校正的引用影響力、清單內引用網路、語意相關性、具影響力引用關係、作者影響力和發表來源影響力。

**Principle**
各指標的原始尺度不同，系統會先將它們標準化。Citation Count、h-index 等分布偏斜的資料，會先做百分位排名或對數轉換，再換算成可比較的尺度。最後按設定權重加總，轉成 0–100 分。

如果某項資料缺失，系統會排除對應維度，重新分配其餘權重。例如沒有 Semantic Similarity，仍可用其他已取得的指標計算 Priority Score。

Evidence Coverage 是可用維度的權重占全部設定權重的比例。涵蓋率越低，Reading Priority 依據的證據類型越少。

預設權重為 Field Impact 30%、Local Network Importance 25%、Semantic Relevance 25%、Influential Citation Relationship 10%、Author Impact 6% 和 Source Impact 4%。這是參考文獻訂出的專案基準權重，尚未經本專案資料集驗證為通用最佳值。

**Why**
不同指標各有用途：Citation Count 有助於找出被大量引用的文章；Semantic Similarity 比較研究內容；Local PageRank 則反映清單內文獻共同依賴哪些研究。Reading Priority 將它們整合為閱讀順序。

**How**
分數越高，表示根據目前取得的資料，這篇文獻越值得優先閱讀。

兩篇同為 85 分的文章，理由可能不同：一篇的 Local PageRank 高，另一篇的 Semantic Similarity 和 FWCI 高。請搭配各項指標查看分數的來源。

Reading Priority 適合比較**同一次分析的參考文獻**。部分指標按目前清單標準化，因此不同原始論文得到的 80 分，不能視為相同程度的優先度。

---

# Local PageRank

**What**
衡量文章在**目前參考文獻引用網路中的中心程度**。

這個網路只包含目前清單中的參考文獻。若文獻 A 引用文獻 B，而且兩者都在清單中，系統便建立以下關係：

$$
A \rightarrow B
$$

所有這類關係組成清單內引用網路。

**Principle**
PageRank 會沿著引用關係反覆傳遞權重，概念如下：

$$
PR(i)=\frac{1-d}{N}
+d\sum_{j\rightarrow i}\frac{PR(j)}{L(j)}
$$

其中 \(N\) 是網路中的文章數，\(L(j)\) 是文章 \(j\) 引用其他文章的數量，\(d\) 是 damping factor。

一篇文章的 PageRank 主要受兩件事影響：

1. 有多少篇文章引用它。
2. 引用它的文章本身在 network 中有多重要。

PageRank 不只計算被引用次數，還會考慮引用者本身的重要性。

**Why**
一份參考文獻清單通常有自己的知識脈絡：有些基礎研究被多篇文獻共同引用，有些則只與其中一小部分相關。

Local PageRank 有助於找出清單中的核心文獻，例如：

> 「如果我希望先理解這整組文獻的知識骨架，應該先讀哪篇？」

**How**
數值越高，表示文章在目前引用網路中越居於核心。

PageRank 的絕對值會隨網路大小、引用結構和演算法參數改變，因此應以**同一份清單內的相對大小與排名**為主。

---

# Local In-Degree

**What**
目前清單中，有多少篇其他文獻引用了這篇文章。

**Principle**
在清單內引用網路中，每一條：

$$
A\rightarrow B
$$

代表 A 引用 B。

B 每被一篇清單內的文章引用，Local In-Degree 就增加 1；也就是「清單中引用此文獻的文章數」。

**Why**
它直接顯示這份清單中的文獻共同引用了哪些研究。

**How**
例如：

**Local In-Degree = 7**

表示目前清單中有 **7 篇其他文獻引用了這篇文章**。

`0` 只表示目前清單內沒有其他文獻引用它；它在其他地方仍可能被大量引用。

兩項指標可搭配閱讀：

**In-Degree** 計算「有多少篇引用它」；
**PageRank** 也考慮「引用它的文章有多核心」。

---

# Semantic Similarity

**What**
衡量參考文獻與目前原始論文在研究內容上的相似程度。

**Principle**
本專案使用 Semantic Scholar 的 **SPECTER2 scientific-document embedding**。SPECTER2 將論文標題與摘要轉成高維向量；訓練資料包含文獻間的引用關係。

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

這是本專案計算 SPECTER2 相似度的方式。

**Why**
一篇大量被引用的文獻，可能只用來支持背景概念或方法。Semantic Similarity 用來比較它與原始論文在模型語意空間中的距離。

它可以協助回答：

> 「如果我想沿著目前這篇 paper 的研究問題繼續往下讀，哪些 references 最接近？」

**How**
數值越高，表示兩篇文章在模型的語意空間中越接近。

若介面顯示 `0–1`，越接近 1 表示越相似；若顯示 `0–100`，只是把同一數值線性放大，方便閱讀。

Semantic Similarity 只比較內容，無法判斷研究品質、證據強度，也不能判斷兩篇文章的結論是否一致。它不是機率：`0.82` 不代表「82% 相同」。

---

# Influential Citation

**What**
Semantic Scholar 對原始論文引用這篇參考文獻的關係所做的判定。

欄位使用 `是`、`否`、`無資料` 三種狀態。

**Principle**
Semantic Scholar 使用機器學習模型分析引用出現的次數、位置和章節等資訊，判斷被引文獻對引用它的論文有多重要。

這個欄位只描述以下方向的引用關係：

$$
Seed\ paper \rightarrow Reference
$$

**Why**
這項判定可協助辨識原始論文實際採用、延伸或高度依賴的參考文獻。

Paper-level `influentialCitationCount` 是這篇參考文獻在整體文獻網路中收到的具影響力引用次數，與目前這條引用關係不同。系統不會用該數值代替此處的判定。

**How**
`是` 表示 Semantic Scholar 判定目前的引用關係具有高度影響力。

`否` 表示已取得明確的否定結果。

`無資料` 表示引用關係或引用脈絡的資料不足。系統會排除這個維度，按其餘可用維度重新計算 Reading Priority。

---

# FWCI — Field-Weighted Citation Impact

**What**
經研究領域、出版年份和文獻類型校正後的引用影響力。

本專案的 FWCI 來源為 **OpenAlex**。

**Principle**
OpenAlex 使用的公式：

$$
FWCI=
\frac{\text{Citations Received}}
{\text{Citations Expected}}
$$

實際引用數計算文章出版當年及其後三年的引用；預期引用數則取相同出版年份、文獻類型和 OpenAlex Subfield 文章的平均值。

因此 FWCI 以同類文章為比較基準：

$$
FWCI=1
$$

表示與同類文章的世界平均相當。

**Why**
不同領域的引用習慣不同，較早出版的文章也有更多時間累積引用。

FWCI 有助於降低這些差異對比較的影響，例如可留意：

* 年份較新但成長很快的文章
* 引用次數通常較低的領域中的重要研究
* 在同年代、同類型文獻中特別突出的文章

**How**

**FWCI = 1.0**
約等於同類文章平均。

**FWCI = 2.0**
約為同類文章預期引用數的兩倍。

**FWCI = 0.5**
約為同類文章預期引用數的一半。

FWCI 可與 Citation Count 搭配閱讀：

**Citation Count** 呈現累積引用規模；
**FWCI** 呈現與同類研究相比的表現。

OpenAlex 和 Scopus/SciVal 等資料庫算出的 FWCI 可能不同，因為收錄範圍、領域分類和出版日期的定義各異。OpenAlex 官方也說明了這些差異。

---

# Citation Count

**What**
一篇文章目前累積的被引用次數。

本專案主要使用 OpenAlex 的 `cited_by_count`。

**Principle**
OpenAlex 根據各篇文章的參考文獻清單建立引用網路。它會先用 DOI 等識別碼比對；沒有 DOI 時，再根據書目資料辨識。當 A 的參考文獻成功對應到 B，B 的 Citation Count 就增加一次引用。

**Why**
Citation Count 直接顯示文章被引用的總量。

引用次數高的文章，可能長期受到研究社群使用、討論或引用。這項指標可協助找出：

* 經典研究
* 基礎研究
* 廣泛使用的方法
* 高度受到學界關注的工作

**How**
數值越高，表示累積引用次數越多。

解讀時應同時考慮：

出版越久，通常越有時間累積引用；各領域的引用密度差距也可能很大。綜述文章等文獻類型，引用模式亦有所不同。

因此，介面同時顯示 FWCI，讓你比較引用總量與校正後的相對影響力。

不同資料庫的 Citation Count 可能不一樣，因為收錄範圍和參考文獻的比對方式不同。

---

# SJR Quartile

**What**
SCImago Journal Rank 依學科分類排出的 **Q1–Q4 期刊分區**。

**Principle**
SCImago 每年會在各學科分類中依 SJR 排序期刊，再分成四個區段：

**Q1**：最高的 25%
**Q2**：25–50%
**Q3**：50–75%
**Q4**：最低的 25%

這是 SCImago 對期刊分區的定義。

同一期刊可能被歸入多個學科分類，在不同分類也可能有不同分區。介面若顯示 **Best Quartile**，指的是該期刊在所有所屬分類中最高的分區。SCImago 會另行記錄這個分區對應的分類。

**Why**
SJR Quartile 可讓你快速查看期刊在所屬學科中的相對位置。

參考文獻很多時，可先用 Q1/Q2 留意期刊在各自學科中的分區，再查看文章本身的指標。

**How**

$$
Q1 > Q2 > Q3 > Q4
$$

Q1 表示該期刊在相應學科分類中的 SJR 位居前 25%。

如果顯示 Best Quartile，Q1 只表示該期刊至少在一個所屬分類中位於 Q1；閱讀跨學科期刊的資料時尤其要留意。

Quartile 衡量的是**期刊**，不是單篇文章。若要評估文章本身，可再參考 FWCI、Citation Count、Influential Citation Count 等指標。

---

# SJR Score — SCImago Journal Rank

**What**
衡量學術期刊在引用網路中所獲權重的數值指標。

Quartile 把期刊分成四區；SJR Score 則保留連續數值，能看出同一分區內的差異。

**Principle**
SJR 根據期刊間的引用網路計算，原理類似 PageRank：來自權重較高期刊的引用，對分數的貢獻也較大。SCImago 反覆計算期刊之間的權重傳遞，直到結果收斂，再按期刊發表量換算為平均每篇文章的權重。

現行 SJR 方法採用三年出版窗口；SJR2 另使用共同引用輪廓的 cosine similarity，讓主題較接近的引用關係傳遞更多權重。

可以簡單理解為：

> **這本期刊平均每篇文章，在整體學術引用網路中獲得多少權重。**

**Why**
Quartile 只有四個區段。兩本期刊都屬 Q1，SJR Score 仍可能相差很大。

SJR Score 因此可以：

* 比較同一分區內的期刊
* 顯示比 Quartile 更細的期刊權重差異
* 補充 Citation Count 沒有呈現的引用來源權重

**How**
數值越高，表示期刊在 SCImago 引用網路中取得的平均權重越高。

比較 SJR Score 時，應使用同年度資料，並留意期刊所屬學科。這是期刊層級的指標，主要提供發表來源的背景資訊。

---

# Median Author h-index 與 Maximum Author h-index

**What**
這篇文章所有已取得作者 h-index 的中位數與最大值。

**Principle**
作者的 h-index 是符合以下條件的最大 \(h\)：至少有 \(h\) 篇文章，各被引用至少 \(h\) 次。

例如：

$$
h=20
$$

表示該作者至少有 **20 篇文章，每篇被引用至少 20 次**。

OpenAlex 在 Author `summary_stats` 中提供 h-index。系統會排除缺少的數值，並另行顯示 Author Metadata Coverage。

**Why**
h-index 同時反映發表量與引用次數，可作為作者長期研究影響力的背景資訊。

Median Author h-index 概括作者團隊的學術資歷，Maximum Author h-index 則保留團隊中最高的數值。Author Impact 不計入作者順位。

**How**
系統先按目前的參考文獻清單，分別標準化各篇文章作者 h-index 的中位數和最大值，再計算：

$$
Author\ Impact =
0.6097 \times MedianH_{norm}
+ 0.3903 \times MaxH_{norm}
$$

`0.6097 / 0.3903` 是把 Jinadu et al. (2026) 發表的 `0.2918 / 0.1868`，只在這兩項作者指標間重新正規化後得到的專案權重。

h-index 會受到研究年資、領域引用習慣和資料庫收錄範圍影響。Author Impact 在總分中占 6%，作為低權重的作者背景指標。

---

# Source h-index

**What**
發表來源（通常是期刊）的 h-index。

**Principle**
算法與作者 h-index 相同，但統計的是這個來源發表的所有作品。

例如：

$$
Source\ h=100
$$

表示該來源至少有 **100 篇文章，每篇被引用至少 100 次**。

OpenAlex 在 Source `summary_stats` 中提供 h-index。

**Why**
Source h-index 反映期刊長期累積的被引用情況。

SJR 著重特定時間窗口內的加權引用網路；Source h-index 則看發表來源長期累積了多少高被引作品。兩者可互相補充。

**How**
數值越高，表示該來源有更多被大量引用的文章。

Source h-index 會受到期刊創刊時間、發表量、領域引用密度和 OpenAlex 收錄範圍影響，因此宜作為期刊的背景資訊。

---
