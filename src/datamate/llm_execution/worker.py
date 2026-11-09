"""
worker.py — Subprocess worker thực thi mã Python/SQL độc lập trong sandbox.

Hỗ trợ 2 chế độ:
1. Persistent Daemon mode (--daemon <biz_dir> <src_dir>):
   - Nạp toàn bộ dữ liệu của shop vào RAM đúng 1 lần duy nhất.
   - Giữ tiến trình sống và thực thi liên tục các đoạn code qua stdin/stdout.
   - Giải quyết triệt để điểm nghẽn I/O đọc lại tệp Excel/CSV từ đĩa.
2. One-shot mode (Legacy: <code_file> <biz_dir> <result_file> <src_dir>):
   - Tương thích ngược với các lệnh gọi đơn lẻ trước đây.
"""

from __future__ import annotations

import datetime
from datetime import datetime as dt, date, timedelta
import io
import json
import math
import ast
import os
from pathlib import Path
import re
import sys
import traceback
import unicodedata
from typing import Any, Dict

from datamate.llm_execution.sandbox import clean_date, clean_num, sanitize_code_syntax, _strip_accents, _patch_pandas_resilience
_patch_pandas_resilience()


def _norm_col_name(c: Any) -> str:
    s = str(c).strip().lower().replace("đ", "d").replace("Đ", "d")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


COLUMN_CLUSTER_ALIASES: Dict[str, list[str]] = {
    "qty": [
        "số lượng", "soluong", "so_luong", "sl", "sl nhập", "sl bán", "slg",
        "khối lượng", "khoiluong", "trọng lượng", "quy đổi", "slquydoi", "sl_ban",
        "số lượng bán", "sl_xuat", "sl tồn"
    ],
    "amt": [
        "thành tiền", "thanhtien", "thanh_tien", "tổng tiền", "tongtien", "tong_tien",
        "tiền bán", "tienban", "tien_ban", "trị giá", "trigia", "tri_gia",
        "doanh thu", "doanhthu", "tiền hàng", "tong tien", "thanh tien"
    ],
    "price": [
        "đơn giá", "dongia", "don_gia", "giá bán", "giaban", "gia_ban",
        "giá lẻ", "giale", "gia_le", "đơn giá bán", "giá mới", "gia_moi",
        "giá niêm yết", "giá nhập", "gianhap"
    ],
    "item": [
        "tên hàng", "tenhang", "ten_hang", "tên món", "tenmon", "ten_mon",
        "sản phẩm", "sanpham", "san_pham", "tên sp", "mặt hàng", "mathang",
        "tên hàng hóa", "tên thuốc", "tenthuoc", "chi tiết hàng", "món", "hàng"
    ],
    "date": [
        "ngày", "ngay", "ngày bán", "ngay_ban", "ngayban", "thời gian",
        "thoigian", "thời gian tạo", "ngày lập", "ngaylap", "ngày tạo",
        "ngày giao hàng", "ngày chở", "date", "created_at"
    ],
    "order_id": [
        "mã đơn", "madon", "ma_don", "mã hoá đơn", "mã hóa đơn", "mahd",
        "mã hd", "mã chứng từ", "machungtu", "mã giao dịch", "magiaodich",
        "mã phiếu", "maphieu", "order_id", "order id", "số phiếu", "mã bill", "mabill",
        "mã đơn hàng"
    ],
    "product_id": [
        "mã hh", "mahh", "ma_hh", "mã sp", "masp", "ma_sp", "mã hàng",
        "mahang", "ma_hang", "mã mặt hàng", "mã sản phẩm", "mã sản phẩm bán",
        "product_id", "sku", "mã món"
    ],
}


