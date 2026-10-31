"""
Script: test_models.py
Mục đích: Chạy thử nghiệm mô hình Qwen2.5-Coder-3B-Instruct trên 10 câu hỏi mẫu từ tập train,
          nạp dữ liệu thực tế của từng shop, thực thi code do AI sinh ra, và in bảng so sánh
          chi tiết giữa kết quả dự đoán và đáp án thực tế (Ground Truth).
Tác giả: Long (AI Architect & Model Lead)
"""

import os
import sys
import json
import glob
import time
import sqlite3
import traceback
import pandas as pd

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi Unicode
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được các module trong thư mục src/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from models.prompt_builder import build_prompt, load_rulebook
from models.llm_client import LLMClient


# =====================================================================
# HÀM BỔ TRỢ: NẠP DỮ LIỆU CỦA MỘT DOANH NGHIỆP & TẠO SCHEMA TÓM TẮT
# =====================================================================
def load_business_data(biz_id: str, data_root: str = "competition_data/train/data"):
    """
    Tự động đọc tất cả các file CSV, Excel, SQLite trong thư mục của doanh nghiệp.
    Trả về:
        - data_dict: {tên_bảng: DataFrame}
        - schema_summary: chuỗi tóm tắt cấu trúc cột và kiểu dữ liệu
    """
    biz_dir = os.path.join(data_root, biz_id)
    if not os.path.exists(biz_dir):
        return {}, "Không tìm thấy thư mục dữ liệu."

    data_dict = {}

    # 1. Nạp file CSV
    for csv_file in glob.glob(os.path.join(biz_dir, "*.csv")):
        tbl_name = os.path.splitext(os.path.basename(csv_file))[0]
        try:
            data_dict[tbl_name] = pd.read_csv(csv_file)
        except Exception:
            pass

    # 2. Nạp file Excel (.xlsx) - nạp tất cả các sheet
    for xls_file in glob.glob(os.path.join(biz_dir, "*.xlsx")):
        base_name = os.path.splitext(os.path.basename(xls_file))[0]
        try:
            excel_sheets = pd.read_excel(xls_file, sheet_name=None)
            for sheet_name, df in excel_sheets.items():
                tbl_name = f"{base_name}_{sheet_name}" if len(excel_sheets) > 1 else base_name
                data_dict[tbl_name] = df
        except Exception:
            pass

    # 3. Nạp file SQLite (.sqlite)
    for sql_file in glob.glob(os.path.join(biz_dir, "*.sqlite")):
        try:
            conn = sqlite3.connect(sql_file)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            for (tname,) in cursor.fetchall():
                data_dict[tname] = pd.read_sql_query(f"SELECT * FROM {tname}", conn)
            conn.close()
        except Exception:
            pass

    # Tạo chuỗi mô tả Schema gọn gàng cho LLM
    schema_lines = []
    for tname, df in data_dict.items():
        cols_info = [f"{col} ({df[col].dtype})" for col in df.columns[:15]]
        schema_lines.append(f"- Bảng '{tname}' ({len(df)} dòng): [{', '.join(cols_info)}]")

    schema_summary = "\n".join(schema_lines)
    return data_dict, schema_summary


