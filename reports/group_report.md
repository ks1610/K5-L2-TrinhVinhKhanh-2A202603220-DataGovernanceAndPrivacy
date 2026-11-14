# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | Cá nhân |
| Challenge | T08 · Retention & Delete Request Simulator |
| Thành viên + vai trò | **Cá nhân (Solo):** Trịnh Vinh Khánh — Toàn bộ vai trò (Lead/Integrator, Data & Internal GT, Core Algorithm, QA/Metric, Human Review & Report) |
| Git URL | https://github.com/ks1610/K5-L2-TrinhVinhKhanh-2A202603220-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | Chưa gắn (làm cá nhân, nộp trọn gói tại mốc `final-24h`) |
| Tag `final-24h` (commit) | `final-24h` (gắn sau khi commit report & unit tests từ base commit `e52ad44`) |
| Deadline (giờ VN) | 2026-11-15 |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?**
  - **Chủ thể dữ liệu (Data Subjects):** Bị xâm phạm quyền được xóa dữ liệu cá nhân nếu hệ thống chỉ xóa file gốc (`raw_video`) mà bỏ sót các bản phái sinh (`frame`, `face_crop`, `embedding`) hoặc bản sao lưu (`backup`, `export`).
  - **Tổ chức vận hành & Pháp chế (Data Controller / Legal / DPO):** Chịu rủi ro vi phạm quy định bảo vệ dữ liệu cá nhân (Luật 91/2025, Nghị định 356/2025, GDPR Điều 17) nếu xóa thiếu dữ liệu hợp lệ, hoặc vi phạm nghĩa vụ lưu giữ chứng cứ pháp lý / xâm phạm dữ liệu người khác nếu xóa nhầm artefact đang chịu `legal_hold` hoặc chứa nhiều chủ thể (`MULTI_SUBJECT`).
- **Điểm nghẽn cụ thể:** Các artefact trong kho dữ liệu có quan hệ kế thừa theo đồ thị (`parent_ids`) đồng thời chịu ràng buộc đan xen bởi cờ tạm giữ pháp lý (`legal_hold`), quyền truy cập (`acl`), tính xác thực nguồn gốc (`origin_known`) và dữ liệu chung nhiều chủ thể (`subject_ids`).
- **Đầu vào → đầu ra:**
  - *Đầu vào:* `fixtures/t08_deletion/data_graph.json` (212 artefact mock), `fixtures/t08_deletion/requests.json` (10 delete requests), `configs/lab.yaml`, `configs/tracks/t08.yaml`.
  - *Đầu ra:* `out/actions.csv` (`request_id, artefact_id, action, reason, artefact_type, score`), `out/review_queue.csv` (top-$B$ với `budget: 30`), `out/audit_log.jsonl` (append-only audit trace), và quyết định `GO / HOLD / REWORK`.
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - **GO:** Guardrail `False-delete count == 0`, `Deletion Completeness` đạt mục tiêu, toàn bộ các mục ngoại lệ trong hàng đợi top-$B$ được reviewer phê duyệt hợp lệ (đủ `reviewer`, `reviewer_decision`, `reviewed_at`) và ghi vào `audit_log.jsonl`.
  - **HOLD:** Còn artefact thuộc `LEGAL_HOLD`, `MULTI_SUBJECT`, thiếu quyền hoặc không rõ nguồn gốc chưa qua bước duyệt thủ công của reviewer/DPO.
  - **REWORK:** Phát hiện `False-delete count > 0` (như kết quả kiểm thử nội bộ ở Bảng 1 ghi nhận 5 ca lệch phạm vi/ngoại lệ cần tinh chỉnh luật lọc), thiếu cột output theo contract, hoặc kết quả không tái lập giữa 2 lần chạy cùng seed.