def _resolve_col_alias(df: Any, col: Any) -> Any:
    """Tra cứu tên cột tương đương một cách mềm dẻo khi xảy ra KeyError."""
    if not isinstance(col, str) or not hasattr(df, "columns") or col in df.columns:
        return col

    norm_target = _norm_col_name(col)
    if not norm_target:
        return col

    # 1. Khớp chính xác sau khi chuẩn hóa
    for c in df.columns:
        if _norm_col_name(c) == norm_target:
            return c

    # 2. Khớp theo nhóm ngữ nghĩa (cluster)
    target_cluster = None
    for cluster, aliases in COLUMN_CLUSTER_ALIASES.items():
        if any(_norm_col_name(a) == norm_target for a in aliases):
            target_cluster = cluster
            break

    if target_cluster:
        for c in df.columns:
            norm_c = _norm_col_name(c)
            if any(_norm_col_name(a) == norm_c for a in COLUMN_CLUSTER_ALIASES[target_cluster]):
                return c

    # 3. Khớp chuỗi con nếu cả hai chuỗi đều có ít nhất 3 ký tự
    for c in df.columns:
        norm_c = _norm_col_name(c)
        if (norm_target in norm_c or norm_c in norm_target) and len(norm_target) >= 3 and len(norm_c) >= 3:
            return c

    return col


def _patch_pandas_dataframe_resilience():
    """Patch pd.DataFrame.__getitem__ và pd.merge để hỗ trợ column alias và dynamic key merge."""
    import pandas as pd

    # 1. Patch pd.DataFrame.__getitem__
    orig_getitem = getattr(pd.DataFrame, "__getitem__", None)
    if orig_getitem and not getattr(orig_getitem, "_is_alias_resilient", False):
        def _resilient_getitem(self, key):
            try:
                return orig_getitem(self, key)
            except KeyError:
                if isinstance(key, str):
                    resolved = _resolve_col_alias(self, key)
                    if resolved in self.columns and resolved != key:
                        return orig_getitem(self, resolved)
                elif isinstance(key, (list, tuple)):
                    resolved_keys = [_resolve_col_alias(self, k) for k in key]
                    if any(r != k for r, k in zip(resolved_keys, key)):
                        return orig_getitem(self, resolved_keys)
                raise

        _resilient_getitem._is_alias_resilient = True
        try:
            pd.DataFrame.__getitem__ = _resilient_getitem
        except Exception:
            pass

    # 2. Patch pd.merge & pd.DataFrame.merge
    orig_merge = getattr(pd, "merge", None)
    if orig_merge and not getattr(orig_merge, "_is_dynamic_key_resilient", False):
        def _resilient_merge(left, right, how="inner", on=None, left_on=None, right_on=None, *args, **kwargs):
            try:
                if on is not None and hasattr(left, "columns") and hasattr(right, "columns"):
                    if isinstance(on, str):
                        in_left = on in left.columns
                        in_right = on in right.columns
                        if in_left and not in_right:
                            r_col = _resolve_col_alias(right, on)
                            if r_col in right.columns:
                                left_on, right_on, on = on, r_col, None
                        elif in_right and not in_left:
                            l_col = _resolve_col_alias(left, on)
                            if l_col in left.columns:
                                left_on, right_on, on = l_col, on, None
                        elif not in_left and not in_right:
                            l_col = _resolve_col_alias(left, on)
                            r_col = _resolve_col_alias(right, on)
                            if l_col in left.columns and r_col in right.columns:
                                left_on, right_on, on = l_col, r_col, None

                if left_on is not None and isinstance(left_on, str) and hasattr(left, "columns") and left_on not in left.columns:
                    l_col = _resolve_col_alias(left, left_on)
                    if l_col in left.columns:
                        left_on = l_col

                if right_on is not None and isinstance(right_on, str) and hasattr(right, "columns") and right_on not in right.columns:
                    r_col = _resolve_col_alias(right, right_on)
                    if r_col in right.columns:
                        right_on = r_col
            except Exception:
                pass
            return orig_merge(left, right, how=how, on=on, left_on=left_on, right_on=right_on, *args, **kwargs)

        _resilient_merge._is_dynamic_key_resilient = True
        try:
            pd.merge = _resilient_merge
            pd.DataFrame.merge = _resilient_merge
        except Exception:
            pass


_patch_pandas_dataframe_resilience()


