# AI-Native PM OS (Route A) 核心守則

## 1. 專案願景與架構邏輯 (Route A)
本專案採用 **Route A 優化路徑**，核心原則是「寬進嚴出」：早期廣度收集信號，僅對高價值候選者進行深度挖掘。
- **L1 (Collect)**: 廣泛獲取信號筆記，存於 `95_Signals/`。
- **L2 (Shortlist)**: 每週評分並產出 Top-K 簡報於 `96_Weekly_Review/`。
- **L3 (Deepen)**: 僅對 Top-K 抓取完整證據，更新至原信號筆記。
- **L4 (Gate)**: 記錄不可篡改的決策於 `97_Decisions/`。
- **L5 (Writeback)**: 自動寫回工作層（02_LTI/RTI），需人工審核。

## 2. 當前開發進度 (截至 2026-02-24)
- **整體狀態**: 90% 已完成，核心流程 L1→L5 已運作，已進入 MVP 驗證階段。
- **重要里程碑**:
  - 三路徑決策分支（Approved / Deferred / Reject）已實作。
  - 自動化 L3 深度挖掘流水線已完成驗證。
  - 已建立基於 JSONL 的追加式存儲系統。
  - Task 1.1：L4→L5 橋接已完成，l5_created 正常產出 LTI-DRAFT。
  - Task 1.2：RTI 三次法則已完成，重複 COS pattern 自動觸發 RTI 提案。
  - Task 1.3：writeback 後自動同步索引（kb_manager.sync_indices）。
  - Task 1.4：weekly_cycle.ps1 全流程自動化腳本已完成。

## 3. 🚨 關鍵技術債與優先修復 (P0 阻斷點)
目前無 P0 阻斷點，以下將轉為例行追蹤：
- 任務 1.2 與 1.3 已結案，持續監看索引同步會否涉及 LTI/COS/RTI 形式不一定造成的不完整性。

## 4. 存儲規範與資料架構
- **不可篡改性 (Immutable)**: L4 決策記錄絕對不可覆寫，僅能建立新修訂檔。
- **信號生命週期**: `raw` -> `shortlisted` -> `deepened` -> `decided`。
- **資料庫**: 採用 JSONL 追加模式（signals.jsonl, tasks.jsonl, gate_decisions.jsonl, cos_cases.jsonl）。

## 5. 開發指令
- **全流程測試**: 執行 L1→L4 Complete Flow。
- **週報生成**: `orchestrator.cli weekly`。
- **規範檢查**: 每次修改後需確認資料 Contract 驗證通過。

## 6. 專案教訓清單 (Compounding Lessons)
- [2026-02-22] 確保 Gate 決策後信號狀態同步更新，避免 Task 重複建立。
- [2026-02-22] 優先考慮資料完整性，大於新增輸入源。
- [2026-02-24] 已驗證 L4 決策能連動 L3 深度挖掘任務與 L5 草稿生成，電路邏輯完整。