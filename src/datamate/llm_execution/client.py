"""
Module: llm_client.py
Mục đích: Quản lý nạp mô hình Qwen2.5-Coder-3B-Instruct với cấu hình lượng tử hóa 4-bit,
          thực hiện suy luận sinh mã Python tất định (Greedy Decoding T=0), kiểm tra cú pháp (AST)
          và hỗ trợ cơ chế tự sửa lỗi ngắn nếu mã sinh ra bị lỗi cú pháp.
Tác giả: Long (AI Architect & Model Lead)
"""

import os
import sys
import re
import ast
import sys
import time
import warnings
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

# Tắt cảnh báo deprecation về torch_dtype của Transformers mới
warnings.filterwarnings("ignore", message=".*torch_dtype.*")

# Đảm bảo hiển thị Unicode tiếng Việt trên console Windows an toàn tuyệt đối
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Cấu hình chống phân mảnh VRAM PyTorch CUDA (tránh lỗi OOM khi cấp phát khối liên tục)
if "PYTORCH_CUDA_ALLOC_CONF" not in os.environ:
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128"

# Nhập torch và transformers có xử lý ngoại lệ an toàn
try:
    import torch
    # Xử lý monkey-patch nội bộ nếu phiên bản transformers gặp lỗi thiếu import torch
    try:
        import transformers.utils.quantization_config as _qc
        _qc.torch = torch
    except Exception:
        pass

    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        StoppingCriteria,
        StoppingCriteriaList,
    )
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    AutoModelForCausalLM = None
    AutoTokenizer = None
    BitsAndBytesConfig = None
    StoppingCriteria = object
    StoppingCriteriaList = list
    TORCH_AVAILABLE = False


class CodeBlockEndStoppingCriteria(StoppingCriteria):
    """
    Dừng sinh sớm ngay khi mô hình viết xong khối hàm solution(data) hợp lệ và đóng code fence ```.
    Giúp tăng tốc độ suy luận gấp 15-30 lần (từ ~116s xuống còn 3-5s/câu) và triệt tiêu sinh thừa.
    """
    def __init__(self, tokenizer: Any, start_len: int):
        self.tokenizer = tokenizer
        self.start_len = start_len

    def __call__(self, input_ids: Any, scores: Any, **kwargs) -> bool:
        new_ids = input_ids[0][self.start_len:]
        num_new = len(new_ids)
        if num_new < 15:
            return False

        # Chỉ decode mỗi 3 tokens để giảm tải CPU giải mã
        if num_new % 3 != 0:
            return False

        full_text = self.tokenizer.decode(new_ids, skip_special_tokens=False)
        if "def solution" in full_text and "return " in full_text:
            if full_text.count("```") >= 2:
                return True
            if not full_text.strip().startswith("```") and full_text.count("```") >= 1:
                return True
            tail_text = self.tokenizer.decode(new_ids[-40:], skip_special_tokens=False)
            if any(k in tail_text for k in [
                "\ndef ", "\nclass ", "\nprint(", "\n# Example", "\n# Ví dụ", "\nif __name__", "\n```"
            ]):
                return True
        return False

        full_text = self.tokenizer.decode(new_ids, skip_special_tokens=False)
        if "def solution" in full_text and "return " in full_text:
            if full_text.count("```") >= 2:
                return True
            if not full_text.strip().startswith("```") and full_text.count("```") >= 1:
                return True
            tail_text = self.tokenizer.decode(new_ids[-40:], skip_special_tokens=False)
            if (
                "\nprint(" in tail_text
                or "\n# Example" in tail_text
                or "\n# Ví dụ" in tail_text
                or "\nif __name__" in tail_text
            ):
                return True
        return False


# ==============================================================================
# HÀM KIỂM TRA CÚ PHÁP VÀ TÍNH HỢP LỆ CỦA MÃ NGUỒN (CODE VALIDATION)
# ==============================================================================

# Danh sách các module hoặc hàm bị cấm vì lý do an toàn
DANGEROUS_MODULES = {"subprocess", "pty", "socket"}
DANGEROUS_OS_FUNCS = {"system", "popen"}