def _is_numeric_type_node(type_node: ast.AST) -> bool:
    """Kiểm tra xem node kiểu dữ liệu có phải là numeric (float, int, numpy float/int) hay không."""
    if isinstance(type_node, ast.Name) and type_node.id in ("float", "int"):
        return True
    if isinstance(type_node, ast.Constant) and isinstance(type_node.value, str):
        v = type_node.value.lower()
        if v in ("float", "float64", "float32", "int", "int64", "int32"):
            return True
    if isinstance(type_node, ast.Attribute) and type_node.attr in (
        "float64", "float32", "int64", "int32", "float_", "int_"
    ):
        return True
    return False


HALLUCINATED_PANDAS_METHODS = {
    "sort_values",
    "head",
    "tail",
    "groupby",
    "drop_duplicates",
    "merge_asof",
}


def sanitize_hallucinated_imports(code: str) -> str:
    """
    Phát hiện và loại bỏ các câu lệnh import DataFrame methods từ pandas (ví dụ: 'from pandas import sort_values').
    Nếu dòng chỉ chứa import method ảo, comment out dòng đó.
    Nếu dòng chứa nhiều import kết hợp (ví dụ: 'from pandas import DataFrame, sort_values'), gỡ bỏ method ảo.
    """
    if not code or not isinstance(code, str):
        return code

    lines = code.split("\n")
    cleaned_lines = []
    for line in lines:
        # Khớp: from pandas import ... hoặc from pandas.core... import ...
        m = re.match(r"^(\s*from\s+pandas(?:\.[a-zA-Z0-9_]+)?\s+import\s+)(.+)$", line)
        if m:
            prefix = m.group(1)
            raw_imports = m.group(2)
            parts = [p.strip() for p in raw_imports.split(",") if p.strip()]
            kept = []
            has_hallucinated = False
            for part in parts:
                base_name = part.split(" as ")[0].strip()
                if base_name in HALLUCINATED_PANDAS_METHODS:
                    has_hallucinated = True
                else:
                    kept.append(part)

            if has_hallucinated:
                indent = " " * (len(line) - len(line.lstrip()))
                if not kept:
                    cleaned_lines.append(f"{indent}# [Sanitized hallucinated import stripped]")
                else:
                    cleaned_lines.append(f"{indent}{prefix.strip()} {', '.join(kept)}")
                continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


