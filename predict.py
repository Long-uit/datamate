"""
Script: predict.py
Mục đích: Pipeline suy luận chính thức (Production Inference Pipeline) cho DataMate (Zalo AI Challenge 2026).
Hoạt động:
1. Đọc danh sách câu hỏi từ questions.jsonl của split kiểm thử (public_test hoặc private_test).
2. Tự động nạp rulebook.md và calendar.csv của split tương ứng.
3. Nạp dữ liệu các doanh nghiệp (CSV, XLSX, SQLite) kèm cơ chế in-memory caching siêu nhanh.
4. Xây dựng prompt kỹ thuật và sinh mã phân tích dữ liệu qua mô hình LLM (Qwen2.5-Coder).
5. Thực thi mã trong môi trường an toàn và chuẩn hóa kết quả về cấu trúc đáp án của Ban Tổ Chức.
6. Ghi trực tiếp ra file submission.jsonl (flush + fsync) kèm file log chi tiết cho từng câu hỏi.
7. Tự động thẩm định tính toàn vẹn và hợp lệ 100% của file nộp bài qua validate_submission.

Tương thích:
- Chạy cục bộ trên máy tính cá nhân (local Windows/Linux/WSL).
- Chạy trong container Docker chính thức của cuộc thi theo quy chế:
  Đọc dữ liệu từ /data, ghi kết quả ra /result/submission.jsonl và logs ra /result/logs/.
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# Đảm bảo hiển thị Unicode tiếng Việt trên console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Nhập các thành phần cốt lõi của package datamate
from datamate.llm.client import LLMClient
from datamate.llm.prompt_builder import build_prompt, load_rulebook, resolve_temporal_context
from datamate.ingestion.loader import load_business, to_sqlite
from datamate.output.submission import (
    to_answer,
    make_abstain,
    SubmissionWriter,
    validate_submission,
)


# ==============================================================================
# BỘ NHỚ ĐỆM DỮ LIỆU CỬA HÀNG (IN-MEMORY CACHE)
# ==============================================================================
_BUSINESS_CACHE: Dict[str, Tuple[Dict[str, pd.DataFrame], Any, str, Any]] = {}


def load_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any]:
    """Nạp dữ liệu sạch của doanh nghiệp và tạo cấu trúc schema summary."""
    biz_dir = data_root / biz_id
    if not biz_dir.exists():
        return {}, None, f"Không tìm thấy thư mục dữ liệu shop tại: {biz_dir}", None

    try:
        bd = load_business(biz_dir)
        con = to_sqlite(bd)
        data_dict: Dict[str, pd.DataFrame] = {}
        schema_lines: List[str] = []

        for ti in bd.tables:
            t_base = Path(ti.fixed_file_name).stem
            t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

            # Đăng ký nhiều alias để code của LLM dễ dàng truy cập
            data_dict[t_name] = ti.df
            if t_base not in data_dict:
                data_dict[t_base] = ti.df
            if ti.table_id:
                data_dict[ti.table_id] = ti.df

            # Trích xuất tối đa 25 cột kèm giá trị mẫu đại diện
            cols_preview = []
            for c in ti.columns[:25]:
                sample_str = ""
                non_null = ti.df[c].dropna()
                if not non_null.empty:
                    val = str(non_null.iloc[0]).strip().replace("\n", " ")
                    if len(val) > 20:
                        val = val[:17] + "..."
                    sample_str = f" (vd: '{val}')"
                cols_preview.append(f"{c}{sample_str}")

            extra_cols_note = f", ... và {len(ti.columns) - 25} cột khác" if len(ti.columns) > 25 else ""
            schema_lines.append(f"- Bảng '{t_name}' ({ti.n_rows} dòng):\n  Cột ({len(ti.columns)}): [{', '.join(cols_preview)}{extra_cols_note}]")

        schema_summary = "\n".join(schema_lines)
        return data_dict, con, schema_summary, bd

    except Exception as exc:
        return {}, None, f"Lỗi nạp dữ liệu: {exc}", None


def get_cached_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any, bool]:
    """Lấy dữ liệu shop từ bộ nhớ đệm RAM nếu đã nạp trước đó."""
    if biz_id in _BUSINESS_CACHE:
        data_dict, con, schema_summary, bd = _BUSINESS_CACHE[biz_id]
        return data_dict, con, schema_summary, bd, True

    data_dict, con, schema_summary, bd = load_business_data(biz_id, data_root)
    _BUSINESS_CACHE[biz_id] = (data_dict, con, schema_summary, bd)
    return data_dict, con, schema_summary, bd, False


# ==============================================================================
# HÀM THỰC THI MÃ NGUỒN AN TOÀN
# ==============================================================================

def execute_solution(code_text: str, data_dict: Dict[str, pd.DataFrame], con: Any, business_obj: Any) -> Tuple[Any, Optional[str], int]:
    """Thực thi hàm solution(data) của mô hình và thu thập kết quả."""
    t_start = time.perf_counter()

    # Bọc adapter để gán kết quả vào FINAL_RESULT
    adapter = """
