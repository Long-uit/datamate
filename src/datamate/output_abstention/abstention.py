"""
Module: src/datamate/output/abstention.py
Mục đích: Module 6.2 — Calibrated Abstention Gate (Cổng từ chối có hiệu chuẩn).
          Tính toán điểm tin cậy tổng hợp C in [0.0, 1.0] dựa trên các tín hiệu:
          1. Sức khỏe thực thi (Execution Health: số lượt self-correction, runtime ms).
          2. Tính hợp lý của dữ liệu (Data Plausibility: sanity check, giá trị biên, tỷ lệ rỗng).
          3. Đánh giá độ bám thực thể & ràng buộc (Grounding Coverage: gom theo mention,
             lọc false positive >= 0.85, ràng buộc thời gian ISO, bảng mở rộng).
          
          Nếu C < tau* (mặc định 0.50), chủ động chuyển đáp án thành 'abstain' (0 điểm) thay vì gửi
          đáp án nghi ngờ để triệt tiêu hoàn toàn rủi ro bị phạt -1 điểm (Penalized Accuracy).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Set


# ==============================================================================
# BỘ TỪ KHÓA BÁN LẺ CHUNG (GENERIC BUSINESS STOPWORDS)
# ==============================================================================
# Các từ ngữ phổ biến trong câu hỏi bán lẻ cần loại trừ khỏi danh sách entity bắt buộc
# để tránh Linker sinh false positive và phạt oan mã nguồn
GENERIC_BUSINESS_STOPWORDS: Set[str] = {
    # Thời gian
    "tháng", "thang", "năm", "nam", "ngày", "ngay", "hôm nay", "hom nay",
    "hôm qua", "hom qua", "bữa qua", "bua qua", "tuần", "tuan", "quý", "quy",
    "đầu tháng", "dau thang", "cuối ngày", "cuoi ngay", "thời gian", "thoi gian",
    # Tiền tệ & Doanh số
    "tiền", "tien", "giá", "gia", "tổng", "tong", "tổng cộng", "tong cong",
    "doanh thu", "dthu", "doanh số", "doanh so", "lãi", "lai", "lợi nhuận", "loi nhuan",
    "chi phí", "chi phi", "thành tiền", "thanh tien", "tổng tiền", "tong tien",
    "tổng đơn", "tong don", "trị giá", "tri gia", "giá trị", "gia tri",
    # Hoạt động mua bán
    "đơn", "don", "đơn hàng", "don hang", "hóa đơn", "hoa don", "bill",
    "hàng", "hang", "hàng hóa", "hang hoa", "mặt hàng", "mat hang",
    "sản phẩm", "san pham", "sp", "món", "mon",
    "bán", "ban", "mua", "nhập", "nhap", "xuất", "xuat", "tồn", "ton", "tồn kho", "ton kho",
    "hủy", "huy", "trả", "tra", "hoàn", "hoan", "giao", "giao dịch", "giao dich",
    # Đối tượng
    "khách", "khach", "khách hàng", "khach hang", "người", "nguoi",
    "cửa hàng", "cua hang", "tiệm", "tiem", "quán", "quan", "shop", "shop_meta", "đối tượng", "doi tuong",
    # Từ ngữ tính toán / thống kê
    "bình quân", "binh quan", "trung bình", "trung binh",
    "mỗi đơn", "moi don", "mỗi", "moi", "từng", "tung", "cả", "ca", "mỗi ngày", "moi ngay",
    "bao nhiêu", "bao nhieu", "bn", "bnhiu", "bao nhiu", "mấy", "may",
    "tất cả", "tat ca", "toàn bộ", "toan bo", "toàn", "toan",
    "số lượng", "so luong", "sl", "lẻ", "le", "sỉ", "si", "chẵn", "chan",
    "mới", "moi", "cũ", "cu", "chưa", "chua", "đã", "da",
    "nào", "nao", "gì", "gi", "ai", "đâu", "dau", "được", "duoc", "đc", "dc",
    "top", "cao nhất", "cao nhat", "thấp nhất", "thap nhat", "nhiều nhất", "nhieu nhat", "ít nhất", "it nhat",
    "tỉ lệ", "ti le", "tỷ lệ", "ty le", "phần trăm", "phan tram", "ptram", "%",
    "chênh lệch", "chenh lech", "tăng", "tang", "giảm", "giam", "thay đổi", "thay doi",
    "đơn vị", "don vi", "đvt", "dvt", "quy cách", "quy cach", "quy đổi", "quy doi",
}


def _strip_diacritics(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp mềm không phụ thuộc chính tả/encoding."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", str(text))
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def _extract_match_info(m: Any) -> Tuple[str, str, float, str, str]:
    """Trích xuất (query_term, matched_value, score, source_table, source_col) an toàn."""
    if hasattr(m, "query_term"):
        term = str(getattr(m, "query_term", "")).strip()
        val = str(getattr(m, "matched_value", "")).strip()
        score = float(getattr(m, "score", 0.0))
        meta = getattr(m, "metadata", {}) or {}
        tbl = str(meta.get("source_table", "")).strip()
        col = str(meta.get("source_col", "")).strip()
    elif isinstance(m, dict):
        term = str(m.get("query_term", m.get("term", ""))).strip()
        val = str(m.get("matched_value", m.get("value", ""))).strip()
        score = float(m.get("score", 0.0))
        meta = m.get("metadata", {}) or {}
        tbl = str(meta.get("source_table", m.get("table", ""))).strip()
        col = str(meta.get("source_col", m.get("col", ""))).strip()
    else:
        term = str(m).strip()
        val = str(m).strip()
        score = 1.0
        tbl = ""
        col = ""
    return term, val, score, tbl, col


# ==============================================================================
# HÀM ĐÁNH GIÁ ĐỘ BÁM DỮ LIỆU & RÀNG BUỘC (GROUNDING COVERAGE EVALUATION)
# ==============================================================================

def evaluate_grounding_coverage(
    code_text: str,
    question: str = "",
    entity_matches: Optional[List[Any]] = None,
    temporal_info: Optional[Dict[str, Any]] = None,
    allowed_tables: Optional[List[str]] = None,
    min_entity_score: float = 0.85,
) -> Dict[str, Any]:
    """
    Đánh giá mức độ bám sát dữ liệu (Grounding Coverage) của đoạn mã do LLM sinh ra:
    
    1. Gom theo Mention (Mention Grouping):
       - Một thực thể/từ khóa trong câu hỏi (query_term) có thể khớp nhiều ứng viên trong DB.
       - Chỉ cần mã nguồn sử dụng ÍT NHẤT 1 ứng viên hợp lệ (hoặc chính chuỗi mention đó)
         là được coi là đã bám (COVERED), không phạt oan.
       - Lọc bỏ stopword / từ ngữ chung chung trong ngành bán lẻ ("tháng", "ngày", "năm", "tiền", "đơn",...).
       - Chỉ xét các liên kết có độ tin cậy cao (score >= min_entity_score, mặc định 0.85).
       
    2. Ràng buộc thời gian (Temporal Grounding):
       - Nếu câu hỏi có mốc thời gian bắt buộc (start_date, end_date), kiểm tra mã có chứa
         chuỗi ngày ISO, năm/tháng, hoặc biến ngày tháng ('clean_date', 'start_date',...).
         
    3. Bảng ngoài phạm vi (Off-topic Tables):
       - Cho phép mở rộng bảng qua quan hệ (allowed_tables). Mức phạt nhẹ (0.05) vì là tín hiệu phụ.
       
    Trả về Dictionary chi tiết:
    - entity_coverage: float (0.0 -> 1.0)
    - temporal_coverage: float (0.0 -> 1.0)
    - table_coverage: float (0.0 -> 1.0)
    - total_penalty: float (0.0 -> 0.70)
    - missed_mentions: List[Dict] (phục vụ feedback cho vòng retry!)
    - offtopic_tables: List[str]
    """
    clean_code = re.sub(r"#.*", "", code_text)
    code_lower = clean_code.lower()
    code_no_acc = _strip_diacritics(clean_code)

    # --------------------------------------------------------------------------
    # 1. Gom theo Mention & Kiểm tra Entity Coverage
    # --------------------------------------------------------------------------
    mention_groups: Dict[str, List[Tuple[str, str, float, str, str]]] = {}
    if entity_matches:
        for m in entity_matches:
            term, val, score, tbl, col = _extract_match_info(m)
            term_clean = term.lower().strip()
            term_no_acc = _strip_diacritics(term_clean)
            if not term_clean:
                continue
            # Lọc bỏ stopword và từ quá ngắn
            if (
                term_clean in GENERIC_BUSINESS_STOPWORDS
                or term_no_acc in GENERIC_BUSINESS_STOPWORDS
                or len(term_clean) <= 2
            ):
                continue
            # Lọc theo ngưỡng tin cậy cao
            if score < min_entity_score:
                continue
            mention_groups.setdefault(term_clean, []).append((term, val, score, tbl, col))

    covered_mentions = 0
    missed_mentions: List[Dict[str, Any]] = []

    for term_clean, candidates in mention_groups.items():
        term_no_acc = _strip_diacritics(term_clean)
        is_covered = False

        # Kiểm tra 1: Chuỗi mention xuất hiện trực tiếp trong mã
        if term_clean in code_lower or term_no_acc in code_no_acc:
            is_covered = True
        else:
            # Kiểm tra 2: Bất kỳ ứng viên nào (matched_value, cột, hoặc token quan trọng) xuất hiện
            for orig_term, val, score, tbl, col in candidates:
                val_lower = val.lower()
                val_no_acc = _strip_diacritics(val)
                col_lower = col.lower()

                # Khớp toàn bộ giá trị thực tế
                if val_lower in code_lower or val_no_acc in code_no_acc:
                    is_covered = True
                    break

                # Khớp token đặc trưng của giá trị (độ dài >= 4 ký tự)
                val_tokens = [t for t in re.split(r"[\s,\-_/]+", val_no_acc) if len(t) >= 4 and t not in GENERIC_BUSINESS_STOPWORDS]
                if val_tokens and any(t in code_no_acc for t in val_tokens):
                    is_covered = True
                    break

                # Khớp tên cột định danh
                if col and (col_lower in code_lower or _strip_diacritics(col) in code_no_acc):
                    is_covered = True
                    break

        if is_covered:
            covered_mentions += 1
        else:
            # Lưu candidate có score cao nhất làm gợi ý feedback cho vòng retry
            best_cand = max(candidates, key=lambda x: x[2])
            missed_mentions.append({
                "term": best_cand[0],
                "candidate": best_cand[1],
                "score": best_cand[2],
                "table": best_cand[3],
                "col": best_cand[4],
            })

    total_valid_mentions = len(mention_groups)
    if total_valid_mentions > 0:
        entity_coverage = round(covered_mentions / total_valid_mentions, 4)
        entity_penalty = round(0.35 * (1.0 - entity_coverage), 4)
    else:
        entity_coverage = 1.0
        entity_penalty = 0.0

    # --------------------------------------------------------------------------
    # 2. Ràng buộc thời gian (Temporal Grounding Coverage)
    # --------------------------------------------------------------------------
    temporal_penalty = 0.0
    temporal_coverage = 1.0

    if temporal_info:
        s_d = str(temporal_info.get("start_date", "")).strip()
        e_d = str(temporal_info.get("end_date", "")).strip()

        # Nếu câu hỏi có mốc thời gian bắt buộc cụ thể
        if s_d and s_d.lower() != "none" and e_d and e_d.lower() != "none":
            has_literal_date = (s_d in code_text) or (e_d in code_text)
            has_temporal_ops = any(k in code_lower for k in [
                "clean_date", "to_datetime", "dt.date", "dt.year", "dt.month", "ngay", "datetime"
            ])

            # Nếu có mốc ngày cụ thể mà mã nguồn hoàn toàn không chứa ngày literal lẫn hàm lọc thời gian
            if not has_literal_date and not has_temporal_ops:
                temporal_coverage = 0.0
                temporal_penalty = 0.25
            elif not has_literal_date and (len(s_d) >= 4 and s_d[:4] not in code_text) and "dt.month" not in code_lower:
                # Có gọi hàm thời gian nhưng không hề xuất hiện năm hay tháng tương ứng
                temporal_coverage = 0.5
                temporal_penalty = 0.15

    # --------------------------------------------------------------------------
    # 3. Bảng ngoài phạm vi (Off-topic Tables Check)
    # --------------------------------------------------------------------------
    table_penalty = 0.0
    offtopic_tables: List[str] = []

    if allowed_tables:
        norm_allowed = {_strip_diacritics(re.sub(r"[^a-zA-Z0-9]", "", t.lower())) for t in allowed_tables}
        queried_tables = set()
        for m_tbl in re.findall(r"(?:data|dfs)\[['\"]([^'\"]+)['\"]\]", code_text):
            queried_tables.add(m_tbl)
        for m_sql in re.findall(r"(?:FROM|JOIN)\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", code_text, re.IGNORECASE):
            queried_tables.add(m_sql)

        for q_t in queried_tables:
            clean_q = _strip_diacritics(re.sub(r"[^a-zA-Z0-9]", "", q_t.lower()))
            if clean_q not in norm_allowed and not any(clean_q in alt or alt in clean_q for alt in norm_allowed):
                offtopic_tables.append(q_t)

        if offtopic_tables:
            table_penalty = 0.05

    total_penalty = round(min(0.70, entity_penalty + temporal_penalty + table_penalty), 4)

    return {
        "entity_coverage": entity_coverage,
        "temporal_coverage": temporal_coverage,
        "table_coverage": 0.0 if offtopic_tables else 1.0,
        "entity_penalty": entity_penalty,
        "temporal_penalty": temporal_penalty,
        "table_penalty": table_penalty,
        "total_penalty": total_penalty,
        "missed_mentions": missed_mentions,
        "offtopic_tables": offtopic_tables,
        "total_valid_mentions": total_valid_mentions,
        "covered_mentions": covered_mentions,
    }


# ==============================================================================
# CỔNG KIỂM CHỨNG NGỮ NGHĨA & ĐỒNG THUẬN HAI NHÁNH (GENERATION-2 VERIFICATION)
# ==============================================================================

def evaluate_semantic_rule_compliance(
    code_text: str,
    question: str = "",
    sub_ans: Optional[Dict[str, Any]] = None,
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Kiểm tra tính tuân thủ ngữ nghĩa Rulebook và tính hợp lệ tất định của đoạn mã Python sinh ra:
    - Phát hiện nhầm lẫn giữa 'ưa chuộng nhất' (đếm số đơn nunique) và 'bán chạy nhất' (tổng số lượng).
    - Phát hiện nhầm lẫn giữa đếm số đơn ('bao nhiêu đơn') và cộng tiền ('.sum()').
    - Phát hiện thiếu điều kiện lọc khách có >= 3 đơn khi hỏi 'khách sộp nhất'.
    - Phát hiện câu hỏi đếm đơn hủy ('bị hủy', 'trạng thái hủy') nhưng code không hề lọc trạng thái hủy.
    - Phát hiện kiểu câu hỏi là percent nhưng code không có phép chia tỷ lệ.
    - Phát hiện kiểu trả về không khớp kiểu câu hỏi kỳ vọng.
    - Phát hiện điều kiện lọc luôn rỗng (vd: dt.day >= 27 & dt.day <= 3).
    """
    violations: List[str] = []
    semantic_penalty = 0.0
    if not code_text and not question:
        return {"is_compliant": True, "semantic_penalty": 0.0, "violations": []}

    q_low = unicodedata.normalize("NFC", question).lower() if question else ""
    q_no_acc = _strip_diacritics(q_low)
    clean_c = re.sub(r"#.*", "", code_text).lower() if code_text else ""
    clean_c_no_acc = _strip_diacritics(clean_c)

    # 1. 'Ưa chuộng nhất' bắt buộc dùng nunique() trên mã đơn, không phải sum() doanh thu
    if "ưa chuộng" in q_low or "ua chuong" in q_no_acc:
        if "nunique" not in clean_c and "drop_duplicates" not in clean_c:
            violations.append("Câu hỏi 'ưa chuộng nhất' (Điều 3) yêu cầu đếm số đơn khác nhau (.nunique()), nhưng code chưa dùng .nunique()")
            semantic_penalty += 0.25

    # 2. 'Khách sộp nhất' bắt buộc lọc >= 3 đơn
    if "khách sộp" in q_low or "sộp nhất" in q_low:
        if not re.search(r">=\s*3|>\s*2", clean_c):
            violations.append("Câu hỏi 'khách sộp nhất' (Điều 3) yêu cầu lọc khách có tối thiểu 3 đơn hợp lệ (>= 3)")
            semantic_penalty += 0.25

    # 3. Hỏi đếm số đơn nhưng code chỉ gọi .sum() trên cột tiền mà không có nunique/count/len
    asks_order_count = bool(re.search(r"(?:bao\s*nhi[eê]u|m[aấ]y|đ[eế]m\s*s[oố])\s*(?:đ[oơ]n|h[oó]a\s*đ[oơ]n|bill)", q_low))
    asks_money = bool(re.search(r"ti[eề]n|doanh\s*thu|doanh\s*s[oố]|gi[aá]\s*tr[iị]", q_low))
    if asks_order_count and not asks_money and clean_c:
        has_count_op = any(k in clean_c for k in ["nunique", "len(", ".count(", "shape[0]", "value_counts", "count_orders"])
        if not has_count_op and ".sum()" in clean_c:
            violations.append("Câu hỏi đếm số đơn nhưng code chỉ gọi .sum() mà không đếm mã đơn (.nunique())")
            semantic_penalty += 0.30

    # 4. Điều kiện lọc luôn rỗng (ví dụ: dt.day >= 27 & dt.day <= 3 trên cùng 1 tháng)
    if clean_c:
        m_day_ge = re.findall(r"dt\.day\s*>=\s*(\d+)", clean_c)
        m_day_le = re.findall(r"dt\.day\s*<=\s*(\d+)", clean_c)
        if m_day_ge and m_day_le:
            for d_ge in m_day_ge:
                for d_le in m_day_le:
                    if int(d_ge) > int(d_le) and "|" not in clean_c:
                        violations.append(f"Điều kiện lọc ngày luôn rỗng (dt.day >= {d_ge} & dt.day <= {d_le})")
                        semantic_penalty += 0.60
        m_month_ge = re.findall(r"dt\.month\s*>=\s*(\d+)", clean_c)
        m_month_le = re.findall(r"dt\.month\s*<=\s*(\d+)", clean_c)
        if m_month_ge and m_month_le:
            for m_ge in m_month_ge:
                for m_le in m_month_le:
                    if int(m_ge) > int(m_le) and "|" not in clean_c:
                        violations.append(f"Điều kiện lọc tháng luôn rỗng (dt.month >= {m_ge} & dt.month <= {m_le})")
                        semantic_penalty += 0.60

    # 5. Kiểu câu hỏi là percent mà code không tính tỷ lệ
    try:
        from src.datamate.output_abstention.normalizer import infer_expected_type
        expected_q_type = infer_expected_type(question) if question else None
    except Exception:
        expected_q_type = None

    ans_type = sub_ans.get("type") if isinstance(sub_ans, dict) else None
    if (ans_type == "percent" or expected_q_type == "percent") and clean_c:
        has_ratio_op = (
            "/" in clean_c
            or any(k in clean_c for k in ("pct", "ratio", "ty_le", "ti_le", "ty_trong", "ti_trong", "percent", "div("))
        )
        if not has_ratio_op:
            violations.append("Câu hỏi kiểu percent nhưng code không thực hiện phép chia tính tỷ lệ")
            semantic_penalty += 0.60

    # 6. Kiểu trả về không khớp kiểu câu hỏi kỳ vọng
    if expected_q_type and ans_type and ans_type not in ("abstain", "unanswerable"):
        if ans_type != expected_q_type and not (expected_q_type == "number" and ans_type == "list"):
            violations.append(f"Kiểu trả về '{ans_type}' không khớp với kiểu câu hỏi kỳ vọng '{expected_q_type}'")
            semantic_penalty += 0.60

    # 7. Câu hỏi hỏi số đơn bị hủy nhưng code không lọc trạng thái hủy
    if re.search(r"\b(?:đon|don|bill|hoa\s*don)\s*(?:o\s*trang\s*thai\s*)?(?:bi\s*)?huy\b|\bbao\s*nhieu\s*(?:don|bill)\s*(?:bi\s*)?huy\b", q_no_acc):
        if clean_c and not re.search(r"huy|cancel|cancelled_orders", clean_c_no_acc):
            violations.append("Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy")
            semantic_penalty += 0.60

    # 8. Câu hỏi hỏi số lượng sản phẩm bán ra (số đĩa, mấy cái, bao nhiêu hộp/gói/chai...) nhưng code chỉ cộng cột tiền mà không dùng cột số lượng
    asks_item_qty = bool(
        re.search(
            r"\b(?:so\s*luong|so\s*dia|so\s*phan|so\s*suat|so\s*to|so\s*ly|so\s*chai|so\s*hop|so\s*goi|so\s*cai|so\s*chiec|may\s*dia|may\s*phan|may\s*hop|may\s*chai|bao\s*nhieu\s*(?:dia|phan|suat|to|ly|chai|hop|goi))\b",
            q_no_acc,
        )
    )
    if asks_item_qty and not asks_money and clean_c:
        uses_amt_only = bool(re.search(r"\bamt_col\b|thanh\s*tien|tong\s*tien|tien\s*ban|doanh\s*thu", clean_c_no_acc))
        uses_qty = bool(re.search(r"\bqty_col\b|so\s*luong|sluong|\bs\.l\b|\bsl\b|quantity|convert_to_base_qty", clean_c_no_acc))
        if uses_amt_only and not uses_qty:
            violations.append("Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng")
            semantic_penalty += 0.60

    # 9. Câu hỏi hỏi công nợ / còn nợ / tiền khách trả bớt nợ nhưng code không truy cập bảng thanh toán / công nợ hay cột nợ
    asks_debt_repayment = bool(re.search(r"tra\s*bot\s*no|thu\s*no|tra\s*no|mua\s*chiu|cong\s*no|con\s*no|no\s*cua\s*hang|khach\s*no", q_no_acc))
    if asks_debt_repayment and clean_c:
        uses_debt_or_pay = bool(re.search(r"thanh_toan|thanh\s*toan|cong_no|cong\s*no|so_no|du\s*no|con_lai|con\s*lai|con\s*no|\bno\b|phieu\s*thu|tra\s*no|debt", clean_c_no_acc))
        if not uses_debt_or_pay:
            violations.append("Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ")
            semantic_penalty += 0.60

    # 10. Câu hỏi hỏi 'hôm qua' / 'bữa qua' nhưng code lọc cứng dt.day == as_of_date.day (lấy nhầm ngày hôm nay)
    if as_of_date and re.search(r"\b(?:hom\s*qua|bua\s*qua|ngay\s*hom\s*qua)\b", q_no_acc) and clean_c:
        try:
            aod_day = int(str(as_of_date).strip().split("-")[2][:2])
            if re.search(rf"dt\.day\s*==\s*{aod_day}\b", clean_c) and not re.search(rf"dt\.day\s*==\s*{aod_day - 1}\b", clean_c):
                violations.append(f"Câu hỏi hỏi 'hôm qua / bữa qua' (as_of_date={as_of_date}) nhưng code lọc nhầm ngày hôm nay (dt.day == {aod_day})")
                semantic_penalty += 0.60
        except Exception:
            pass

    # 11. Bất cân xứng khoảng thời gian so sánh (so sánh một ngày với nửa tháng / nhiều ngày)
    # hoặc câu hỏi hỏi 'từ đầu tháng' nhưng code chỉ lọc 1 ngày hôm nay (as_of_date)
    if as_of_date and re.search(r"\b(?:tu\s*dau\s*thang|từ\s*đầu\s*tháng)\b", q_low + " " + q_no_acc) and clean_c:
        try:
            aod_str = str(as_of_date).strip()
            parts = aod_str.split("-")
            month_start_iso = f"{parts[0]}-{parts[1]}-01"
            has_month_start = (
                (month_start_iso in clean_c)
                or ("start_date" in clean_c)
                or ("dt.month" in clean_c and "dt.day >=" not in clean_c)
                or ("revenue(" in clean_c and ("start_date" in clean_c or month_start_iso in clean_c))
            )
            is_single_aod_day = bool(
                re.search(rf"clean_date.*?>=\s*pd\.timestamp\(['\"]{aod_str}.*?clean_date.*?<=\s*pd\.timestamp\(['\"]{aod_str}", clean_c)
                or re.search(rf"{aod_str}.*?{aod_str}", clean_c)
                or re.search(rf"dt\.day\s*==\s*{int(parts[2])}\b", clean_c)
            )
            if not has_month_start and is_single_aod_day:
                violations.append(f"Câu hỏi yêu cầu tính 'từ đầu tháng' (as_of_date={as_of_date}) nhưng code chỉ lọc duy nhất 1 ngày hôm nay (so sánh một ngày với nửa tháng)")
                semantic_penalty += 0.60
        except Exception:
            pass

    semantic_penalty = round(min(0.80, semantic_penalty), 4)
    return {
        "is_compliant": len(violations) == 0,
        "semantic_penalty": semantic_penalty,
        "violations": violations,
    }


