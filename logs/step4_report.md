# 📊 Báo cáo Đánh giá Toàn diện Hệ thống DataMate (Batch Evaluation Report)

- **Mô hình sử dụng (`model_id`)**: `Qwen/Qwen2.5-Coder-7B-Instruct`
- **Tổng số câu hỏi đánh giá**: `30` câu
- **Tổng thời gian thực thi**: `800.04s` (Trung bình `26.67s/câu`)

## 1. Tổng hợp Điểm Penalized Accuracy (PA)

| Chỉ số Đánh giá | Giá trị | Tỷ lệ / Ghi chú |
| :--- | :---: | :--- |
| **Penalized Accuracy (PA)** | **`+0.5000`** | Công thức: $(Correct - Wrong) / N$ |
| **Số câu Đúng (+1 điểm)** | `16` | `53.3%` |
| **Số câu Sai (-1 điểm)** | `1` | `3.3%` |
| **Số câu Từ chối / Abstain (0 điểm)** | `13` | `43.3%` |
| **Accuracy (khi trả lời)** | `94.1%` | $Correct / (Correct + Wrong)$ |
| **Coverage (Độ bao phủ trả lời)** | `56.7%` | $(Correct + Wrong) / N$ |

## 2. Phân rã Kết quả theo Kiểu Đáp án (Answer Type Breakdown)

| Kiểu đáp án (`type`) | Tổng số câu | Đúng (+1) | Sai (-1) | Abstain (0) | Điểm PA | Độ trễ TB (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `boolean` | 1 | 1 | 0 | 0 | **`+1.000`** | 7978.0 |
| `list` | 1 | 1 | 0 | 0 | **`+1.000`** | 98436.0 |
| `number` | 22 | 12 | 0 | 10 | **`+0.545`** | 19431.0 |
| `percent` | 4 | 0 | 1 | 3 | **`-0.250`** | 42072.2 |
| `string` | 1 | 1 | 0 | 0 | **`+1.000`** | 57825.0 |
| `unanswerable` | 1 | 1 | 0 | 0 | **`+1.000`** | 39094.0 |

---

## 4. Báo cáo Phân tích Chi tiết Từng Câu hỏi (Per-Question Analysis)

### 🛡️ Câu 1: `q_23401b31d098` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `66` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 2: `q_5e92228fd206` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `70712` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 3: `q_e0bed6042dfe` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `6405500` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `6405500` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 4: `q_20cfa482235e` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `Cty Thân Ngọc` (Kiểu: `string`) | **Đáp án Chuẩn (Gold)**: `Cty Thân Ngọc` (Kiểu: `string`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 5: `q_c26a816e7c91` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `False` (Kiểu: `boolean`) | **Đáp án Chuẩn (Gold)**: `False` (Kiểu: `boolean`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 6: `q_0794a9a26cef` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `[13, 2]` (Kiểu: `list`) | **Đáp án Chuẩn (Gold)**: `[13, 2]` (Kiểu: `list`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 7: `q_30d639b40362` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `4064300` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `4064300` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 8: `q_cea1b708d80a` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `3` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `3` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 9: `q_4d7fc53fcc41` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `1828785` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 10: `q_e390c3cb0b3b` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `10792500` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `10792500` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 11: `q_ebf285497536` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `unanswerable`) | **Đáp án Chuẩn (Gold)**: `None` (Kiểu: `unanswerable`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 12: `q_f3d30bcd1487` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `7.04` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 13: `q_083211e2c80c` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `2496270800` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `2496270800` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 14: `q_d2b32a2c57d8` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `36868000` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung bình`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 15: `q_4befa8de665c` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `26` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 16: `q_94fd5882870e` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `13.53` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả phần trăm bằng 0 bất thường`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 17: `q_9602e7257869` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `1371362` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung bình`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 18: `q_0a626a4c76d0` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `78584` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `78584` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 19: `q_bbf707d184af` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `104880600` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `104880600` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 20: `q_5412252566a0` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `327` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 21: `q_260318057077` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `797461200` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `797461200` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 22: `q_f95fc735e3bc` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `-36.41` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 23: `q_0983ff49fa23` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `67` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 24: `q_af1ea83ef086` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `571124700` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `571124700` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 25: `q_507a4f0e1ee9` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `25578000` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi 'hôm qua / bữa qua' (as_of_date=2025-04-30) nhưng code lọc nhầm ngày hôm nay (dt.day == 30)`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### 🛡️ Câu 26: `q_bc10815b2bf1` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `3478999` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 27: `q_1eca36df20a0` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `53` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `53` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 28: `q_44ab47ab8b70` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `307548300` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `307548300` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ✅ Câu 29: `q_9de78b7e6230` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `532524` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `532524` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>

### ❌ Câu 30: `q_4cb3efa8bd01` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `-93.71` (Kiểu: `percent`) | **Đáp án Chuẩn (Gold)**: `38.88` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Không có mã nguồn
```
</details>
