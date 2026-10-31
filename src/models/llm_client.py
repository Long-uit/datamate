"""
Module: llm_client.py
Mục đích: Quản lý khởi tạo mô hình LLM Qwen2.5-Coder-3B-Instruct với cấu hình lượng tử hóa 4-bit (bitsandbytes),
          và thực hiện suy luận (inference) sinh mã Python tất định (Greedy Decoding T=0).
Tác giả: Long (AI Architect & Model Lead)
"""

import re
import torch

# ------------------------------------------------------------------------------
# VÁ LỖI NỘI BỘ (MONKEY-PATCH) CỦA TRANSFORMERS:
# Trong một số phiên bản của transformers, file quantization_config.py bị quên
# dòng 'import torch', khiến lệnh getattr(torch, ...) bị NameError.
# Dòng lệnh dưới đây tiêm trực tiếp module torch vào namespace của quantization_config
# để khắc phục triệt để lỗi mà không cần sửa file site-packages bằng tay.
# ------------------------------------------------------------------------------
try:
    import transformers.utils.quantization_config as _qc
    _qc.torch = torch
except Exception:
    pass

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


class LLMClient:
    """
    Client quản lý nạp và suy luận mô hình Qwen2.5-Coder-3B-Instruct ở chế độ 4-bit.
    Tối ưu hóa VRAM trên GPU cá nhân / Anaconda.
    """
    def __init__(self, model_id: str = "Qwen/Qwen2.5-Coder-3B-Instruct"):
        """
        Khởi tạo mô hình và cấu hình lượng tử hóa 4-bit.
        
        Args:
            model_id (str): Tên repo HuggingFace hoặc đường dẫn thư mục model local.
        """
        self.model_id = model_id
        print(f"[LLMClient] Bắt đầu khởi tạo và nạp mô hình: {self.model_id}...")

        # 1. Cấu hình lượng tử hóa 4-bit (NF4 - NormalFloat4) qua bitsandbytes
        # Dùng chuỗi "bfloat16" hoặc "float16" để tránh bug NameError: 'torch' is not defined trong transformers
        compute_dtype = "bfloat16" if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else "float16"
        self.quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",              # Sử dụng kiểu NF4 tối ưu cho LLM
            bnb_4bit_use_double_quant=True,         # Lượng tử hóa lồng nhau giúp tiết kiệm thêm bộ nhớ
            bnb_4bit_compute_dtype=compute_dtype    # Truyền dạng chuỗi ("float16" / "bfloat16")
        )

        # 2. Nạp Tokenizer
        print("[LLMClient] Nạp Tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # 3. Nạp Model vào GPU với cấu hình 4-bit
        # Chú ý: Cần GPU có CUDA để chạy 4-bit bitsandbytes
        print("[LLMClient] Nạp Model với cấu hình 4-bit...")
        device_map = "auto" if torch.cuda.is_available() else "cpu"
        
        load_kwargs = {
            "device_map": device_map,
            "trust_remote_code": True,
        }
        
        # Chỉ áp dụng quantization_config khi có CUDA
        if torch.cuda.is_available():
            load_kwargs["quantization_config"] = self.quant_config
        else:
            print("[CẢNH BÁO] Không tìm thấy GPU CUDA! Model sẽ chạy trên CPU (chậm hơn và không áp dụng 4-bit).")
            load_kwargs["torch_dtype"] = torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            **load_kwargs
        )
        self.model.eval()

        print("[LLMClient] Mô hình đã nạp thành công!")
        self.print_gpu_stats()

    def print_gpu_stats(self):
        """In thông số dung lượng VRAM GPU đã sử dụng"""
        if torch.cuda.is_available():
            allocated = round(torch.cuda.memory_allocated() / (1024 ** 3), 2)
            reserved = round(torch.cuda.memory_reserved() / (1024 ** 3), 2)
            print(f"[GPU Memory] Đã cấp phát (Allocated): {allocated} GB | Dự trữ (Reserved): {reserved} GB")
        else:
            print("[GPU Memory] Chạy trên CPU.")

    def generate_code(self, prompt: str, max_new_tokens: int = 1024) -> str:
        """
        Sinh chuỗi code Python từ prompt đầu vào sử dụng cơ chế Greedy Decoding (T=0).
        
        Args:
            prompt (str): Chuỗi prompt đã được xây dựng từ prompt_builder.py
            max_new_tokens (int): Giới hạn số token sinh ra tối đa (mặc định 1024)
            
        Returns:
            str: Khối mã nguồn Python sạch chứa hàm def solution(data):
        """
        messages = [
            {"role": "user", "content": prompt}
        ]

        # Áp dụng template hội thoại chuẩn của Qwen (ChatML format)
        chat_text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self.tokenizer([chat_text], return_tensors="pt").to(self.model.device)

        # CỰC KỲ QUAN TRỌNG TRONG CUỘC THI:
        # do_sample = False (Greedy Decoding) tương đương với Temperature = 0
        # Đảm bảo câu trả lời luôn ổn định, tính tái lập 100% (Reproducibility theo tiêu chí BTC)
        with torch.no_grad():
            output_tokens = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id
            )

        # Cắt bỏ phần token câu hỏi ban đầu, chỉ lấy token do model sinh ra
        generated_token_ids = output_tokens[0][len(inputs.input_ids[0]):]
        raw_output_text = self.tokenizer.decode(generated_token_ids, skip_special_tokens=True)

        # Làm sạch chuỗi, bóc tách code Python ra khỏi text
        clean_code = self._extract_python_code(raw_output_text)
        return clean_code

    def _extract_python_code(self, text: str) -> str:
        """
        Trích xuất và làm sạch khối code Python từ phản hồi dạng Markdown của LLM.
        Loại bỏ các văn bản giải thích thừa trước hoặc sau khối code.
        """
        text = text.strip()

        # Trường hợp 1: Model trả về trong khối ```python ... ```
        match_py = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match_py:
            return match_py.group(1).strip()

        # Trường hợp 2: Model trả về trong khối ``` ... ``` (không có chữ python)
        match_generic = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if match_generic:
            return match_generic.group(1).strip()

        # Trường hợp 3: Model không bọc code trong dấu backtick mà viết trực tiếp def solution
        if "def solution(" in text:
            idx = text.find("def solution(")
            return text[idx:].strip()

        # Fallback: Trả về toàn bộ text nếu không phát hiện mẫu chuẩn
        return text


# Cho phép chạy thử trực tiếp file này để kiểm tra quá trình nạp model
if __name__ == "__main__":
    client = LLMClient()
    test_prompt = "Hãy viết hàm def solution(data): trả về số 42."
    print("\n--- TEST SINH MÃ ---")
    code = client.generate_code(test_prompt)
    print("Mã sinh ra:")
    print(code)