def cross_verify_dual_execution(
    primary_ans: Dict[str, Any],
    secondary_ans: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Kiểm chứng chéo (Dual-Execution Cross-Verification) giữa 2 kết quả thực thi độc lập:
    - Nếu 2 nhánh ra cùng đáp án: tăng độ tin cậy (+0.10).
    - Nếu 2 nhánh ra kết quả mâu thuẫn: phạt độ tin cậy (-0.35) để cảnh báo rủi ro -1 điểm.
    """
    if not secondary_ans or secondary_ans.get("type") in ("abstain", "unanswerable", None):
        return {"verified": None, "confidence_delta": 0.0, "reason": "Single execution path"}

    p_type = primary_ans.get("type")
    s_type = secondary_ans.get("type")
    p_val = primary_ans.get("answer")
    s_val = secondary_ans.get("answer")

    if p_type != s_type:
        return {
            "verified": False,
            "confidence_delta": -0.35,
            "reason": f"Bất đồng kiểu đáp án giữa 2 nhánh ({p_type} vs {s_type})",
        }

    if p_type in ("number", "percent") and isinstance(p_val, (int, float)) and isinstance(s_val, (int, float)):
        diff = abs(float(p_val) - float(s_val))
        denom = max(abs(float(p_val)), abs(float(s_val)), 1.0)
        if diff <= 1e-2 or (diff / denom) <= 1e-4:
            return {"verified": True, "confidence_delta": 0.10, "reason": "Hai nhánh tính toán khớp số học"}
        return {
            "verified": False,
            "confidence_delta": -0.35,
            "reason": f"Bất đồng giá trị số giữa 2 nhánh ({p_val} vs {s_val})",
        }

    if str(p_val).strip().lower() == str(s_val).strip().lower():
        return {"verified": True, "confidence_delta": 0.10, "reason": "Hai nhánh khớp kết quả"}

    return {
        "verified": False,
        "confidence_delta": -0.35,
        "reason": f"Bất đồng kết quả giữa 2 nhánh ({p_val} vs {s_val})",
    }


# ==============================================================================
# HÀM TÍNH ĐIỂM ĐỘ TIN CẬY CÓ HIỆU CHUẨN (CALIBRATED CONFIDENCE SCORE)
# ==============================================================================

def compute_confidence_score(
    sub_ans: Dict[str, Any],
    exec_error: Optional[str] = None,
    exec_ms: int = 0,
    retry_count: int = 0,
    sanity_passed: bool = True,
    sanity_error: Optional[str] = None,
    code_text: str = "",
    has_feasibility_pass: bool = True,
    unanswerable_source: str = "none",
    grounding_eval: Optional[Dict[str, Any]] = None,
    entity_matches: Optional[List[Any]] = None,
    temporal_info: Optional[Dict[str, Any]] = None,
    allowed_tables: Optional[List[str]] = None,
    question: str = "",
    penalize_zero_revenue_qty: Optional[bool] = None,
) -> float:
    """
    Tính điểm độ tin cậy C in [0.0, 1.0] có hiệu chuẩn dựa trên sức khỏe thực thi,
    tính hợp lý dữ liệu và mức độ bám sát thực thể / thời gian (Grounding Penalties).
    """
    ans_type = sub_ans.get("type")
    ans_val = sub_ans.get("answer")
    source = sub_ans.get("unanswerable_source") or unanswerable_source

    if penalize_zero_revenue_qty is None:
        try:
            from src.datamate.config import get_config
            penalize_zero_revenue_qty = get_config().abstention.penalize_zero_revenue_qty
        except Exception:
            penalize_zero_revenue_qty = True

    # Nếu câu hỏi đã được Feasibility Gate xác định là không khả thi ngay từ đầu
    if not has_feasibility_pass:
        return 1.0 if ans_type == "unanswerable" else 0.0

    # Nếu đáp án là unanswerable:
    # CHỈ giữ confidence 1.0 nếu nguồn gốc thực sự từ Feasibility Gate ('gate').
    # Nếu do mô hình tự ý sinh ra ('model') khi gate đã cho qua -> triệt tiêu confidence về 0.0!
    if ans_type == "unanswerable":
        if source == "gate":
            return 1.0
        return 0.0

    if ans_type == "abstain":
        return 0.0

    # Nếu sanity_passed=False (vi phạm bất kỳ quy tắc tất định nào ở check_result_sanity),
    # kiểm tra xem lỗi có phải do zero penalty đang tắt hay không; nếu lỗi thật sự -> hạ C xuống dưới ngưỡng (< 0.50).
    if not sanity_passed:
        if not penalize_zero_revenue_qty and sanity_error and "Silent Zero" in sanity_error:
            sanity_passed = True
        else:
            return 0.20

    # 1. Điểm sức khỏe thực thi (Execution Health Score) - Tối đa 0.40
    if exec_error is not None:
        exec_score = 0.0
    elif retry_count == 0:
        exec_score = 0.40
    else:
        # Cứ mỗi lần retry thì độ tin cậy giảm nhẹ
        exec_score = max(0.20, 0.40 - 0.10 * retry_count)

    # Phạt nếu runtime quá dài (> 5000ms có thể là query vét cạn dễ OOM/timeout)
    if exec_ms > 5000:
        exec_score = max(0.10, exec_score - 0.10)

    # 2. Điểm hợp lý dữ liệu (Data Plausibility Score) - Tối đa 0.35
    plausibility_score = 0.35
    q_low = unicodedata.normalize("NFC", question).lower() if question else ""
    if ans_type in ("number", "percent"):
        if isinstance(ans_val, (int, float)):
            if math.isnan(ans_val) or math.isinf(ans_val):
                return 0.0
            elif float(ans_val) == 0.0:
                is_change_or_profit = bool(re.search(r"t[aă]ng|gi[aả]m|ch[eê]nh\s*l[eệ]ch|thay\s*đ[oổ]i|l[aã]i|l[oỗ]|l[oợ]i\s*nhu[aậ]n|bi[eế]n\s*đ[oộ]ng", q_low))
                is_rev_qty_avg = bool(re.search(
                    r"doanh\s*thu|dthu|doanh\s*s[oố]|t[oổ]ng\s*ti[eề]n|ti[eề]n\s*b[aá]n|s[oố]\s*lu[oợ]ng|"
                    r"trung\s*b[iì]nh|trung\s*binh|b[iì]nh\s*qu[aâ]n|binh\s*quan|\baov\b|"
                    r"t[ỉỷi]\s*tr[ọo]ng|ty\s*trong|ph[ầa]n\s*tr[ăa]m|%|"
                    r"(?:bao\s*nhi[eê]u|bnhiu|bao\s*nhiu|bn|m[aấ]y|may)\s*(?:đ[oơ]n|ly|chai|h[oộ]p|g[oó]i|s[aả]n\s*ph[aẩ]m|kh[aá]ch|ti[eề]n|h[oó]a\s*đ[oơ]n|kg|kilo|g|gram|t[aấ]n|tan|m[eé]t|met|m3|l[ií]t|lit|th[uú]c|h[aà]ng|m[oó]n|đ[iĩ]a|vi[eê]n)",
                    q_low,
                ))
                is_pure_count = bool(re.search(r"đ[eế]m|s[oố]\s*đ[oơ]n|đ[oơ]n\s*(?:h[uủ]y|hu[yỷ])|m[aấ]y\s*đ[oơ]n|m[aấ]y\s*đ[oợ]t|s[oố]\s*đ[oợ]t|bao\s*nhi[eê]u\s*(?:đ[oơ]n|đ[oợ]t|bill)|m[aặ]t\s*h[aà]ng\s*[eế]|kh[oô]ng\s*ai\s*mua|b[aá]n\s*(?:ko|kh[oô]ng)\s*(?:đc|được|dc)", q_low))
                if penalize_zero_revenue_qty and is_rev_qty_avg and not is_change_or_profit and not is_pure_count:
                    # Hạ C xuống dưới ngưỡng 0.50 khi kết quả = 0 trên câu hỏi doanh thu / số lượng / trung bình
                    return 0.20
                plausibility_score = 0.30
    elif ans_type == "list":
        if not ans_val or len(ans_val) == 0:
            return 0.0
        elif len(ans_val) > 50:
            plausibility_score = 0.20
    elif ans_type == "table":
        rows = ans_val.get("rows", []) if isinstance(ans_val, dict) else []
        if not rows:
            return 0.0
    elif ans_type == "string":
        if not ans_val or str(ans_val).strip() == "":
            return 0.0

    # 3. Điểm cấu trúc mã nguồn (Code Structure Score) - Tối đa 0.25
    code_score = 0.25
    if not code_text or "def solution" not in code_text:
        code_score = 0.0
    else:
        if "return" not in code_text:
            code_score = 0.0
        if len(code_text) < 50:
            code_score = 0.10
        elif len(code_text) > 4000:
            code_score = 0.15

    # 4. Trừ điểm phạt Grounding (Grounding Penalties)
    # Bước 6: Nếu câu hỏi hỏi đích danh thực thể cụ thể mà không tìm thấy thực thể trong CSDL (entity_matches rỗng) -> hạ C để abstain
    if entity_matches is not None and len(entity_matches) == 0 and question:
        is_named_entity_q = bool(re.search(r"\b(?:ti[eề]n\s*b[aá]n|b[aá]n\s*m[aặ]t\s*h[aà]ng|m[aặ]t\s*h[aà]ng|s[aả]n\s*ph[aẩ]m|m[oó]n|thu[oố]c|gas)\s+([a-zà-ỹ0-9\s]+)", q_low))
        is_generic = any(k in q_low for k in ["tổng", "toàn bộ", "mỗi đơn", "trung bình", "nào", "gì", "nhất", "hôm nay", "hôm qua", "bữa qua"])
        if is_named_entity_q and not is_generic and (ans_val in (0, 0.0, None) or not sanity_passed):
            return 0.20

    if grounding_eval is None and (entity_matches or temporal_info or allowed_tables):
        grounding_eval = evaluate_grounding_coverage(
            code_text=code_text,
            question=question,
            entity_matches=entity_matches,
            temporal_info=temporal_info,
            allowed_tables=allowed_tables,
        )

    total_penalty = grounding_eval.get("total_penalty", 0.0) if grounding_eval else 0.0
    aod_str = str(temporal_info.get("as_of_date", "")) if isinstance(temporal_info, dict) else None
    sem_eval = evaluate_semantic_rule_compliance(
        code_text=code_text,
        question=question,
        sub_ans=sub_ans,
        as_of_date=aod_str,
    )
    sem_penalty = sem_eval.get("semantic_penalty", 0.0)

    raw_confidence = exec_score + plausibility_score + code_score - total_penalty - sem_penalty
    total_confidence = round(min(1.0, max(0.0, raw_confidence)), 4)
    return total_confidence


# ==============================================================================
# HÀM ÁP DỤNG CỔNG TỪ CHỐI (ABSTENTION GATE ENFORCEMENT)
# ==============================================================================

def apply_abstention_gate(
    sub_ans: Dict[str, Any],
    confidence: float,
    threshold: float = 0.50,
    unanswerable_source: str = "none",
) -> Tuple[Dict[str, Any], bool]:
    """
    Áp dụng cổng từ chối theo ngưỡng tau*:
    - Kiểu 'unanswerable' CHỈ được phép nộp nếu do Feasibility Gate phát hiện (source == 'gate').
      Nếu do mô hình tự sinh (source == 'model') khi gate đã cho qua -> ÉP THÀNH 'abstain' để tránh bị phạt -1!
    - Nếu confidence < threshold: Chuyển đáp án thành {"type": "abstain", "answer": None}.
    - Trả về tuple: (final_answer, is_abstained).
    """
    ans_type = sub_ans.get("type")
    source = sub_ans.get("unanswerable_source") or unanswerable_source

    if ans_type == "unanswerable":
        if source == "gate":
            return sub_ans, False
        # Mô hình tự sinh unanswerable khi Feasibility Gate đã pass -> ép thành abstain
        return {
            "type": "abstain",
            "answer": None,
            "unanswerable_source": source,
            "reason": "Overridden model unanswerable: Feasibility Gate passed",
        }, True

    if ans_type == "abstain":
        return sub_ans, False

    if confidence < threshold:
        return {
            "type": "abstain",
            "answer": None,
            "unanswerable_source": source,
            "reason": f"Confidence {confidence:.2f} < threshold {threshold:.2f}",
        }, True

    return sub_ans, False


# ==============================================================================
# QUÉT TÌM NGƯỠNG TAU* TỐI ƯU TRÊN TẬP VALIDATION (GRID SEARCH TAU)
# ==============================================================================

def find_optimal_threshold(
    eval_predictions: List[Dict[str, Any]],
    eval_ground_truth: List[Dict[str, Any]],
    threshold_candidates: Optional[List[float]] = None,
) -> Tuple[float, float]:
    """
    Quét tìm ngưỡng tau* tối ưu trên tập validation để tối đa hóa Penalized Accuracy (PA).
    
    Công thức PA:
        PA(tau) = (Correct(tau) - Incorrect(tau)) / Total
    """
    if threshold_candidates is None:
        threshold_candidates = [round(x * 0.05, 2) for x in range(4, 17)]  # 0.20 -> 0.80

    truth_map = {item["id"]: item for item in eval_ground_truth}
    total = len(eval_ground_truth)
    if total == 0:
        return 0.50, 0.0

    best_tau = 0.50
    best_pa = -1.0

    for tau in threshold_candidates:
        correct = 0
        incorrect = 0

        for pred in eval_predictions:
            qid = pred.get("id")
            gold = truth_map.get(qid)
            if not gold:
                continue

            conf = pred.get("confidence", 1.0)
            pred_ans = pred.get("answer", {})
            pred_type = pred_ans.get("type")

            # Áp dụng ngưỡng tau
            if conf < tau and pred_type not in ("unanswerable", "abstain"):
                effective_ans = {"type": "abstain", "answer": None}
            else:
                effective_ans = pred_ans

            eff_type = effective_ans.get("type")

            if eff_type == "abstain":
                continue

            gold_type = gold.get("type")
            gold_ans = gold.get("answer")

            if eff_type == gold_type and str(effective_ans.get("answer")) == str(gold_ans):
                correct += 1
            else:
                incorrect += 1

        pa = (correct - incorrect) / total
        if pa > best_pa:
            best_pa = pa
            best_tau = tau

    return best_tau, round(best_pa, 4)


__all__ = [
    "evaluate_grounding_coverage",
    "evaluate_semantic_rule_compliance",
    "cross_verify_dual_execution",
    "compute_confidence_score",
    "apply_abstention_gate",
    "find_optimal_threshold",
    "GENERIC_BUSINESS_STOPWORDS",
]
