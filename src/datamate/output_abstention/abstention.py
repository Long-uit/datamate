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
    "tháng", "thang", "năm", "nam", "ngày", "ngay", "tiền", "tien",
    "đơn", "don", "hàng", "hang", "giá", "gia", "tổng", "tong",
    "bán", "ban", "mua", "khách", "khach", "số lượng", "so luong", "sl",
    "doanh thu", "dthu", "lãi", "lai", "hủy", "huy", "trả", "tra",
    "quý", "quy", "hôm nay", "hom nay", "tuần", "tuan", "mặt hàng",
    "mat hang", "sản phẩm", "san pham", "sp", "khách hàng", "khach hang",
    "chi phí", "chi phi", "lợi nhuận", "loi nhuan", "doanh số", "doanh so",
    "cửa hàng", "cua hang", "tiệm", "tiem", "shop", "shop_meta", "đối tượng",
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
            term_clean = term.lower()
            if not term_clean:
                continue
            # Lọc bỏ stopword và từ quá ngắn
            if term_clean in GENERIC_BUSINESS_STOPWORDS or len(term_clean) <= 2:
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
) -> Dict[str, Any]:
    """
    Kiểm tra tính tuân thủ ngữ nghĩa Rulebook của đoạn mã Python sinh ra:
    - Phát hiện nhầm lẫn giữa 'ưa chuộng nhất' (đếm số đơn nunique) và 'bán chạy nhất' (tổng số lượng).
    - Phát hiện nhầm lẫn giữa đếm số đơn ('bao nhiêu đơn') và cộng tiền ('.sum()').
    - Phát hiện thiếu điều kiện lọc khách có >= 3 đơn khi hỏi 'khách sộp nhất'.
    """
    violations: List[str] = []
    semantic_penalty = 0.0
    if not code_text or not question:
        return {"is_compliant": True, "semantic_penalty": 0.0, "violations": []}

    q_low = question.lower()
    clean_c = re.sub(r"#.*", "", code_text).lower()

    # 1. 'Ưa chuộng nhất' bắt buộc dùng nunique() trên mã đơn, không phải sum() doanh thu
    if "ưa chuộng" in q_low or "ua chuong" in _strip_diacritics(q_low):
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
    if asks_order_count and not asks_money:
        has_count_op = any(k in clean_c for k in ["nunique", "len(", ".count(", "shape[0]", "value_counts"])
        if not has_count_op and ".sum()" in clean_c:
            violations.append("Câu hỏi đếm số đơn nhưng code chỉ gọi .sum() mà không đếm mã đơn (.nunique())")
            semantic_penalty += 0.30

    semantic_penalty = round(min(0.45, semantic_penalty), 4)
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
) -> float:
    """
    Tính điểm độ tin cậy C in [0.0, 1.0] có hiệu chuẩn dựa trên sức khỏe thực thi,
    tính hợp lý dữ liệu và mức độ bám sát thực thể / thời gian (Grounding Penalties).
    """
    ans_type = sub_ans.get("type")
    ans_val = sub_ans.get("answer")
    source = sub_ans.get("unanswerable_source") or unanswerable_source

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
    if not sanity_passed:
        plausibility_score = 0.0
    else:
        plausibility_score = 0.35
        # Kiểm tra chi tiết giá trị đáp án
        if ans_type == "number":
            if isinstance(ans_val, (int, float)):
                if math.isnan(ans_val) or math.isinf(ans_val):
                    plausibility_score = 0.0
                elif ans_val == 0:
                    # Số 0 có thể hợp lệ nhưng độ tin cậy thấp hơn một chút nếu là câu hỏi đếm
                    plausibility_score = 0.30
        elif ans_type == "list":
            if not ans_val or len(ans_val) == 0:
                plausibility_score = 0.0
            elif len(ans_val) > 50:
                # Danh sách quá dài bất thường
                plausibility_score = 0.20
        elif ans_type == "table":
            rows = ans_val.get("rows", []) if isinstance(ans_val, dict) else []
            if not rows:
                plausibility_score = 0.0
        elif ans_type == "string":
            if not ans_val or str(ans_val).strip() == "":
                plausibility_score = 0.0

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
    if grounding_eval is None and (entity_matches or temporal_info or allowed_tables):
        grounding_eval = evaluate_grounding_coverage(
            code_text=code_text,
            question=question,
            entity_matches=entity_matches,
            temporal_info=temporal_info,
            allowed_tables=allowed_tables,
        )

    total_penalty = grounding_eval.get("total_penalty", 0.0) if grounding_eval else 0.0
    sem_eval = evaluate_semantic_rule_compliance(code_text=code_text, question=question, sub_ans=sub_ans)
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
