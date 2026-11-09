# BẢNG KHẢO SÁT VÀ PHÂN LOẠI TRẠNG THÁI ĐƠN HÀNG (STATUS VALUES SURVEY)

Tài liệu khảo sát toàn diện 30 shop tập train (`biz_101` – `biz_130`) phục vụ Bước 1 và Quy tắc 1, 8 trong `rulebook.md`.

---

## 1. THỐNG KÊ TỔNG QUAN

- **Tổng số shop khảo sát**: 30 shop (`biz_101` đến `biz_130`).
- **Tổng số dòng dữ liệu toàn tập train**: 1,664,524 dòng.
- **Tổng số giá trị trạng thái phân biệt**: 42 giá trị (bao gồm cả giá trị ô trống / null).
- **Shop không có cột trạng thái chuẩn**: 
  - `biz_101`: Không có cột tên "trạng thái", nhưng sử dụng cột `Kết quả` với các giá trị `Xong`, `Đã hủy`, `Đổi trả`, `Đang giao`.
  - `biz_114`: Sử dụng cột tên không dấu `trang_thai` (`đã lấy`, `Đã hủy đơn`, `Trả hàng`, `Đang giao`).
  - *Kết luận*: 100% (30/30) shop đều có cột thể hiện trạng thái giao dịch bán hàng.
- **Shop ghi nhận trả hàng ở cấp dòng (Line-level return columns)**:
  - 6 shop có cột số lượng trả hàng ở cấp dòng sản phẩm/lô: `biz_119`, `biz_120`, `biz_121`, `biz_122`, `biz_123`, `biz_124`.
  - Theo Rule 1 (`rulebook.md`): "Đơn có trả hàng, kể cả chỉ trả một phần, là đơn trả hàng: bỏ cả đơn". Khi dòng có `Số lượng trả > 0`, toàn bộ mã đơn tương ứng phải bị loại khỏi doanh thu.
- **Bảng/file ghi nhận trả hàng riêng biệt**:
  - Không có shop nào tách riêng file trả hàng độc lập ngoài các file hóa đơn chi tiết / chi tiết theo lô. Mọi thông tin trả hàng được ghi nhận qua cột trạng thái đơn hoặc cột số lượng trả cấp dòng trong bảng chi tiết đơn.

---

## 2. DANH SÁCH KHẢO SÁT CHI TIẾT 42 GIÁ TRỊ TRẠNG THÁI (GẠCH ĐẦU DÒNG)

### Nhóm 1: "GIỮ" (Đơn thành công hoặc đang giao — Tính vào doanh thu theo Rule 1)
*Quy tắc Rule 1: Đơn tính vào doanh thu là đơn không huỷ và không trả hàng. Đơn đang giao vẫn tính.*

- **Đã hoàn thành**:
  - Số dòng: 614,246 dòng | Số đơn: 280,888 đơn | Số shop: 10 shop (`biz_102`, `biz_104`, `biz_107`, `biz_111`, `biz_115`, `biz_121`, `biz_122`, `biz_125`, `biz_128`, `biz_130`).
  - Cột xuất hiện: `Trạng thái đơn hàng`, `Trạng thái`, `Ghi chú TT`, `Trạng thái xử lý`.
  - Đề xuất phân loại: **giữ** (Đơn bán thành công trọn vẹn).
- **xong**:
  - Số dòng: 151,990 dòng | Số đơn: 96,670 đơn | Số shop: 4 shop (`biz_106`, `biz_112`, `biz_113`, `biz_117`).
  - Cột xuất hiện: `Trạng thái`, `Ghi chú TT`.
  - Đề xuất phân loại: **giữ** (Giao dịch hoàn tất).
- **Hoàn thành**:
  - Số dòng: 139,599 dòng | Số đơn: 111,408 đơn | Số shop: 5 shop (`biz_106`, `biz_108`, `biz_109`, `biz_110`, `biz_128`).
  - Cột xuất hiện: `Trạng thái`, `Status`.
  - Đề xuất phân loại: **giữ** (Đơn hoàn thành).
