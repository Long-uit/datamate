"""
Module: src/datamate/output/abstention.py
Mục đích: Module 6.2 — Calibrated Abstention Gate (Cổng từ chối có hiệu chuẩn).
          Tính toán điểm tin cậy tổng hợp C in [0.0, 1.0] dựa trên các tín hiệu:
          1. Sức khỏe thực thi (Execution Health: số lượt self-correction, runtime ms).
          2. Tính hợp lý của dữ liệu (Data Plausibility: sanity check, giá trị biên, tỷ lệ rỗng).
          3. Độ khớp thực thể & quy tắc (Rulebook & Entity Alignment).
          
          Nếu C < tau*, chủ động chuyển đáp án thành 'abstain' (0 điểm) thay vì gửi
          đáp án nghi ngờ để triệt tiêu hoàn toàn rủi ro bị phạt -1 điểm (Penalized Accuracy).

Tác giả: Long (AI Architect & Model Lead)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


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
) -> float:
    """
    Tính điểm độ tin cậy C in [0.0, 1.0] cho một đáp án suy luận.
    
    Trọng số các thành phần:
    - Feasibility pass: Nếu không hợp lệ -> C = 1.0 (cho đáp án unanswerable chuẩn từ Gate)
    - unanswerable_source: CHỈ giữ confidence 1.0 khi source == 'gate'.
      Nếu do mô hình sinh ra (source == 'model') khi gate đã cho qua -> C = 0.0
    - Execution health (0.4): Lỗi thực thi -> 0.0; Không lỗi lượt 1 -> 1.0; Sau retry -> 0.75
    - Sanity check (0.35): Pass -> 1.0; Fail -> 0.0
    - Code quality & Completeness (0.25): Có return hợp lệ, độ dài code hợp lý, không import cấm
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
        # Nếu code quá ngắn (< 50 ký tự) hoặc quá dài (> 4000 ký tự)
        if len(code_text) < 50:
            code_score = 0.10
        elif len(code_text) > 4000:
            code_score = 0.15

    total_confidence = round(exec_score + plausibility_score + code_score, 4)
    return min(1.0, max(0.0, total_confidence))


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


def find_optimal_threshold(
    eval_predictions: List[Dict[str, Any]],
    eval_ground_truth: List[Dict[str, Any]],
    threshold_candidates: Optional[List[float]] = None,
) -> Tuple[float, float]:
    """
    Quét tìm ngưỡng tau* tối ưu trên tập validation để tối đa hóa Penalized Accuracy (PA).
    
    Công thức PA:
        PA(tau) = (Correct(tau) - Incorrect(tau)) / Total
    
    Args:
        eval_predictions: Danh sách dự đoán kèm confidence_score.
        eval_ground_truth: Danh sách ground truth.
        threshold_candidates: Danh sách các giá trị ngưỡng cần quét (mặc định 0.20 -> 0.80 bước 0.05).
        
    Returns:
        Tuple[float, float]: (best_threshold, best_pa_score)
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
                # Abstain nhận 0 điểm, không cộng cũng không trừ
                continue

            gold_type = gold.get("type")
            gold_ans = gold.get("answer")

            # Kiểm tra khớp loại và giá trị
            if eff_type == gold_type and str(effective_ans.get("answer")) == str(gold_ans):
                correct += 1
            else:
                incorrect += 1

        pa = (correct - incorrect) / total
        if pa > best_pa:
            best_pa = pa
            best_tau = tau

    return best_tau, round(best_pa, 4)

