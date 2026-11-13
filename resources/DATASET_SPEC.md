# Đặc Tả Bộ Dữ Liệu Chuẩn Hóa Teencode & Từ Viết Tắt Tiếng Việt
**Dataset Specification: Vietnamese Teencode, Slang & Business Abbreviations**

---

## 1. Tổng Quan & Cấu Trúc Thư Mục (Dataset Overview)

Bộ dữ liệu được chuẩn hóa từ `resources/teencode.csv` kết hợp với từ điển thuật ngữ bán lẻ / thương mại điện tử chuyên sâu của **DataMate** và danh mục lỗi kẹt bộ gõ Telex tiếng Việt.

### Các tệp thành phần:
| Tên tệp | Định dạng | Mục đích sử dụng | Số lượng mẫu |
|---|---|---|---|
| `teencode_cleaned.csv` | CSV (UTF-8) | Dữ liệu gốc sạch có gán nhãn miền (domain), nhóm lỗi (category) và cờ đa nghĩa (context_sensitive) | 527 mục từ |
| `teencode_dictionary.json` | JSON | Từ điển tra cứu O(1), phân tầng miền nghiệp vụ (`retail_specific`, `general_chat`) & luật giải quyết đa nghĩa | 527 mục từ |
| `embedding_pairs.jsonl` | JSON Lines | Cặp câu/từ đối sánh (Anchor - Positive) cho Huấn luyện Mô hình Nhúng (Contrastive / Triplet Loss) | 547 cặp |
| `sft_instruct_train.jsonl` | JSON Lines | Tập huấn luyện Fine-tuning LLM (Instruction Tuning / Alpaca format, 90% split) | 519 mẫu |
| `sft_instruct_val.jsonl` | JSON Lines | Tập kiểm định đánh giá mô hình (10% split) | 58 mẫu |

---

## 2. Đặc Tả Schema & Phân Nhóm Dữ Liệu

### 2.1. Cấu trúc `teencode_cleaned.csv`
```csv
teencode,standard,domain,category,context_sensitive,notes
"bnhiu","bao nhiêu","retail_business","abbreviation",false,""
"khôg","không","spelling_typo","diacritic_typo",false,"Rút gọn đuôi 'ng' thành 'g' phổ biến trên điện thoại"
"bn","bạn","general_chat","abbreviation",true,"bán lẻ: 'bao nhiêu' | giao tiếp: 'bạn'"
```

- **`teencode`** (`string`): Chuỗi từ khóa viết tắt, teencode, hoặc từ kẹt phím Telex gốc.
- **`standard`** (`string`): Dạng tiếng Việt chuẩn có dấu hoàn chỉnh (NFC).
- **`domain`** (`enum`):
  - `retail_business`: Thuật ngữ bán lẻ, đơn hàng, hóa đơn, doanh thu, thanh toán (`sp`, `dthu`, `sl`, `đh`, `ncc`, `stk`, `ck`...).
  - `general_chat`: Từ viết tắt giao tiếp thông dụng hàng ngày (`bme`, `mng`, `thgian`, `hnay`, `hqua`, `j`, `z`...).
  - `spelling_typo`: Lỗi chính tả, rút gọn vần đuôi (`khôg`, `nhữg`, `đag`, `trog`) hoặc kẹt bộ gõ Telex (`thangs`, `ngayf`, `dduwowcj`...).
  - `social_slang`: Từ lóng, thán từ hoặc tiếng lóng mạng xã hội (`atsm`, `sml`, `gato`...).
  - `organization`: Tên viết tắt trường học, cơ quan (`đhbkhn`, `thpt`, `nvqs`...).
- **`category`** (`enum`): `abbreviation`, `diacritic_typo`, `telex_slip`, `phonetic_replacement`, `elongated`, `slang`.
- **`context_sensitive`** (`boolean`): Đánh dấu từ đa nghĩa phụ thuộc ngữ cảnh cao.

### 2.2. Cơ Chế Khử Đa Nghĩa (Context Disambiguation)
Một số từ viết tắt mang ý nghĩa hoàn toàn khác nhau giữa ngữ cảnh **Bán lẻ (Retail)** và **Giao tiếp đời sống (Social)**:

