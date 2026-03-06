# AI-Native PM OS (Route A) 核心守則

## 1. 專案願景與架構邏輯 (Route A)
本專案採用 **Route A 優化路徑**，核心原則是「寬進嚴出」：早期廣度收集信號，僅對高價值候選者進行深度挖掘。
- **L1 (Collect)**: 廣泛獲取信號筆記，存於 `95_Signals/`。
- **L2 (Shortlist)**: 每週評分並產出 Top-K 簡報於 `96_Weekly_Review/`。
- **L3 (Deepen)**: 僅對 Top-K 抓取完整證據，更新至原信號筆記。
- **L4 (Gate)**: 記錄不可篡改的決策於 `97_Decisions/`。
- **L5 (Writeback)**: 自動寫回工作層（02_LTI/RTI），需人工審核。

## 2. 當前開發進度 (截至 2026-03-06)
- **整體狀態**: v4.1 Core Validation System 已完成，核心驗證流程 Graph→VP→AVL→Promotion→LTI 已運作，進入 MVP 驗證階段。
- **重要里程碑**:
  - 三路徑決策分支（Approved / Deferred / Reject）已實作。
  - 自動化 L3 深度挖掘流水線已完成驗證。
  - 已建立基於 JSONL 的追加式存儲系統。
  - Task 1.1：L4→L5 橋接已完成，l5_created 正常產出 LTI-DRAFT。
  - Task 1.2：RTI 三次法則已完成，重複 COS pattern 自動觸發 RTI 提案。
  - Task 1.3：writeback 後自動同步索引（kb_manager.sync_indices）。
  - Task 1.4：weekly_cycle.ps1 全流程自動化腳本已完成。
  - Task 1.5：v4.1 Graph Layer + AVL Evidence Pack + Validation Project + Manual Promotion Router (MVP) 已完成。
  - v4.1 MVP Tasks 1–5 已完成，並保持 v3.0 流程相容。
  - v4.1 Promotion Governance (Promotion Report) 已完成。
  - VP Validation Plan + vp_plan.md 已完成。
  - Newsletter → Graph writeback 已完成，Graph hypothesis 可保存 validation seed。
  - 目前完成模組：Graph Hypothesis / Newsletter Governance / VP Validation Plan / AVL Evidence / Promotion Governance / LTI Generation。
  - 未完成模組：Research Program Queue / RTI Knowledge Accumulation。

## v4.1 Human-Augmented Validation Architecture
Validation Pipeline (current):
External Signal
↓
Graph Hypothesis
↓
Validation Project (VP)
↓
AVL Evidence Pack
↓
Promotion Report
↓
LTI Provisional

Layer responsibilities:
- Graph: 保存 hypothesis 與 signal interpretation
- VP: 保存 validation plan（experiment design）
- AVL: 保存 evidence
- Promotion: 保存 promotion governance reasoning
- LTI: provisional knowledge

Design principles:
- Graph 保存 hypothesis
- VP 保存 experiment design
- AVL 保存 evidence
- Promotion 保存 governance reasoning
- LTI 保存 provisional knowledge

## Validation Governance Rules (v4.1)
1. VP.claim 語義統一
   - `vp init --from-graph` 時，VP.claim 必須使用 `hypothesis_statement`
   - fallback：`core_claim`
   - 語義規則：
     - `core_claim` → external source wording
     - `hypothesis_statement` → testable hypothesis
     - `VP.claim` → `hypothesis_statement`
2. Graph existence guard
   - `vp init --from-graph` / `vp link-graph` 必須驗證 Graph node 存在
   - 若 Graph 不存在：CLI error = "Graph node not found"
3. Validation plan lint
   - `metrics` / `success_criteria` 為空 → warning
   - 顯示於 `vp status` / `vp promote`
   - 不阻止 promotion（v4.1 human-augmented decision）
4. Promotion decision governance
   - if success_criteria defined AND metrics evaluated AND evidence outcome positive → `provisional_lti`
   - if evidence outcome negative → `reject`
   - else → `needs_more_validation`
5. Evidence aggregation
   - Promotion report 支援多 evidence pack（AVL-EP-001 / AVL-EP-002 / ...）
   - 聚合規則：any reject → reject；all positive → provisional_lti；otherwise → inconclusive
   - Promotion report 輸出：`aggregated_outcome`, `packs_evaluated`
6. Deterministic content_id
   - Newsletter ingestion fallback：`content_id = sha1(source_url)`

## Promotion Governance Artifact
Promotion Report：
- 位置：`promotion_reports/PR-XXXX/`
- Artifacts：`promotion.json` / `promotion_report.md`
- Promotion report 保存：`validation_summary`, `validation_result`, `confidence_level`, `promotion_decision`
- `promotion.json` 新增治理欄位：`evidence_count`, `validation_plan_metrics_defined`, `validation_plan_success_defined`
- 用途：support promotion traceability / support governance review

## 3. 🚨 關鍵技術債與優先修復 (P0 阻斷點)
目前無 P0 阻斷點，以下為技術債追蹤：
- Metrics gate 尚未啟用（v4.1 先以 human-augmented 為主）。
- CX replay validator 尚未接入。
- Provisional revalidation policy 尚未自動化。

## v4.1 技術債追蹤
1. Promotion decision source of truth
   - 目前：promotion report decision 與 decide_manual_promotion 為兩套邏輯
   - 未來需要：promotion report decision → constrain LTI generation
2. Metrics evaluation source
   - 目前：metrics_evaluated 來自 VP validation_plan
   - 未來應改為：AVL evidence pack metrics
3. Evidence aggregation model
   - 目前 aggregation：any reject / all positive / otherwise inconclusive
   - 未來可能加入：evidence weighting / time decay / confidence scoring
4. content_id canonicalization
   - 目前 fallback：sha1(url)
   - 未來需加入：URL canonicalization（remove query / normalize domain）

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


### v4.1 Validation Architecture Lessons (Graph → VP → AVL → Promotion → LTI)

- [2026-03-06] Graph → VP claim mapping 必須優先使用 hypothesis_statement，而不是 core_claim，以保持 external signal wording 與 testable hypothesis 的語義分離。
- [2026-03-06] vp init --from-graph 與 vp link-graph 必須強制檢查 Graph existence，避免 validation project 在不存在的 hypothesis 上建立。
- [2026-03-06] Promotion decision 不應只依賴 AVL outcome，必須同時考慮 validation_plan（metrics / success criteria）與 evidence aggregation。
- [2026-03-06] Newsletter ingestion 必須提供 deterministic content_id（fallback: sha1(source_url)），避免 URL variant 造成 duplicate Graph hypothesis。
- [2026-03-06] Promotion report 必須作為 promotion governance artifact（JSON + Markdown），用於 machine validation 與 human governance review。
- [2026-03-06] Evidence aggregation 必須支援 multi-pack validation，promotion decision 應基於 aggregated outcome 而非單一 evidence pack。
- [2026-03-06] External knowledge 不得直接 promotion 為 LTI，必須經過 Graph hypothesis → VP validation → AVL evidence → Promotion governance。