class _ProtectedDefsTransformer(ast.NodeTransformer):
    """
    Biến đổi AST để:
    1. Ngăn chặn mã do LLM sinh ra định nghĩa đè (shadow) lên các hàm tiện ích toàn cục quan trọng:
       clean_date, clean_num, DataNotFoundError.
    2. Tự động khắc phục lỗi chaining accessor: X.dt.date.dt.<attr> -> X.dt.<attr>.
    3. Gỡ bỏ .dt.date và .dt.date() khi gán vào cột ngày (clean_date, date, ngay) để giữ nguyên kiểu Datetime Series.
    4. Viết lại pd.to_datetime(...) và to_datetime(...) thành clean_date(..., dayfirst=True).
    5. Viết lại .astype(float) và pd.to_numeric(...) thành clean_num(...).
    6. Tự động inject na=False vào .str.contains(...) nếu chưa có tham số na.
    7. Tái cấu trúc phép so sánh chuỗi có toán tử bitwise: df['col'] >= start & df['col'] <= end
       thành: (df['col'] >= start) & (df['col'] <= end).
    8. Tự động bọc clean_num(target) trước khi gọi .sum() hoặc .mean() trên Series/cột.
    9. Gỡ bỏ các import method DataFrame từ pandas (ví dụ: from pandas import sort_values).
    """
    PROTECTED = {
        "clean_date",
        "clean_num",
        "filter_valid_sales",
        "convert_to_base_qty",
        "DataNotFoundError",
        "_resolve_col_alias",
        "_strip_accents",
        "sanitize_code_syntax",
    }

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module in ("pandas", "pd"):
            filtered_names = [alias for alias in node.names if alias.name not in HALLUCINATED_PANDAS_METHODS]
            if not filtered_names:
                pass_node = ast.Pass()
                return ast.copy_location(pass_node, node)
            node.names = filtered_names
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name in self.PROTECTED:
            node.name = f"_shadowed_{node.name}"
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        if node.name in self.PROTECTED:
            node.name = f"_shadowed_{node.name}"
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in self.PROTECTED:
                target.id = f"_shadowed_{target.id}"
            target_str = ast.unparse(target).lower() if hasattr(ast, "unparse") else ""
            if any(k in target_str for k in ["date", "ngay", "ngày"]):
                # Case a: node.value is Attribute (...dt.date)
                if (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr == "date"
                    and isinstance(node.value.value, ast.Attribute)
                    and node.value.value.attr == "dt"
                ):
                    node.value = node.value.value.value
                # Case b: node.value is Call (...dt.date())
                elif (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "date"
                    and isinstance(node.value.func.value, ast.Attribute)
                    and node.value.func.value.attr == "dt"
                ):
                    node.value = node.value.func.value.value
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        self.generic_visit(node)
        # Chuyển đổi biểu thức so sánh chuỗi bị lỗi độ ưu tiên toán tử bitwise:
        # e.g.: df['col'] >= start & df['col'] <= end
        # AST parser sinh ra: node.ops = [GtE(), LtE()], node.comparators = [BinOp(start & df['col']), end]
        if len(node.ops) == 2 and len(node.comparators) == 2:
            comp = node.comparators[0]
            if isinstance(comp, ast.BinOp) and isinstance(comp.op, (ast.BitAnd, ast.BitOr)):
                left_comp = ast.Compare(
                    left=node.left,
                    ops=[node.ops[0]],
                    comparators=[comp.left],
                )
                right_comp = ast.Compare(
                    left=comp.right,
                    ops=[node.ops[1]],
                    comparators=[node.comparators[1]],
                )
                return ast.BinOp(left=left_comp, op=comp.op, right=right_comp)
        return node

    def visit_Attribute(self, node: ast.Attribute):
        self.generic_visit(node)
        if (
            node.attr in ("year", "month", "day", "hour", "minute", "second", "quarter", "dayofweek", "date")
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "dt"
            and isinstance(node.value.value, ast.Attribute)
            and node.value.value.attr == "date"
            and isinstance(node.value.value.value, ast.Attribute)
            and node.value.value.value.attr == "dt"
        ):
            X = node.value.value.value.value
            return ast.Attribute(
                value=ast.Attribute(value=X, attr="dt", ctx=ast.Load()),
                attr=node.attr,
                ctx=node.ctx,
            )
        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)

        # 1. pd.to_datetime / to_datetime -> clean_date(..., dayfirst=True)
        is_to_datetime = False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "to_datetime":
            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("pd", "pandas"):
                is_to_datetime = True
        elif isinstance(node.func, ast.Name) and node.func.id == "to_datetime":
            is_to_datetime = True

        if is_to_datetime and node.args:
            has_dayfirst = any(kw.arg == "dayfirst" for kw in node.keywords)
            new_keywords = list(node.keywords)
            if not has_dayfirst:
                new_keywords.append(ast.keyword(arg="dayfirst", value=ast.Constant(value=True)))
            return ast.Call(
                func=ast.Name(id="clean_date", ctx=ast.Load()),
                args=node.args,
                keywords=new_keywords,
            )

        # 2. pd.to_numeric / to_numeric -> clean_num(...)
        is_to_numeric = False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "to_numeric":
            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("pd", "pandas"):
                is_to_numeric = True
        elif isinstance(node.func, ast.Name) and node.func.id == "to_numeric":
            is_to_numeric = True

        if is_to_numeric and node.args:
            return ast.Call(
                func=ast.Name(id="clean_num", ctx=ast.Load()),
                args=[node.args[0]],
                keywords=[],
            )

        # 3. X.astype(float / int / ...) -> clean_num(X)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "astype":
            if node.args and _is_numeric_type_node(node.args[0]):
                X = node.func.value
                return ast.Call(
                    func=ast.Name(id="clean_num", ctx=ast.Load()),
                    args=[X],
                    keywords=[],
                )

        # 4. float(X) -> clean_num(X)
        if isinstance(node.func, ast.Name) and node.func.id == "float" and len(node.args) == 1:
            return ast.Call(
                func=ast.Name(id="clean_num", ctx=ast.Load()),
                args=[node.args[0]],
                keywords=[],
            )

        # 5. .str.contains(...) -> ensure na=False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "contains":
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "str":
                has_na = any(kw.arg == "na" for kw in node.keywords)
                if not has_na:
                    new_keywords = list(node.keywords)
                    new_keywords.append(ast.keyword(arg="na", value=ast.Constant(value=False)))
                    node.keywords = new_keywords

        # 6. Series String Aggregation: X.sum() / X.mean() -> clean_num(X).sum() / clean_num(X).mean()
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("sum", "mean"):
            target = node.func.value
            is_already_clean_num = (
                isinstance(target, ast.Call)
                and isinstance(target.func, ast.Name)
                and target.func.id == "clean_num"
            )
            if not is_already_clean_num:
                should_wrap = False
                if isinstance(target, ast.Subscript):
                    # Bọc các subscript như df['col'], df[col], df_filtered[qty_col]
                    # Bỏ qua groupby/rolling/resample subscripts
                    if not (
                        isinstance(target.value, ast.Call)
                        and isinstance(target.value.func, ast.Attribute)
                        and target.value.func.attr in ("groupby", "resample", "rolling")
                    ):
                        should_wrap = True
                elif isinstance(target, ast.Attribute):
                    # Bọc các attribute như df.col hoặc df_filtered.amount
                    # Bỏ qua các module như np, pd
                    if not (
                        isinstance(target.value, ast.Name)
                        and target.value.id in ("np", "numpy", "pd", "pandas")
                    ):
                        should_wrap = True

                if should_wrap:
                    node.func.value = ast.Call(
                        func=ast.Name(id="clean_num", ctx=ast.Load()),
                        args=[target],
                        keywords=[],
                    )

        return node