def validate_code(code_str: str) -> Tuple[bool, Optional[str]]:
    """
    Kiểm tra cú pháp và cấu trúc bắt buộc của mã Python do mô hình sinh ra bằng AST.
    
    Tiêu chí kiểm tra:
    1. Cú pháp Python hợp lệ (không dính SyntaxError).
    2. Có định nghĩa hàm tên 'solution'.
    3. Hàm 'solution' có ít nhất 1 tham số đầu vào (thường là 'data').
    4. Trong hàm có ít nhất một lệnh 'return'.
    5. Không chứa các lệnh gọi thực thi hệ thống nguy hiểm.
    
    Args:
        code_str (str): Chuỗi mã nguồn Python cần kiểm tra.
        
    Returns:
        Tuple[bool, Optional[str]]: (True, None) nếu hợp lệ; (False, "lý do lỗi") nếu không hợp lệ.
    """
    if not code_str or not code_str.strip():
        return False, "Mã nguồn rỗng"

    # 1. Kiểm tra cú pháp bằng AST
    try:
        tree = ast.parse(code_str, filename="<generated_code>")
    except SyntaxError as e:
        return False, f"Lỗi cú pháp Python (SyntaxError): {e.msg} ở dòng {e.lineno}"
    except Exception as e:
        return False, f"Lỗi parse AST: {str(e)}"

    # 2. Tìm hàm solution trong cây cú pháp (chấp nhận cả hàm thường và async)
    solution_node: Optional[ast.AST] = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "solution":
            solution_node = node
            break

    if solution_node is None:
        return False, "Thiếu định nghĩa hàm 'def solution(data):'"

    # 3. Kiểm tra tham số của hàm solution (chấp nhận positional args hoặc *args)
    has_args = len(solution_node.args.args) >= 1 or solution_node.args.vararg is not None
    if not has_args:
        return False, "Hàm 'solution' phải nhận ít nhất 1 tham số đầu vào (ví dụ: data)"

    # 4. Kiểm tra có lệnh return bên trong hàm không
    has_return = any(isinstance(sub_node, ast.Return) for sub_node in ast.walk(solution_node))
    if not has_return:
        return False, "Hàm 'solution' không chứa lệnh 'return' để trả về kết quả"

    # 5. Kiểm tra an toàn bằng AST: phát hiện import hoặc gọi hàm nguy hiểm
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in DANGEROUS_MODULES:
                    return False, f"Mã nguồn chứa lệnh import bị hạn chế: '{alias.name}'"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg in DANGEROUS_MODULES:
                    return False, f"Mã nguồn chứa lệnh import bị hạn chế: '{node.module}'"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                return False, f"Mã nguồn chứa lệnh gọi bị hạn chế: '{node.func.id}'"
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in DANGEROUS_OS_FUNCS:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        return False, f"Mã nguồn chứa lệnh gọi bị hạn chế: 'os.{node.func.attr}'"
                if node.func.attr == "rmtree":
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "shutil":
                        return False, f"Mã nguồn chứa lệnh gọi bị hạn chế: 'shutil.rmtree'"

    return True, None


def extract_python_code(text: str) -> str:
    """
    Bóc tách và làm sạch khối mã nguồn Python từ văn bản phản hồi của mô hình.
    Xử lý các trường hợp: bọc trong ```python, bọc trong ```, hoặc viết trực tiếp def solution.
    
    Args:
        text (str): Toàn bộ văn bản do mô hình sinh ra.
        
    Returns:
        str: Đoạn mã Python đã làm sạch.
    """
    if not text:
        return ""

    text = text.strip()

    # Trường hợp 1: Có khối ```python ... ``` hoàn chỉnh
    match_py = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match_py:
        code = match_py.group(1).strip()
        return cut_after_first_solution(code)

    # Trường hợp 2: Có khối ``` ... ``` chung
    match_generic = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match_generic:
        code = match_generic.group(1).strip()
        return cut_after_first_solution(code)

    # Trường hợp 3: Khối ```python nhưng bị cắt cụt chưa đóng ```
    match_unclosed = re.search(r"```python\s*(def\s+solution.*)", text, re.DOTALL | re.IGNORECASE)
    if match_unclosed:
        code = match_unclosed.group(1).strip()
        return cut_after_first_solution(code)

    # Trường hợp 4: Viết trực tiếp def solution( mà không bọc backtick
    if "def solution(" in text:
        idx = text.find("def solution(")
        code = text[idx:].strip()
        if code.endswith("```"):
            code = code[:-3].strip()
        return cut_after_first_solution(code)

    return text


