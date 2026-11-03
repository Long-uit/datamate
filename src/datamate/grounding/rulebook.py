"""
rulebook.py — Nạp và quản lý nội dung Rulebook theo split.

Rulebook có thể khác nhau giữa các split (train, public_test, private_test).
Module này cung cấp hàm load_rulebook an toàn, có cache để tránh đọc đĩa nhiều lần.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_RULEBOOK_CACHE: dict[str, str] = {}


def find_rulebook_path(hint: Optional[str | Path] = None) -> Optional[Path]:
    """Tìm đường dẫn tệp rulebook.md từ gợi ý đường dẫn."""
    if hint:
        p = Path(hint)
        candidates = []
        if p.is_file() and p.name == "rulebook.md":
            candidates.append(p)
        else:
            candidates.extend([
                p / "rulebook.md",
                p.parent / "rulebook.md",
            ])
        for c in candidates:
            if c.exists() and c.is_file():
                return c.resolve()
        return None

    root = Path.cwd()
    fallback_candidates = [
        root / "competition_data" / "public_test" / "rulebook.md",
        root / "competition_data" / "train" / "rulebook.md",
        root / "rulebook.md",
    ]

    for c in fallback_candidates:
        if c.exists() and c.is_file():
            return c.resolve()

    return None


def load_rulebook(split_dir: str | Path = "competition_data/train", use_cache: bool = True) -> str:
    """
    Đọc nội dung tệp rulebook.md của split dữ liệu tương ứng.
    
    Args:
        split_dir: Đường dẫn thư mục chứa rulebook.md hoặc đường dẫn trực tiếp tới tệp.
        use_cache: Có lưu cache nội dung trong bộ nhớ hay không.
        
    Returns:
        str: Nội dung rulebook.md hoặc chuỗi rỗng nếu không tìm thấy tệp.
    """
    global _RULEBOOK_CACHE

    target = find_rulebook_path(split_dir)
    if not target or not target.exists():
        log.warning("Không tìm thấy rulebook.md tại gợi ý: %s", split_dir)
        return ""

    key = str(target.resolve())
    if use_cache and key in _RULEBOOK_CACHE:
        return _RULEBOOK_CACHE[key]

    try:
        content = target.read_text(encoding="utf-8-sig", errors="replace").strip()
        if use_cache:
            _RULEBOOK_CACHE[key] = content
        return content
    except Exception as exc:
        log.warning("Không thể đọc %s: %s", target, exc)
        return ""


def clear_rulebook_cache() -> None:
    """Xóa cache rulebook."""
    global _RULEBOOK_CACHE
    _RULEBOOK_CACHE.clear()
