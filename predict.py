"""
Script: predict.py
Mục đích: Pipeline suy luận chính thức (Production Inference Pipeline) cho DataMate (Zalo AI Challenge 2026).
Hoạt động:
1. Đọc danh sách câu hỏi từ questions.jsonl của split kiểm thử (public_test hoặc private_test).
2. Tự động nạp rulebook.md và calendar.csv của split tương ứng.
3. Nạp dữ liệu các doanh nghiệp (CSV, XLSX, SQLite, JSON) kèm cơ chế in-memory caching (bao gồm cả shop_meta).
4. Kiểm tra tính khả thi qua Module 3 (Feasibility Gate) để bắt sớm các câu hỏi 'unanswerable' (+1 điểm, 0s GPU).
5. Xây dựng prompt kỹ thuật (kèm README.md của shop) và sinh mã phân tích dữ liệu qua mô hình LLM (Qwen2.5-Coder-3B).
6. Thực thi mã trong môi trường an toàn; nếu gặp lỗi thực thi (Runtime Error), tự động kích hoạt 1 lượt
   Self-Correction để mô hình tự sửa lỗi trước khi fallback về 'abstain'.
7. Chuẩn hóa kết quả đầu ra qua Module 6 (Format Normalizer & Tie-Breaker) về đúng 8 kiểu đáp án của Ban Tổ Chức.
8. Ghi trực tiếp ra file submission.jsonl (flush + fsync) kèm file log chi tiết cho từng câu hỏi và thẩm định toàn vẹn.

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

# Tự động nạp thư mục src vào sys.path để chạy trực tiếp không cần cài đặt package
_SRC_DIR = str(Path(__file__).resolve().parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Đảm bảo hiển thị Unicode tiếng Việt trên console Windows an toàn tuyệt đối
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class DualLogger:
    """Tự động ghi đồng thời ra màn hình console và tệp log UTF-8 không lo lỗi pipe PowerShell."""
    def __init__(self, filepath: Path | str, mode: str = "a"):
        self.terminal = sys.stdout
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.logfile = open(self.filepath, mode, encoding="utf-8", errors="replace")

    def write(self, message):
        try:
            self.terminal.write(message)
            self.terminal.flush()
        except Exception:
            try:
                self.terminal.buffer.write(message.encode("ascii", errors="replace"))
                self.terminal.buffer.flush()
            except Exception:
                pass
        try:
            self.logfile.write(message)
            self.logfile.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self.terminal.flush()
        except Exception:
            pass
        try:
            self.logfile.flush()
        except Exception:
            pass

    def close(self):
        try:
            self.logfile.close()
        except Exception:
            pass


# Nhập các thành phần cốt lõi của package datamate
from datamate.grounding_feasibility.temporal import (
    filter_future_data,
    resolve_temporal_context,
    format_temporal_for_prompt,
)
from datamate.llm_execution.sandbox import clean_num, clean_date, run_code, RunResult
from datamate.llm_execution.client import LLMClient
from datamate.llm_execution.prompt import (
    build_prompt,
    load_rulebook,
    build_retry_prompt,
    classify_intent,
    prune_schema_by_intent,
)
from datamate.grounding_feasibility.feasibility import check_feasibility, extract_shop_metadata
from datamate.ingestion_schema.loader import load_business, to_sqlite
from datamate.ingestion_schema.schema_profiler import profile_business_schema
from datamate.ingestion_schema.cleaner import clean_business
from datamate.grounding_feasibility.entity_linker import extract_candidates_from_business, link_entities, expand_abbreviations
from datamate.output_abstention.submission import (
    to_answer,
    make_abstain,
    SubmissionWriter,
    validate_submission,
)
from datamate.output_abstention.normalizer import normalize_output, apply_tie_breaker, check_result_sanity
from datamate.output_abstention.abstention import (
    compute_confidence_score,
    apply_abstention_gate,
    evaluate_grounding_coverage,
    evaluate_semantic_rule_compliance,
)


# ==============================================================================
# BỘ NHỚ ĐỆM DỮ LIỆU CỬA HÀNG (IN-MEMORY CACHE)
# ==============================================================================
_BUSINESS_CACHE: Dict[str, Tuple[Dict[str, pd.DataFrame], Any, str, Any, Dict[str, Any], List[Any]]] = {}


def load_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any, Dict[str, Any], List[Any]]:
    """Nạp dữ liệu sạch của doanh nghiệp (áp dụng Rule 8), tạo schema summary, trích xuất shop_meta và candidates."""
    biz_dir = data_root / biz_id
    if not biz_dir.exists():
        return {}, None, f"Không tìm thấy thư mục dữ liệu shop tại: {biz_dir}", None, {}, []

    try:
        raw_bd = load_business(biz_dir)
        # Kích hoạt làm sạch Rule 8 (Group Forward-Fill & Deduplication)
        bd = clean_business(raw_bd)
        con = None  # Tối ưu hóa: LLM 100% dùng Pandas trên data, bỏ nạp kép SQLite để giảm 50% thời gian load & RAM
        data_dict: Dict[str, pd.DataFrame] = {}
        for ti in bd.tables:
            t_base = Path(ti.fixed_file_name).stem if getattr(ti, "fixed_file_name", None) else ti.table_id
            t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

            data_dict[t_name] = ti.df
            if t_base != t_name and t_base not in data_dict:
                data_dict[t_base] = ti.df
            if ti.table_id and ti.table_id not in data_dict:
                data_dict[ti.table_id] = ti.df

        # Sử dụng Rich Schema Profiler hiển thị kiểu dữ liệu, min-max date và giá trị mẫu
        schema_summary = profile_business_schema(bd, max_cols=25)
        shop_meta = extract_shop_metadata(business_obj=bd, data_dict=data_dict)
        candidates = extract_candidates_from_business(bd)
        return data_dict, con, schema_summary, bd, shop_meta, candidates

    except Exception as exc:
        return {}, None, f"Lỗi nạp dữ liệu: {exc}", None, {}, []


def get_cached_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any, Dict[str, Any], List[Any], bool]:
    """Lấy dữ liệu shop, shop_meta và candidates từ bộ nhớ đệm RAM nếu đã nạp trước đó."""
    if biz_id in _BUSINESS_CACHE:
        data_dict, con, schema_summary, bd, shop_meta, candidates = _BUSINESS_CACHE[biz_id]
        return data_dict, con, schema_summary, bd, shop_meta, candidates, True

    data_dict, con, schema_summary, bd, shop_meta, candidates = load_business_data(biz_id, data_root)
    _BUSINESS_CACHE[biz_id] = (data_dict, con, schema_summary, bd, shop_meta, candidates)
    return data_dict, con, schema_summary, bd, shop_meta, candidates, False


# ==============================================================================
# HÀM THỰC THI MÃ NGUỒN AN TOÀN (SANDBOX / SUBPROCESS)
# ==============================================================================

def execute_solution(
    code_text: str,
    biz_dir: Path,
    data_dict: Dict[str, pd.DataFrame],
    con: Any,
    business_obj: Any,
    timeout_s: int = 30,
    use_sandbox: bool = True,
) -> Tuple[Any, Optional[str], int]:
    """
    Thực thi hàm solution(data) qua sandbox subprocess độc lập (cô lập hoàn toàn, có hard timeout),
    hoặc chế độ in-process an toàn (sao chép độc lập để bảo vệ cache).
    """
    adapter = """
