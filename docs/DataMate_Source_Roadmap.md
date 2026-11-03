# DataMate — Lộ trình Source Code theo Phase

> Mục đích: mô tả **cấu trúc source code đích ở cuối mỗi phase** và **những gì thay đổi giữa các phase**, để Long và Phát cùng một bản đồ khi làm song song.
> Phạm vi: từ hiện trạng cuối Phase 1 (01/11/2026) đến bản nộp Docker (16/11/2026).
> Cơ sở: kế hoạch trong `Timeline_and_Contribution.md`, kiến trúc 6 module trong `DataMate_Solution_Architecture.md`, và 5 file mã nguồn Phase 1 (`ingest.py`, `runner.py`, `submission.py`, `llm_client.py`, `prompt_builder.py`).
> Lưu ý: tên file và tên hàm ở Phase 2–4 là **đề xuất**, có thể điều chỉnh khi code thật; ranh giới trách nhiệm và hướng phụ thuộc giữa các module mới là phần cần giữ.

---

## 0. Cách đọc tài liệu

**Ký hiệu trạng thái file**

| Ký hiệu | Ý nghĩa                                                            |
| --------- | -------------------------------------------------------------------- |
| 🆕        | File mới được tạo trong phase này                              |
| ♻️      | File đã có, nội dung được sửa                                |
| ✂️      | File được tách ra từ file khác (hoặc bị cắt bớt vì tách) |
| 📦        | Chỉ di chuyển / đổi tên, không đổi nội dung                 |
| ✅        | Giữ nguyên                                                         |

**Người phụ trách**: `[P]` = Phát, `[L]` = Long, `[P+L]` = làm chung hoặc review chéo.

---

## 1. Tổng quan các phase

| Phase                    | Thời gian     | Trọng tâm                                                                       | Trạng thái mã nguồn khi kết thúc                  | Mục tiêu điểm (PA nội bộ)                                      |
| ------------------------ | -------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------- | -------------------------------------------------------------------- |
| 1. Fast Pipeline         | 31/10 – 02/11 | Thông luồng đầu–cuối, nộp bài lần đầu                                  | Mã phẳng trong `src/`, chạy được, có baseline  | Điểm baseline trên public leaderboard                             |
| Bước 0. Refactor       | 03/11 (sáng)  | Chuyển sang package `datamate`, không đổi hành vi                          | Cấu trúc package, test xanh, output không đổi      | Không đổi so với Phase 1                                         |
| 2. Deterministic Shields | 03/11 – 06/11 | Rule 8, SQLite mirror, Temporal Grounder, Feasibility Gate, Normalizer, Benchmark | Pipeline có lá chắn tất định + bộ đo PA         | ≥ 0.50                                                              |
| 3. Core Enhancement      | 07/11 – 12/11 | Dữ liệu tổng hợp, fine-tune, entity linker, schema nén, tự sửa lỗi        | Có model đã tinh chỉnh + toàn bộ module nâng cao | ≥ 0.70 – 0.80+                                                     |
| 4. Polish & Submit       | 13/11 – 16/11 | Cổng abstain hiệu chuẩn, tái lập, Docker offline                             | Docker chạy được với `--network none`, đã nộp | Giữ nguyên hoặc tăng nhờ abstain; \|PA_up − PA_rerun\| ≤ 0.03 |

### Luồng xử lý một câu hỏi qua các phase

```text
Phase 1:  câu hỏi → load_business → describe_schema → build_prompt → LLM(3B) → run_code
                    → to_answer → SubmissionWriter

Phase 2:  câu hỏi → [nạp + Rule 8 + SQLite mirror + metadata]  (có cache theo business)
                    → [Temporal Grounder → TimeWindow]
                    → [Feasibility Gate] ──không khả thi──→ unanswerable
                    → build_prompt → LLM → run_code → [Normalizer + Rule 9] → Writer

Phase 3:  như Phase 2, thêm: [Entity Linker] + [Schema nén] + [Few-shot động]
                    → LLM(14B đã tinh chỉnh, vLLM) → run_code ──lỗi──→ [Self-Correct ≤ 2 vòng]

Phase 4:  như Phase 3, thêm: [Confidence C] → C < τ* → abstain
                    + seed cố định, log đầy đủ /result/logs, chạy offline trong Docker
```

---

## 2. Nguyên tắc cấu trúc (áp dụng cho mọi phase)

1. **Src-layout**: mã nằm trong `src/datamate/`, cài bằng `pip install -e . --no-deps`; không dùng `sys.path.insert`.
2. **`__init__.py` luôn để trống.** Nếu `llm/__init__.py` import `client.py`, mỗi subprocess của sandbox sẽ nạp `torch` mỗi câu hỏi.
3. **Hướng phụ thuộc một chiều, không vòng:**
   `types` ← `ingestion`, `grounding` ← `gate`, `llm`, `execution` ← `output` ← `pipeline`.
   Module bên trái không được import module bên phải; không module nào import `pipeline`.