class SmartDataDict(dict):
    """
    Dictionary thông minh hỗ trợ tra cứu bảng dữ liệu mềm dẻo:
    - Không phân biệt chữ hoa, chữ thường.
    - Không phụ thuộc dấu tiếng Việt (NFD/NFC).
    - Tự động bỏ qua phần mở rộng file (.csv, .xlsx).
    - Hỗ trợ khớp mềm (substring match) nếu tên bảng có tiền tố/hậu tố.
    """
    def __init__(self, data_dict: Dict[str, Any]):
        super().__init__(data_dict)
        self._norm_map: Dict[str, str] = {}
        for k in data_dict.keys():
            norm_k = self._normalize(k)
            if norm_k:
                self._norm_map[norm_k] = k

    @staticmethod
    def _normalize(k: Any) -> str:
        s = str(k).strip().lower()
        s = s.replace("đ", "d").replace("Đ", "d")
        s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
        s = re.sub(r"\.(?:csv|xlsx|xls)$", "", s)
        s = re.sub(r"[^a-z0-9]", "", s)
        return s

    def __getitem__(self, key: Any) -> Any:
        if key in self:
            return super().__getitem__(key)
        nk = self._normalize(key)
        if nk in self._norm_map:
            return super().__getitem__(self._norm_map[nk])
        # Khớp mềm nếu một bên chứa bên kia
        for norm_cand, orig_k in self._norm_map.items():
            if nk and (nk in norm_cand or norm_cand in nk):
                return super().__getitem__(orig_k)
        raise KeyError(key)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def _to_json_serializable(val: Any) -> Any:
    """Chuyển đổi các kiểu dữ liệu phong phú (numpy, pandas, datetime) sang JSON chuẩn."""
    if val is None or val is Ellipsis:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int,)):
        return int(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)

    type_str = type(val).__name__
    module_str = type(val).__module__

    if "numpy" in module_str or "pandas" in module_str:
        if hasattr(val, "item"):
            try:
                py_val = val.item()
                return _to_json_serializable(py_val)
            except Exception:
                pass
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if type_str in ("NAType", "NaTType"):
            return None

    if hasattr(val, "isoformat"):
        return val.isoformat()

    if isinstance(val, (list, tuple, set)):
        return [_to_json_serializable(x) for x in val]

    if isinstance(val, dict):
        return {str(k): _to_json_serializable(v) for k, v in val.items()}

    if hasattr(val, "to_dict"):
        try:
            return _to_json_serializable(val.to_dict())
        except Exception:
            pass

    return str(val)