- **Giả định của tác giả (cần DPO/legal/domain owner xác nhận):**
  - Toàn bộ dữ liệu `fixtures/t08_deletion/` là dữ liệu tổng hợp (`CC0-1.0`), chỉ thực hiện mô phỏng (`dry_run: true`), không xóa dữ liệu thật.
  - Thứ tự ưu tiên chính sách (`legal_hold > permission/origin_known > multi-subject > delete`) cần được DPO và bộ phận pháp chế rà soát xác nhận trước khi áp dụng cho dữ liệu thực tế.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev / input (`fixtures/t08_deletion`) | 212 artefacts, 10 delete requests | `synthetic:tools/make_fixtures.py (seed 42)` (có sẵn trong repo) | `CC0-1.0 (synthetic, generated for AI20K Day06)` | Có (100% synthetic, không PII thật) |
| eval / heldout | Ẩn (do giảng viên quản lý) | Repo private của giảng viên (`fixtures/t08_deletion/gt/gt_actions.csv`) | Theo quy định học phần AI20K | Có |
| internal_gt (tự kiểm nội bộ) | 164 cặp `(request_id, artefact_id)` (135 `delete`, 27 `escalate`, 2 `retain_legal_hold`) | Tự xây dựng từ `data_graph.json` & `requests.json` (`out/internal_gt/gt_actions.csv`) | Nội bộ phục vụ kiểm thử | Có |

- **Schema & class mapping:**
  - `data_graph.json`: `id`/`artefact_id`, `type`, `subject_ids`, `parent_ids`, `uri`, `owner`, `acl`, `legal_hold`, `origin_known`.
  - `requests.json`: `request_id` (`DR-001`..`DR-010`), `subject_id`, `received_at`, `deadline`.
  - `actions.csv`: ánh xạ `(request_id, artefact_id)` sang `action` $\in \{\text{delete}, \text{retain\_legal\_hold}, \text{escalate}\}$ kèm `reason`, `artefact_type`, `score`.
- **Seed & Cách chia split:** Cố định `seed: 42`. Trong `fixtures/t08_deletion/manifest.csv`, trường `split` có giá trị `na` (dùng chung cho toàn bộ simulator; tập `gt/` đánh giá chính thức nằm ở overlay giảng viên).
- **`manifest.csv` verified (sha256):** Đã xác minh qua `strict_provenance: true` và `make verify`:
  - `data_graph.json`: `53c2bd968209e7c73a89a593a7c932edcef2cd03ea218f34a7ad873c7e9c9f2e`
  - `requests.json`: `aa7c66c418d1b87b1f1cc05a49d8fdc71c1be56c3be7455f959c2bbfed12e557`
- **Dữ liệu thật dùng:** Không sử dụng dữ liệu thật (`data/real/` không dùng cho Track T08).

## 03 · Research & design

- **References & vì sao chọn kỹ thuật:**
  1. **Nghị định 356/2025 & Luật 91/2025 (Việt Nam) / GDPR Article 17(3):** Cơ sở thiết kế cây quyết định theo thứ tự ưu tiên **Policy Precedence**: `legal_hold > permission/origin_known > multi-subject > delete`, đảm bảo nghĩa vụ lưu giữ pháp lý luôn thắng quyền yêu cầu xóa thông thường.
  2. **Graph Traversal (BFS Lineage Closure):** Duyệt theo chiều rộng qua `parent_ids` để truy vết toàn bộ dữ liệu phái sinh (`raw_video` $\rightarrow$ `frame` $\rightarrow$ `face_crop` $\rightarrow$ `embedding`, `backup`, `export`), khắc phục tình trạng xóa sót dữ liệu của Baseline.
  3. **California DROP & Data Cards Playbook:** Áp dụng cơ chế lưu vết kiểm toán bất biến (`audit_log.jsonl`) và hàng đợi Human-in-the-loop (`review_queue.csv`) cho các ca ngoại lệ rủi ro cao.