4. **Mỗi module có test tương ứng** trong `tests/<module>/test_<tên>.py`.
5. **Không hard-code `business_id` / `question_id`** và không hard-code đáp án (vi phạm luật cuộc thi).
6. **Dữ liệu `/data` chỉ đọc**; file tạm ghi ở nơi khác (`tempfile`, `/tmp`, `/result`).
7. **Inference offline hoàn toàn**: không gọi mạng, không tải model lúc chạy.
8. **Mọi thay đổi phải qua Internal Benchmark** (từ Phase 2). PA không tăng hoặc số câu −1 tăng thì rollback.
9. **Code dev/huấn luyện nằm ngoài package** (`benchmark/`, `training/`, `data_synth/`, `notebooks/`) để không bị đóng vào đường chạy inference.

---

## 3. Hiện trạng cuối Phase 1

```text
datamate/
├── docs/                         # 3 file tài liệu .md
├── logs/                         # nhật ký commit (vd. commit_..._ingest_module...)
├── research/                     # 35 bản tóm tắt bài báo
├── src/
│   ├── eda/                      # code khám phá dữ liệu
│   ├── models/
│   │   ├── __init__.py
│   │   ├── llm_client.py         # LLMClient: Qwen2.5-Coder-3B 4-bit, greedy, trích code
│   │   └── prompt_builder.py     # load_rulebook, build_prompt, few-shot, system prompt
│   ├── ingest.py                 # đọc CSV/Excel/SQLite, to_sqlite, describe_schema
│   ├── runner.py                 # run_code: subprocess + timeout + FINAL_RESULT
│   └── submission.py             # to_answer, SubmissionWriter, validate_submission
├── tests/
│   ├── test_ingest.py
│   ├── test_models.py
│   ├── test_runner.py
│   └── test_submission.py
├── .gitignore
├── Dockerfile                    # trống
├── predict.sh                    # trống
├── train.sh                      # trống
├── README.md
└── requirements.txt              # torch cu121, transformers 4.46.3, bitsandbytes...
```

*(`competition_data/` nằm ngoài git.)*

### Vai trò từng file Phase 1

| File                  | Việc đang làm                                                                                                                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ingest.py`         | Đọc CSV (thử nhiều encoding), Excel (dò header, gộp sheet cùng cấu trúc), SQLite (chỉ đọc); `to_sqlite` nạp bảng vào SQLite RAM; `describe_schema` tạo mô tả cho prompt. Mọi cột là chuỗi |
| `runner.py`         | Chạy code trong subprocess, nạp lại business bằng `ingest`, đặt biến `con`, `dfs`, `business`, `pd`, yêu cầu `FINAL_RESULT`, bắt lỗi/timeout                                                 |
| `submission.py`     | `to_answer` suy luận type tối giản; `SubmissionWriter` ghi JSONL + log theo câu (flush + fsync); `validate_submission` kiểm tra file nộp                                                                |
| `llm_client.py`     | Nạp Qwen2.5-Coder-3B 4-bit bằng transformers, sinh code (T=0), tách khối ```python                                                                                                                              |
| `prompt_builder.py` | Ráp prompt từ system prompt, rulebook của split, few-shot, schema, câu hỏi                                                                                                                                     |

### Nợ kỹ thuật phát hiện được (sẽ xử lý ở các phase sau)

| # | Vấn đề                                                                                                                   | Hậu quả                                                       | Xử lý ở                                         |
| - | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------- |
| 1 | `to_answer` biến chuỗi `"unanswerable"` thành `type: string`                                                       | Mọi câu unanswerable bị chấm sai (−1) thay vì đúng (+1) | Phase 2 — `normalizer.py`                       |
| 2 | Prompt yêu cầu `def solution(data)`, runner đòi `FINAL_RESULT` và có `dfs` khóa `t_01...`                    | Cần đoạn nối (vd. `FINAL_RESULT = solution(dfs)`)         | Phase 2 — `pipeline.py`                         |
| 3 | Mỗi lần `run_code` nạp lại business từ file gốc (Excel bằng openpyxl)                                              | Chậm khi 300K dòng × hàng nghìn câu                       | Phase 2 — SQLite mirror có cache + `worker.py` |
| 4 | Dữ liệu chưa qua Rule 8 (forward-fill, khử trùng)                                                                      | Sai số doanh thu/đếm đơn                                   | Phase 2 — `cleaner.py`                          |
| 5 | `logging.basicConfig` chạy lúc import `ingest.py`; `sys.stdout.reconfigure` chạy lúc import `prompt_builder.py` | Side effect của thư viện                                     | Phase 2 — chuyển lên entry point                |
| 6 | Model id ghi cứng trong `LLMClient`                                                                                      | Khó đổi 3B → 14B                                            | Phase 3 — `config`                              |
| 7 | `requirements.txt` dùng wheel `cu121`                                                                                  | RTX 5090 (Blackwell) cần CUDA ≥ 12.8                          | Phase 4 — `requirements-docker.txt`             |

---