def execute_code_in_env(
    code_str: str,
    data_dict: Dict[str, Any],
    business: Any,
    con: Any,
    pd: Any,
    np: Any,
    apply_tie_breaker: Any,
    filter_future_data: Any,
    clean_num: Any,
    clean_date: Any,
    DataNotFoundError: Any,
) -> Dict[str, Any]:
    """Thực thi mã nguồn an toàn trong môi trường namespace có dữ liệu nạp sẵn."""
    # Tạo bản sao shallow-copy để bảo vệ DataFrame gốc trong RAM và bọc bằng SmartDataDict
    isolated_data = {k: v.copy(deep=False) for k, v in data_dict.items()}
    smart_data = SmartDataDict(isolated_data)

    def _pct(a: Any, b: Any) -> float:
        try:
            fa, fb = float(a), float(b)
            return (fa / fb * 100.0) if fb != 0 else 0.0
        except Exception:
            return 0.0

    from datamate.llm_execution.sandbox import filter_valid_sales, convert_to_base_qty

    namespace = {
        "__builtins__": __builtins__,
        "con": con,
        "dfs": smart_data,
        "data": smart_data,
        "business": business,
        "pd": pd,
        "np": np,
        "re": re,
        "math": math,
        "datetime": datetime,
        "date": date,
        "timedelta": timedelta,
        "pct": _pct,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "filter_valid_sales": filter_valid_sales,
        "convert_to_base_qty": convert_to_base_qty,
        "clean_num": clean_num,
        "clean_date": clean_date,
        "_strip_accents": _strip_accents,
        "DataNotFoundError": DataNotFoundError,
        "_resolve_col_alias": _resolve_col_alias,
    }
    if isinstance(namespace.get("__builtins__"), dict):
        namespace["__builtins__"]["DataNotFoundError"] = DataNotFoundError

    # Bắt stdout của code
    old_stdout = sys.stdout
    captured_stdout = io.StringIO()
    sys.stdout = captured_stdout

    res_payload: Dict[str, Any] = {
        "ok": False,
        "final_result": None,
        "stdout": "",
        "error": None,
        "error_type": None,
        "unanswerable_source": "none",
        "missing_info": None,
    }

    try:
        clean_code_str = sanitize_code_syntax(code_str)
        clean_code_str = sanitize_hallucinated_imports(clean_code_str)
        try:
            tree = ast.parse(clean_code_str)
            transformer = _ProtectedDefsTransformer()
            tree = transformer.visit(tree)
            ast.fix_missing_locations(tree)
            compiled = compile(tree, "<submitted_code>", "exec")
        except SyntaxError:
            compiled = compile(clean_code_str, "<submitted_code>", "exec")

        exec(compiled, namespace)

        # Bảo vệ tuyệt đối các hàm chuẩn của DataMate: không để mã mô hình shadow
        namespace["clean_date"] = clean_date
        namespace["clean_num"] = clean_num
        namespace["DataNotFoundError"] = DataNotFoundError
        if "solution" in namespace and callable(namespace["solution"]):
            sol_fn = namespace["solution"]
            if hasattr(sol_fn, "__globals__"):
                sol_fn.__globals__["clean_date"] = clean_date
                sol_fn.__globals__["clean_num"] = clean_num
                sol_fn.__globals__["DataNotFoundError"] = DataNotFoundError

        if "FINAL_RESULT" not in namespace:
            if "solution" in namespace and callable(namespace["solution"]):
                _raw = namespace["solution"](isolated_data)
                captured = captured_stdout.getvalue()
                # Bắt lỗi âm thầm khi code LLM có try...except Exception và trả về None nhưng in ra lỗi
                if (_raw is None or (isinstance(_raw, str) and not _raw.strip())) and (
                    "Error:" in captured or "Traceback" in captured
                ):
                    res_payload["ok"] = False
                    res_payload["error"] = captured.strip()
                    res_payload["error_type"] = "RuntimeError"
                elif _raw is None or (isinstance(_raw, str) and not _raw.strip()):
                    namespace["FINAL_RESULT"] = {
                        "type": "abstain",
                        "answer": None,
                        "unanswerable_source": "none",
                        "reason": "Solution returned None or empty string",
                    }
                elif _raw == "unanswerable" or (
                    isinstance(_raw, str) and _raw.strip().lower() in ("unanswerable", "không thể trả lời")
                ):
                    namespace["FINAL_RESULT"] = {
                        "type": "unanswerable",
                        "answer": None,
                        "unanswerable_source": "model",
                        "reason": "Model explicitly returned unanswerable string",
                    }
                elif isinstance(_raw, dict) and _raw.get("type") == "unanswerable":
                    src = _raw.get("unanswerable_source", "model")
                    namespace["FINAL_RESULT"] = {
                        "type": "unanswerable",
                        "answer": None,
                        "unanswerable_source": src,
                    }
                else:
                    namespace["FINAL_RESULT"] = _raw
            else:
                res_payload["ok"] = False
                res_payload["error"] = "NO_FINAL_RESULT"
                res_payload["error_type"] = "NoFinalResult"

        if res_payload.get("error") is None and "FINAL_RESULT" in namespace:
            raw_res = namespace["FINAL_RESULT"]
            try:
                clean_res = _to_json_serializable(raw_res)
                json.dumps(clean_res, ensure_ascii=False)
                res_payload["ok"] = True
                res_payload["final_result"] = clean_res
                if isinstance(raw_res, dict):
                    res_payload["unanswerable_source"] = raw_res.get("unanswerable_source", "none")
            except Exception as ser_err:
                res_payload["ok"] = False
                res_payload["error"] = f"CANNOT_SERIALIZE_JSON: {ser_err}"
                res_payload["error_type"] = "SerializationError"

    except DataNotFoundError as dne:
        res_payload["ok"] = False
        res_payload["error_type"] = "DataNotFoundError"
        res_payload["error"] = str(dne)
        res_payload["missing_info"] = str(dne)
    except Exception as exc:
        res_payload["ok"] = False
        err_tb = traceback.format_exc()
        if "DataNotFoundError" in str(exc) or "DataNotFoundError" in err_tb:
            res_payload["error_type"] = "DataNotFoundError"
            res_payload["error"] = str(exc)
            res_payload["missing_info"] = str(exc)
        else:
            res_payload["error_type"] = type(exc).__name__
            res_payload["error"] = err_tb
    finally:
        sys.stdout = old_stdout

    # Lấy stdout tối đa 10_000 ký tự
    stdout_val = captured_stdout.getvalue()
    if len(stdout_val) > 10_000:
        stdout_val = stdout_val[:10_000]
    res_payload["stdout"] = stdout_val

    return res_payload


