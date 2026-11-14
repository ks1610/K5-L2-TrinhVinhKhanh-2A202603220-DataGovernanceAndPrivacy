# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.




| Mục | Khai báo của nhóm |
|---|---|
| Track | T08 |
| Primary metric | Deletion Completeness |
| Tăng tốt hay giảm tốt? | higher |
| ơn vị đánh giá (image / region / pair / release / batch / case …) | case (mỗi delete request = 1 case) |
| Công thức + numerator/denominator | Deletion Completeness = (số bản ghi/trường thuộc phạm vi request đã bị xoá đúng) / (tổng số bản ghi/trường phải xoá theo request); tính per-case rồi lấy trung bình trên toàn bộ request |
| Cách ghép prediction ↔ GT | theo `record_id`/`request_id` khớp chính xác (exact match, không IoU) |
| Candidate pool cố định | toàn bộ delete requests trong `fixtures/t08/` (không lọc/bớt) |
| Review budget B / K | theo `configs/tracks/t08.yaml` (cần đọc giá trị thực tế trong file này) |
| Seed | 42 |
| Threshold policy | không dùng threshold xác suất; quyết định dựa rule cứng: completeness < 1.0 → HOLD/REWORK; bất kỳ false-delete > 0 → fail guardrail, chốt trước khi chạy eval, không đổi sau |
| Eval split | toàn bộ `fixtures/t08/` dùng làm heldout, không dùng để tune pipeline |
| Chỉ số lỗi xấu | miss = bản ghi còn sót chưa xoá; false alarm = false-delete (xoá nhầm bản ghi ngoài phạm vi); false reject = từ chối nhầm request hợp lệ |
| Slices sẽ báo cáo (≥2) | (1) theo loại request (xoá toàn bộ vs xoá một phần); (2) theo quy mô phạm vi xoá (ít bản ghi vs nhiều bản ghi) |
| Cách báo độ bất định khi N nhỏ | bootstrap CI |
| Ngày giờ chốt + người chốt | _[điền ngày giờ thực tế + tên bạn]_ |