## 4. Bước 0 — Refactor sang package (sáng 03/11, trước khi code Phase 2)

> Nguyên tắc: **chỉ di chuyển, không tách, không đổi logic.** Đảm bảo `submission.jsonl` / output kiểm tra không đổi so với Phase 1, rồi mới bắt đầu Phase 2. Làm trên nhánh `refactor/package-layout`; cả hai bạn tạm dừng commit trong lúc refactor.

### Cấu trúc đích

```text
datamate/
├── pyproject.toml                          🆕
├── requirements.txt                        ✅
├── README.md  .gitignore                   ✅
├── Dockerfile  predict.sh  train.sh        ✅ (vẫn trống)
├── docs/  research/  logs/                 ✅
├── notebooks/eda/                          📦 từ src/eda
├── src/datamate/
│   ├── __init__.py                         🆕 (trống)
│   ├── ingestion/
│   │   ├── __init__.py                     🆕 (trống)
│   │   └── loader.py                       📦 từ ingest.py
│   ├── llm/
│   │   ├── __init__.py                     📦 từ models/__init__.py (trống)
│   │   ├── client.py                       📦 từ models/llm_client.py
│   │   └── prompt_builder.py               📦 từ models/prompt_builder.py
│   ├── execution/
│   │   ├── __init__.py                     🆕 (trống)
│   │   └── sandbox.py                      📦♻️ từ runner.py (sửa 2 chỗ)
│   └── output/
│       ├── __init__.py                     🆕 (trống)
│       └── submission.py                   📦 từ submission.py
└── tests/
    ├── ingestion/test_loader.py            📦 từ test_ingest.py
    ├── llm/test_llm.py                     📦 từ test_models.py
    ├── execution/test_sandbox.py           📦 từ test_runner.py
    └── output/test_submission.py           📦 từ test_submission.py
```

*(mỗi thư mục con của `tests/` có thêm `__init__.py` trống.)*

### Hai chỗ phải sửa trong `sandbox.py`

| Vị trí                             | Cũ                                             | Mới                                                               |
| ------------------------------------ | ----------------------------------------------- | ------------------------------------------------------------------ |
| Chuỗi `_SUBPROCESS_WORKER_SCRIPT` | `from ingest import load_business, to_sqlite` | `from datamate.ingestion.loader import load_business, to_sqlite` |
| Hàm `run_code`                    | `src_dir = Path(__file__).parent.resolve()`   | `src_dir = Path(__file__).resolve().parents[2]`                  |

Import nằm trong **chuỗi**, nên tìm kiếm import thông thường không thấy; nếu bỏ sót, mọi `run_code` lỗi và pipeline trả `abstain` hàng loạt mà không báo rõ.

### Tiêu chí hoàn thành Bước 0

- `pytest -q` xanh, số test pass bằng trước refactor.
- `describe_schema` và kết quả `run_code` mẫu trên 5 business **giống hệt** trước refactor (so sánh file before/after).
- `import datamate.llm` không làm `torch` xuất hiện trong `sys.modules`.
- Không còn `from ingest`, `from runner`, `from models`... sót lại trong repo.

---

## 5. Phase 2 — Deterministic Shields (03/11 – 06/11)

**Mục tiêu:** chặn điểm âm bằng quy tắc tất định; dữ liệu sạch và nhanh; có bộ đo PA để mọi thay đổi sau này đều đo được.

### Cấu trúc cuối Phase 2