- **Sơ đồ data flow:**
  `Input (data_graph.json, requests.json, sha256 verify)` $\rightarrow$ `Process (BFS Lineage + Policy Precedence)` $\rightarrow$ `Rank/QC (score=1.0 cho ngoại lệ, trích top B=30 vào review_queue.csv)` $\rightarrow$ `Review (Human duyệt review_queue_reviewed.csv, kiểm tra reviewer + reviewed_at, ghi audit_log.jsonl)` $\rightarrow$ `Decision (actions.csv + GO/HOLD/REWORK)` $\rightarrow$ `Report (metrics_*.json, table1_baseline_vs_poc.md)`.
- **Thành phần offline:** Chạy 100% offline (`offline: true` trong `configs/lab.yaml`), thuần Python 3.12 + Pandas trên CPU, không tải model/weights bên ngoài.
- **Trade-offs đã cân nhắc:**
  - *Completeness vs. False-delete:* Tăng bao đóng duyệt đồ thị giúp tăng mạnh `Deletion Completeness` (từ `0.0593` lên `0.9556`), nhưng nếu điều kiện dừng BFS hoặc kiểm tra giao thoa `subject_ids` / `acl` chưa đủ chặt ở một số nút nhánh, có thể phát sinh `False-delete` trên các nút biên (`5.0` ca trên tập kiểm tra nội bộ — đã phân tích tại Mục 06).

## 04 · Baseline vs PoC

- **Baseline (`src/baseline_t08.py`, git `e52ad44`, `seed 42`):** Chỉ xử lý các artefact gốc khớp trực tiếp với yêu cầu xóa (tổng `n_items = 10` bản ghi hành động), không duyệt đồ thị lineage để tìm bản phái sinh/backup.
- **PoC (`src/pipeline.py`, git `e52ad44`, `seed 42`):** Truy vết đầy đủ chuỗi kế thừa bằng BFS (`n_items = 152` bản ghi hành động), xếp hạng ưu tiên rủi ro vào `review_queue.csv` (`budget: 30`), áp dụng override từ `review_queue_reviewed.csv` và ghi đầy đủ `audit_log.jsonl`.
- **Xác nhận công bằng thực nghiệm:** Cùng input `fixtures/t08_deletion`, cùng `configs/lab.yaml` (`budget: 30`, `dry_run: true`), cùng `--offline` và cùng `--seed 42`, đánh giá trên cùng tập kiểm tra nội bộ `out/internal_gt/gt_actions.csv` (`N = 164`).

**Bảng 1 · Baseline vs PoC & hard slices** — Output trực tiếp từ `python3 -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md`:

Baseline: `baseline` (git e52ad44, seed 42) · PoC: `poc` (git e52ad44, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Deletion Completeness** (must-delete artefacts deleted / must-delete artefacts) | all | 0.0593 | 0.9556 | 0.8963 | +1512.5% | higher | 164 |
| False-delete count (count (target 0): exceptions deleted + deletes outside request scope) | all | 0.0000 | 5.0000 | 5.0000 | baseline=0 | lower | None |
| Exception handling accuracy (legal-hold/escalate rows handled as expected / such rows) | all | 0.0690 | 0.6207 | 0.5517 | +800.0% | higher | None |
| Audit trace completeness (actions with an audit entry / actions) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | None |
| Runtime / 100 items (s) | all | 0.1650 | 0.0236 | | | lower | |

## 05 · Evaluation protocol

- **Công thức primary metric & các metric phụ (`src/metrics/tracks.py::eval_t08`):**
  - **Primary — Deletion Completeness (`higher`):** `numerator / denominator` = số artefact `expected_action == "delete"` được dự đoán `"delete"` trên tổng số artefact phải xóa (`8/135 = 0.0593` ở Baseline; `129/135 = 0.9556` ở PoC).
  - **Guardrail — False-delete count (`lower`, target = 0):** Số dòng ngoại lệ (`expected_action != "delete"`) bị gán `"delete"` cộng với số lệnh `"delete"` nằm ngoài phạm vi cặp `(request_id, artefact_id)` của ground truth (`0` ở Baseline do chỉ xóa 8 file gốc; `5` ở PoC trên tập kiểm tra nội bộ).
  - **Secondary — Exception handling accuracy (`higher`):** Số dòng ngoại lệ (`retain_legal_hold`, `escalate`) được xử lý đúng trên tổng số dòng ngoại lệ (`2/29 = 0.0690` ở Baseline; `18/29 = 0.6207` ở PoC).
  - **Secondary — Audit trace completeness (`higher`):** Tỷ lệ hành động có bản ghi tương ứng trong `audit_log.jsonl` (`10/10 = 1.0000` ở Baseline; `152/152 = 1.0000` ở PoC).
- **Threshold / budget B & lúc chốt:** `budget: 30` và `dry_run: true` được chốt cố định trong `configs/lab.yaml` và `configs/tracks/t08.yaml` trước khi chạy đánh giá.
- **Độ bất định khi N nhỏ:** Đánh giá trên `N = 164` cặp `(request_id, artefact_id)` từ 10 requests và 212 artefacts. Hệ thống hoạt động hoàn toàn xác định (deterministic) với `--seed 42`, phương sai giữa các lần chạy bằng `0` (đã xác minh qua `diff out/poc/actions.csv out/poc2/actions.csv`).
- **Lệnh evaluate chính xác:**
  ```bash
  python3 -m src.evaluate --track t08 --gt out/internal_gt/gt_actions.csv --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json
  ```

## 06 · Result slices

| Slice (`expected_action`) | N | Baseline (accuracy) | PoC (accuracy) | Ghi chú |
|---|---|---|---|---|
| `delete` | 135 | `0.0593` (8/135) | `0.9556` (129/135) | PoC tăng +1512.5% nhờ duyệt BFS toàn bộ cây phái sinh |
| `escalate` | 27 | `0.0000` (0/27) | `0.5926` (16/27) | PoC nhận diện và đẩy các ca `MULTI_SUBJECT` lên hàng đợi duyệt |
| `retain_legal_hold` | 2 | `1.0000` (2/2) | `1.0000` (2/2) | Cả 2 đều bảo toàn 100% các bản ghi chịu `LEGAL_HOLD` |

- **Failure case 1 (Bỏ sót toàn bộ dữ liệu phái sinh & backup ở Baseline):**
  - *Metadata minh họa:* Trong yêu cầu `DR-001`, dữ liệu gốc `raw_video` (`a0015`) liên kết qua `parent_ids` tới các bản sao `backup` (`a0016`), `frame` (`a0017`), `face_crop` (`a0018`).
  - *Root cause:* Baseline chỉ đối chiếu trực tiếp file gốc nên chỉ xóa được 8/135 artefact phải xóa trên toàn bộ 10 requests (`Deletion Completeness = 0.0593`), để lọt toàn bộ bản sao lưu và vector đặc trưng định danh. PoC giải quyết bằng duyệt đồ thị BFS từ các nút gốc của chủ thể.
- **Failure case 2 (Phát sinh 5 ca False-delete & bỏ sót 11/27 ca `escalate` khi lan truyền qua nút trung gian):**
  - *Metadata minh họa:* Trên slice `escalate` (`N = 27`), PoC đạt độ chính xác `0.5926` (`16/27` ca đúng, `5` ca bị gán nhầm sang `delete` làm `False-delete count = 5.0`, và `6` ca ngoại lệ khác bị gán nhãn ngoài `delete` hoặc thiếu phạm vi). Điển hình như các nút có `acl` hạn chế hoặc `origin_known = false` trong nhánh con của `DR-003` / `DR-004` (`a0067`, `a0070`, `a0075`, `a0079`, `a0083`).
  - *Root cause:* Trong khi `retain_legal_hold` được chặn tuyệt đối (`2/2 = 1.0000`), một số nút con kế thừa trong quá trình lan truyền BFS chưa kiểm tra lại đầy đủ điều kiện `origin_known` / `acl` của từng nút con độc lập với nút cha, dẫn đến việc gán `delete` thay vì `escalate`. Đây là điểm cần ưu tiên siết chặt ở vòng cải tiến tiếp theo (theo tiêu chí `REWORK` nếu `False-delete > 0`).
- **Latency / compute:**
  - Baseline: `0.0165s` cho `10` items (`0.1650s / 100 items`).
  - PoC: `0.0358s` cho `152` items (`0.0236s / 100 items`, tương đương `~0.236 ms/item` trên CPU x86_64).

## 07 · Human & decision

- **Review queue (`out/poc/review_queue.csv`):**
  - Trích xuất tối đa `budget: 30` bản ghi có điểm rủi ro cao nhất (`score = 1.0`) để con người rà soát trước khi thực thi xóa, đứng đầu là các ca `MULTI_SUBJECT` (ví dụ rank 1: `DR-001:a0212`) và `LEGAL_HOLD` (ví dụ rank 2: `DR-002:a0043`).
- **Cách override + audit log (`out/poc/audit_log.jsonl`):**
  - Reviewer điền các trường bắt buộc trong `review_queue_reviewed.csv` gồm `reviewer`, `reviewer_decision`, `override_value`, `review_note`, và `reviewed_at`.
  - Pipeline kiểm tra chặt đầu vào tại hàm `review()` trong `src/pipeline.py` (thiếu `reviewer`, thiếu `reviewed_at` hoặc `override_value` không hợp lệ sẽ dừng ngay với exit code `2`), sau đó cập nhật `actions.csv` và ghi nối tiếp toàn bộ 152 sự kiện vào `out/poc/audit_log.jsonl` (`Audit trace completeness = 1.0000`).
- **Decision policy + `reason_code` + owner:**
  - Mỗi dòng trong `actions.csv` đều gắn `reason` rõ ràng (`SUBJECT_DATA`, `MULTI_SUBJECT`, `LEGAL_HOLD`, ...) và gắn trách nhiệm cho `owner: "Trịnh Vinh Khánh"` (`configs/lab.yaml`).
- **Khi nào HOLD/REWORK thay vì tự động release:**
  - Chuyển **HOLD** khi còn ca `LEGAL_HOLD` hoặc `MULTI_SUBJECT` chưa được reviewer phê duyệt.
  - Chuyển **REWORK** khi `False-delete count > 0` (như 5 ca phát hiện ở trên), thiếu trường audit bắt buộc, hoặc vi phạm Idempotency.

## 08 · Reproduce & tests

```bash
# 1. Cài đặt môi trường
make setup          # hoặc: python3 -m venv .venv && pip install -r requirements.txt

# 2. Chạy Baseline & PoC (offline, seed 42)
python3 -m src.main --track t08 --input fixtures/t08_deletion --config configs/lab.yaml --output out/baseline --run-name baseline --pipeline src.baseline_t08 --offline --seed 42
python3 -m src.main --track t08 --input fixtures/t08_deletion --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42

# 3. Kiểm tra Idempotency
mkdir -p out/poc2 && cp out/poc/review_queue_reviewed.csv out/poc2/
python3 -m src.main --track t08 --config configs/lab.yaml --output out/poc2 --offline --seed 42
diff out/poc/actions.csv out/poc2/actions.csv   # Kết quả: rỗng (0 dòng khác biệt)

# 4. Đánh giá & so sánh
python3 -m src.evaluate --track t08 --gt out/internal_gt/gt_actions.csv --pred out/baseline/actions.csv --run-name baseline --out reports/metrics_baseline.json
python3 -m src.evaluate --track t08 --gt out/internal_gt/gt_actions.csv --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json
python3 -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md

# 5. Chạy unit tests
pytest -q
```

- **Output của `pytest -q`:**
  `...s....s...s............................ssssssssssssss............ssssssssssssssssssssss [100%]` (0 failed; gồm 3 unit tests trong `tests/test_t08_pipeline.py` kiểm tra end-to-end guardrail `LEGAL_HOLD`, luồng HITL + `audit_log.jsonl`, và failure mode thiếu `reviewer` / `override_value` sai).
- **Máy / CPU / OS / Python:** `Linux-7.0.0-38-generic-x86_64-with-glibc2.39` · CPU `x86_64` · Python `3.12.3` · **git sha:** `e52ad44`

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:**
  - Dữ liệu `fixtures/t08_deletion/` là synthetic (`CC0-1.0`), không có PII thật và chỉ chạy ở chế độ mô phỏng (`dry_run: true`). Trong môi trường thật, cần cơ chế xóa vật lý triệt để trên cả kho lưu trữ chính lẫn bản sao lưu lạnh.
- **Điều chưa biết; false alarms; nếu scale 10× thì sao:**
  - *Điều chưa biết & False alarms:* Hiện còn 5 ca `False-delete` trên tập kiểm tra nội bộ ở các nút nhánh có thuộc tính quyền/nguồn gốc đặc biệt (`escalate` slice), đồng thời các ca `MULTI_SUBJECT` đang được chuyển duyệt thủ công thay vì tự động tách/làm mờ chủ thể.
  - *Khi scale 10× (2.120+ artefacts, 100+ requests):* Tốc độ xử lý hiện tại (`0.0236s / 100 items`) vẫn đáp ứng tốt dưới 1 giây cho quy mô gấp 10 lần, nhưng cần lưu trữ đồ thị trên cơ sở dữ liệu có chỉ mục và phân bổ ngân sách duyệt (`budget`) theo mức độ khẩn cấp của `deadline`.
- **Tuyên bố tuân thủ pháp lý:**
  - Báo cáo này **không** tuyên bố hệ thống tự động đạt chuẩn tuân thủ GDPR hay Luật Bảo vệ dữ liệu cá nhân Việt Nam (Luật 91/2025, Nghị định 356/2025) từ các kiểm tra tự động; mọi quyết định ngoại lệ và chính sách xóa cần được DPO và bộ phận pháp chế xác nhận.
- **Kế hoạch cải tiến:**
  - Khắc phục triệt để 5 ca `False-delete` bằng cách kiểm tra độc lập `origin_known` và `acl` tại từng nút con trong quá trình duyệt BFS để đưa `False-delete count` về đúng `0`.
  - Bổ sung bộ lọc ưu tiên theo `deadline` của từng request để tránh trễ hạn SLA.

## 10 · Contribution (Cá nhân)

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Trịnh Vinh Khánh (Cá nhân) | `ks1610 <trinhvinhkhanh1610@gmail.com>` | Toàn bộ bài lab T08: cấu hình `configs/lab.yaml`, thuật toán `src/pipeline.py` & `src/baseline_t08.py`, bộ test `tests/test_t08_pipeline.py`, đánh giá & báo cáo `reports/*` | `117cd8a`, `eacb9ce`, `e52ad44` (và commit hoàn thiện tests + group report) | không |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://gdpr-info.eu/art-17-gdpr/ | 2026-11-14 | Quy định quyền được xóa dữ liệu cá nhân (Right to Erasure) và các ngoại lệ lưu giữ vì nghĩa vụ pháp lý tại Điều 17(3). |
| https://privacy.ca.gov/drop/ | 2026-11-14 | Nền tảng California DROP chuẩn hóa việc điều phối một yêu cầu xóa tới nhiều hệ thống dữ liệu kèm theo dõi trạng thái. |
| https://pair-code.github.io/datacardsplaybook/ | 2026-11-14 | Khung tài liệu hóa nguồn gốc (provenance), lineage và các ràng buộc vòng đời của tập dữ liệu AI. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Thành viên cá nhân có đầy đủ commit thực chất và được nêu minh bạch trong bảng trên.
