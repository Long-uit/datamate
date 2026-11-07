"""
Script: scripts/inspect_pipeline.py
Mục đích: Công cụ chẩn đoán chuyên sâu từng module (Step-by-step Modular Diagnostic Inspector).
Cho phép:
1. Chọn ngẫu nhiên (--random) hoặc chỉ định 1 doanh nghiệp (--biz) và 1 câu hỏi cụ thể (--id).
2. Chạy tuần tự qua từng module và đo đạc:
   - Module 1: Ingestion & Loader (Thời gian nạp, số bảng, dung lượng RAM)
   - Module 2: Schema Profiler & Data Cleaner (Thời gian làm sạch, trích xuất Schema, danh sách cột)
   - Module 3: Feasibility Gate (Thời gian kiểm tra tính khả thi, phát hiện unanswerable sớm)
   - Module 4: Grounding (Temporal Resolver + Lunar Calendar + Entity Linker)
   - Module 5: Prompt Assembly & Dynamic Few-shot (Phân loại Intent, chọn ví dụ mẫu, kích thước prompt)
   - Module 6: LLM Code Generation (Thời gian sinh mã, số tokens, đoạn code Python)
   - Module 7: Execution Sandbox (Thời gian chạy code, kiểm tra AST, kết quả thô trả về)
   - Module 8: Output Normalizer & Abstention Shield (Chuẩn hóa 8 format, độ tin cậy, quyết định nộp/từ chối)
   - Module 9: So sánh đối chiếu với Expected Output (Gold Answer) & Chấm điểm PA (+1 / -1 / 0)
"""

from __future__ import annotations

import os
import sys
import json
import time
import random
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