```text
datamate/
├── pyproject.toml                          ✅
├── requirements.txt  README.md  .gitignore ✅
├── Dockerfile  predict.sh  train.sh        ✅ (vẫn trống)
├── benchmark/                              🆕 [P+L]
│   ├── split.py                            🆕 [P]   tách 2.400 train / 600 val, lưu danh sách id
│   ├── evaluate.py                         🆕 [P]   chạy pipeline trên val, so với answers.jsonl, tính PA
│   └── report.py                           🆕 [L]   số đúng/sai/abstain, unanswerable đúng, theo loại câu
├── src/datamate/
│   ├── __init__.py                         ✅
│   ├── types.py                            🆕 [P+L] TimeWindow, BusinessMeta, BusinessContext, GateDecision
│   ├── pipeline.py                         🆕 [P+L] điều phối + entry point (python -m datamate.pipeline)
│   ├── ingestion/
│   │   ├── loader.py                       ✂️ [P]   chỉ còn hàm đọc file
│   │   ├── schema.py                       ✂️ [P]   describe_schema (tách khỏi loader)
│   │   ├── cleaner.py                      🆕 [P]   Rule 8: group forward-fill + khử trùng dòng lỗi xuất
│   │   ├── sqlite_mirror.py                🆕 [P]   to_sqlite + index + cache theo business
│   │   └── metadata.py                     🆕 [P]   [min_date, max_date], cột, giá trị phân loại
│   ├── grounding/
│   │   ├── __init__.py                     🆕
│   │   ├── rulebook.py                     ✂️ [P]   load_rulebook (tách khỏi prompt_builder)
│   │   ├── lunar_calendar.py               🆕 [P]   đọc calendar.csv, tra Tết/âm–dương
│   │   └── temporal.py                     🆕 [P]   hôm nay, tuần này/trước, tháng này, N ngày gần nhất, Tết năm Y
│   ├── gate/
│   │   ├── __init__.py                     🆕
│   │   └── feasibility.py                  🆕 [L]   kỳ hỏi hoàn toàn ngoài dữ liệu / thiếu loại thông tin → unanswerable
│   ├── llm/
│   │   ├── client.py                       ✅
│   │   └── prompt_builder.py               ♻️ [L]   dùng rulebook từ grounding; bỏ side effect stdout
│   ├── execution/
│   │   ├── sandbox.py                      ♻️ [P]   dùng mirror đã cache, không nạp lại từ file gốc
│   │   └── worker.py                       ✂️ [P]   worker thành file thật (không còn là chuỗi)
│   └── output/
│       ├── normalizer.py                   🆕✂️ [L] to_answer chuyển sang đây, 8 kiểu đáp án, sửa lỗi "unanswerable"
│       ├── ranking.py                      🆕 [L]   Rule 9: đồng hạng → sắp theo mã code tăng dần
│       └── submission.py                   ♻️ [L]   writer + validate, import helper từ normalizer
├── tests/
│   ├── ingestion/  test_loader.py ✅  test_cleaner.py 🆕  test_sqlite_mirror.py 🆕  test_metadata.py 🆕
│   ├── grounding/  test_rulebook.py 🆕  test_temporal.py 🆕  test_lunar_calendar.py 🆕
│   ├── gate/       test_feasibility.py 🆕
│   ├── llm/        test_llm.py ✅  test_prompt_builder.py 🆕
│   ├── execution/  test_sandbox.py ♻️
│   ├── output/     test_normalizer.py 🆕  test_ranking.py 🆕  test_submission.py ♻️
│   └── benchmark/  test_evaluate.py 🆕
└── notebooks/  docs/  research/  logs/     ✅
```

### Việc cần làm theo từng file

