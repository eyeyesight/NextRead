# Scite 整合評估（2026-10-23）

查核日期：2026-10-23。本次只閱讀官方文件、API 規格與條款，沒有開通訂閱、建立金鑰、上傳 PDF，或修改 Scite 功能。

## 建議

**目前不必把 Scite 納入預設分析，適合之後做成選用的引用脈絡資訊。** NextRead 現在的核心需求是辨識參考文獻並安排閱讀順序；Scite 增加的是「後續研究如何引用這篇文獻」，有助於閱讀時尋找支持或相異證據，但不保證補齊原文清單，也不能直接當作品質或真偽分數。Scite 官方同樣提醒，支持引用不證明研究可靠，相異引用也不證明研究錯誤，仍需閱讀引用脈絡及研究設計。[官方文獻回顧指南](https://scite.ai/blog/how-to-use-ai-for-literature-review)

## 能增加什麼？

| 需求 | Scite 的價值與限制 |
|---|---|
| 看後續研究的反應 | Smart Citations 區分 supporting、contrasting、mentioning，API 另有 unclassified，適合提供閱讀線索。[資料模型](https://api.scite.ai/docs) |
| 看實際引用內容 | 引用圖譜可查誰引用誰、引用類型與位置，但這與單純取得統計是不同的存取範圍。[Smart Citations 指南](https://docs.scite.ai/guides/smart-citations) |
| 檢查撤稿或編輯通知 | Reference Check 可提供這類檢查，值得用在引用前核對；仍需確認權限及個別結果。[官方 API 功能說明](https://scite.ai/api) |
| 補齊 PDF 的參考文獻 | 圖譜與 Reference Check 有相關功能，但索引不是原文一致性證明。官方也說沒有單一索引包含所有資料，不能承諾替代 PDF 核對或 GROBID。[官方文獻回顧指南](https://scite.ai/blog/how-to-use-ai-for-literature-review) |

Tallies 統計的是「引用陳述」數量，`citingPublications` 才是不同引用文獻的篇數，同一篇論文可能有多段引用。API 使用 `contradicting`，介面使用 contrasting，整合時不能混淆欄位與單位。[官方 API 規格的 Overview & Terminology](https://api.scite.ai/openapi.json)

## 不一定要付費，但需要分清楚範圍

Papers 和 Tallies 是公開端點，官方明確表示不用帳號或 API Key；批次 Tallies 文件列出每次最多 500 個 DOI。這使「在既有結果旁補上分類統計」有較輕量的技術路徑，不能一概說 Scite 必須付費。[官方入門](https://docs.scite.ai/introduction)、[批次統計指南](https://docs.scite.ai/guides/smart-citations)

其他 API 需要憑證與對應 scopes。Pro 可建立自助 API Key，文件列價為每月 US$50 或每年 US$480，年繳折算每月 US$40，但這不是所有資料、商業部署或研究使用的無限制授權。官方特別指出 Search 的商業或研究使用需另簽授權，Search snippets 對自助 Key 會遮蔽，且沒有公開的 API 單次計價，正式整合應逐項確認。[驗證說明](https://docs.scite.ai/authentication)、[方案與授權](https://docs.scite.ai/pricing-and-plans)

公開可呼叫也不等於可自由再散布。現行條款第 8 節限制超出個人研究所需的系統性擷取，以及把內容或衍生資料提供第三方；NextRead 的快取、共享網站和 JSON 匯出如何適用，應在正式納入前確認，不能直接把 Scite 資料當成專案 MIT 授權的一部分。[服務條款](https://scite.ai/terms)

## 效能與後續實作方式

**工程判斷：**只呼叫遠端 Tallies 並解析 JSON，不需要另開 Docker 或載入本機分類模型，主要新增成本會是連線、等待與錯誤處理。這次沒有測量耗時、記憶體或本專案論文的涵蓋率，不能宣稱固定速度或完整涵蓋。批次 DOI 查詢可避免逐篇發出請求，限流則依回應標頭與 `Retry-After` 處理，不把公開端點理解成永遠不限量。[Smart Citations 指南](https://docs.scite.ai/guides/smart-citations)、[限流與重試](https://docs.scite.ai/errors-and-rate-limits)

若之後要做，建議先以自願開啟的統計顯示試驗，清楚區分「查無資料」「查詢失敗」「有資料但為零」，並提供原始報告連結。先驗證使用者是否會依這些資訊調整閱讀，再決定是否需要付費引用脈絡或 Reference Check。**不要直接把 supporting 當加分、contrasting 當扣分，也不要讓 Scite 失敗阻止既有分析完成。**這是依 NextRead 用途提出的設計建議，並非 Scite 官方的排名規則。

技術細節仍須實測：目前官方 Smart Citations 指南的批次範例使用含 `dois` 的物件，公開 OpenAPI 的 `/tallies` schema 則是 DOI 陣列，正式串接前應以小量公開 DOI 核對實際回應，而非照抄其中一份文件。[指南](https://docs.scite.ai/guides/smart-citations)、[OpenAPI](https://api.scite.ai/openapi.json)
