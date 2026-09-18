# NextRead Demo 預覽

> 本預覽以 `Jolly_2021.pdf` 的實際分析結果示範 NextRead，截圖展示使用者在介面中會看到的書目資料與分析指標，不包含原始 PDF 內文。

## 1. 由基礎解析逐步加入更多分析

介面上的三個模式是同一條分析流程的三個層級，後一個層級保留前一個層級的功能，再增加新資料來源與計分面向。

| 分析層級 | 累積開啟的功能 | 何時使用 |
| --- | --- | --- |
| 僅解析 | 使用 GROBID 讀取 PDF，擷取原始論文與參考文獻清單 | 只需要可搜尋、可匯出的書目資料 |
| 標準分析 | 在解析結果上加入 Crossref 辨識、OpenAlex 引用指標、SJR 期刊品質與清單內引用網路 | 需要閱讀優先度與主要學術指標時，這是預設選項 |
| 完整分析 | 在標準分析上再加入 Semantic Scholar 語意相似度與具影響力引用關係 | 需要六個計分面向，並可接受較多 API 查詢時間時 |

![Jolly 2021 與漸進式分析層級](docs/demo/01-progressive-analysis.png)

## 2. 使用進階設定調整資料來源

模式會預先選好對應的服務，使用者仍可在進階設定中獨立開關 Crossref、OpenAlex 與 Semantic Scholar。「強制重新取得 API 資料」會略過本機快取，適合排錯或確實需要重新查詢時使用。

![外部服務與快取設定](docs/demo/02-advanced-services.png)

SJR 資料不是透過 API 即時下載，使用者可從 SCImago 取得新年度 CSV，上傳後由 NextRead 驗證格式並更新本機資料。

![SJR 年度資料更新](docs/demo/03-sjr-update.png)

## 3. 從摘要確認辨識與指標覆蓋率

以 *Gossip drives vicarious learning and facilitates social connection* 為例，NextRead 從 PDF 擷取 62 篇參考文獻，其中 54 篇成功辨識，SJR 覆蓋 48 篇，OpenAlex 覆蓋 54 篇，Semantic Scholar 覆蓋 49 篇，六個計分面向均有可用資料。缺少的指標不會被當成 0 分，覆蓋率則幫助使用者判斷排序的證據完整度。

![Jolly 2021 分析摘要](docs/demo/04-analysis-summary.png)

## 4. 分開查看每個計分面向

「語意關聯」顯示參考文獻與原始論文的 Semantic Similarity，「研究影響」則並列 Influential Citation 與 FWCI。除了 SJR Score 直接使用原始尺度，其餘長條圖的 0–100 代表該篇文獻在當前清單中的相對位置，將滑鼠移到長條上可查看原始數值與書目資料。

![Semantic Similarity 分布](docs/demo/05-semantic-distribution.png)

![Influential Citation 與 FWCI 分布](docs/demo/06-impact-distribution.png)

## 5. 依閱讀優先度瀏覽參考文獻

排序表將證據可用的指標整合成 Reading Priority，並將優先度較高的文獻排在前面。全螢幕模式可同時查看更多欄位與排名，其餘文獻可在同一張表中捲動查看，或以 CSV、JSON 取得完整清單。

![閱讀優先度全螢幕排序表](docs/demo/07-reading-priority.png)

## 6. 展開單篇文獻的計分依據

從 Jolly 2021 的參考文獻中，以 *Gossip and Ostracism Promote Cooperation in Groups* 為例。這篇文獻的 SJR Quartile 為 Q1，Reading Priority 為 87.5，證據涵蓋率為 100%，介面並提供 DOI、OpenAlex 與 Semantic Scholar 連結供進一步核對。

![Gossip and Ostracism 文獻總覽](docs/demo/08-paper-overview.png)

展開原始指標後，可一次核對所有計分依據：Local PageRank 0.01375、Local In-Degree 3、Semantic Similarity 0.9255、Influential Citation 是、FWCI 76.3、Citation Count 485、SJR Quartile Q1、SJR Score 2.5、Median Author h-index 31、Maximum Author h-index 58 與 Source h-index 417。

![單篇文獻的完整原始指標](docs/demo/09-paper-scoring-evidence.png)

## 7. 匯出完整結果

CSV 適合在試算表中篩選、排序與繪圖，JSON 則保留結構化欄位，適合交給其他程式或 agent 處理。

![匯出完整 CSV 或 JSON](docs/demo/10-export.png)