if 'solution' in globals() and callable(solution):
    _raw_sol = solution(data)
    if _raw_sol == "unanswerable" or (isinstance(_raw_sol, str) and _raw_sol.strip().lower() in ("unanswerable", "không thể trả lời")):
        FINAL_RESULT = {"type": "unanswerable", "answer": None}
    elif _raw_sol is None:
        FINAL_RESULT = {"type": "abstain", "answer": None}
    else:
        FINAL_RESULT = _raw_sol
"""
    executable_code = code_text + "\n" + adapter

    exec_globals = {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "data": data_dict,
        "dfs": data_dict,
        "con": con,
        "business": business_obj,
    }

    try:
        exec(executable_code, exec_globals)
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        if "FINAL_RESULT" in exec_globals:
            return exec_globals["FINAL_RESULT"], None, elapsed_ms
        elif "solution" in exec_globals and callable(exec_globals["solution"]):
            return exec_globals["solution"](data_dict), None, elapsed_ms
        else:
            return None, "NO_RESULT: Không tìm thấy kết quả từ hàm solution", elapsed_ms

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        return None, f"{type(exc).__name__}: {exc}", elapsed_ms


# ==============================================================================
# CHƯƠNG TRÌNH SUY LUẬN CHÍNH (MAIN INFERENCE PIPELINE)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline suy luận và xuất kết quả nộp bài Zalo AI Challenge 2026 (DataMate)."
    )
    # Xác định đường dẫn mặc định: nếu chạy trong Docker (/data tồn tại) thì dùng /data, ngược lại dùng local public_test
    default_data_dir = "/data" if Path("/data").exists() else "competition_data/public_test"
    default_output_file = "/result/submission.jsonl" if Path("/result").exists() else "submission.jsonl"
    default_log_dir = "/result/logs" if Path("/result").exists() else "submission_logs"

    parser.add_argument("--data_dir", type=str, default=default_data_dir, help=f"Thư mục chứa dữ liệu test (mặc định: {default_data_dir})")
    parser.add_argument("--output_file", type=str, default=default_output_file, help=f"Đường dẫn file xuất kết quả (mặc định: {default_output_file})")
    parser.add_argument("--log_dir", type=str, default=default_log_dir, help=f"Thư mục lưu log chi tiết từng câu hỏi (mặc định: {default_log_dir})")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng câu hỏi cần chạy suy luận bằng LLM (mặc định: toàn bộ)")
    parser.add_argument("--biz", type=str, default=None, help="Chỉ chạy câu hỏi thuộc doanh nghiệp cụ thể (ví dụ: biz_201)")
    parser.add_argument("--id", type=str, default=None, help="Chỉ chạy câu hỏi theo ID cụ thể")
    parser.add_argument("--dry_run", action="store_true", help="Chế độ chạy thử: chỉ nạp prompt/schema, không nạp LLM vào GPU")
    parser.add_argument("--no_fill_abstain", action="store_true", help="Không tự động điền 'abstain' cho các câu hỏi còn lại khi dùng --limit")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    questions_path = data_dir / "questions.jsonl"
    data_root = data_dir / "data"

    if not questions_path.exists():
        print(f"[Lỗi] Không tìm thấy tệp câu hỏi tại: {questions_path.resolve()}")
        sys.exit(1)

    # 1. Đọc danh sách toàn bộ câu hỏi
    with open(questions_path, "r", encoding="utf-8") as f:
        all_questions = [json.loads(line) for line in f if line.strip()]

    print("=" * 80)
    print("DATAMATE - PIPELINE SUY LUẬN & XUẤT SUBMISSION (ZALO AI CHALLENGE 2026)")
    print("=" * 80)
    print(f"• Thư mục dữ liệu split : {data_dir.resolve()}")
    print(f"• Tệp câu hỏi đầu vào   : {questions_path.resolve()} (Tổng: {len(all_questions)} câu)")
    print(f"• Tệp nộp bài đầu ra    : {Path(args.output_file).resolve()}")
    print(f"• Thư mục nhật ký (logs): {Path(args.log_dir).resolve()}")

    rulebook_content = load_rulebook(str(data_dir))
    calendar_path = data_dir / "calendar.csv"
    calendar_str = str(calendar_path) if calendar_path.exists() else None

    # Lọc câu hỏi nếu người dùng chỉ định
    target_questions = all_questions
    if args.biz:
        target_questions = [q for q in target_questions if q.get("business_id") == args.biz]
        print(f"• Lọc theo doanh nghiệp : {args.biz} ({len(target_questions)} câu)")
    if args.id:
        target_questions = [q for q in target_questions if q.get("id") == args.id]
        print(f"• Lọc theo Question ID  : {args.id} ({len(target_questions)} câu)")

    total_target = len(target_questions)
    active_limit = args.limit if args.limit is not None else total_target
    active_questions = target_questions[:active_limit]
    active_qids = {q["id"] for q in active_questions}

    print(f"• Số câu chạy suy luận  : {len(active_questions)} câu")
    if len(active_questions) < len(all_questions) and not args.no_fill_abstain:
        remaining_count = len(all_questions) - len(active_questions)
        print(f"• Tự động điền 'abstain': {remaining_count} câu còn lại (đảm bảo file submission đủ {len(all_questions)} câu chuẩn)")
    print("=" * 80)

    # Khởi tạo mô hình LLM (trừ khi chạy dry-run)
    llm: Optional[LLMClient] = None
    if not args.dry_run:
        print("[Khởi tạo] Đang nạp mô hình Qwen2.5-Coder vào GPU...")
        llm = LLMClient()
        stats_vram = llm.get_gpu_memory_stats()
        print(f"[VRAM] Bộ nhớ GPU đã sử dụng: {stats_vram.get('allocated_gb', 0):.2f} GB")

    # Mở SubmissionWriter
    writer = SubmissionWriter(output_file=args.output_file, log_dir=args.log_dir).open()
    written_count = 0
    t_pipeline_start = time.time()

    try:
        # VÒNG LẶP SUY LUẬN TỪNG CÂU HỎI
        for idx, q in enumerate(active_questions, start=1):
            qid = q["id"]
            biz_id = q["business_id"]
            question_text = q["question"]
            as_of_date = q["as_of_date"]

            print(f"\n[{idx}/{len(active_questions)}] Câu hỏi ID: {qid} (Shop: {biz_id})")
            print(f"Nội dung: \"{question_text}\" | as_of_date: {as_of_date}")

            if args.dry_run:
                print("  [DRY-RUN] Bỏ qua suy luận GPU.")
                sub_ans = make_abstain("Dry Run Mode")
                writer.write(question_id=qid, answer=sub_ans, code="", raw_result=None, error=None, elapsed_ms=0)
                written_count += 1
                continue

            # 1. Nạp dữ liệu doanh nghiệp (In-Memory Cache)
            data_dict, con, schema_str, bd, is_cache = get_cached_business_data(biz_id, data_root)
            cache_note = "Cache Hit" if is_cache else "Nạp mới"
            print(f"  -> Dữ liệu: {len(data_dict)} bảng ({cache_note})")

            if not data_dict:
                print(f"  ⚠️ Cảnh báo: Không nạp được dữ liệu shop {biz_id}. Tự động Abstain.")
                sub_ans = make_abstain(f"Data Not Found: {schema_str}")
                writer.write(question_id=qid, answer=sub_ans, code="", raw_result=None, error=schema_str, elapsed_ms=0)
                written_count += 1
                continue

            # 2. Xây dựng prompt ChatML
            sys_prompt, user_prompt = build_prompt(
                schema_str=schema_str,
                as_of_date=as_of_date,
                question=question_text,
                rulebook_content=rulebook_content,
                return_messages=True
            )

            # 3. Sinh mã phân tích Python qua LLM
            t0 = time.time()
            assert llm is not None
            code_text = llm.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=1024)
            gen_sec = round(time.time() - t0, 2)

            # 4. Thực thi mã nguồn
            raw_result, exec_err, exec_ms = execute_solution(code_text, data_dict, con, bd)

            # 5. Chuẩn hóa kết quả đầu ra
            if exec_err:
                sub_ans = make_abstain(f"Runtime Error: {exec_err}")
                print(f"  ⚠️ Lỗi thực thi ({exec_ms}ms) -> Abstain an toàn: {exec_err}")
            else:
                sub_ans = to_answer(raw_result)
                print(f"  ✓ Sinh mã: {gen_sec}s | Chạy: {exec_ms}ms | Kết quả: {sub_ans.get('answer')} (Type: {sub_ans.get('type')})")

            # 6. Ghi ngay ra file submission.jsonl và logs/<qid>.json
            writer.write(
                question_id=qid,
                answer=sub_ans,
                code=code_text,
                raw_result=raw_result,
                error=exec_err,
                elapsed_ms=int(gen_sec * 1000 + exec_ms),
            )
            written_count += 1

        # NẾU CÒN CÂU HỎI CHƯA CHẠY -> ĐIỀN ABSTAIN AN TOÀN (0 ĐIỂM)
        if not args.no_fill_abstain:
            for q in all_questions:
                if q["id"] not in active_qids:
                    abstain_ans = make_abstain("Default Abstain (Not evaluated in batch)")
                    writer.write(
                        question_id=q["id"],
                        answer=abstain_ans,
                        code="",
                        raw_result=None,
                        error=None,
                        elapsed_ms=0,
                    )
                    written_count += 1

    finally:
        writer.close()
        # Đóng toàn bộ SQLite in-memory connections
        for _, con_c, _, _ in _BUSINESS_CACHE.values():
            if con_c:
                try:
                    con_c.close()
                except Exception:
                    pass

    total_time_sec = round(time.time() - t_pipeline_start, 2)
    print("\n" + "=" * 80)
    print("HOÀN THÀNH QUÁ TRÌNH SUY LUẬN & XUẤT SUBMISSION!")
    print(f"• Tổng số câu đã ghi vào submission: {written_count} / {len(all_questions)}")
    print(f"• Tổng thời gian thực thi         : {total_time_sec} giây")
    print(f"• Tệp kết quả                     : {Path(args.output_file).resolve()}")
    print("=" * 80)

    # TỰ ĐỘNG THẨM ĐỊNH TÍNH TOÀN VẸN CỦA FILE SUBMISSION
    print("\n[Thẩm định File Nộp Bài] Đang kiểm tra tính hợp lệ qua validate_submission...")
    val_errors = validate_submission(Path(args.output_file), questions_path)
    if not val_errors:
        print("🎉 XÁC THỰC THÀNH CÔNG: Tệp submission tuân thủ 100% quy chuẩn Ban Tổ Chức (0 lỗi)!")
        print("   Bạn có thể tự tin nộp tệp này lên hệ thống Zalo AI Challenge.")
    else:
        print(f"⚠️ CẢNH BÁO: Phát hiện {len(val_errors)} lỗi định dạng:")
        for err in val_errors[:10]:
            print(f"   - {err}")


if __name__ == "__main__":
    main()