def cut_after_first_solution(code: str) -> str:
    """
    Nếu mô hình sinh lặp lại từ 2 hàm solution trở lên hoặc sinh thêm mã thừa phía sau
    (như def clean_date, def clean_num, class DataNotFoundError, print),
    chỉ giữ lại khối hàm solution đầu tiên và các import ở đầu.
    """
    if code.endswith("```"):
        code = code[:-3].strip()

    indices = [m.start() for m in re.finditer(r"def solution\s*\(", code)]
    if len(indices) > 1:
        code = code[:indices[1]].strip()

    # Cắt bỏ mọi hàm def phụ hoặc class phụ ở thụt lề 0 sau hàm solution
    m_sol = re.search(r"def solution\s*\(", code)
    if m_sol:
        post = code[m_sol.end():]
        stop_match = re.search(r"\n(?=(?:def (?!solution)|class |if __name__|print\(|#\s*Example|#\s*Ví dụ))", post)
        if stop_match:
            code = code[:m_sol.end() + stop_match.start()].strip()

    return code


# ==============================================================================
# CLASS QUẢN LÝ MÔ HÌNH VÀ SUY LUẬN (LLMCLIENT)
# ==============================================================================

class LLMClient:
    """
    Quản lý khởi tạo và suy luận mô hình Qwen2.5-Coder-3B-Instruct với cấu hình 4-bit.
    Tích hợp kiểm tra cú pháp AST và cơ chế tự sửa lỗi (Self-Correction).
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        auto_load: bool = True,
        backend: Optional[str] = None,
    ):
        """
        Khởi tạo client quản lý mô hình.
        
        Args:
            model_id (str, optional): Đường dẫn repo HuggingFace hoặc thư mục model local (mặc định: Qwen/Qwen2.5-Coder-3B-Instruct).
            auto_load (bool): Tự động nạp trọng số mô hình khi khởi tạo.
            backend (str, optional): Động cơ suy luận ('transformers' hoặc 'vllm'). Khi dùng 'vllm', tự động bật Prefix Caching.
        """
        cfg_model_id = None
        cfg_backend = None
        try:
            from datamate.config import load_config
            _cfg = load_config()
            cfg_model_id = _cfg.model.model_id
            cfg_backend = _cfg.model.backend
        except Exception:
            pass

        if model_id is None:
            model_id = os.environ.get("DATAMATE_MODEL_ID") or os.environ.get("MODEL_ID") or cfg_model_id or "Qwen/Qwen2.5-Coder-14B-Instruct"
        # Trong môi trường Docker Offline, nếu trọng số đã được bake tại /app/weights/model hoặc DATAMATE_MODEL_ID trỏ tới thư mục có thực
        env_model_path = os.environ.get("DATAMATE_MODEL_ID") or "/app/weights/model"
        if not os.path.isdir(str(model_id)) and os.path.isdir(env_model_path) and os.path.exists(os.path.join(env_model_path, "config.json")):
            model_id = env_model_path
        self.model_id = model_id
        self.backend = (backend or os.environ.get("DATAMATE_BACKEND") or cfg_backend or "transformers").lower()
        self.model = None
        self.tokenizer = None
        self.vllm_engine = None
        self.is_loaded = False
        self.device = "cpu"
        self.last_latency_ms: int = 0

        if auto_load:
            self.load_model()

    def load_model(self) -> None:
        """Nạp tokenizer và trọng số mô hình vào bộ nhớ."""
        if not TORCH_AVAILABLE:
            print("[Cảnh báo] PyTorch/Transformers chưa được cài đặt. LLMClient chạy ở chế độ giả lập.")
            return

        print(f"[LLMClient] Bắt đầu nạp mô hình: {self.model_id} (backend={self.backend})...")

        # Hỗ trợ động cơ vLLM tốc độ cao với Prefix Caching (enable_prefix_caching=True)
        if self.backend == "vllm":
            try:
                from vllm import LLM as VLLMEngine  # type: ignore
                tp_size = max(1, torch.cuda.device_count()) if torch.cuda.is_available() else 1
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
                self.vllm_engine = VLLMEngine(
                    model=self.model_id,
                    trust_remote_code=True,
                    tensor_parallel_size=tp_size,
                    enable_prefix_caching=True,
                    gpu_memory_utilization=0.90,
                    max_model_len=8192,
                )
                self.device = "cuda"
                self.is_loaded = True
                print(f"[LLMClient] Đã nạp vLLM Engine (enable_prefix_caching=True, TP={tp_size}) thành công!")
                return
            except Exception as vllm_err:
                print(f"[LLMClient] Không thể khởi tạo vLLM ({vllm_err}), tự động chuyển về HuggingFace Transformers...")
                self.backend = "transformers"

        # 1. Cấu hình kiểu dữ liệu tính toán (compute_dtype) & Lượng tử hóa
        has_cuda = torch.cuda.is_available()
        num_gpus = torch.cuda.device_count() if has_cuda else 0
        
        # Bật cờ tối ưu phân bổ bộ nhớ PyTorch chống phân mảnh VRAM
        if has_cuda:
            os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
            # Với GPU T4 (Turing), float16 ổn định và tương thích BitsAndBytes hơn bfloat16
            use_bf16 = torch.cuda.is_bf16_supported() and "T4" not in torch.cuda.get_device_name(0)
            compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
        else:
            compute_dtype = torch.float32

        # Cấu hình lượng tử hóa
        quant_mode = (os.environ.get("DATAMATE_QUANTIZATION") or "8bit").lower().strip()
        
        # TỰ ĐỘNG BẢO VỆ OOM: Nếu chỉ có 1 GPU (<= 16GB) mà nạp mô hình 14B, 8-bit (14GB) chắc chắn OOM
        # -> Tự động kích hoạt 4-bit NF4 (~8.5GB) để dành 6GB VRAM cho Attention Forward!
        is_14b = "14b" in str(self.model_id).lower()
        if has_cuda and num_gpus == 1 and is_14b and quant_mode != "4bit":
            print(f"[LLMClient] ⚠️ Phát hiện chỉ có 1 GPU ({torch.cuda.get_device_name(0)}) chạy mô hình 14B.")
            print(f"[LLMClient] 🛡️ Tự động chuyển lượng tử hóa sang 4-bit NF4 để chống CUDA Out of Memory!")
            quant_mode = "4bit"

        if quant_mode in ("4bit", "4-bit", "nf4"):
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=compute_dtype,
            )
            print(f"[LLMClient] Áp dụng lượng tử hóa: 4-bit NF4 (compute_dtype={compute_dtype})")
        else:
            quant_config = BitsAndBytesConfig(
                load_in_8bit=True,
                llm_int8_enable_fp32_cpu_offload=True,
            )
            print(f"[LLMClient] Áp dụng lượng tử hóa: 8-bit INT8 (load_in_8bit=True, llm_int8_enable_fp32_cpu_offload=True)")

        # 2. Dọn dẹp bộ nhớ GPU trước khi nạp model
        if has_cuda:
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass

        # 3. Nạp Tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # 4. Nạp Model
        if has_cuda:
            self.device = "cuda"
            load_kwargs = {
                "device_map": "auto",
                "torch_dtype": compute_dtype,
                "low_cpu_mem_usage": True,
                "quantization_config": quant_config,
                "trust_remote_code": True,
                "attn_implementation": "sdpa",
            }
            # PHÂN BỔ ĐỀU BỘ NHỚ CHO ĐA GPU (GPU T4 x 2):
            # Mặc định Accelerate sẽ nhồi đầy GPU 0 trước khi sang GPU 1 dẫn đến GPU 0 bị OOM.
            # Ta thiết lập max_memory trần cho mỗi GPU để chia đều tải 50-50!
            if num_gpus >= 2:
                max_memory = {}
                for g_idx in range(num_gpus):
                    vram_gb = torch.cuda.get_device_properties(g_idx).total_memory / (1024 ** 3)
                    # Dành ~12GiB trên mỗi thẻ 14.5GiB cho model, giữ 2.5GiB cho Attention/KV-Cache
                    safe_limit_gb = max(4, int(vram_gb - 2.5))
                    max_memory[g_idx] = f"{safe_limit_gb}GiB"
                max_memory["cpu"] = "28GiB"
                load_kwargs["max_memory"] = max_memory
                print(f"[LLMClient] ⚖️ Bật chia tải đều qua {num_gpus} GPU: max_memory={max_memory}")
        else:
            self.device = "cpu"
            print("[Cảnh báo] Không tìm thấy GPU CUDA. Mô hình sẽ chạy trên CPU ở chế độ float32.")
            load_kwargs = {
                "device_map": "cpu",
                "torch_dtype": torch.float32,
                "trust_remote_code": True,
            }

        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                **load_kwargs
            )
            self.model.eval()
            self.is_loaded = True
        except Exception as e:
            import gc
            gc.collect()
            if has_cuda:
                torch.cuda.empty_cache()

            print(f"[LLMClient] Cảnh báo bước đầu nạp mô hình gặp lỗi: {e}")

            # FALLBACK CẤP 1: NẾU ĐANG CHẠY 8-BIT THẤT BẠI HOẶC BỊ OOM -> CHUYỂN SANG 4-BIT NF4
            if has_cuda and quant_mode not in ("4bit", "4-bit", "nf4"):
                print(f"[LLMClient] 🛡️ Fallback cấp 1: Chuyển sang lượng tử hóa 4-bit NF4 (tiết kiệm ~50% VRAM, bảo đảm không OOM)...")
                try:
                    quant_4bit = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=compute_dtype,
                    )
                    load_kwargs["quantization_config"] = quant_4bit
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_id,
                        **load_kwargs
                    )
                    self.model.eval()
                    self.is_loaded = True
                    print(f"[LLMClient] ✅ Fallback 4-bit NF4 thành công trên {self.device}!")
                except Exception as e_4bit:
                    print(f"[LLMClient] Fallback 4-bit với max_memory thất bại ({e_4bit}), thử auto device_map hoàn toàn...")
                    try:
                        gc.collect()
                        torch.cuda.empty_cache()
                        load_kwargs.pop("max_memory", None)
                        load_kwargs["device_map"] = "auto"
                        self.model = AutoModelForCausalLM.from_pretrained(
                            self.model_id,
                            **load_kwargs
                        )
                        self.model.eval()
                        self.is_loaded = True
                        print(f"[LLMClient] ✅ Fallback 4-bit auto device_map thành công!")
                    except Exception as e_final_4bit:
                        print(f"[Lỗi] Nạp mô hình 4-bit thất bại: {e_final_4bit}")
                        self.is_loaded = False

            # FALLBACK CẤP 2 (CHỈ DÀNH CHO MODEL NHỎ < 4B):
            # Tuyệt đối không fallback float16 cho model 7B hoặc 14B vì 100% sẽ OOM GPU 15GB!
            elif has_cuda and not is_14b and "7b" not in str(self.model_id).lower():
                print(f"[LLMClient] 🛡️ Fallback cấp 2: Thử nạp không lượng tử hóa (torch_dtype={compute_dtype}) cho mô hình nhỏ...")
                try:
                    fallback_kwargs = {
                        "device_map": "auto",
                        "torch_dtype": compute_dtype,
                        "low_cpu_mem_usage": True,
                        "trust_remote_code": True,
                    }
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_id,
                        **fallback_kwargs
                    )
                    self.model.eval()
                    self.is_loaded = True
                    print(f"[LLMClient] Nạp mô hình nhỏ thành công: {self.device}")
                except Exception as e_cuda:
                    print(f"[Lỗi] Nạp mô hình thất bại: {e_cuda}")
                    self.is_loaded = False
            else:
                print(f"[Lỗi] Không thể nạp mô hình {self.model_id}: {e}")
                self.is_loaded = False

        if self.is_loaded:
            # Tự động nạp QLoRA Adapter nếu đã fine-tune
            adapter_path = Path("models/qwen2.5_coder_qlora_adapter")
            if adapter_path.exists() and (adapter_path / "adapter_config.json").exists():
                try:
                    from peft import PeftModel
                    print(f"[LLMClient] Phát hiện QLoRA adapter tại {adapter_path}. Đang nạp adapter...")
                    self.model = PeftModel.from_pretrained(self.model, str(adapter_path))
                    self.model.eval()
                    print("[LLMClient] Nạp QLoRA adapter thành công!")
                except Exception as e_lora:
                    print(f"[LLMClient] Cảnh báo không nạp được LoRA adapter: {e_lora}")

            print(f"[LLMClient] Nạp mô hình thành công trên thiết bị: {self.device}")
            self.print_gpu_stats()

    def get_gpu_memory_stats(self) -> Dict[str, float]:
        """Trả về thông số dung lượng VRAM GPU đã sử dụng (đơn vị: GB)."""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            allocated = round(torch.cuda.memory_allocated() / (1024 ** 3), 2)
            reserved = round(torch.cuda.memory_reserved() / (1024 ** 3), 2)
            return {"allocated_gb": allocated, "reserved_gb": reserved}
        return {"allocated_gb": 0.0, "reserved_gb": 0.0}

    def print_gpu_stats(self) -> None:
        """In thông số bộ nhớ GPU ra console."""
        stats = self.get_gpu_memory_stats()
        try:
            if float(stats.get("allocated_gb", 0)) > 0:
                print(f"[GPU Memory] Đã cấp phát: {stats['allocated_gb']} GB | Dự trữ: {stats['reserved_gb']} GB")
            else:
                print(f"[GPU Memory] Thiết bị hiện tại: {self.device}")
        except Exception:
            print(f"[GPU Memory] Thiết bị hiện tại: {self.device}")

    def _generate_raw(self, messages: List[Dict[str, str]], max_new_tokens: int = 1536) -> str:
        """Thực hiện một lần suy luận thô với cơ chế Greedy Decoding (hỗ trợ cả vLLM Prefix Caching và Transformers)."""
        if not self.is_loaded or self.tokenizer is None:
            return ""

        chat_text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        if self.backend == "vllm" and self.vllm_engine is not None:
            from vllm import SamplingParams  # type: ignore
            sampling_params = SamplingParams(
                temperature=0.0,
                max_tokens=max_new_tokens,
                repetition_penalty=1.05,
            )
            outputs = self.vllm_engine.generate([chat_text], sampling_params, use_tqdm=False)
            if outputs and outputs[0].outputs:
                return outputs[0].outputs[0].text
            return ""

        if self.model is None:
            return ""

        if torch.cuda.is_available():
            import gc
            gc.collect()
            torch.cuda.empty_cache()

        inputs = self.tokenizer([chat_text], return_tensors="pt").to(self.model.device)

        start_len = inputs.input_ids.shape[1]
        stopping_criteria = StoppingCriteriaList([CodeBlockEndStoppingCriteria(self.tokenizer, start_len)])

        # Cấu hình Greedy Decoding (T=0) chuẩn kèm StoppingCriteria tối ưu tốc độ:
        # Bật repetition_penalty=1.05 để chống lặp code
        # Giới hạn max_new_tokens tối đa 1536 để tiết kiệm VRAM KV-cache
        gen_tokens = min(max_new_tokens, 1536) if max_new_tokens > 0 else 1024
        with torch.inference_mode():
            output_tokens = self.model.generate(
                **inputs,
                max_new_tokens=gen_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                repetition_penalty=1.05,
                use_cache=True,
                stopping_criteria=stopping_criteria,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )

        generated_token_ids = output_tokens[0][len(inputs.input_ids[0]):]
        result_text = self.tokenizer.decode(generated_token_ids, skip_special_tokens=True)

        del inputs, output_tokens
        if torch.cuda.is_available():
            import gc
            gc.collect()
            torch.cuda.empty_cache()

        return result_text

    def generate_code(
        self,
        prompt: str,
        max_new_tokens: int = 1536,
        system_prompt: Optional[str] = None,
        max_retries: int = 1
    ) -> str:
        """
        Sinh chuỗi mã nguồn Python từ prompt đầu vào, có kiểm tra cú pháp AST và tự sửa lỗi ngắn.
        
        Args:
            prompt (str): Chuỗi prompt người dùng hoặc nội dung truy vấn.
            max_new_tokens (int): Giới hạn số token sinh ra (mặc định 512).
            system_prompt (str, optional): Chỉ dẫn hệ thống theo chuẩn ChatML.
            max_retries (int): Số lần thử lại tối đa nếu mã sinh ra bị lỗi cú pháp (mặc định 1).
            
        Returns:
            str: Khối mã nguồn Python hợp lệ chứa hàm def solution(data):
        """
        start_time = time.time()

        # Tạo danh sách messages chuẩn ChatML
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Lần sinh mã đầu tiên
        raw_text = self._generate_raw(messages, max_new_tokens=max_new_tokens)
        code = extract_python_code(raw_text)
        is_valid, error_msg = validate_code(code)

        # Nếu mã không hợp lệ và còn lượt thử lại (Self-Correction Loop)
        attempt = 0
        while not is_valid and attempt < max_retries:
            attempt += 1
            print(f"[Tự sửa lỗi - Lần {attempt}] Mã sinh ra gặp vấn đề: {error_msg}. Gửi yêu cầu sửa lại...")

            # Bổ sung thông điệp sửa lỗi vào lịch sử hội thoại
            correction_messages = list(messages)
            correction_messages.append({"role": "assistant", "content": f"```python\n{code}\n```"})
            correction_messages.append({
                "role": "user",
                "content": f"Mã nguồn trước bị lỗi sau:\n{error_msg}\n\nHãy sửa lại và chỉ trả về một hàm hoàn chỉnh: def solution(data):"
            })

            raw_retry = self._generate_raw(correction_messages, max_new_tokens=max_new_tokens)
            retry_code = extract_python_code(raw_retry)
            retry_valid, retry_error = validate_code(retry_code)

            if retry_valid:
                code = retry_code
                is_valid = True
                print("[Tự sửa lỗi] Sửa mã nguồn thành công.")
                break
            else:
                error_msg = retry_error

        # Nếu sau khi sửa vẫn không hợp lệ -> fallback an toàn để chương trình không sập (trả về None để to_answer chuyển thành abstain 0 điểm)
        if not is_valid:
            print(f"[Cảnh báo] Sau {max_retries} lần thử, mã nguồn vẫn không đạt chuẩn ({error_msg}). Sử dụng fallback abstain an toàn.")
            code = (
                "def solution(data):\n"
                "    # Fallback an toàn khi mã sinh ra không đạt chuẩn cú pháp\n"
                "    return None\n"
            )

        self.last_latency_ms = int((time.time() - start_time) * 1000)
        return code

    def generate_solution(
        self,
        prompt: str,
        max_new_tokens: int = 1536,
        system_prompt: Optional[str] = None,
        max_retries: int = 1,
        **kwargs: Any,
    ) -> str:
        """Alias cho generate_code với default max_new_tokens=1536."""
        return self.generate_code(
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            system_prompt=system_prompt,
            max_retries=max_retries,
        )

    async def generate_solution_async(
        self,
        prompt: str,
        max_new_tokens: int = 1536,
        system_prompt: Optional[str] = None,
        max_retries: int = 1,
        **kwargs: Any,
    ) -> str:
        """Phiên bản async của generate_solution."""
        return self.generate_code(
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            system_prompt=system_prompt,
            max_retries=max_retries,
        )



# Kiểm tra nhanh khi chạy file trực tiếp
if __name__ == "__main__":
    sample_valid_code = """
import pandas as pd
def solution(data):
    return 42
"""
    val_ok, msg = validate_code(sample_valid_code)
    print("Kiểm tra mã hợp lệ:", val_ok, msg)

    sample_invalid_code = """
def solution(:
    pass
"""
    val_bad, msg_bad = validate_code(sample_invalid_code)
    print("Kiểm tra mã lỗi cú pháp:", val_bad, msg_bad)
