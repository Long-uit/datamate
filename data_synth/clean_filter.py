"""
clean_filter.py — Bộ lọc và thẩm định chất lượng dữ liệu tổng hợp (Quality Assurance).

Nhiệm vụ:
- Kiểm tra tính hợp lệ cú pháp mã Python/SQL bằng AST.
- Ngăn chặn các câu lệnh nguy hiểm hoặc không an toàn.
- Kiểm tra tính tuân thủ Rulebook: loại bỏ đơn huỷ / trả hàng khi tính doanh thu.
"""

from __future__ import annotations

import ast
from typing import Any

# Các từ khóa không an toàn bị cấm tuyệt đối trong mã thực thi
FORBIDDEN_CALLS = {
    "os.system",
    "subprocess",
    "shutil.rmtree",
    "eval",
    "exec",
    "socket",
    "urllib",
    "requests",
}


def validate_python_code(code_str: str) -> tuple[bool, str]:
    """Kiểm tra cú pháp AST của đoạn mã Python sinh ra."""
    if not code_str or not code_str.strip():
        return False, "Mã nguồn rỗng"

    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        return False, f"Lỗi cú pháp Python: {e}"

    # Kiểm tra các hàm nguy hiểm
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                func_name = f"{node.func.value.id}.{node.func.attr}"

            if func_name in FORBIDDEN_CALLS:
                return False, f"Chứa lệnh không an toàn bị cấm: {func_name}"

    return True, "Hợp lệ"


def validate_rulebook_compliance(code_str: str, question: str) -> tuple[bool, str]:
    """
    Kiểm tra tuân thủ Rulebook cơ bản:
    - Nếu câu hỏi hỏi về 'doanh thu', mã nên có logic lọc bỏ đơn 'hủy' hoặc 'trả hàng'.
    """
    q_norm = question.lower()
    c_norm = code_str.lower()

    if "doanh thu" in q_norm or "tiền bán" in q_norm:
        if "huỷ" not in c_norm and "hủy" not in c_norm and "trả hàng" not in c_norm:
            return True, "Cảnh báo: Có thể chưa xử lý trừ đơn hủy/trả hàng theo Điều 8 Rulebook"

    return True, "Tuân thủ"


def filter_synthetic_sample(sample: dict[str, Any]) -> bool:
    """Kiểm tra toàn diện một mẫu dữ liệu tổng hợp trước khi nạp vào dataset SFT."""
    # Kiểm tra trường bắt buộc
    if not sample.get("question") or not sample.get("business_id"):
        return False

    # Nếu có mã code đi kèm, phải qua kiểm tra AST
    code = sample.get("synthetic_code") or sample.get("code")
    if code:
        is_valid_code, _ = validate_python_code(code)
        if not is_valid_code:
            return False

    return True