| Từ viết tắt | Trong nghiệp vụ Bán lẻ / Doanh nghiệp | Trong giao tiếp mạng xã hội / Đời sống | Dấu hiệu phân biệt trong câu |
|---|---|---|---|
| `bn` | **bao nhiêu** (hỏi số lượng, doanh thu, đơn) | **bạn** (đại từ xưng hô) | Đi cùng: `đơn`, `tiền`, `sp`, `ly`, `kg`, `bán`, `giá` -> `bao nhiêu` |
| `ck` | **chiết khấu** / **chuyển khoản** | **chồng** (trong gia đình) | Đi cùng: `%`, `giảm`, `tiền`, `đơn`, `stk`, `ngân hàng` -> `chiết khấu / chuyển khoản` |
| `kh` | **khách hàng** | **không** | Đi cùng: `vip`, `mua`, `quen`, `mã`, `tên` -> `khách hàng`; Đi trước động từ -> `không` |
| `dt` | **doanh thu** | **điện thoại** | Đi cùng: `tháng`, `ngày`, `tổng`, `đạt`, `thu` -> `doanh thu` |
| `tt` | **thành tiền** / **thanh toán** | **thông tin** | Đi cùng: `cột`, `tiền`, `tổng`, `hóa đơn` -> `thành tiền` |

---

## 3. Hướng Dẫn Huấn Luyện & Nhúng Dữ Liệu (Code Snippets)

### 3.1. Dùng cho Huấn Luyện Mô Hình Nhúng (Embedding / Contrastive Learning)
Sử dụng thư viện `sentence-transformers` với tệp `resources/embedding_pairs.jsonl`:

```python
import json
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

# 1. Nạp dữ liệu
train_examples = []
with open("resources/embedding_pairs.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line.strip())
        train_examples.append(InputExample(texts=[data["anchor"], data["positive"]]))

# 2. Khởi tạo mô hình nền
model = SentenceTransformer("bkai-foundation-models/vietnamese-bi-encoder")
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=32)

# 3. Sử dụng hàm mất mát MultipleNegativesRankingLoss
train_loss = losses.MultipleNegativesRankingLoss(model)

# 4. Huấn luyện (Fine-tune Embedding)
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100,
    show_progress_bar=True
)

# 5. Lưu mô hình nhúng đã tinh chỉnh
model.save("models/vietnamese-teencode-embedding")
```

---

### 3.2. Dùng cho Huấn Luyện Mô Hình Sinh / SFT (LLM Fine-tuning)
Sử dụng Hugging Face `trl` (SFTTrainer) & `peft` (LoRA) với tập `sft_instruct_train.jsonl` và `sft_instruct_val.jsonl`:

```python
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer

# 1. Nạp Dataset chuẩn Alpaca
dataset = load_dataset("json", data_files={
    "train": "resources/sft_instruct_train.jsonl",
    "validation": "resources/sft_instruct_val.jsonl"
})

def formatting_prompts_func(example):
    output_texts = []
    for i in range(len(example['instruction'])):
        text = f"<|im_start|>system\n{example['instruction'][i]}<|im_end|>\n<|im_start|>user\n{example['input'][i]}<|im_end|>\n<|im_start|>assistant\n{example['output'][i]}<|im_end|>"
        output_texts.append(text)
    return output_texts

# 2. Cấu hình LoRA
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

# 3. Huấn luyện SFT
training_args = TrainingArguments(
    output_dir="./results_teencode_sft",
    num_train_epochs=3,
    per_device_train_batch_size=8,
    learning_rate=2e-4,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    logging_steps=10,
    fp16=True
)

trainer = SFTTrainer(
    model="Qwen/Qwen2.5-Coder-7B-Instruct",
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    peft_config=peft_config,
    formatting_func=formatting_prompts_func,
    args=training_args,
)

trainer.train()
```

---

### 3.3. Dùng trực tiếp trong Python Pipeline (Fast In-Memory Preprocessing)
Hệ thống cung cấp module `normalizer_teencode.py`:

```python
from datamate.grounding_feasibility.normalizer_teencode import normalize_teencode

# Tự động giải quyết đa nghĩa theo miền bán lẻ:
raw_query = "Hnay shop ban dc bn don? Sp dthu cao nhat la gi?"
clean_query = normalize_teencode(raw_query, domain="retail")

print(clean_query)
# Output: "hôm nay shop bán được bao nhiêu đơn? sản phẩm doanh thu cao nhất là gì?"
```