| File                                             | Người | Hạn (kế hoạch) | Nội dung chính                                                                                                                                                                                                                       |
| ------------------------------------------------ | ------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ingestion/cleaner.py`                         | P       | 04/11 18:00       | Forward-fill các cột cấp đơn (mã đơn, ngày, trạng thái, tên khách) khi dòng chi tiết để trống; hai dòng giống hệt trong **cùng một mã đơn** chỉ giữ một, ở hai đơn khác nhau giữ cả hai       |
| `ingestion/sqlite_mirror.py`                   | P       | 04/11 23:59       | Nạp bảng đã làm sạch vào SQLite RAM, index `Mã đơn`, `Ngày`, `SKU`, `Khách hàng`; cache theo business để không nạp lại mỗi câu; mục tiêu < 1 giây / business                                            |
| `ingestion/metadata.py`                        | P       | 05/11 (sớm)      | Trả về khoảng ngày hoạt động, danh sách cột từng bảng, giá trị phân loại; **đầu vào cho Feasibility Gate của Long**                                                                                           |
| `grounding/lunar_calendar.py`, `temporal.py` | P       | 05/11 18:00       | Giải mã thời gian tương đối theo `as_of_date` và rulebook của split; Tết = 23 tháng Chạp → mùng 10 tháng Giêng; lọc bỏ dữ liệu phát sinh sau `as_of_date`                                                     |
| `grounding/rulebook.py`                        | P       | 05/11             | Đọc rulebook của **đúng split** (rulebook có thể khác nhau giữa các split)                                                                                                                                             |
| `gate/feasibility.py`                          | L       | 05/11 23:59       | Nhận `(question, ctx, windows)`; trả `Feasible` hoặc `Unanswerable(reason)` khi kỳ hỏi nằm **hoàn toàn** ngoài dữ liệu; kỳ hỏi chỉ một phần nằm trong dữ liệu thì vẫn tính trên phần có dữ liệu |
| `output/normalizer.py`                         | L       | 06/11 18:00       | Chuẩn hóa 8 kiểu đáp án (tiền VND số nguyên, percent không kèm `%`, date ISO...); chuỗi `"unanswerable"` → `{"type": "unanswerable", "answer": null}`                                                               |
| `output/ranking.py`                            | L       | 06/11 18:00       | Top-K/“…nhất” với đồng hạng sắp theo mã code tăng dần                                                                                                                                                                      |
| `benchmark/*`                                  | P+L     | 06/11 23:59       | Tách 2.400/600, chạy tự động sau mỗi commit, báo cáo chi tiết                                                                                                                                                                 |
| `pipeline.py`                                  | P+L     | 03/11–06/11      | Nối các module; đoạn nối `solution(dfs)` → `FINAL_RESULT`; cấu hình logging ở đây thay vì trong module thư viện                                                                                                      |

### Giao diện (interface) giữa Long và Phát

```text
Phát cung cấp:
  ingestion.metadata.get_metadata(business) -> BusinessMeta(date_range, columns, categories)
  grounding.temporal.resolve(question, as_of_date, calendar) -> list[TimeWindow]

Long nhận và dùng:
  gate.feasibility.check(question, ctx: BusinessContext, windows: list[TimeWindow])
      -> Feasible | Unanswerable(reason)

Long cung cấp:
  output.normalizer.normalize(raw_result, hint) -> Answer(type, answer)
  output.ranking.rank(items, key, k, ascending=False) -> list
```

### Thay đổi so với Bước 0

| Hạng mục                | Trước                                     | Sau                                             |
| ------------------------- | ------------------------------------------- | ----------------------------------------------- |
| Thư mục mới            | —                                          | `grounding/`, `gate/`, `benchmark/`       |
| Dữ liệu vào sandbox    | Nạp thô từ file mỗi câu                | Đã qua Rule 8, nằm trong mirror có cache    |
| `loader.py`             | Đọc + `to_sqlite` + `describe_schema` | Chỉ đọc file                                 |
| `prompt_builder.py`     | Chứa `load_rulebook`                     | Gọi `grounding.rulebook`                     |
| `submission.py`         | Chứa `to_answer`                         | `to_answer` chuyển sang `normalizer.py`    |
| Câu ngoài kỳ dữ liệu | LLM đoán                                  | Gate trả `unanswerable` trước khi gọi LLM |
| Đo chất lượng         | Thủ công                                  | Tự động, 600 câu val, PA                    |

### Tiêu chí nghiệm thu Phase 2

- PA nội bộ trên 600 câu val **≥ 0.50**.
- Nhóm câu `unanswerable` do ngoài kỳ dữ liệu: gate trả đúng 100%.
- Không còn dòng trùng do lỗi xuất file; nạp một business < 1 giây (khi đã cache).
- Báo cáo benchmark xuất được số câu +1, −1, 0 và unanswerable đúng.

---

## 6. Phase 3 — Core Enhancement (07/11 – 12/11)

**Mục tiêu:** nâng chất lượng sinh mã bằng dữ liệu tổng hợp và fine-tune; làm giàu ngữ cảnh (entity, schema nén, few-shot động); tự sửa lỗi. Dành khoảng 60% nguồn lực của cả dự án.

### Cấu trúc cuối Phase 3

```text
datamate/
├── pyproject.toml  README.md  .gitignore   ✅
├── requirements.txt                        ♻️ [L] thêm peft/trl/vllm (dùng khi train/benchmark 14B)
├── Dockerfile  predict.sh                  ✅ (vẫn trống)
├── train.sh                                🆕 [L] gọi training/sft.py (và dpo.py nếu đủ GPU)
├── config/
│   └── default.yaml                        🆕 [P+L] model_id, backend, timeout, đường dẫn, (tau để Phase 4)
├── data_synth/                             🆕 [P]  (code sinh dữ liệu, không đóng vào inference)
│   ├── paraphrase.py                       🆕 teencode, viết tắt ("dthu", "hnay"), không dấu
│   ├── unanswerable_gen.py                 🆕 hỏi ngoài năm, mặt hàng không có, thông tin shop không có
│   ├── tet_variants.py                     🆕 biến thể Tết/lịch âm, đối chiếu calendar.csv
│   ├── build_dataset.py                    🆕 ghép (câu hỏi, ngữ cảnh, code, đáp án)
│   └── clean_filter.py                     🆕 loại mẫu sai đáp án / sai Rulebook trước khi SFT
├── training/                               🆕 [L]
│   ├── sft.py                              🆕
│   ├── dpo.py                              🆕 (tùy tài nguyên: chosen = code ra đúng đáp án, rejected = lỗi/sai)
│   ├── merge_lora.py                       🆕
│   └── configs/                            🆕
├── benchmark/
│   ├── split.py  evaluate.py  report.py    ✅ (evaluate nhận backend/model làm tham số)
│   └── error_analysis.py                   🆕 [P+L] nhóm câu −1 theo nguyên nhân, nhật ký lỗi hàng ngày
├── src/datamate/
│   ├── config.py                           🆕 [P]   đọc config/default.yaml
│   ├── types.py                            ♻️ [P+L] thêm EntityMatch, Candidate
│   ├── pipeline.py                         ♻️ [P+L] chèn entity linking, schema nén, few-shot, self-correct
│   ├── ingestion/                          ✅ (sửa nhỏ nếu phát hiện lỗi dữ liệu mới từ error analysis)
│   ├── grounding/
│   │   └── entity_linker.py                🆕 [P]   BM25 + Jaro-Winkler + bi-gram; size (M)/(L); khách viết tắt
│   ├── gate/
│   │   └── feasibility.py                  ♻️ [L]   thêm: thực thể hỏi không tồn tại trong shop → unanswerable
│   ├── llm/
│   │   ├── client.py                       ♻️ [L]   giữ backend transformers; đọc model từ config
│   │   ├── vllm_client.py                  🆕 [L]   backend vLLM cho model 14B (cùng giao diện generate_code)
│   │   ├── schema_compressor.py            🆕 [L]   chỉ nạp tên cột, kiểu, giá trị phân loại, 3 dòng mẫu
│   │   ├── fewshot_retriever.py            🆕 [L]   chọn 2–3 ví dụ tương đồng thay cho few-shot cố định
│   │   └── prompt_builder.py               ♻️ [L]   nhận schema nén, few-shot động, kết quả entity
│   ├── execution/
│   │   ├── sandbox.py  worker.py           ✅
│   │   └── self_correct.py                 🆕 [L]   bắt traceback → LLM sửa, tối đa 2 vòng
│   └── output/                             ✅ (bổ sung quy tắc từ error analysis)
└── tests/                                  thêm test cho entity_linker, schema_compressor,
                                            fewshot_retriever, self_correct, vllm_client (mock)
```

### Việc cần làm theo từng file

| File / nhóm                                           | Người | Hạn                      | Nội dung chính                                                                                                                              |
| ------------------------------------------------------ | ------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `data_synth/*`                                       | P       | 08/11 18:00               | 15.000–20.000 mẫu từ 3.000 câu train; paraphrase tiếng Việt; câu unanswerable có chủ đích; biến thể Tết; lọc sạch trước SFT |
| `grounding/entity_linker.py`                         | P       | trong Phase 3             | Mục tiêu khớp tên viết tắt/teencode/thiếu dấu ≥ 90%                                                                                  |
| `training/*`, `train.sh`                           | L       | 11/11 23:59               | SFT trên `Qwen2.5-Coder-14B-Instruct` (tổng tham số ≤ 15B); DPO nếu đủ GPU                                                           |
| `llm/vllm_client.py`                                 | L       | trước khi benchmark 14B | Cùng giao diện với `client.py` để đổi backend bằng config                                                                           |
| `llm/schema_compressor.py`, `fewshot_retriever.py` | L       | trong Phase 3             | Giảm context, tăng tốc, chọn ví dụ phù hợp                                                                                            |
| `execution/self_correct.py`                          | L       | 12/11 18:00               | Sửa thành công ≥ 60% lỗi cú pháp ở vòng 2; quá 2 vòng → `abstain`                                                               |
| `benchmark/error_analysis.py`                        | P+L     | hàng ngày               | Nhật ký lỗi: nguyên nhân gốc, số câu bị −1, đã sửa chưa                                                                         |

### Thay đổi so với Phase 2

| Hạng mục     | Phase 2                                                   | Phase 3                                                             |
| -------------- | --------------------------------------------------------- | ------------------------------------------------------------------- |
| Model          | Qwen2.5-Coder-3B 4-bit (transformers), model id ghi cứng | 14B đã tinh chỉnh, chạy bằng vLLM, chọn qua config            |
| Prompt         | Schema đầy đủ + few-shot cố định                   | Schema nén + few-shot truy xuất động + kết quả entity linking |
| Lỗi runtime   | Trả lỗi ra ngoài                                       | Vòng tự sửa tối đa 2 lần                                      |
| Gate           | Chỉ kiểm tra kỳ và loại thông tin                   | Thêm kiểm tra thực thể không tồn tại                         |
| Thư mục mới | —                                                        | `config/`, `data_synth/`, `training/`                         |
| Cấu hình     | Rải rác trong code                                      | Tập trung `config/default.yaml`                                  |

### Tiêu chí nghiệm thu Phase 3 (Milestone 12/11)

- PA nội bộ trên val **≥ 0.70 – 0.80+**; khóa checkpoint tốt nhất (Best Model Weights).
- Có nhật ký phân tích lỗi hàng ngày; các lỗi lặp lại gây −1 đã được xử lý.
- Self-correct đạt ≥ 60% ở vòng 2; entity linking ≥ 90%.
- Nộp bài tối ưu lên public leaderboard.

---

## 7. Phase 4 — Calibrated Abstention, Docker Offline & Submit (13/11 – 16/11)

**Mục tiêu:** bảo vệ điểm bằng cổng abstain có hiệu chuẩn, đảm bảo tái lập, đóng gói Docker chạy 100% offline và nộp sớm hơn hạn chót.

### Cấu trúc cuối Phase 4 (bản nộp)

```text
datamate/
├── pyproject.toml                          ✅
├── requirements.txt                        ✅ (dev, cu121)
├── requirements-docker.txt                 🆕 [P]   inference: CUDA ≥ 12.8, PyTorch/vLLM hỗ trợ Blackwell
├── Dockerfile                              🆕 [P]   weights + code + thư viện, chạy offline
├── predict.sh                              🆕 [P]   đọc /data (chỉ đọc), ghi /result/submission.jsonl, /result/logs/
├── train.sh                                ♻️ [L]   bản cuối, tái dựng được model
├── README.md                               ♻️ [P+L] khai báo model, tham số, cách chạy, cấu trúc
├── config/default.yaml                     ♻️ [L]   thêm tau (τ*), seed, ngưỡng timeout
├── weights/                                🆕       model cuối (ngoài git, copy vào image)
├── scripts/                                🆕 [P]
│   ├── check_offline.sh                    🆕 chạy container với --network none
│   ├── make_checksum.sh                    🆕 SHA256 cho image
│   └── verify_submission.py                🆕 đủ dòng, đúng id, không sót câu
├── benchmark/
│   ├── calibrate_tau.py                    🆕 [L]   quét τ* tối ưu trên val
│   ├── repro_check.py                      🆕 [L]   chạy 2 lần, so sánh |PA1 − PA2|
│   └── latency.py                          🆕 [P]   đo tổng thời gian, mục tiêu ≤ 3–4 giờ
├── src/datamate/
│   ├── config.py                           ♻️       đọc thêm tau, seed
│   ├── types.py                            ♻️       thêm Confidence
│   ├── pipeline.py                         ♻️ [P+L] set seed; gọi cổng abstain; ghi log đủ trường; ghi từng dòng để không mất dữ liệu nếu dừng giữa chừng
│   ├── gate/
│   │   ├── feasibility.py                  ✅
│   │   └── abstention.py                   🆕 [L]   C = f(execution health, data plausibility, entity score); C < τ* → abstain
│   ├── output/
│   │   └── submission.py                   ♻️       log theo câu: qid, đáp án, mã sinh ra, kết quả thô, độ tin cậy, quyết định, latency
│   └── (ingestion, grounding, llm, execution) ✅ (chỉ sửa lỗi phát hiện từ kiểm thử Docker)
├── tests/
│   └── test_e2e_offline.py                 🆕 [P+L] chạy end-to-end trên mẫu nhỏ, kiểm tra không có truy cập mạng
└── data_synth/  training/  notebooks/      ✅ (đi kèm nhưng không nằm trên đường chạy inference)
```

### Việc cần làm theo từng file

| File                                                   | Người | Hạn                | Nội dung chính                                                                                                                |
| ------------------------------------------------------ | ------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `gate/abstention.py`, `benchmark/calibrate_tau.py` | L       | 13/11 23:59         | Tính độ tin cậy C ∈ [0,1], chọn τ* bằng cách quét trên val để tối đa hóa PA; câu có C < τ* xuất `abstain` |
| `benchmark/repro_check.py`, seed                     | L       | 15/11 23:59         | Cố định seed, greedy T=0; kiểm tra hai lần chạy cho cùng kết quả                                                       |
| `predict.sh`                                         | P       | 14/11 18:00         | Chạy `python -m datamate.pipeline` với `/data` → `/result`                                                             |
| `Dockerfile`, `requirements-docker.txt`            | P       | 15/11 12:00         | Base image theo guideline BTC; CUDA ≥ 12.8; không tải gì lúc chạy                                                         |
| `scripts/check_offline.sh`                           | P       | 15/11               | `docker run --gpus all --network none -v /data:/data -v /result:/result <image> /app/predict.sh`                              |
| `benchmark/latency.py`                               | P       | 15/11               | Toàn bộ test set ≤ 3–4 giờ (trần chính thức 6 giờ, đã gồm nạp model)                                               |
| Nộp bài                                              | P+L     | 16/11 trước 18:00 | Link Google Drive công khai, SHA256, README; hạn chót chính thức 23:59                                                     |

### Thay đổi so với Phase 3

| Hạng mục                     | Phase 3                        | Phase 4                                                         |
| ------------------------------ | ------------------------------ | --------------------------------------------------------------- |
| Quyết định cuối            | Trả lời mọi câu khả thi   | Câu độ tin cậy thấp → `abstain` (0 điểm thay vì −1) |
| Tái lập                      | Chưa kiểm                    | Seed cố định, kiểm tra chạy hai lần                       |
| Môi trường                  | Máy dev (cu121, bitsandbytes) | Docker offline, CUDA ≥ 12.8, vLLM                              |
| `predict.sh`, `Dockerfile` | Trống                         | Hoàn chỉnh                                                    |
| Log                            | Cơ bản                       | Đủ trường theo yêu cầu BTC trong `/result/logs/`        |
| Config                         | Model, đường dẫn           | Thêm τ*, seed                                                 |

### Tiêu chí nghiệm thu Phase 4 (Milestone 16/11)

- Container chạy thành công với `--network none`, không truy cập mạng.
- Hai lần chạy độc lập cho cùng kết quả; sai lệch với bản nộp trong ngưỡng \|PA_uploaded − PA_rerun\| ≤ 0.03.
- Tổng thời gian trên test set ≤ 3–4 giờ; log từng câu đầy đủ.
- Tổng tham số mọi model dùng khi inference ≤ 15B, đã khai báo trong README.
- Đã nộp trước 18:00 ngày 16/11/2026.

---

## 8. Ma trận file × phase

*(🆕 tạo mới · ♻️ sửa nội dung · ✂️ tách · 📦 chuyển · ✅ giữ · — chưa tồn tại)*

| File (đường dẫn trong `src/datamate/` trừ khi ghi khác) | Phase 1 | Bước 0 | Phase 2 | Phase 3 | Phase 4 |
| --------------------------------------------------------------- | :-----: | :------: | :-----: | :-----: | :-----: |
| `ingestion/loader.py` (từ `ingest.py`)                     |   🆕   |    📦    |  ✂️  |   ✅   |   ✅   |
| `ingestion/schema.py`                                         |   —   |    —    |  ✂️  |   ✅   |   ✅   |
| `ingestion/cleaner.py`                                        |   —   |    —    |   🆕   |  ♻️  |   ✅   |
| `ingestion/sqlite_mirror.py`                                  |   —   |    —    |   🆕   |   ✅   |   ✅   |
| `ingestion/metadata.py`                                       |   —   |    —    |   🆕   |   ✅   |   ✅   |
| `grounding/rulebook.py`                                       |   —   |    —    |  ✂️  |   ✅   |   ✅   |
| `grounding/lunar_calendar.py`, `temporal.py`                |   —   |    —    |   🆕   |  ♻️  |   ✅   |
| `grounding/entity_linker.py`                                  |   —   |    —    |   —   |   🆕   |   ✅   |
| `gate/feasibility.py`                                         |   —   |    —    |   🆕   |  ♻️  |   ✅   |
| `gate/abstention.py`                                          |   —   |    —    |   —   |   —   |   🆕   |
| `llm/client.py` (từ `llm_client.py`)                       |   🆕   |    📦    |   ✅   |  ♻️  |   ✅   |
| `llm/vllm_client.py`                                          |   —   |    —    |   —   |   🆕   |   ✅   |
| `llm/prompt_builder.py`                                       |   🆕   |    📦    |  ♻️  |  ♻️  |   ✅   |
| `llm/schema_compressor.py`, `fewshot_retriever.py`          |   —   |    —    |   —   |   🆕   |   ✅   |
| `execution/sandbox.py` (từ `runner.py`)                    |   🆕   |  📦♻️  |  ♻️  |   ✅   |   ✅   |
| `execution/worker.py`                                         |   —   |    —    |  ✂️  |   ✅   |   ✅   |
| `execution/self_correct.py`                                   |   —   |    —    |   —   |   🆕   |   ✅   |
| `output/submission.py`                                        |   🆕   |    📦    |  ♻️  |   ✅   |  ♻️  |
| `output/normalizer.py`, `ranking.py`                        |   —   |    —    |   🆕   |  ♻️  |   ✅   |
| `types.py`                                                    |   —   |    —    |   🆕   |  ♻️  |  ♻️  |
| `pipeline.py`                                                 |   —   |    —    |   🆕   |  ♻️  |  ♻️  |
| `config.py` + `config/default.yaml`                         |   —   |    —    |   —   |   🆕   |  ♻️  |
| `benchmark/` (split, evaluate, report)                        |   —   |    —    |   🆕   |   ✅   |   ✅   |
| `benchmark/` (error_analysis)                                 |   —   |    —    |   —   |   🆕   |   ✅   |
| `benchmark/` (calibrate_tau, repro_check, latency)            |   —   |    —    |   —   |   —   |   🆕   |
| `data_synth/`, `training/`                                  |   —   |    —    |   —   |   🆕   |   ✅   |
| `Dockerfile`, `predict.sh`                                  | trống |  trống  | trống | trống |   🆕   |
| `train.sh`                                                    | trống |  trống  | trống |   🆕   |  ♻️  |
| `pyproject.toml`                                              |   —   |    🆕    |   ✅   |   ✅   |   ✅   |

---

## 9. Quy tắc làm việc song song trên cùng cây thư mục

| Quy tắc                                                                                                                                                                                                   | Lý do                                                              |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Mỗi người chỉ sửa trong thư mục mình phụ trách: Phát — `ingestion/`, `grounding/`, `data_synth/`; Long — `gate/`, `llm/`, `execution/self_correct.py`, `output/`, `training/` | Tránh conflict git                                                 |
| `types.py` và `pipeline.py` sửa qua pull request, người còn lại review                                                                                                                           | Đây là hợp đồng giữa hai phía                               |
| Không đổi tên hàm công khai khi người kia đang dùng; cần đổi thì báo trước                                                                                                                | Pipeline đứt âm thầm là lỗi khó thấy nhất                  |
| Mỗi PR ghi kèm PA trước/sau trên 600 câu val (từ Phase 2)                                                                                                                                           | Mọi cải tiến phải quy ra điểm                                 |
| Không merge khi `pytest -q` đỏ                                                                                                                                                                        | Giữ nhánh chính luôn chạy được để nộp bất kỳ lúc nào |
| Dừng thêm tính năng từ 15/11, chỉ sửa lỗi đóng gói                                                                                                                                              | Chừa thời gian đệm cho Docker và nộp bài                     |

---
