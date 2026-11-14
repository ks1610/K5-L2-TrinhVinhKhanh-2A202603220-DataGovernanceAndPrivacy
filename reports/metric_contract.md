# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.



| Mục | Khai báo của nhóm |
|---|---|
| Track | T08 |
| Primary metric | Deletion Completeness |
| Tăng tốt hay giảm tốt? | Higher |
| Đơn vị đánh giá | Request–artefact pair (`request_id`, `artefact_id`) |
| Công thức | Số cặp có `expected_action = delete` và `predicted action = delete` / Tổng số cặp có `expected_action = delete` |
| Cách ghép prediction ↔ GT | Exact match theo `request_id` và `artefact_id` |
| Candidate pool | Toàn bộ 10 delete requests trong `fixtures/t08_deletion/` và các artefact trong `data_graph.json` |
| Review budget B | 20 |
| Seed | 42 |
| Threshold policy | Không sử dụng threshold xác suất. Quyết định dựa trên policy rules: legal hold > permission > multi-subject > delete |
| False-delete guardrail | False-delete count = 0 |
| Eval split | Toàn bộ các cặp trong GT `gt_actions.csv` theo evaluator T08; không tự lọc hoặc thay đổi tập đánh giá |
| Miss | Artefact có expected action là delete nhưng không được dự đoán delete |
| False alarm | Artefact thuộc exception bị dự đoán delete hoặc artefact bị delete ngoài phạm vi request |
| False reject | Request hợp lệ không được xử lý đầy đủ; báo cáo bổ sung nếu có dữ liệu kiểm chứng |
| Slices chính thức | Theo `expected_action`: delete, retain_legal_hold, escalate |
| Slices bổ sung | Theo quy mô phạm vi xử lý của request, nếu có dữ liệu và phương pháp phân nhóm được xác định trước |
| Độ bất định | Evaluator chuẩn T08 không tính bootstrap CI. Báo cáo numerator, denominator và số lượng mẫu; chỉ bổ sung CI khi có dữ liệu đánh giá được phép sử dụng |
| Ngày giờ chốt | 2026-11-14 22:29 (UTC+7) |
| Người chốt | Trịnh Vinh Khánh |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.