# =====================================================================
# CHƯƠNG TRÌNH KIỂM THỬ CHÍNH
# =====================================================================
def main():
    print("=" * 80)
    print("KHỞI ĐỘNG BỘ TEST 10 CÂU HỎI MẪU CHO MODEL Qwen2.5-Coder-3B-Instruct")
    print("=" * 80)

    # 1. Khởi tạo LLM Client (4-bit qua bitsandbytes)
    llm = LLMClient()

    # 2. Đọc câu hỏi, đáp án và rulebook của split
    questions_path = "competition_data/train/questions.jsonl"
    answers_path = "competition_data/train/answers.jsonl"
    rulebook_content = load_rulebook("competition_data/train")

    if not os.path.exists(questions_path) or not os.path.exists(answers_path):
        print(f"[LỖI] Không tìm thấy file dữ liệu: {questions_path} hoặc {answers_path}")
        return

    with open(questions_path, "r", encoding="utf-8") as f:
        questions = {q["id"]: q for q in [json.loads(line) for line in f if line.strip()]}

    with open(answers_path, "r", encoding="utf-8") as f:
        answers = {a["id"]: a for a in [json.loads(line) for line in f if line.strip()]}

    # Lấy 10 câu đầu tiên có đáp án
    sample_ids = list(answers.keys())[:10]

    stats = {
        "pass": 0,
        "wrong": 0,
        "runtime_error": 0,
        "no_func": 0
    }

    print(f"\nBắt đầu chạy kiểm thử trên {len(sample_ids)} câu hỏi...\n")

    for idx, qid in enumerate(sample_ids, start=1):
        q = questions[qid]
        gt = answers[qid]
        biz_id = q["business_id"]

        print("\n" + "=" * 80)
        print(f"CÂU HỎI [{idx}/{len(sample_ids)}] - ID: {qid} (Shop: {biz_id})")
        print(f"Nội dung: \"{q['question']}\"")
        print(f"Ngày mốc (as_of_date): {q['as_of_date']}")
        print(f"Đáp án thực tế (Ground Truth): {gt['answer']} (Kiểu: {gt['type']})")
        print("-" * 80)

        # 1. Nạp dữ liệu của shop tương ứng
        data_dict, schema_str = load_business_data(biz_id)
        if not data_dict:
            print("[CẢNH BÁO] Không có dữ liệu DataFrame cho shop này, bỏ qua.")
            continue

        # 2. Tạo Prompt & Gọi Model sinh mã
        start_time = time.time()
        prompt = build_prompt(schema_str, q["as_of_date"], q["question"], rulebook_content=rulebook_content)
        code_text = llm.generate_code(prompt)
        gen_time = round(time.time() - start_time, 2)

        print(f"[1. Mã nguồn do AI sinh ra ({gen_time}s)]:")
        print(code_text)
        print("-" * 40)

        # 3. Thực thi mã nguồn trên RAM qua exec()
        local_scope = {"pd": pd}
        predicted_val = None
        status = "CHƯA XÁC ĐỊNH"

        try:
            exec(code_text, {}, local_scope)

            if "solution" not in local_scope:
                status = "❌ LỖI: Model không định nghĩa hàm 'solution(data)'"
                stats["no_func"] += 1
            else:
                # Gọi hàm solution
                raw_pred = local_scope["solution"](data_dict)
                predicted_val = raw_pred

                # 4. So sánh chi tiết kết quả
                pred_str = str(predicted_val).strip()
                gt_str = str(gt["answer"]).strip()

                if pred_str.lower() == gt_str.lower():
                    status = "✅ CHÍNH XÁC (PASS +1)"
                    stats["pass"] += 1
                else:
                    status = "⚠️ SAI KẾT QUẢ (WRONG -1)"
                    stats["wrong"] += 1

        except Exception as e:
            status = f"💥 LỖI RUNTIME ({type(e).__name__}): {e}"
            stats["runtime_error"] += 1

        # In kết quả chi tiết để kiểm tra
        print(f"[2. Kết quả dự đoán]: {predicted_val} (Kiểu: {type(predicted_val).__name__})")
        print(f"[3. Đáp án thực tế ]: {gt['answer']} (Kiểu: {gt['type']})")
        print(f"[4. Đánh giá        ]: {status}")

    # =====================================================================
    # TỔNG KẾT BÁO CÁO TOÀN DIỆN
    # =====================================================================
    print("\n" + "=" * 80)
    print("TỔNG KẾT KẾT QUẢ KIỂM THỬ 10 CÂU:")
    print(f"  • Đúng (+1 điểm)    : {stats['pass']} câu")
    print(f"  • Sai (-1 điểm)     : {stats['wrong']} câu")
    print(f"  • Lỗi Runtime (crash): {stats['runtime_error']} câu")
    print(f"  • Thiếu hàm solution: {stats['no_func']} câu")
    est_pa = (stats["pass"] - stats["wrong"]) / len(sample_ids)
    print(f"  • Điểm Penalized Accuracy ước lượng: {est_pa:.2f}")
    print("=" * 80)


if __name__ == "__main__":
    main()