def _load_shop_context(biz_dir: Path):
    """Nạp và làm sạch dữ liệu shop vào RAM 1 lần duy nhất."""
    import pandas as pd
    import numpy as np
    from datamate.ingestion_schema.loader import load_business
    from datamate.ingestion_schema.cleaner import clean_business
    from datamate.ingestion_schema.sqlite_mirror import get_sqlite_mirror
    from datamate.output_abstention.normalizer import apply_tie_breaker
    from datamate.grounding_feasibility.temporal import filter_future_data
    from datamate.llm_execution.sandbox import clean_num, clean_date
    from datamate.exceptions import DataNotFoundError

    class _LazySQLiteConnection:
        """Tối ưu hóa nạp kép: Không nạp SQLite mặc định. Chỉ dựng SQLite Mirror khi mã thực sự gọi con."""
        def __init__(self, biz_obj):
            self._biz_obj = biz_obj
            self._real_con = None

        def _get(self):
            if self._real_con is None:
                self._real_con = get_sqlite_mirror(self._biz_obj, clean=False, use_cache=True)
            return self._real_con

        def cursor(self, *args, **kwargs):
            return self._get().cursor(*args, **kwargs)

        def execute(self, *args, **kwargs):
            return self._get().execute(*args, **kwargs)

        def close(self):
            if self._real_con is not None:
                try:
                    self._real_con.close()
                except Exception:
                    pass
                self._real_con = None

        def __getattr__(self, item):
            return getattr(self._get(), item)

    raw_business = load_business(biz_dir)
    business = clean_business(raw_business)
    con = _LazySQLiteConnection(business)

    data_dict = {}
    for ti in business.tables:
        t_base = Path(ti.fixed_file_name).stem if getattr(ti, "fixed_file_name", None) else ti.table_id
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base
        data_dict[t_name] = ti.df
        if t_base != t_name and t_base not in data_dict:
            data_dict[t_base] = ti.df
        if ti.table_id and ti.table_id not in data_dict:
            data_dict[ti.table_id] = ti.df

    return {
        "business": business,
        "con": con,
        "data_dict": data_dict,
        "pd": pd,
        "np": np,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "clean_num": clean_num,
        "clean_date": clean_date,
        "DataNotFoundError": DataNotFoundError,
    }


