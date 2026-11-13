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
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

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
    Decode tăng dần (incremental) để tránh O(N^2) CPU overhead và bắt được cả trường hợp prompt đã mở sẵn ```python.
    """
    def __init__(self, tokenizer: Any, start_len: int):
        self.tokenizer = tokenizer
        self.start_len = start_len
        self._decoded_len = 0
        self._decoded_text = ""

    def __call__(self, input_ids: Any, scores: Any, **kwargs) -> bool:
        new_ids = input_ids[0][self.start_len:]
        num_new = len(new_ids)
        if num_new < 12 or (num_new - self._decoded_len) < 4:
            return False

        # Chỉ decode phần token mới phát sinh thay vì toàn bộ chuỗi từ đầu
        delta_ids = new_ids[self._decoded_len:]
        self._decoded_text += self.tokenizer.decode(delta_ids, skip_special_tokens=False)
        self._decoded_len = num_new
        text = self._decoded_text

        # Kiểm tra token kết thúc đặc biệt (ChatML hoặc EOS)
        if any(tok in text for tok in ("<|im_end|>", "<|endoftext|>", "</s>")):
            return True

        if "def solution" in text and "return " in text:
            # Cắt phần sinh sau dòng chứa return đầu tiên để kiểm tra dấu đóng code block
            ret_idx = text.find("return ")
            after_ret = text[ret_idx:]
            if "\n```" in after_ret or text.rstrip().endswith("```"):
                return True

            # Nếu mô hình viết tiếp ví dụ/hàm khác ở thụt lề 0 mà không đóng fence
            if any(k in after_ret for k in (
                "\ndef ", "\nclass ", "\nprint(", "\n# Example", "\n# Ví dụ", "\nif __name__"
            )):
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
    Bảo toàn các import ở trước def solution và xử lý mượt mà khi fence ``` bị thiếu dấu đóng.
    
    Args:
        text (str): Toàn bộ văn bản do mô hình sinh ra.
        
    Returns:
        str: Đoạn mã Python đã làm sạch.
    """
    if not text or not text.strip():
        return ""

    text = text.strip()

    # Trường hợp 1: Có khối ```python ... ``` hoặc ```py ... ``` hoặc ``` ... ``` hoàn chỉnh
    match_closed = re.search(r"```(?:python|py)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if match_closed:
        code = match_closed.group(1).strip()
        return cut_after_first_solution(code)

    # Trường hợp 2: Khối ```python hoặc ```py hoặc ``` chưa đóng (unclosed fence)
    match_unclosed = re.search(r"```(?:python|py)?\s*\n?(.*)", text, re.DOTALL | re.IGNORECASE)
    if match_unclosed:
        candidate = match_unclosed.group(1).strip()
        if "def solution" in candidate:
            return cut_after_first_solution(candidate)

    # Trường hợp 3: Viết trực tiếp def solution( hoặc có import phía trước
    if "def solution" in text:
        lines = text.splitlines()
        code_lines = []
        found_sol = False
        for line in lines:
            if not found_sol:
                if re.match(r"^\s*(import|from)\s+", line) or line.strip().startswith("#"):
                    code_lines.append(line)
                elif re.match(r"^\s*def\s+solution\s*\(", line):
                    found_sol = True
                    code_lines.append(line)
            else:
                if line.strip() == "```":
                    break
                code_lines.append(line)
        if found_sol:
            return cut_after_first_solution("\n".join(code_lines).strip())

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


def build_balanced_device_map(
    model_id: str,
    num_gpus: int,
    trust_remote_code: bool = True
) -> Optional[Dict[str, int]]:
    """
    Xây dựng device_map phân bổ tối ưu các tầng của mô hình qua nhiều GPU.
    
    Đặc thù mô hình Causal LM (Qwen2.5, LLaMA, Mistral, Gemma):
    - GPU cuối cùng luôn chứa `lm_head` (chiếm ~1.5GB ở float16 với vocab 152k của Qwen) và `model.norm`.
    - Ngoài ra, GPU cuối cùng tính toán logits ma trận [batch, seq_len, vocab_size].
    - Vì vậy, nếu chia số tầng 50-50, GPU cuối cùng sẽ luôn bị OOM vì phải gánh thêm lm_head + activation.
    - Giải pháp: GPU cuối cùng nhận ÍT HƠN 4-6 tầng transformer (tùy model size).
      Số tầng này được chuyển sang GPU 0 (hoặc các GPU đầu).
    
    Ví dụ:
    - Qwen2.5-Coder-14B (48 layers) trên 2 GPU:
      • GPU 0: embed_tokens + layers 0 -> 26 (27 layers) => ~8.8 GB (INT8)
      • GPU 1: layers 27 -> 47 (21 layers) + norm + lm_head => ~8.5 GB (INT8)
      => Cả 2 GPU đều dư ~6 GB VRAM cho Attention/KV-Cache, hoàn toàn không bị OOM!
    - Qwen2.5-Coder-7B (28 layers) trên 2 GPU:
      • GPU 0: embed_tokens + layers 0 -> 15 (16 layers) => ~4.5 GB (INT8)
      • GPU 1: layers 16 -> 27 (12 layers) + norm + lm_head => ~4.2 GB (INT8)
    """
    if num_gpus < 2:
        return None
    try:
        from transformers import AutoConfig
        config = AutoConfig.from_pretrained(model_id, trust_remote_code=trust_remote_code)
        num_layers = getattr(config, "num_hidden_layers", None) or getattr(config, "n_layer", None) or getattr(config, "num_layers", None)
        if not num_layers or not isinstance(num_layers, int) or num_layers < 2:
            return None
        
        # Xác định tiền tố tầng dựa trên kiến trúc
        model_type = str(getattr(config, "model_type", "")).lower()
        arch = ""
        if hasattr(config, "architectures") and config.architectures:
            arch = str(config.architectures[0]).lower()
        
        if "gpt_neox" in model_type or "pythia" in model_type:
            layer_prefix = "gpt_neox.layers"
            embed_name = "gpt_neox.embed_in"
            norm_name = "gpt_neox.final_layer_norm"
            head_name = "embed_out"
            extra_modules = []
        elif "qwen" in model_type and "qwen2" not in model_type and "coder" not in arch and "qwen2" not in arch:
            layer_prefix = "transformer.h"
            embed_name = "transformer.wte"
            norm_name = "transformer.ln_f"
            head_name = "lm_head"
            extra_modules = []
        else:
            # Chuẩn phổ biến nhất: Qwen2, Qwen2.5, LLaMA 1/2/3, Mistral, Gemma, Phi-3, Starcoder2
            layer_prefix = "model.layers"
            embed_name = "model.embed_tokens"
            norm_name = "model.norm"
            head_name = "lm_head"
            extra_modules = ["model.rotary_emb"]

        last_gpu = num_gpus - 1
        
        # Tính toán số tầng bớt đi ở GPU cuối để bù trừ dung lượng khổng lồ của lm_head (vocab 152k)
        head_equiv_layers = min(6, max(2, int(num_layers * 0.12)))
        
        device_map: Dict[str, int] = {}
        
        if num_gpus == 2:
            # Chia cho 2 GPU: GPU 0 gánh nhiều hơn head_equiv_layers tầng
            split_idx = (num_layers // 2) + (head_equiv_layers // 2)
            # Giới hạn an toàn split_idx không vượt quá num_layers - 1
            split_idx = max(1, min(split_idx, num_layers - 2))
            for i in range(num_layers):
                device_map[f"{layer_prefix}.{i}"] = 0 if i < split_idx else 1
            print(f"[LLMClient] ⚖️ Phân bổ tầng cân bằng 2 GPU ({num_layers} tầng): GPU 0 nhận {split_idx} tầng (0..{split_idx-1}), GPU 1 nhận {num_layers - split_idx} tầng ({split_idx}..{num_layers-1}) + lm_head")
        else:
            # Chia cho N > 2 GPU
            base_layers = (num_layers - head_equiv_layers) // num_gpus
            curr = 0
            for g in range(num_gpus - 1):
                cnt = base_layers + (1 if g < (num_layers - head_equiv_layers) % num_gpus else 0)
                for _ in range(cnt):
                    if curr < num_layers:
                        device_map[f"{layer_prefix}.{curr}"] = g
                        curr += 1
            while curr < num_layers:
                device_map[f"{layer_prefix}.{curr}"] = last_gpu
                curr += 1

        # Gán các module gốc
        device_map[embed_name] = 0
        device_map[norm_name] = last_gpu
        device_map[head_name] = last_gpu
        
        for extra in extra_modules:
            device_map[extra] = 0
            
        return device_map
    except Exception as e:
        print(f"[LLMClient] Lưu ý: Không tạo được balanced device_map động ({e}), chuyển sang chế độ tự động.")
        return None


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
        
        # Tự động nhận diện thư mục trọng số mô hình offline (hỗ trợ Docker BTC /app/weights/model, /weights, models/...)
        for candidate_path in [
            model_id,
            os.environ.get("DATAMATE_MODEL_ID"),
            "/app/weights/model",
            "/weights",
            "models/Qwen2.5-Coder-14B-Instruct",
        ]:
            if candidate_path and os.path.isdir(str(candidate_path)) and os.path.exists(os.path.join(str(candidate_path), "config.json")):
                model_id = str(candidate_path)
                break

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
        total_vram_gb = sum(
            torch.cuda.get_device_properties(i).total_memory / (1024 ** 3)
            for i in range(num_gpus)
        ) if has_cuda else 0.0
        min_gpu_vram = min(
            (torch.cuda.get_device_properties(i).total_memory / (1024 ** 3) for i in range(num_gpus)),
            default=0.0
        ) if has_cuda else 0.0
        
        # Bật cờ tối ưu phân bổ bộ nhớ PyTorch chống phân mảnh VRAM
        if has_cuda:
            os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
            gpu_names = [torch.cuda.get_device_name(i) for i in range(num_gpus)]
            print(f"[LLMClient] 🖥️ Phát hiện phần cứng: {num_gpus} GPU ({', '.join(gpu_names)}) | Tổng VRAM: {total_vram_gb:.1f} GB")
            # Với GPU T4 (Turing), float16 ổn định và tương thích BitsAndBytes hơn bfloat16
            # Với GPU Blackwell RTX 5090 (máy BTC), bfloat16 hoạt động chuẩn xác với Tensor Cores thế hệ mới
            use_bf16 = torch.cuda.is_bf16_supported() and "T4" not in torch.cuda.get_device_name(0)
            compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
        else:
            compute_dtype = torch.float32

        # Cấu hình lượng tử hóa (mặc định ưu tiên 4-bit NF4: siêu nhẹ, bảo đảm tuyệt đối không OOM)
        quant_mode = (os.environ.get("DATAMATE_QUANTIZATION") or "4bit").lower().strip()
        
        # TỰ ĐỘNG BẢO VỆ OOM: Nếu GPU (<= 16.5GB như Tesla T4) mà nạp mô hình 14B, 8-bit (14GB) dễ gây OOM
        # -> Tự động kích hoạt 4-bit NF4 (~8.5GB tổng) để dành >6GB VRAM cho Attention Forward / KV-Cache!
        is_14b = "14b" in str(self.model_id).lower()
        if has_cuda and is_14b and min_gpu_vram <= 16.5 and quant_mode != "4bit":
            print(f"[LLMClient] ⚠️ Phát hiện phần cứng GPU ({min_gpu_vram:.1f} GB <= 16GB) chạy mô hình 14B.")
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
                "torch_dtype": compute_dtype,
                "low_cpu_mem_usage": True,
                "quantization_config": quant_config,
                "trust_remote_code": True,
                "attn_implementation": "sdpa",
            }
            # PHÂN BỔ ĐỀU BỘ NHỚ CHO ĐA GPU (GPU T4 x 2):
            if num_gpus >= 2:
                balanced_map = build_balanced_device_map(self.model_id, num_gpus, trust_remote_code=True)
                if balanced_map:
                    load_kwargs["device_map"] = balanced_map
                    print(f"[LLMClient] ⚖️ Đã thiết lập Balanced Device Map ({len(balanced_map)} modules) cho {num_gpus} GPU thành công!")
                else:
                    # Fallback max_memory bất đối xứng: GPU 0 nhận nhiều hơn, GPU cuối nhận ít hơn vì gánh lm_head (~1.5GB)
                    max_memory = {}
                    for g_idx in range(num_gpus):
                        vram_gb = torch.cuda.get_device_properties(g_idx).total_memory / (1024 ** 3)
                        limit_gb = max(4, int(vram_gb - 5.5 if g_idx == num_gpus - 1 else vram_gb - 1.5))
                        max_memory[g_idx] = f"{limit_gb}GiB"
                    load_kwargs["device_map"] = "auto"
                    load_kwargs["max_memory"] = max_memory
                    print(f"[LLMClient] ⚖️ Bật chia tải đều qua {num_gpus} GPU: max_memory={max_memory}")
            else:
                load_kwargs["device_map"] = "auto"
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

            # FALLBACK CẤP 1: NẾU DÙNG BALANCED DEVICE MAP THẤT BẠI -> THỬ AUTO DEVICE MAP VỚI ASYMMETRIC MAX_MEMORY
            if has_cuda and isinstance(load_kwargs.get("device_map"), dict):
                print(f"[LLMClient] 🔄 Thử lại với device_map='auto' và asymmetric max_memory...")
                try:
                    gc.collect()
                    torch.cuda.empty_cache()
                    max_memory = {}
                    for g_idx in range(num_gpus):
                        vram_gb = torch.cuda.get_device_properties(g_idx).total_memory / (1024 ** 3)
                        limit_gb = max(4, int(vram_gb - 5.5 if g_idx == num_gpus - 1 else vram_gb - 1.5))
                        max_memory[g_idx] = f"{limit_gb}GiB"
                    load_kwargs["device_map"] = "auto"
                    load_kwargs["max_memory"] = max_memory
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_id,
                        **load_kwargs
                    )
                    self.model.eval()
                    self.is_loaded = True
                    print(f"[LLMClient] ✅ Nạp mô hình với auto device_map thành công!")
                except Exception as e_auto:
                    print(f"[LLMClient] Auto device_map thất bại: {e_auto}")

            # FALLBACK CẤP 2: NẾU ĐANG CHẠY 8-BIT THẤT BẠI HOẶC BỊ OOM -> CHUYỂN SANG 4-BIT NF4
            if not self.is_loaded and has_cuda and quant_mode not in ("4bit", "4-bit", "nf4"):
                print(f"[LLMClient] 🛡️ Fallback cấp 2: Chuyển sang lượng tử hóa 4-bit NF4 (tiết kiệm ~50% VRAM, bảo đảm không OOM)...")
                try:
                    gc.collect()
                    torch.cuda.empty_cache()
                    quant_4bit = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=compute_dtype,
                    )
                    load_kwargs["quantization_config"] = quant_4bit
                    load_kwargs["device_map"] = "auto"
                    load_kwargs.pop("max_memory", None)
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_id,
                        **load_kwargs
                    )
                    self.model.eval()
                    self.is_loaded = True
                    print(f"[LLMClient] ✅ Fallback 4-bit NF4 thành công trên {self.device}!")
                except Exception as e_4bit:
                    print(f"[Lỗi] Nạp mô hình 4-bit thất bại: {e_4bit}")
                    self.is_loaded = False

            # FALLBACK CẤP 3: NẾU THẤT BẠI VÀ HỆ THỐNG CÓ ĐỦ VRAM HOẶC MÔ HÌNH NHỎ
            # Nếu chạy trên máy BTC (2x RTX 5090 = 64GB VRAM) hoặc máy trạm có VRAM lớn:
            # Model 14B nguyên bản (bfloat16) chỉ chiếm ~28GB VRAM.
            # Trên máy có tổng VRAM >= 36GB, hoàn toàn có thể nạp không lượng tử hóa (bfloat16) an toàn 100%!
            can_load_unquantized = (
                (is_14b and total_vram_gb >= 36.0) or
                ("7b" in str(self.model_id).lower() and total_vram_gb >= 20.0) or
                (not is_14b and "7b" not in str(self.model_id).lower() and total_vram_gb >= 8.0)
            )
            if not self.is_loaded and has_cuda and can_load_unquantized:
                print(f"[LLMClient] 🛡️ Fallback cấp 3: Phát hiện hệ thống có VRAM dồi dào ({total_vram_gb:.1f} GB). Thử nạp không lượng tử hóa (torch_dtype={compute_dtype})...")
                try:
                    gc.collect()
                    torch.cuda.empty_cache()
                    fallback_kwargs = {
                        "device_map": "auto",
                        "torch_dtype": compute_dtype,
                        "low_cpu_mem_usage": True,
                        "trust_remote_code": True,
                        "attn_implementation": "sdpa",
                    }
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_id,
                        **fallback_kwargs
                    )
                    self.model.eval()
                    self.is_loaded = True
                    print(f"[LLMClient] ✅ Nạp mô hình không lượng tử hóa thành công: {self.device}")
                except Exception as e_cuda:
                    print(f"[Lỗi] Nạp mô hình không lượng tử hóa thất bại: {e_cuda}")
                    self.is_loaded = False
            else:
                if not self.is_loaded:
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

    def get_gpu_memory_stats(self) -> Dict[str, Any]:
        """Trả về thông số dung lượng VRAM GPU đã sử dụng (đơn vị: GB)."""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            stats = {}
            for i in range(torch.cuda.device_count()):
                allocated = round(torch.cuda.memory_allocated(i) / (1024 ** 3), 2)
                reserved = round(torch.cuda.memory_reserved(i) / (1024 ** 3), 2)
                total = round(torch.cuda.get_device_properties(i).total_memory / (1024 ** 3), 2)
                stats[f"gpu_{i}"] = {
                    "allocated_gb": allocated,
                    "reserved_gb": reserved,
                    "total_gb": total,
                    "free_gb": max(0.0, round(total - reserved, 2)),
                }
            return stats
        return {}

    def print_gpu_stats(self) -> None:
        """In thông số bộ nhớ GPU ra console cho từng card đồ họa."""
        if not (TORCH_AVAILABLE and torch.cuda.is_available()):
            print(f"[GPU Memory] Thiết bị hiện tại: {self.device}")
            return

        try:
            num_g = torch.cuda.device_count()
            parts = []
            for i in range(num_g):
                alloc = round(torch.cuda.memory_allocated(i) / (1024 ** 3), 2)
                res = round(torch.cuda.memory_reserved(i) / (1024 ** 3), 2)
                tot = round(torch.cuda.get_device_properties(i).total_memory / (1024 ** 3), 2)
                free = max(0.0, round(tot - res, 2))
                parts.append(f"GPU {i}: Cấp phát {alloc}GB / Dự trữ {res}GB (Trống ~{free}GB/{tot}GB)")
            print(f"[GPU Memory] 📊 " + " | ".join(parts))
        except Exception as e:
            print(f"[GPU Memory] Thiết bị hiện tại: {self.device} ({e})")

    def _generate_raw(self, messages: List[Dict[str, str]], max_new_tokens: int = 1536) -> str:
        """Thực hiện một lần suy luận thô với cơ chế Greedy Decoding (hỗ trợ cả vLLM Prefix Caching và Transformers)."""
        if not self.is_loaded or self.tokenizer is None:
            return ""

        # QUẢN LÝ NGÂN SÁCH CONTEXT AN TOÀN TRÊN TỪNG PHẦN CỨNG (Text-Level Clean Pruning):
        # - GPU <= 16GB (Tesla T4 trên Kaggle, P100): giới hạn 2,800 tokens để dành >6GB VRAM cho Attention/KV-Cache
        # - GPU >= 24GB (RTX 5090 trên máy BTC, A100, RTX 4090): 8,192 tokens
        num_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 0
        min_vram_gb = min(
            (torch.cuda.get_device_properties(i).total_memory / (1024 ** 3) for i in range(num_gpus)),
            default=15.0
        ) if num_gpus > 0 else 15.0

        MAX_SAFE_INPUT_TOKENS = 8192 if min_vram_gb >= 24.0 else 2800

        # Tỉa text sạch sẽ bảo toàn cấu trúc ChatML (không bao giờ cắt đứt tensor)
        cleaned_messages = [dict(m) for m in messages]
        raw_text_len = sum(len(m.get("content", "")) for m in cleaned_messages)

        if raw_text_len > 7000:
            for m in cleaned_messages:
                if m.get("role") == "system":
                    content = m["content"]
                    # 1. Bỏ khối ví dụ mẫu nếu prompt quá dài
                    if "==================== VÍ DỤ MINH HỌA" in content:
                        parts = content.split("==================== VÍ DỤ MINH HỌA")
                        content = parts[0].strip()
                    # 2. Cắt bớt phần chi tiết cột schema nếu vẫn quá dài (> 4,500 ký tự)
                    if len(content) > 4500 and "### CHI TIẾT CÁC BẢNG VÀ CỘT:" in content:
                        head_sec, detail_sec = content.split("### CHI TIẾT CÁC BẢNG VÀ CỘT:", 1)
                        detail_lines = detail_sec.splitlines()
                        content = f"{head_sec}\n### CHI TIẾT CÁC BẢNG VÀ CỘT:\n" + "\n".join(detail_lines[:50])
                    m["content"] = content

        chat_text = self.tokenizer.apply_chat_template(
            cleaned_messages,
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

        inputs = self.tokenizer([chat_text], return_tensors="pt").to(self.model.device)
        start_len = inputs.input_ids.shape[1]

        # Nếu sau khi tỉa text vẫn vượt ngưỡng MAX_SAFE_INPUT_TOKENS, tiếp tục nén ở tầng text sạch
        if start_len > MAX_SAFE_INPUT_TOKENS:
            print(f"[LLMClient] ⚡ Prompt dài ({start_len} tokens). Tự động nén gọn System Prompt xuống {MAX_SAFE_INPUT_TOKENS} tokens...")
            ratio = max(0.4, (MAX_SAFE_INPUT_TOKENS - 400) / max(start_len, 1))
            for m in cleaned_messages:
                if m.get("role") == "system":
                    m["content"] = m["content"][:int(len(m["content"]) * ratio)].strip()
            chat_text = self.tokenizer.apply_chat_template(
                cleaned_messages,
                tokenize=False,
                add_generation_prompt=True
            )
            inputs = self.tokenizer([chat_text], return_tensors="pt").to(self.model.device)
            start_len = inputs.input_ids.shape[1]

        stopping_criteria = StoppingCriteriaList([CodeBlockEndStoppingCriteria(self.tokenizer, start_len)])

        gen_tokens = min(max_new_tokens, 768) if max_new_tokens > 0 else 512
        try:
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
        except (torch.cuda.OutOfMemoryError, RuntimeError) as oom_err:
            if "out of memory" in str(oom_err).lower():
                print(f"[LLMClient] ⚠️ Cảnh báo CUDA OOM: {oom_err}. Dọn dẹp cache và khởi tạo prompt tối giản...")
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                try:
                    # Tạo prompt tối giản nguyên vẹn chuẩn ChatML, không cắt đứt tensor
                    oom_user_content = messages[-1].get("content", "")
                    oom_messages = [
                        {
                            "role": "system",
                            "content": (
                                "Bạn là chuyên gia lập trình Python phân tích dữ liệu. "
                                "Chỉ viết duy nhất một hàm `def solution(data):` trả về kết quả số hoặc chuỗi hoặc list. "
                                "Dùng get_sales_table, clean_date, clean_num, get_amount_col, get_qty_col."
                            ),
                        },
                        {"role": "user", "content": oom_user_content},
                    ]
                    oom_chat = self.tokenizer.apply_chat_template(oom_messages, tokenize=False, add_generation_prompt=True)
                    retry_inputs = self.tokenizer([oom_chat], return_tensors="pt").to(self.model.device)
                    retry_start_len = retry_inputs.input_ids.shape[1]
                    retry_stopping = StoppingCriteriaList([CodeBlockEndStoppingCriteria(self.tokenizer, retry_start_len)])

                    with torch.inference_mode():
                        output_tokens = self.model.generate(
                            **retry_inputs,
                            max_new_tokens=min(gen_tokens, 384),
                            do_sample=False,
                            temperature=None,
                            top_p=None,
                            top_k=None,
                            repetition_penalty=1.05,
                            use_cache=True,
                            stopping_criteria=retry_stopping,
                            pad_token_id=self.tokenizer.eos_token_id,
                            eos_token_id=self.tokenizer.eos_token_id
                        )
                    inputs = retry_inputs
                    print(f"[LLMClient] ✅ Phục hồi OOM thành công với prompt ChatML tinh gọn!")
                except Exception as retry_err:
                    print(f"[LLMClient] ❌ Thử lại sau OOM vẫn gặp lỗi ({retry_err}). Pipeline sẽ fallback an toàn.")
                    import gc
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    return ""
            else:
                raise oom_err

        in_ids = inputs["input_ids"] if isinstance(inputs, dict) else inputs.input_ids
        generated_token_ids = output_tokens[0][len(in_ids[0]):]
        result_text = self.tokenizer.decode(generated_token_ids, skip_special_tokens=True)

        del inputs, output_tokens
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

        try:
            from datamate.llm_execution.sandbox import sanitize_code_syntax
        except ImportError:
            try:
                from src.datamate.llm_execution.sandbox import sanitize_code_syntax
            except ImportError:
                sanitize_code_syntax = lambda x: x  # noqa: E731

        # Lần sinh mã đầu tiên
        raw_text = self._generate_raw(messages, max_new_tokens=max_new_tokens)
        if not raw_text or not raw_text.strip():
            # _generate_raw trả về rỗng thường do CUDA OOM đã hết ngưỡng phục hồi -> fallback ngay, tránh retry gây OOM dây chuyền
            print("[Cảnh báo] Không nhận được đầu ra từ mô hình (có thể do CUDA OOM). Sử dụng fallback abstain an toàn.")
            self.last_latency_ms = int((time.time() - start_time) * 1000)
            return (
                "def solution(data):\n"
                "    # Fallback an toàn khi mô hình không sinh được mã\n"
                "    return None\n"
            )

        code = sanitize_code_syntax(extract_python_code(raw_text))
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
            if not raw_retry or not raw_retry.strip():
                error_msg = "Mô hình không sinh được mã khi tự sửa lỗi (có thể do OOM)"
                break
            retry_code = sanitize_code_syntax(extract_python_code(raw_retry))
            retry_valid, retry_error = validate_code(retry_code)

            if retry_valid:
                code = retry_code
                is_valid = True
                print("[Tự sửa lỗi] Sửa mã nguồn thành công.")
                break
            else:
                code = retry_code or code
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