# Tự động nạp thư mục src và root vào sys.path
_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = str(_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd
import numpy as np

# Nhập các thành phần module cốt lõi của DataMate
from datamate.config import load_config
from datamate.grounding.temporal import filter_future_data
from datamate.grounding.entity_linker import link_entities
from datamate.grounding.rulebook import load_rulebook
from datamate.llm.feasibility import check_feasibility
from datamate.llm.prompt_builder import classify_intent, build_prompt, resolve_temporal_context
from datamate.llm.few_shot_retriever import retrieve_dynamic_few_shot
from datamate.llm.client import LLMClient
from datamate.output.normalizer import normalize_output, check_result_sanity
from datamate.output.abstention import compute_confidence_score, apply_abstention_gate
from datamate.output.submission import make_abstain

# Nhập các hàm pipeline đã kiểm chứng từ tests/run_eval.py
from tests.run_eval import load_business_data, execute_solution, compare_single_answer


def print_header(title: str, icon: str = "🔷"):
    print("\n" + "=" * 80)
    print(f" {icon}  {title}")
    print("=" * 80)


def print_step(step_num: int, name: str, elapsed_ms: float):
    print(f"\n--- [BƯỚC {step_num}] {name.upper()} (⏱️ {elapsed_ms:.2f} ms) ---")


def main():
    parser = argparse.ArgumentParser(description="Chẩn đoán chuyên sâu từng module DataMate trên 1 câu hỏi cụ thể.")
    parser.add_argument("--data_dir", type=str, default="competition_data/train", help="Thư mục dữ liệu train/public_test")
    parser.add_argument("--biz", type=str, default=None, help="Chỉ định ID doanh nghiệp (ví dụ: biz_128)")
    parser.add_argument("--id", type=str, default=None, help="Chỉ định ID câu hỏi (ví dụ: q_001883280e83)")
    parser.add_argument("--random", action="store_true", help="Chọn ngẫu nhiên 1 câu hỏi từ tập dữ liệu")
    parser.add_argument("--with_llm", action="store_true", help="Kích hoạt nạp mô hình LLM GPU thật để sinh mã")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-Coder-3B-Instruct", help="Tên model LLM")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    questions_file = data_dir / "questions.jsonl"
    answers_file = data_dir / "answers.jsonl"
    data_root = data_dir / "data"

    if not questions_file.exists():
        print(f"❌ Không tìm thấy {questions_file}")
        sys.exit(1)

    with open(questions_file, "r", encoding="utf-8") as f:
        all_questions = [json.loads(line) for line in f if line.strip()]

    gold_answers = {}
    if answers_file.exists():
        with open(answers_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    gold_answers[item["id"]] = item

    # Chọn câu hỏi mục tiêu
    target_q = None
    if args.id:
        target_q = next((q for q in all_questions if q.get("id") == args.id), None)
    elif args.biz:
        biz_qs = [q for q in all_questions if q.get("business_id") == args.biz]
        if biz_qs:
            target_q = random.choice(biz_qs) if args.random else biz_qs[0]
    elif args.random:
        target_q = random.choice(all_questions)
    else:
        target_q = all_questions[0]

    if not target_q:
        print("❌ Không tìm thấy câu hỏi phù hợp với tiêu chí lọc!")
        sys.exit(1)

    qid = target_q["id"]
    biz_id = target_q["business_id"]
    question_text = target_q["question"]
    as_of_date = target_q["as_of_date"]
    gold_record = gold_answers.get(qid)

    print_header("CÔNG CỤ KIỂM THỬ CHẤT LƯỢNG TỪNG MODULE (DATAMATE DIAGNOSTIC INSPECTOR)")
    print(f"• Question ID   : {qid}")
    print(f"• Business ID   : {biz_id}")
    print(f"• as_of_date    : {as_of_date}")
    print(f"• Câu hỏi       : \"{question_text}\"")
    if gold_record:
        print(f"• Expected Gold : {gold_record.get('answer')} (Type: {gold_record.get('type')})")
    print("=" * 80)

    total_pipeline_time_ms = 0.0

    # --------------------------------------------------------------------------
    # BƯỚC 1 & 2: MODULE INGESTION + SCHEMA PROFILER & CLEANER
    # --------------------------------------------------------------------------
    t0 = time.time()
    data_dict, con, schema_str, bd, shop_meta, candidates = load_business_data(biz_id, data_root)
    t1 = time.time()
    ms_ingest_schema = (t1 - t0) * 1000
    total_pipeline_time_ms += ms_ingest_schema

    print_step(1, "Module Ingestion (Nạp đa định dạng) & Module Schema Profiler (Làm sạch & Schema)", ms_ingest_schema)
    print(f"  • Thư mục shop      : {(data_root / biz_id).resolve()}")
    print(f"  • Số bảng đọc được  : {len(bd.tables) if bd else 0} bảng")
    table_summary = [f"{t} ({len(df)} dòng, {len(df.columns)} cột)" for t, df in list(data_dict.items())[:4]]
    print(f"  • Các bảng nạp RAM  : {', '.join(table_summary)}" + (" ..." if len(data_dict) > 4 else ""))
    print(f"  • SQLite in-memory  : {'Đã tạo kết nối' if con else 'Không'}")
    print(f"  • Trích đoạn Schema :\n" + "\n".join(schema_str.splitlines()[:5]) + "\n    ...")

    # --------------------------------------------------------------------------
    # BƯỚC 3: FEASIBILITY GATE (LÁ CHẮN UNANSWERABLE SỚM)
    # --------------------------------------------------------------------------
    t0 = time.time()
    is_feasible, unans_reason = check_feasibility(question_text, as_of_date, shop_meta)
    t1 = time.time()
    ms_feas = (t1 - t0) * 1000
    total_pipeline_time_ms += ms_feas

    print_step(3, "Module Feasibility Gate (Kiểm tra tính khả thi câu hỏi)", ms_feas)
    print(f"  • Khả thi trả lời   : {is_feasible}")
    if not is_feasible:
        print(f"  • Lý do từ chối sớm : {unans_reason}")
        print("  -> ĐÁNH GIÁ: Module bắt trúng câu Unanswerable sớm, tiết kiệm 100% thời gian gọi GPU!")
    else:
        print("  • Đánh giá          : Câu hỏi hợp lệ, tiếp tục chuyển giao cho Grounding & LLM.")

    # --------------------------------------------------------------------------
    # BƯỚC 4: GROUNDING (TEMPORAL RESOLUTION & ENTITY LINKING)
    # --------------------------------------------------------------------------
    t0 = time.time()
    calendar_path = data_dir / "calendar.csv"
    cal_str = str(calendar_path) if calendar_path.exists() else None
    temp_info = resolve_temporal_context(question_text, as_of_date, calendar_path=cal_str)
    entity_matches = link_entities(question_text, candidates=candidates, threshold=0.55) if candidates else []
    t1 = time.time()
    ms_grounding = (t1 - t0) * 1000
    total_pipeline_time_ms += ms_grounding

    print_step(4, "Module Grounding (Định vị mốc thời gian & Đối soát thực thể)", ms_grounding)
    print(f"  • as_of_date        : {temp_info['as_of_date']}")
    print(f"  • Khoảng giải mã    : {temp_info['description']}")
    print(f"  • Gợi ý lọc Pandas  : {temp_info['code_hint']}")
    print(f"  • Tổng thực thể shop: {len(candidates)} ứng viên")
    if entity_matches:
        matches_repr = [f"'{m.matched_value}' (score: {m.score:.2f})" for m in entity_matches[:3]]
        print(f"  • Khớp thực thể     : {', '.join(matches_repr)}")
    else:
        print("  • Khớp thực thể     : Không có thực thể riêng biệt khớp trong câu")

    # --------------------------------------------------------------------------
    # BƯỚC 5: PROMPT BUILDER & INTENT CLASSIFICATION
    # --------------------------------------------------------------------------
    t0 = time.time()
    rulebook_content = load_rulebook(str(data_dir))
    intent = classify_intent(question_text)
    few_shot = retrieve_dynamic_few_shot(question=question_text, intent=intent, entity_matches=entity_matches)
    sys_prompt, user_prompt = build_prompt(
        schema_str=schema_str,
        as_of_date=as_of_date,
        question=question_text,
        rulebook_content=rulebook_content,
        business_note=getattr(bd, "readme_text", None) if bd else None,
        candidates=candidates,
        entity_matches=entity_matches,
        return_messages=True
    )
    t1 = time.time()
    ms_prompt = (t1 - t0) * 1000
    total_pipeline_time_ms += ms_prompt

    print_step(5, "Module LLM Prompt Assembly & Few-Shot (Phân loại ý định & Dựng Prompt)", ms_prompt)
    print(f"  • Ý định (Intent)   : '{intent}'")
    print(f"  • Ví dụ Few-Shot    : {few_shot.splitlines()[0] if few_shot else 'Không'}")
    print(f"  • Độ dài User Prompt: {len(user_prompt)} ký tự (~{len(user_prompt)//4} tokens)")

    # --------------------------------------------------------------------------
    # BƯỚC 6: LLM CODE GENERATION
    # --------------------------------------------------------------------------
    code_text = ""
    gen_time_s = 0.0
    if not is_feasible:
        code_text = '# Feasibility Gate detected unanswerable\ndef solution(data):\n    return "unanswerable"'
        print_step(6, "Module LLM Code Generation (Bỏ qua vì câu Unanswerable)", 0.0)
    elif args.with_llm:
        print_step(6, "Module LLM Code Generation (Sinh mã qua Qwen2.5-Coder GPU)", 0.0)
        print(f"  • Đang nạp mô hình {args.model_id} (4-bit NF4)...")
        t0 = time.time()
        client = LLMClient(model_id=args.model_id, auto_load=True)
        code_text = client.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=512)
        gen_time_s = time.time() - t0
        total_pipeline_time_ms += gen_time_s * 1000
        print(f"  • Thời gian sinh mã : {gen_time_s:.2f} giây")
    else:
        print_step(6, "Module LLM Code Generation (Chế độ Dry-Run: Bỏ qua nạp GPU)", 0.0)
        print("  💡 Muốn chạy sinh mã LLM thật, hãy thêm cờ: --with_llm")
        code_text = 'def solution(data):\n    # Dry run mock placeholder\n    return "abstain"'

    print("\n  [MÃ PYTHON SINH RA]:")
    print("  --------------------------------------------------")
    for line in code_text.strip().splitlines()[:15]:
        print(f"  | {line}")
    if len(code_text.strip().splitlines()) > 15:
        print("  | ... (đã rút gọn)")
    print("  --------------------------------------------------")

    # --------------------------------------------------------------------------
    # BƯỚC 7: EXECUTION SANDBOX
    # --------------------------------------------------------------------------
    t0 = time.time()
    raw_result = None
    exec_err = None
    exec_ms = 0.0

    if not is_feasible:
        raw_result = "unanswerable"
    elif args.with_llm:
        raw_result, exec_err, exec_ms = execute_solution(
            code_text=code_text,
            biz_dir=data_root / biz_id,
            data_dict=data_dict,
            con=con,
            business_obj=bd,
            timeout_s=30,
            use_sandbox=True,
        )
    else:
        raw_result = "abstain"
        exec_ms = 1.0

    t1 = time.time()
    ms_sandbox = (t1 - t0) * 1000
    total_pipeline_time_ms += ms_sandbox

    print_step(7, "Module Execution Sandbox (Thực thi mã an toàn trong Subprocess)", ms_sandbox)
    print(f"  • Thời gian chạy code: {exec_ms:.2f} ms")
    print(f"  • Lỗi Sandbox (nếu)  : {exec_err or 'Không có (Thực thi thành công)'}")
    print(f"  • Kết quả thô (Raw)  : {raw_result} (Kiểu: {type(raw_result).__name__})")

    # --------------------------------------------------------------------------
    # BƯỚC 8: OUTPUT NORMALIZER & ABSTENTION SHIELD
    # --------------------------------------------------------------------------
    t0 = time.time()
    if not args.with_llm and is_feasible:
        final_ans = make_abstain("Dry Run Mock")
        confidence = 0.0
    elif exec_err:
        final_ans = make_abstain(f"Execution Error: {exec_err}")
        confidence = 0.0
    elif not is_feasible:
        final_ans = {"type": "unanswerable", "answer": None}
        confidence = 1.0
    else:
        norm_cand = normalize_output(raw_result, question=question_text, code_text=code_text)
        is_sane, sanity_reason = check_result_sanity(norm_cand, question=question_text, code_text=code_text)
        if not is_sane:
            final_ans = make_abstain(f"Sanity Check Failed: {sanity_reason}")
            confidence = 0.0
        else:
            confidence = compute_confidence_score(
                sub_ans=norm_cand,
                exec_error=exec_err,
                exec_ms=int(exec_ms),
                retry_count=0,
                sanity_passed=True,
                sanity_error=None,
                code_text=code_text,
                has_feasibility_pass=is_feasible,
            )
            final_ans, is_abs = apply_abstention_gate(norm_cand, confidence=confidence, threshold=0.50)

    t1 = time.time()
    ms_output = (t1 - t0) * 1000
    total_pipeline_time_ms += ms_output

    print_step(8, "Module Output Normalizer & Abstention Shield (Chuẩn hóa & Phòng thủ)", ms_output)
    print(f"  • Độ tin cậy C       : {confidence:.2f} (Ngưỡng tau*: 0.50)")
    print(f"  • Output cuối cùng   : {json.dumps(final_ans, ensure_ascii=False)}")

    # --------------------------------------------------------------------------
    # BƯỚC 9: SO SÁNH VỚI EXPECTED OUTPUT & CHẤM ĐIỂM PA
    # --------------------------------------------------------------------------
    print_header("TỔNG KẾT & SO KHỚP VỚI ĐÁP ÁN CHUẨN (EVALUATION)", "🎯")
    print(f"• DỰ ĐOÁN (PREDICTION): {final_ans.get('answer')} (Type: {final_ans.get('type')})")

    if gold_record:
        g_ans = gold_record.get("answer")
        g_type = gold_record.get("type")
        print(f"• CHUẨN   (GOLD TRUTH): {g_ans} (Type: {g_type})")

        is_match = compare_single_answer(final_ans, gold_record)
        pred_type = final_ans.get("type")

        if pred_type == "abstain":
            status = "🟡 TỪ CHỐI TRẢ LỜI (ABSTAIN) -> ĐIỂM PA: 0.0 (Bảo toàn điểm, không bị phạt)"
        elif is_match:
            status = "🟢 HOÀN TOÀN TRÙNG KHỚP (CORRECT) -> ĐIỂM PA: +1.0 (Ăn trọn điểm)"
        else:
            status = "🔴 SAI LỆCH VỚI ĐÁP ÁN (WRONG) -> ĐIỂM PA: -1.0 (Bị trừ điểm)"

        print(f"\n=> KẾT QUẢ ĐÁNH GIÁ: {status}")
    else:
        print("• Không có đáp án chuẩn trong file answers.jsonl để so sánh.")

    print("\n" + "-" * 80)
    print("BẢNG TỔNG KẾT THỜI GIAN THỰC THI TỪNG MODULE:")
    print("-" * 80)
    print(f"1. Ingestion & Schema Profiler         : {ms_ingest_schema:8.2f} ms")
    print(f"2. Feasibility Gate (Unans Check)      : {ms_feas:8.2f} ms")
    print(f"3. Grounding (Temporal & Entity Link)  : {ms_grounding:8.2f} ms")
    print(f"4. Prompt Assembly & Few-Shot          : {ms_prompt:8.2f} ms")
    if args.with_llm:
        print(f"5. LLM Code Generation (Qwen-3B GPU)   : {gen_time_s*1000:8.2f} ms ({gen_time_s:.2f} s)")
    else:
        print(f"5. LLM Code Generation (Dry-Run Mock)  :     0.00 ms")
    print(f"6. Execution Sandbox Subprocess        : {ms_sandbox:8.2f} ms")
    print(f"7. Output Normalizer & Abstention Gate : {ms_output:8.2f} ms")
    print("-" * 80)
    print(f"👉 TỔNG THỜI GIAN TOÀN TRÌNH (END-TO-END) : {total_pipeline_time_ms:8.2f} ms ({total_pipeline_time_ms/1000:.2f} s)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