def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    # =========================================================================
    # CHẾ ĐỘ 1: PERSISTENT DAEMON WORKER (Nạp 1 lần, chạy liên tục qua pipe)
    # =========================================================================
    if sys.argv[1] == "--daemon":
        biz_dir = Path(sys.argv[2])
        root_src = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        if root_src and str(root_src) not in sys.path:
            sys.path.insert(0, str(root_src))

        ctx = _load_shop_context(biz_dir)

        # Gửi tín hiệu hoàn tất nạp dữ liệu tới Sandbox runner
        sys.stdout.write("__WORKER_READY__\n")
        sys.stdout.flush()

        # Vòng lặp nhận và thực thi các câu hỏi
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                msg = json.loads(line_str)
            except Exception:
                continue

            cmd = msg.get("cmd")
            if cmd == "quit":
                break
            elif cmd == "run":
                code_text = msg.get("code", "")
                result_payload = execute_code_in_env(
                    code_str=code_text,
                    data_dict=ctx["data_dict"],
                    business=ctx["business"],
                    con=ctx["con"],
                    pd=ctx["pd"],
                    np=ctx["np"],
                    apply_tie_breaker=ctx["apply_tie_breaker"],
                    filter_future_data=ctx["filter_future_data"],
                    clean_num=ctx["clean_num"],
                    clean_date=ctx["clean_date"],
                    DataNotFoundError=ctx["DataNotFoundError"],
                )
                serialized = json.dumps(result_payload, ensure_ascii=False)
                sys.stdout.write(f"__RESULT__:{serialized}\n")
                sys.stdout.flush()

        try:
            if ctx.get("con"):
                ctx["con"].close()
        except Exception:
            pass
        sys.exit(0)

    # =========================================================================
    # CHẾ ĐỘ 2: ONE-SHOT (Tương thích ngược với định dạng đối số cũ)
    # =========================================================================
    code_file = Path(sys.argv[1])
    biz_dir = Path(sys.argv[2])
    result_file = Path(sys.argv[3])
    root_src = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    if root_src and str(root_src) not in sys.path:
        sys.path.insert(0, str(root_src))

    code_str = code_file.read_text(encoding="utf-8")
    ctx = _load_shop_context(biz_dir)

    res_payload = execute_code_in_env(
        code_str=code_str,
        data_dict=ctx["data_dict"],
        business=ctx["business"],
        con=ctx["con"],
        pd=ctx["pd"],
        np=ctx["np"],
        apply_tie_breaker=ctx["apply_tie_breaker"],
        filter_future_data=ctx["filter_future_data"],
        clean_num=ctx["clean_num"],
        clean_date=ctx["clean_date"],
        DataNotFoundError=ctx["DataNotFoundError"],
    )

    try:
        if ctx.get("con"):
            ctx["con"].close()
    except Exception:
        pass

    result_file.write_text(json.dumps(res_payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