if 'FINAL_RESULT' not in globals() and 'solution' in globals() and callable(solution):
    _raw_sol = solution(data)
    if _raw_sol == "unanswerable" or (isinstance(_raw_sol, str) and _raw_sol.strip().lower() in ("unanswerable", "không thể trả lời")):
        FINAL_RESULT = {"type": "unanswerable", "answer": None}
    elif _raw_sol is None:
        FINAL_RESULT = {"type": "abstain", "answer": None}
    else:
        FINAL_RESULT = _raw_sol
"""
    executable_code = code_text.strip() + "\n" + adapter

    if use_sandbox:
        res = run_code(executable_code, business_dir=biz_dir, timeout_s=timeout_s)
        if res.ok:
            return res.final_result, None, res.elapsed_ms
        else:
            return None, res.error or "Lỗi không xác định trong sandbox", res.elapsed_ms

    # Fallback chạy in-process: tạo bản sao tham chiếu để không làm bẩn DataFrame gốc trong cache
    t_start = time.perf_counter()
    isolated_data = {k: v.copy(deep=False) for k, v in data_dict.items()}
    exec_globals = {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "data": isolated_data,
        "dfs": isolated_data,
        "con": con,
        "business": business_obj,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "clean_num": clean_num,
        "clean_date": clean_date,
    }

    try:
        exec(executable_code, exec_globals)
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        if "FINAL_RESULT" in exec_globals:
            return exec_globals["FINAL_RESULT"], None, elapsed_ms
        elif "solution" in exec_globals and callable(exec_globals["solution"]):
            return exec_globals["solution"](isolated_data), None, elapsed_ms
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
    parser.add_argument("--log_file", type=str, default=None, help="Đường dẫn tệp để tự động ghi toàn bộ nhật ký console UTF-8 (thay thế cho Tee-Object)")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-Coder-3B-Instruct", help="Tên hoặc đường dẫn mô hình (mặc định: Qwen/Qwen2.5-Coder-3B-Instruct)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng câu hỏi cần chạy suy luận bằng LLM (mặc định: toàn bộ)")
    parser.add_argument("--biz", type=str, default=None, help="Chỉ chạy câu hỏi thuộc doanh nghiệp cụ thể (ví dụ: biz_201)")
    parser.add_argument("--id", type=str, default=None, help="Chỉ chạy câu hỏi theo ID cụ thể")
    parser.add_argument("--dry_run", action="store_true", help="Chế độ chạy thử: chỉ nạp prompt/schema, không nạp LLM vào GPU")
    parser.add_argument("--no_fill_abstain", action="store_true", help="Không tự động điền 'abstain' cho các câu hỏi còn lại khi dùng --limit")
    parser.add_argument("--resume", action="store_true", help="Tiếp tục chạy từ câu hỏi chưa hoàn thành (bỏ qua các câu đã có trong file submission)")
    parser.add_argument("--tau_star", type=float, default=0.50, help="Ngưỡng độ tin cậy tối ưu tau* để từ chối trả lời (mặc định: 0.50)")
    parser.add_argument("--timeout", type=int, default=30, help="Thời gian chờ tối đa khi chạy code trong sandbox (giây, mặc định: 30)")
    parser.add_argument("--in_process", action="store_true", help="Chạy code trực tiếp trong tiến trình (bảo vệ cache bằng bản sao RAM) thay vì sandbox subprocess")
    args = parser.parse_args()

    # Kích hoạt bộ ghi log song song nội bộ nếu người dùng truyền --log_file
    dual_logger = None
    if args.log_file:
        dual_logger = DualLogger(args.log_file, mode="a" if args.resume else "w")
        sys.stdout = dual_logger

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

    # Xử lý tính năng Resume nếu được kích hoạt
    existing_completed_ids = set()
    output_path = Path(args.output_file)
    write_mode = "w"

    if args.resume and output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f_ex:
                for line in f_ex:
                    if line.strip():
                        item = json.loads(line)
                        if "id" in item:
                            existing_completed_ids.add(item["id"])
            if existing_completed_ids:
                write_mode = "a"
                print(f"• [Resume Mode] Phát hiện {len(existing_completed_ids)} câu đã hoàn thành trước đó trong {output_path.name}.")
        except Exception as exc:
            print(f"⚠️ Không đọc được file cũ để resume: {exc}. Chạy ở chế độ ghi mới.")

    # Lọc bỏ các câu đã hoàn thành nếu resume
    if existing_completed_ids:
        target_questions = [q for q in target_questions if q["id"] not in existing_completed_ids]

    total_target = len(target_questions)
    active_limit = args.limit if args.limit is not None else total_target
    active_questions = target_questions[:active_limit]
    # Gom nhóm các câu hỏi theo shop để tận dụng tối đa RAM Cache và Persistent Sandbox Worker
    active_questions = sorted(active_questions, key=lambda q: (q.get("business_id", ""), q.get("id", "")))
    active_qids = {q["id"] for q in active_questions} | existing_completed_ids

    print(f"• Số câu chạy suy luận  : {len(active_questions)} câu")
    if len(active_questions) < len(all_questions) and not args.no_fill_abstain:
        remaining_count = len(all_questions) - len(active_questions)
        print(f"• Tự động điền 'abstain': {remaining_count} câu còn lại (đảm bảo file submission đủ {len(all_questions)} câu chuẩn)")
    print("=" * 80)

    # Khởi tạo mô hình LLM (trừ khi chạy dry-run)
    llm: Optional[LLMClient] = None
    if not args.dry_run:
        print(f"[Khởi tạo] Đang nạp mô hình {args.model_id} vào GPU...")
        llm = LLMClient(model_id=args.model_id)
        if not llm.is_loaded:
            print("[Lỗi nghiêm trọng] Không thể nạp mô hình vào GPU. Vui lòng kiểm tra lại VRAM hoặc cấu hình.")
            sys.exit(1)
        stats_vram = llm.get_gpu_memory_stats()
        print(f"[VRAM] Bộ nhớ GPU đã sử dụng: {stats_vram.get('allocated_gb', 0):.2f} GB")

    # Mở SubmissionWriter
    writer = SubmissionWriter(output_file=args.output_file, log_dir=args.log_dir, mode=write_mode).open()
    written_count = 0
    t_pipeline_start = time.time()

    try:
        current_biz_id: Optional[str] = None
        # VÒNG LẶP SUY LUẬN TỪNG CÂU HỎI (ĐÃ ĐƯỢC GROUP BY BUSINESS_ID)
        for idx, q in enumerate(active_questions, start=1):
            qid = q["id"]
            biz_id = q["business_id"]
            question_text = q["question"]
            as_of_date = q["as_of_date"]

            # Giải phóng RAM của shop cũ khi đã xử lý xong toàn bộ câu hỏi của shop đó
            if current_biz_id is not None and biz_id != current_biz_id:
                old_entry = _BUSINESS_CACHE.pop(current_biz_id, None)
                if old_entry and old_entry[1] is not None:
                    try:
                        old_entry[1].close()
                    except Exception:
                        pass
            current_biz_id = biz_id

            print(f"\n[{idx}/{len(active_questions)}] Câu hỏi ID: {qid} (Shop: {biz_id})")
            print(f"Nội dung: \"{question_text}\" | as_of_date: {as_of_date}")

            # 1. Nạp dữ liệu doanh nghiệp + shop_meta + candidates (In-Memory Cache)
            data_dict, con, schema_str, bd, shop_meta, candidates, is_cache = get_cached_business_data(biz_id, data_root)
            cache_note = "Cache Hit" if is_cache else "Nạp mới"
            print(f"  -> Dữ liệu: {len(data_dict)} bảng ({cache_note}) | Rule 8: Bật")

            if not data_dict:
                print(f"  ⚠️ Cảnh báo: Không nạp được dữ liệu shop {biz_id}. Tự động Abstain.")
                sub_ans = make_abstain(f"Data Not Found: {schema_str}")
                writer.write(question_id=qid, answer=sub_ans, code="", raw_result=None, error=schema_str, elapsed_ms=0, confidence=0.0)
                written_count += 1
                continue

            # 2. Module 3 — Deterministic Feasibility Gate (Lá chắn chống phạt)
            is_feasible, unans_reason = check_feasibility(question_text, as_of_date, shop_meta)

            if not is_feasible:
                print(f"  🛡️ [Feasibility Gate] Bất khả thi: {unans_reason} -> Trả về 'unanswerable'")
                sub_ans = {"type": "unanswerable", "answer": None}
                writer.write(
                    question_id=qid,
                    answer=sub_ans,
                    code="# Feasibility Gate: Unanswerable detected deterministically",
                    raw_result="unanswerable",
                    error=None,
                    elapsed_ms=0,
                    confidence=1.0,
                )
                written_count += 1
                continue

            if args.dry_run:
                print("  [DRY-RUN] Bỏ qua suy luận GPU.")
                sub_ans = make_abstain("Dry Run Mode")
                writer.write(question_id=qid, answer=sub_ans, code="", raw_result=None, error=None, elapsed_ms=0, confidence=0.0)
                written_count += 1
                continue

            # 3. Entity Linking & Prompt Building (Module 2)
            biz_dir = data_root / biz_id
            normalized_q = expand_abbreviations(question_text)
            intent = classify_intent(normalized_q)
            temporal_res = resolve_temporal_context(normalized_q, as_of_date, calendar_path=calendar_str)
            temporal_text = format_temporal_for_prompt(temporal_res)
            entity_matches = link_entities(question_text, candidates=candidates, threshold=0.55) if candidates else []
            pruned_schema = prune_schema_by_intent(
                schema_str=schema_str,
                intent=intent,
                question=normalized_q,
                entity_matches=entity_matches,
            )
            if entity_matches:
                matched_names = [getattr(m, 'matched_value', str(m)) for m in entity_matches[:3]]
                print(f"  🔍 [Entity Linking] Khớp {len(entity_matches)} thực thể trong CSDL: {matched_names}")
            if temporal_res.get("start_date") or temporal_res.get("end_date"):
                print(f"  ⏳ [Temporal Grounding] Mốc: {temporal_res.get('description', '')}")

            biz_readme = getattr(bd, "readme_text", None) if bd is not None else None
            sys_prompt, user_prompt = build_prompt(
                schema_str=pruned_schema,
                as_of_date=as_of_date,
                question=question_text,
                rulebook_content=rulebook_content,
                business_note=biz_readme,
                candidates=candidates,
                entity_matches=entity_matches,
                return_messages=True
            )

            # 4. Sinh mã phân tích Python qua LLM (Lượt 1)
            t0 = time.time()
            assert llm is not None
            code_text = llm.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=1536)
            gen_sec = round(time.time() - t0, 2)

            # 5. Thực thi mã nguồn (Lượt 1) qua Sandbox / Subprocess
            retry_count = 0
            raw_result, exec_err, exec_ms = execute_solution(
                code_text=code_text,
                biz_dir=biz_dir,
                data_dict=data_dict,
                con=con,
                business_obj=bd,
                timeout_s=args.timeout,
                use_sandbox=not args.in_process,
            )

            # 5.1. Kiểm tra tính hợp lý hậu thực thi (Sanity Check Lượt 1) & Feasibility Authority
            sanity_err = None
            if not exec_err:
                sub_ans_cand = normalize_output(raw_result, question=question_text, code_text=code_text)
                is_sane, sanity_reason = check_result_sanity(sub_ans_cand, question=question_text, code_text=code_text)
                if raw_result == "unanswerable" or sub_ans_cand.get("type") == "unanswerable":
                    sanity_err = "Cơ sở dữ liệu của cửa hàng CÓ ĐẦY ĐỦ số liệu để trả lời câu hỏi này (KHÔNG ĐƯỢC trả về 'unanswerable'!). Hãy kiểm tra lại danh sách bảng và cột để tính toán và trả về kết quả số/danh sách cụ thể."
                    print("  ⚠️ [Feasibility Authority] Phát hiện code trả về unanswerable trên câu hỏi khả thi -> Kích hoạt Self-Correction...")
                elif not is_sane:
                    sanity_err = sanity_reason
                    print(f"  ⚠️ [Sanity Check] Lượt 1 vi phạm ({sanity_reason}) -> Kích hoạt Self-Correction...")
                else:
                    sem_eval1 = evaluate_semantic_rule_compliance(code_text=code_text, question=question_text, sub_ans=sub_ans_cand)
                    if not sem_eval1.get("is_compliant", True):
                        sanity_err = "; ".join(sem_eval1.get("violations", []))
                        print(f"  ⚠️ [Semantic Rule Check] Lượt 1 vi phạm ({sanity_err}) -> Kích hoạt Self-Correction...")

            # Đánh giá độ phủ thực thể & thời gian (Grounding Coverage) ở Lượt 1
            grounding_eval = evaluate_grounding_coverage(
                code_text=code_text,
                question=question_text,
                entity_matches=entity_matches,
                temporal_info=temporal_res,
            )
            missed_mentions = grounding_eval.get("missed_mentions", [])
            should_retry_for_missed = bool(missed_mentions and not exec_err and not sanity_err and grounding_eval.get("entity_coverage", 1.0) < 0.5)

            # 5.2. Cơ chế Runtime Self-Correction (1 lượt tự sửa lỗi nếu gặp ngoại lệ, vi phạm Sanity Check, hoặc bỏ sót thực thể quan trọng)
            if exec_err or sanity_err or should_retry_for_missed:
                retry_count = 1
                if exec_err:
                    err_feedback = exec_err
                elif sanity_err:
                    err_feedback = f"Kết quả tính toán không hợp lý: {sanity_err}"
                else:
                    first_m = missed_mentions[0]
                    err_feedback = f"Mã nguồn chưa lọc theo thực thể được hỏi: '{first_m['term']}' (giá trị thực tế: '{first_m['candidate']}')"
                    print(f"  🔍 [Grounding Feedback] Phát hiện bỏ sót thực thể quan trọng -> Kích hoạt Self-Correction Turn 2...")

                print(f"  🔄 [Self-Correction] Yêu cầu LLM tự sửa mã ({err_feedback})...")
                retry_sys_prompt, retry_user_prompt = build_retry_prompt(
                    question=question_text,
                    failed_code=code_text,
                    error_message=err_feedback,
                    schema_str=pruned_schema,
                    as_of_date=as_of_date,
                    retry_round=1,
                    temporal_text=temporal_text,
                    missed_mentions=missed_mentions,
                )
                t_retry = time.time()
                retry_code = llm.generate_code(prompt=retry_user_prompt, system_prompt=retry_sys_prompt, max_new_tokens=1536)
                gen_sec = round(gen_sec + (time.time() - t_retry), 2)
                raw_retry, err_retry, ms_retry = execute_solution(
                    code_text=retry_code,
                    biz_dir=biz_dir,
                    data_dict=data_dict,
                    con=con,
                    business_obj=bd,
                    timeout_s=args.timeout,
                    use_sandbox=not args.in_process,
                )
                exec_ms += ms_retry
                if not err_retry:
                    code_text = retry_code
                    raw_result = raw_retry
                    exec_err = None
                    sanity_err = None
                    # Kiểm tra lại Sanity Check ở Lượt 2
                    sub_ans_cand2 = normalize_output(raw_result, question=question_text, code_text=code_text)
                    is_sane2, sanity_reason2 = check_result_sanity(sub_ans_cand2, question=question_text, code_text=code_text)
                    if raw_result == "unanswerable" or sub_ans_cand2.get("type") == "unanswerable":
                        sanity_err = "Sau khi thử lại, mô hình vẫn trả về 'unanswerable' trên câu hỏi khả thi."
                        print("  🛡️ [Feasibility Authority] Lượt 2 vẫn trả về unanswerable -> Ép về 'abstain' an toàn (0 điểm)")
                    elif is_sane2:
                        print("  ✓ [Self-Correction] Khắc phục lỗi và thỏa mãn Sanity Check ở lượt 2!")
                    else:
                        sanity_err = sanity_reason2
                        print(f"  🛡️ [Sanity Check] Lượt 2 vẫn vi phạm ({sanity_reason2}) -> Ép về 'abstain' an toàn (0 điểm)")
                else:
                    code_text = retry_code
                    exec_err = err_retry

            # Đánh giá lại Grounding Coverage sau lượt thử lại (nếu có)
            grounding_eval = evaluate_grounding_coverage(
                code_text=code_text,
                question=question_text,
                entity_matches=entity_matches,
                temporal_info=temporal_res,
            )

            # 6. Chuẩn hóa kết quả đầu ra & Đánh giá Calibrated Abstention Gate (Module 6)
            confidence = 0.0
            if exec_err:
                sub_ans = make_abstain(f"Runtime Error: {exec_err}")
                print(f"  ⚠️ Lỗi thực thi ({exec_ms}ms) -> Abstain an toàn: {exec_err}")
            elif sanity_err:
                sub_ans = make_abstain(f"Sanity Check: {sanity_err}")
                print(f"  🛡️ Kết quả vô lý ({sanity_err}) -> Abstain an toàn (0 điểm)")
            else:
                sub_ans = normalize_output(raw_result, question=question_text, code_text=code_text)
                if sub_ans.get("type") == "unanswerable":
                    print(f"  🛡️ [Feasibility Authority Guard] Chặn false unanswerable -> Ép về 'abstain' để tránh bị phạt -1 điểm!")
                    sub_ans = make_abstain("False unanswerable override: Feasibility passed")
                else:
                    confidence = compute_confidence_score(
                        sub_ans=sub_ans,
                        exec_error=exec_err,
                        exec_ms=exec_ms,
                        retry_count=retry_count,
                        sanity_passed=(sanity_err is None),
                        sanity_error=sanity_err,
                        code_text=code_text,
                        has_feasibility_pass=True,
                        grounding_eval=grounding_eval,
                    )
                    sub_ans, is_abstained = apply_abstention_gate(sub_ans, confidence=confidence, threshold=args.tau_star)
                    penalty = grounding_eval.get("total_penalty", 0.0)
                    if penalty > 0:
                        print(f"  🛡️ [Grounding Penalty] -{penalty:.2f} (Entity Coverage: {grounding_eval.get('entity_coverage', 1.0)*100:.0f}%, Time Coverage: {grounding_eval.get('temporal_coverage', 1.0)*100:.0f}%)")
                    if is_abstained:
                        print(f"  🛡️ [Abstention Gate] Độ tin cậy thấp C={confidence:.2f} < tau*={args.tau_star:.2f} -> Chủ động Abstain (0 điểm)")
                    else:
                        print(f"  ✓ Sinh mã: {gen_sec}s | Chạy: {exec_ms}ms | Tin cậy C={confidence:.2f} | Kết quả: {sub_ans.get('answer')} (Type: {sub_ans.get('type')})")

            # 7. Ghi ngay ra file submission.jsonl và logs/<qid>.json
            writer.write(
                question_id=qid,
                answer=sub_ans,
                code=code_text,
                raw_result=raw_result,
                error=exec_err or sanity_err,
                elapsed_ms=int(gen_sec * 1000 + exec_ms),
                confidence=confidence,
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
                        confidence=0.0,
                    )
                    written_count += 1

    finally:
        writer.close()
        if dual_logger:
            sys.stdout = dual_logger.terminal
            dual_logger.close()
        # Đóng toàn bộ SQLite in-memory connections
        for item in _BUSINESS_CACHE.values():
            con_c = item[1]
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