- **Đã giao**:
  - Số dòng: 134,375 dòng | Số đơn: 58,775 đơn | Số shop: 3 shop (`biz_118`, `biz_124`, `biz_126`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái đơn`.
  - Đề xuất phân loại: **giữ** (Đơn giao hàng thành công).
- **đã lấy**:
  - Số dòng: 132,925 dòng | Số đơn: 86,723 đơn | Số shop: 5 shop (`biz_103`, `biz_105`, `biz_109`, `biz_110`, `biz_114`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái đơn hàng`, `Status`, `Ghi chú TT`, `trang_thai`.
  - Đề xuất phân loại: **giữ** (Khách đã nhận hàng / shipper đã lấy hàng đi giao thành công).
- **completed**:
  - Số dòng: 103,797 dòng | Số đơn: 70,805 đơn | Số shop: 3 shop (`biz_123`, `biz_127`, `biz_129`).
  - Cột xuất hiện: `TinhTrang`, `Tình trạng`, `Tình trạng đơn`.
  - Đề xuất phân loại: **giữ** (Hoàn thành - thuật ngữ tiếng Anh).
- **đã xong**:
  - Số dòng: 93,473 dòng | Số đơn: 53,355 đơn | Số shop: 2 shop (`biz_105`, `biz_118`).
  - Cột xuất hiện: `Status`, `Trạng thái`.
  - Đề xuất phân loại: **giữ** (Giao dịch hoàn tất).
- **Thành công**:
  - Số dòng: 72,255 dòng | Số đơn: 58,850 đơn | Số shop: 5 shop (`biz_103`, `biz_116`, `biz_117`, `biz_120`, `biz_126`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái đơn hàng`, `Ghi chú TT`.
  - Đề xuất phân loại: **giữ** (Đơn bán thành công).
- **Xong**:
  - Số dòng: 53,893 dòng | Số đơn: 21,386 đơn | Số shop: 1 shop (`biz_101`).
  - Cột xuất hiện: `Kết quả`.
  - Đề xuất phân loại: **giữ** (Hoàn thành giao dịch tại `biz_101`).
- **ok**:
  - Số dòng: 42,876 dòng | Số đơn: 28,935 đơn | Số shop: 2 shop (`biz_116`, `biz_120`).
  - Cột xuất hiện: `Trạng thái`.
  - Đề xuất phân loại: **giữ** (Xác nhận hoàn tất).
- **received**:
  - Số dòng: 540 dòng | Số đơn: 540 đơn | Số shop: 1 shop (`biz_123`).
  - Cột xuất hiện: `TinhTrang`.
  - Đề xuất phân loại: **giữ** (Đã nhận hàng).
- **Đang giao hàng**:
  - Số dòng: 124 dòng | Số đơn: 68 đơn | Số shop: 6 shop (`biz_105`, `biz_108`, `biz_115`, `biz_121`, `biz_122`, `biz_130`).
  - Cột xuất hiện: `Trạng thái`, `Status`.
  - Đề xuất phân loại: **giữ** (Rule 1: "Đơn đang giao vẫn tính").
- **Đang giao dịch**:
  - Số dòng: 123 dòng | Số đơn: 99 đơn | Số shop: 6 shop (`biz_102`, `biz_103`, `biz_104`, `biz_107`, `biz_125`, `biz_128`).
  - Cột xuất hiện: `Trạng thái đơn hàng`, `Trạng thái`.
  - Đề xuất phân loại: **giữ** (Đơn đang thực hiện, Rule 1).
- **Đang vận chuyển**:
  - Số dòng: 123 dòng | Số đơn: 71 đơn | Số shop: 4 shop (`biz_112`, `biz_113`, `biz_116`, `biz_117`).
  - Cột xuất hiện: `Trạng thái`, `Ghi chú TT`.
  - Đề xuất phân loại: **giữ** (Đơn đang giao, Rule 1).
- **Đang xử lý**:
  - Số dòng: 94 dòng | Số đơn: 50 đơn | Số shop: 4 shop (`biz_109`, `biz_118`, `biz_120`, `biz_124`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái xử lý`.
  - Đề xuất phân loại: **giữ** (Đơn đang tiến hành, Rule 1).
- **Đang giao**:
  - Số dòng: 93 dòng | Số đơn: 41 đơn | Số shop: 4 shop (`biz_101`, `biz_105`, `biz_114`, `biz_117`).
  - Cột xuất hiện: `Status`, `Ghi chú TT`, `Kết quả`, `trang_thai`.
  - Đề xuất phân loại: **giữ** (Đơn đang giao, Rule 1).
- **đang gửi**:
  - Số dòng: 47 dòng | Số đơn: 2 đơn | Số shop: 3 shop (`biz_107`, `biz_117`, `biz_126`).
  - Cột xuất hiện: `Trạng thái đơn`, `Trạng thái xử lý`, `Ghi chú TT`.
  - Đề xuất phân loại: **giữ** (Đơn đang gửi đi, Rule 1).
- **shipping**:
  - Số dòng: 37 dòng | Số đơn: 21 đơn | Số shop: 3 shop (`biz_123`, `biz_127`, `biz_129`).
  - Cột xuất hiện: `TinhTrang`, `Tình trạng`, `Tình trạng đơn`.
  - Đề xuất phân loại: **giữ** (Đang giao hàng tiếng Anh, Rule 1).
- **Chờ giao**:
  - Số dòng: 15 dòng | Số đơn: 0 đơn (thuộc bảng phiếu nạp/kho) | Số shop: 1 shop (`biz_110`).
  - Cột xuất hiện: `Status`.
  - Đề xuất phân loại: **giữ** (Đang chuẩn bị giao, Rule 1).

---

### Nhóm 2: "LOẠI (HUỶ)" (Đơn huỷ bỏ — Bỏ khỏi doanh thu, tính vào tỉ lệ đơn huỷ)
*Quy tắc Rule 1 & Rule 8: Bỏ khỏi doanh thu. Đơn có trạng thái huỷ tính vào "Đơn bị huỷ" và "Tỉ lệ đơn huỷ".*

- **Đã hủy**:
  - Số dòng: 12,319 dòng | Số đơn: 6,616 đơn | Số shop: 10 shop (`biz_101`, `biz_102`, `biz_104`, `biz_106`, `biz_107`, `biz_111`, `biz_115`, `biz_121`, `biz_122`, `biz_130`).
  - Cột xuất hiện: `Trạng thái đơn hàng`, `Trạng thái`, `Kết quả`.
  - Đề xuất phân loại: **loại (huỷ)**.
- **hủy**:
  - Số dòng: 3,849 dòng | Số đơn: 1,594 đơn | Số shop: 5 shop (`biz_105`, `biz_117`, `biz_118`, `biz_124`, `biz_126`).
  - Cột xuất hiện: `Status`, `Trạng thái`, `Trạng thái đơn`, `Ghi chú TT`.
  - Đề xuất phân loại: **loại (huỷ)**.
- **Đã hủy đơn**:
  - Số dòng: 2,957 dòng | Số đơn: 1,823 đơn | Số shop: 4 shop (`biz_103`, `biz_105`, `biz_112`, `biz_114`).
  - Cột xuất hiện: `Status`, `Trạng thái`, `Trạng thái đơn hàng`, `trang_thai`.
  - Đề xuất phân loại: **loại (huỷ)**.
- **Huỷ đơn**:
  - Số dòng: 2,074 dòng | Số đơn: 962 đơn | Số shop: 3 shop (`biz_120`, `biz_125`, `biz_128`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái xử lý`.
  - Đề xuất phân loại: **loại (huỷ)**.
- **hủy đơn**:
  - Số dòng: 1,931 dòng | Số đơn: 1,931 đơn | Số shop: 4 shop (`biz_103`, `biz_106`, `biz_109`, `biz_110`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái đơn hàng`.
  - Đề xuất phân loại: **loại (huỷ)**.
- **cancelled**:
  - Số dòng: 1,753 dòng | Số đơn: 1,404 đơn | Số shop: 3 shop (`biz_123`, `biz_127`, `biz_129`).
  - Cột xuất hiện: `TinhTrang`, `Tình trạng`, `Tình trạng đơn`.
  - Đề xuất phân loại: **loại (huỷ)** (Huỷ tiếng Anh).
- **khách hủy**:
  - Số dòng: 1,675 dòng | Số đơn: 223 đơn | Số shop: 3 shop (`biz_110`, `biz_113`, `biz_116`).
  - Cột xuất hiện: `Trạng thái`, `Status`, `Ghi chú TT`.
  - Đề xuất phân loại: **loại (huỷ)** (Khách chủ động huỷ đơn).
- **cancel**:
  - Số dòng: 1,344 dòng | Số đơn: 837 đơn | Số shop: 1 shop (`biz_112`).
  - Cột xuất hiện: `Trạng thái`.
  - Đề xuất phân loại: **loại (huỷ)**.
- **Đã huỷ**:
  - Số dòng: 486 dòng | Số đơn: 486 đơn | Số shop: 1 shop (`biz_109`).
  - Cột xuất hiện: `Trạng thái`.
  - Đề xuất phân loại: **loại (huỷ)** (Dấu hỏi ngã chuẩn Unicode).
- **Hủy**:
  - Số dòng: 330 dòng | Số đơn: 146 đơn | Số shop: 1 shop (`biz_117`).
  - Cột xuất hiện: `Ghi chú TT`.
  - Đề xuất phân loại: **loại (huỷ)**.

---

### Nhóm 3: "LOẠI (TRẢ)" (Đơn trả hàng / hoàn hàng — Bỏ khỏi doanh thu, KHÔNG phải đơn huỷ)
*Quy tắc Rule 1: Đơn có trả hàng, kể cả chỉ trả một phần, là đơn trả hàng: bỏ cả đơn. Đơn trả hàng KHÔNG phải đơn huỷ.*

- **Đã hoàn hàng**:
  - Số dòng: 2,520 dòng | Số đơn: 1,588 đơn | Số shop: 4 shop (`biz_102`, `biz_104`, `biz_121`, `biz_122`).
  - Cột xuất hiện: `Trạng thái đơn hàng`.
  - Đề xuất phân loại: **loại (trả)**.
  - *Lưu ý đặc biệt*: Chứa chữ "hoàn" nhưng là hoàn hàng/trả hàng. Bỏ sót từ khóa này chính là nguyên nhân làm lệch doanh thu batch 50 (mục B trong `batch50_diagnosis.md`).
- **Đã trả hàng**:
  - Số dòng: 2,158 dòng | Số đơn: 1,592 đơn | Số shop: 9 shop (`biz_108`, `biz_109`, `biz_115`, `biz_116`, `biz_118`, `biz_120`, `biz_125`, `biz_126`, `biz_128`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái xử lý`, `Ghi chú TT`.
  - Đề xuất phân loại: **loại (trả)**.
- **trả hàng**:
  - Số dòng: 1,801 dòng | Số đơn: 715 đơn | Số shop: 6 shop (`biz_107`, `biz_109`, `biz_112`, `biz_113`, `biz_116`, `biz_117`).
  - Cột xuất hiện: `Trạng thái`, `Trạng thái xử lý`, `Ghi chú TT`.
  - Đề xuất phân loại: **loại (trả)**.
- **Đổi trả**:
  - Số dòng: 1,555 dòng | Số đơn: 876 đơn | Số shop: 4 shop (`biz_101`, `biz_105`, `biz_124`, `biz_128`).
  - Cột xuất hiện: `Status`, `Trạng thái`, `Kết quả`.
  - Đề xuất phân loại: **loại (trả)**.
- **Hoàn trả**:
  - Số dòng: 775 dòng | Số đơn: 438 đơn | Số shop: 5 shop (`biz_103`, `biz_105`, `biz_106`, `biz_111`, `biz_130`).
  - Cột xuất hiện: `Status`, `Trạng thái`, `Trạng thái đơn hàng`.
  - Đề xuất phân loại: **loại (trả)**.
- **Trả hàng**:
  - Số dòng: 687 dòng | Số đơn: 255 đơn | Số shop: 4 shop (`biz_105`, `biz_114`, `biz_118`, `biz_126`).
  - Cột xuất hiện: `Status`, `Trạng thái`, `Trạng thái đơn`, `trang_thai`.
  - Đề xuất phân loại: **loại (trả)**.
- **hàng trả về**:
  - Số dòng: 576 dòng | Số đơn: 374 đơn | Số shop: 4 shop (`biz_103`, `biz_105`, `biz_118`, `biz_130`).
  - Cột xuất hiện: `Status`, `Trạng thái`, `Trạng thái đơn hàng`.
  - Đề xuất phân loại: **loại (trả)**.
- **trả lại**:
  - Số dòng: 443 dòng | Số đơn: 289 đơn | Số shop: 2 shop (`biz_106`, `biz_117`).
  - Cột xuất hiện: `Trạng thái`, `Ghi chú TT`.
  - Đề xuất phân loại: **loại (trả)**.
- **returned**:
  - Số dòng: 416 dòng | Số đơn: 143 đơn | Số shop: 3 shop (`biz_123`, `biz_127`, `biz_129`).
  - Cột xuất hiện: `TinhTrang`, `Tình trạng`, `Tình trạng đơn`.
  - Đề xuất phân loại: **loại (trả)** (Trả hàng tiếng Anh).

---

### Nhóm 4: "MƠ HỒ" / CẦN XEM XÉT ĐẶC BIỆT (AMBIGUOUS VALUES)
*Yêu cầu R3.2: Không tự quyết, nêu rõ 2 cách hiểu để người dùng phê duyệt.*

- **Không giao được**:
  - Thống kê: 2,345 dòng | 804 đơn | 4 shop (`biz_107`, `biz_116`, `biz_118`, `biz_126`) | Cột: `Trạng thái`, `Trạng thái xử lý`.
  - Ngữ cảnh: Đơn hàng giao không thành công (khách không nghe máy, từ chối nhận hàng, địa chỉ sai).
  - **Cách hiểu 1 (Khuyến nghị)**: Phân vào **`loại (huỷ)`**. Lý do: Giao không thành công dẫn tới đơn bị huỷ bỏ giao dịch, chưa thu tiền và không tạo doanh thu.
  - **Cách hiểu 2**: Phân vào **`loại (trả)`**. Lý do: Hàng đã xuất kho giao cho shipper nhưng giao thất bại nên bị chuyển hoàn/hoàn kho về shop.
  - *Tác động*: Cả 2 cách hiểu đều **LOẠI BỎ KHỎI DOANH THU**. Chỉ khác nhau khi trả lời câu hỏi "tỉ lệ đơn huỷ" hoặc "số đơn huỷ" vs "số đơn trả".
- **<TRỐNG / NULL>**:
  - Thống kê: 150,565 dòng | Cột: `Trạng thái`, `Status`, `Trạng thái đơn hàng`, `TinhTrangHDDT`...
  - Ngữ cảnh:
    - 110,643 dòng trong số này thuộc các shop có merged cells (`biz_103`: 27,401 dòng; `biz_121`: 38,878 dòng; `biz_122`: 44,312 + 4,272 dòng). Sau khi chạy Forward-Fill ở tầng nạp dữ liệu theo Rule 8, **toàn bộ 110,643 dòng này đã được điền đầy đủ trạng thái của đơn** (ví dụ `Đã hoàn thành`).
    - Số dòng còn lại nằm ở các bảng danh mục (`SanPham`, `KhachHang`, `NhanVien`) hoặc bảng không có cột trạng thái.
    - **Cách hiểu 1 (Khuyến nghị)**: Sau khi FFill theo mã đơn, nếu một dòng đơn bán hàng vẫn còn `NULL` trạng thái thì coi là **`giữ`** (mặc định giao dịch phát sinh là bán hàng thành công, trừ khi ghi rõ huỷ/trả).
    - **Cách hiểu 2**: Coi dòng `NULL` là không hợp lệ hoặc cần kiểm tra thêm ở bảng khác.
- **Đã nhập hàng**:
  - Thống kê: 3,132 dòng | 0 đơn bán | 6 shop (`biz_106`, `biz_108`, `biz_109`, `biz_110`, `biz_111`, `biz_115`).
  - Ngữ cảnh: Trạng thái nằm trong bảng nhập kho / mua hàng (`SoNhapHang`, `PhieuNhapHang`). Không phải bảng đơn bán hàng.
  - Phân loại: **giữ** trong ngữ cảnh tính tiền nhập hàng (Rule 5: "tổng tiền các phiếu nhập có ngày phiếu trong kỳ, bỏ phiếu huỷ").
- **Đang hoạt động**:
  - Thống kê: 2,040 dòng | 0 đơn bán | 8 shop (`biz_106`, `biz_108`, `biz_109`, `biz_110`, `biz_111`, `biz_112`, `biz_113`, `biz_115`).
  - Ngữ cảnh: Trạng thái của mặt hàng hoặc đối tác trong bảng danh mục (`DanhSachSanPham`, `KhachHang`), biểu thị entity còn active. Không phải trạng thái đơn hàng.

---

## 3. CẢNH BÁO BẪY REGEX CHỮ "HOÀN" (CRITICAL REGEX WARNING)

- **Nguy cơ tuyệt đối không dùng regex `"hoàn"` trần**:
  - Nếu viết regex lọc đơn huỷ/trả là `re.search(r"hủy|huỷ|trả|hoàn", status)`:
    - Chuỗi `"hoàn"` sẽ khớp nhầm toàn bộ:
      - `Đã hoàn thành`: 614,246 dòng
      - `Hoàn thành`: 139,599 dòng
    - Tổng cộng **753,845 dòng doanh thu hợp lệ (chiếm ~45% toàn bộ dữ liệu)** sẽ bị xóa sổ nhầm! Doanh thu của hệ thống sẽ sụp đổ về 0.
- **Quy tắc phân tách bắt buộc**:
  - **Giữ lại (Thành công)**: Khớp cụm từ đầy đủ `hoàn\s*thành`, `hoàn\s*tất`.
  - **Loại trừ (Trả hàng)**: Khớp cụm từ rõ ràng `hoàn\s*hàng`, `hoàn\s*trả`, `hàng\s*hoàn`, `hoàn\s*tiền`.

---

## 4. BẢNG TỔNG HỢP THEO CỘT VÀ SHOP CÓ CẤU TRÚC ĐẶC THÙ

| Shop ID | Tên bảng bán hàng chính | Cột trạng thái / Trả hàng | Cấu trúc đặc thù |
|---|---|---|---|
| `biz_101` | `ban_hang.csv` | `Kết quả` (`Xong`, `Đã hủy`, `Đổi trả`, `Đang giao`) | Cột trạng thái mang tên `Kết quả` |
| `biz_102` | `DonHang_ChiTiet.xlsx` | `Trạng thái đơn hàng` (`Đã hoàn thành`, `Đã hoàn hàng`, `Đã hủy`, `Đang giao dịch`) | Không có ô gộp; chứa `Đã hoàn hàng` |
| `biz_103` | `DonHang_ChiTiet.xlsx` | `Trạng thái đơn hàng` | Ô gộp nặng (60.2% null trước FFill) |
| `biz_114` | `ban_hang.csv` | `trang_thai` (`đã lấy`, `Đã hủy đơn`, `Trả hàng`, `Đang giao`) | Tên cột viết không dấu `trang_thai` |
| `biz_119` | `DanhSachHoaDonChiTietLo.xlsx` | `Số lượng trả (ĐVT cơ bản)` | Cột trả hàng cấp dòng (Line-level return) |
| `biz_120` | `DanhSachHoaDonChiTietLo.xlsx` | `Số lượng trả (ĐVT cơ bản)` | Cột trả hàng cấp dòng (Line-level return) |
| `biz_121` | `DonHang_ChiTiet.xlsx` & `DonHang_Lo` | `Trạng thái đơn hàng` & `Số lượng trả` | Ô gộp 46.9% & Trả hàng cấp dòng |
| `biz_122` | `DonHang_ChiTiet_1.xlsx` & `DonHang_Lo` | `Trạng thái đơn hàng` & `Số lượng trả` | Ô gộp 46.9% & Trả hàng cấp dòng |
| `biz_123` | `pos.sqlite::chi_tiet_don_lo` | `TinhTrang` & `SLTraQuyDoi` | Trả hàng cấp dòng trong SQLite |
| `biz_124` | `BanHang_BanTheoLo.xlsx` | `Trạng thái` & `SL trả (ĐVT cơ bản)` | Trả hàng cấp dòng |

---

## 5. ĐIỂM DỪNG BẮT BUỘC (MANDATORY CHECKPOINT)

**TUÂN THỦ RÀNG BUỘC CHECKPOINT**:
Báo cáo khảo sát này được xuất ra để người dùng và Orchestrator xem xét, phê duyệt.
**TUYỆT ĐỐI CHƯA CÀI ĐẶT BỘ LỌC ĐƠN HUỶ/TRẢ VÀO MÃ NGUỒN PIPELINE** cho tới khi nhận được quyết định phê duyệt chính thức từ người dùng về bảng trạng thái trên và lựa chọn phân loại cho giá trị mơ hồ (`Không giao được`).
