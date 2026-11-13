"""
rulebook.py — Bộ nạp, phân tích cấu trúc nguyên tử (Atomic Clause Parser)
và truy hồi điều khoản Rulebook tổng quát hóa theo ngữ cảnh câu hỏi & cửa hàng.

Nguyên lý thiết kế (Zero-Overfitting):
1. Phân rã tự động mọi tệp `rulebook.md` (train, public_test, private_test) thành các
   điều khoản nguyên tử (`RuleClause`) từ bảng Markdown (`| Luật | Mặc định |`) và danh sách mục.
2. Tự động nhận diện các mẫu biến số khái quát trong tên luật (như `<đơn vị>`, `ngày X`,
   `tháng M/Y`, `N ngày`, `quý Q`) và biên dịch thành biểu thức khớp cấu trúc tổng quát.
3. Truy hồi đa tín hiệu (Multi-Signal Retrieval) kết hợp:
   - Tín hiệu từ vựng & cụm từ câu hỏi (có dấu & không dấu).
   - Tín hiệu cấu trúc mẫu câu hỏi (Structural Template Matching).
   - Tín hiệu ngữ cảnh cửa hàng (Schema bảng/cột & README ngành nghề của shop),
     giúp tự động kích hoạt luật của các ngành mới xuất hiện trong `private_test`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Optional
import unicodedata

log = logging.getLogger(__name__)

_RULEBOOK_CACHE: dict[str, str] = {}
_PARSED_RULEBOOK_CACHE: dict[int, list["RuleClause"]] = {}


def _strip_accents(text: str) -> str:
    s = unicodedata.normalize("NFD", str(text))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def _norm_text(text: str, strip_accents: bool = False) -> str:
    s = unicodedata.normalize("NFC", str(text)).lower().strip()
    if strip_accents:
        s = _strip_accents(s)
    s = re.sub(r"[^\w\s%<>]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_STOPWORDS = {
    "la", "cua", "va", "hoac", "trong", "theo", "voi", "cac", "nhung", "mot",
    "co", "khong", "duoc", "tinh", "khi", "thi", "neu", "cho", "tu", "den",
    "ra", "ve", "tren", "duoi", "o", "tai", "nay", "do", "ay", "bao", "nhieu",
    "may", "nao", "gi", "ai", "dau", "sao", "cung", "nhu", "moi", "tung",
}


@dataclass
class RuleClause:
    section_id: str
    section_title: str
    subsection_title: str
    term: str
    definition: str
    is_industry_rule: bool = False
    is_core_invariant: bool = False
    norm_term: str = ""
    unacc_term: str = ""
    norm_def: str = ""
    unacc_def: str = ""
    term_phrases: list[str] = field(default_factory=list)
    unacc_phrases: list[str] = field(default_factory=list)
    term_tokens: set[str] = field(default_factory=set)
    unacc_tokens: set[str] = field(default_factory=set)
    structural_regex: Optional[re.Pattern] = None

    def format_compact(self) -> str:
        loc = f"{self.section_title} > {self.subsection_title}" if self.subsection_title else self.section_title
        loc_short = re.sub(r"^\d+\.\s*", "§", loc)
        if self.term:
            return f"- [{loc_short}] **{self.term}**: {self.definition}"
        return f"- [{loc_short}] {self.definition}"


def _compile_structural_pattern(term: str) -> Optional[re.Pattern]:
    """
    Biên dịch tên luật có chứa biến số tổng quát (như 'Bán được bao nhiêu <đơn vị>',
    'Trung bình mỗi ngày thứ X của kỳ', 'Hàng hết hạn trong N ngày tới', 'Giá bán X ngày D')
    thành biểu thức chính quy không dấu để khớp mọi câu hỏi thực tế.
    """
    if not term:
        return None
    has_placeholder = bool(
        re.search(r"<[^>]+>|\b[XYNMQD]\b", term)
    )
    if not has_placeholder:
        return None

    parts = [p.strip() for p in re.split(r"[,;/]", term) if p.strip()]
    regex_branches = []
    for p in parts:
        u = _norm_text(p, strip_accents=True)
        if not u:
            continue
        # Thay thế các biến placeholder bằng mẫu tổng quát
        u_pat = re.sub(r"<[^>]+>", r"(?:\\w+(?:\\s+\\w+)?)", u)
        u_pat = re.sub(r"\b[nmq]\b", r"\\d+", u_pat)
        u_pat = re.sub(r"\b[xyd]\b", r"(?:[\\w/\\-]+(?:\\s+[\\w/\\-]+){0,3})", u_pat)
        u_pat = re.sub(r"\s+", r"\\s+", u_pat)
        regex_branches.append(u_pat)

    if not regex_branches:
        return None
    try:
        return re.compile(r"\b(?:" + "|".join(regex_branches) + r")\b", re.IGNORECASE)
    except Exception:
        return None


def parse_rulebook(rulebook_content: str) -> list[RuleClause]:
    """
    Phân tích tệp `rulebook.md` bất kỳ thành danh sách các điều khoản nguyên tử `RuleClause`.
    Có lưu cache trong RAM để không phải phân tích lại giữa các câu hỏi.
    """
    if not rulebook_content or not rulebook_content.strip():
        return []

    cache_key = hash(rulebook_content)
    if cache_key in _PARSED_RULEBOOK_CACHE:
        return _PARSED_RULEBOOK_CACHE[cache_key]

    clauses: list[RuleClause] = []
    current_sec_id = "0"
    current_sec_title = "Quy tắc chung"
    current_sub_title = ""

    lines = rulebook_content.splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # 1. Phát hiện tiêu đề cấp 1, 2, 3
        m_h2 = re.match(r"^##\s+(?:(\d+)\.\s*)?(.+)$", line)
        if m_h2:
            current_sec_id = m_h2.group(1) or "0"
            current_sec_title = f"{current_sec_id}. {m_h2.group(2).strip()}" if m_h2.group(1) else m_h2.group(2).strip()
            current_sub_title = ""
            continue

        m_h3 = re.match(r"^###\s+(.+)$", line)
        if m_h3:
            current_sub_title = m_h3.group(1).strip()
            continue

        if line.startswith("# "):
            continue

        # Bỏ qua mục 9 (bảng format JSON mẫu đã có sẵn trong System Prompt) để tiết kiệm context,
        # nhưng giữ lại các dòng quy tắc làm tròn / bằng nhau / chuỗi / danh sách của mục 9.
        if current_sec_id == "9" and line.startswith("|"):
            continue

        # 2. Phân tích dòng bảng Markdown: | Cột 1 | Cột 2 |
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            c0, c1 = cells[0], cells[1]
            # Bỏ qua dòng tiêu đề bảng và dòng phân cách |---|---|
            if re.match(r"^[\-\s:]+$", c0) or c0.lower() in ("luật", "cách nói", "cách ghi", "từ", "type"):
                continue

            term_clean = re.sub(r"\*\*|\*", "", c0).strip()
            def_clean = c1.strip()
        elif line.startswith("- ") or (current_sec_id == "0" and "**Hôm nay**" in line):
            bullet_body = line[2:].strip() if line.startswith("- ") else line
            m_bold = re.match(r"^\*\*([^*]+)\*\*[:\s]*(.+)$", bullet_body)
            if m_bold:
                term_clean = m_bold.group(1).strip().rstrip(":")
                def_clean = m_bold.group(2).strip()
            else:
                term_clean = ""
                def_clean = bullet_body
        else:
            continue

        if not def_clean:
            continue

        norm_t = _norm_text(term_clean, strip_accents=False)
        unacc_t = _norm_text(term_clean, strip_accents=True)
        norm_d = _norm_text(def_clean, strip_accents=False)
        unacc_d = _norm_text(def_clean, strip_accents=True)

        # Tách các cụm đồng nghĩa trong cột Luật (ngăn cách bởi dấu phẩy hoặc /)
        raw_sub_phrases = [p.strip() for p in re.split(r"[,;/]", term_clean) if p.strip()]
        t_phrases = [_norm_text(p, strip_accents=False) for p in raw_sub_phrases if len(_norm_text(p)) >= 2]
        u_phrases = [_norm_text(p, strip_accents=True) for p in raw_sub_phrases if len(_norm_text(p, True)) >= 2]

        t_tokens = {w for w in re.findall(r"\w+", norm_t) if len(w) >= 2 and _strip_accents(w) not in _STOPWORDS}
        u_tokens = {w for w in re.findall(r"\w+", unacc_t) if len(w) >= 2 and w not in _STOPWORDS}

        is_ind = (current_sec_id == "6") or bool(current_sub_title)
        is_core = (
            current_sec_id == "0"
            or (current_sec_id == "1" and any(k in unacc_t for k in ["don tinh vao doanh thu", "doanh thu mot don", "so don"]))
            or (current_sec_id == "9" and any(k in unacc_t for k in ["lam tron", "bang nhau"]))
        )

        clause = RuleClause(
            section_id=current_sec_id,
            section_title=current_sec_title,
            subsection_title=current_sub_title,
            term=term_clean,
            definition=def_clean,
            is_industry_rule=is_ind,
            is_core_invariant=is_core,
            norm_term=norm_t,
            unacc_term=unacc_t,
            norm_def=norm_d,
            unacc_def=unacc_d,
            term_phrases=t_phrases,
            unacc_phrases=u_phrases,
            term_tokens=t_tokens,
            unacc_tokens=u_tokens,
            structural_regex=_compile_structural_pattern(term_clean),
        )
        clauses.append(clause)

    _PARSED_RULEBOOK_CACHE[cache_key] = clauses
    return clauses


def retrieve_relevant_rulebook_clauses(
    rulebook_content: str,
    question: str,
    schema_str: str = "",
    business_note: str = "",
    max_chars: int = 1400,
) -> str:
    """
    Truy hồi các điều khoản Rulebook nguyên tử phù hợp nhất với câu hỏi và đặc thù cửa hàng.
    Hoạt động tổng quát trên mọi `rulebook.md` (kể cả khi BTC thêm luật mới hoặc ngành mới ở private_test).
    """
    clauses = parse_rulebook(rulebook_content)
    if not clauses:
        return ""

    q_norm = _norm_text(question, strip_accents=False)
    q_unacc = _norm_text(question, strip_accents=True)
    q_tokens = {w for w in re.findall(r"\w+", q_norm) if len(w) >= 2 and _strip_accents(w) not in _STOPWORDS}
    q_unacc_tokens = {w for w in re.findall(r"\w+", q_unacc) if len(w) >= 2 and w not in _STOPWORDS}

    shop_ctx_unacc = _norm_text(f"{schema_str or ''} {business_note or ''}", strip_accents=True)

    scored: list[tuple[float, int, RuleClause]] = []

    for idx, c in enumerate(clauses):
        score = 0.0

        # 1. Luật nền tảng cốt lõi (Core Invariants)
        if c.is_core_invariant:
            score += 3.5

        # 2. Khớp cụm từ trực tiếp trong cột Luật (Term Phrase Match) - Tín hiệu mạnh nhất
        for ph in c.term_phrases:
            if len(ph) >= 3 and ph in q_norm:
                score += 12.0 + min(len(ph.split()), 4) * 1.5
        for uph in c.unacc_phrases:
            if len(uph) >= 4 and uph in q_unacc:
                score += 8.0 + min(len(uph.split()), 4) * 1.0

        # 3. Khớp cấu trúc mẫu câu hỏi có biến số (Structural Template Pattern)
        if c.structural_regex is not None and c.structural_regex.search(q_unacc):
            score += 14.0

        # 4. Độ phủ từ khóa giữa câu hỏi và tên Luật (Token Overlap)
        if c.unacc_tokens:
            common_u = q_unacc_tokens & c.unacc_tokens
            if common_u:
                overlap_ratio = len(common_u) / len(c.unacc_tokens)
                score += len(common_u) * 2.5 + (4.0 if overlap_ratio >= 0.6 else 0.0)
        if c.term_tokens:
            common_t = q_tokens & c.term_tokens
            if common_t:
                score += len(common_t) * 2.0

        # 5. Độ phủ từ khóa với nội dung định nghĩa Luật (Definition Overlap)
        def_tokens = {w for w in re.findall(r"\w+", c.unacc_def) if len(w) >= 3 and w not in _STOPWORDS}
        common_def = q_unacc_tokens & def_tokens
        if common_def:
            score += min(len(common_def) * 0.8, 4.0)

        # 6. Tín hiệu Ngành nghề & Schema cửa hàng (Domain & Shop Context Alignment)
        if c.is_industry_rule and c.subsection_title:
            ind_unacc = _norm_text(c.subsection_title, strip_accents=True)
            ind_words = [w for w in ind_unacc.split() if len(w) >= 3 and w not in ("cua", "hang", "tiem", "quan")]
            # Nếu tên ngành xuất hiện trong câu hỏi hoặc trong Schema/README của shop
            in_question = bool(ind_unacc and ind_unacc in q_unacc) or any(w in q_unacc_tokens for w in ind_words)
            in_shop = bool(ind_unacc and ind_unacc in shop_ctx_unacc) or (
                len(ind_words) > 0 and all(w in shop_ctx_unacc for w in ind_words)
            )
            if in_question:
                score += 8.0
            elif in_shop and score > 0:
                score += 5.0
            elif not in_question and not in_shop:
                # Phạt nhẹ luật của ngành khác nếu shop và câu hỏi không liên quan tới ngành đó
                score -= 5.0

        if score > 1.5:
            scored.append((score, idx, c))

    scored.sort(key=lambda x: (-x[0], x[1]))

    selected_indices: list[int] = []
    total_len = 0
    for score, idx, c in scored:
        line_str = c.format_compact()
        if total_len + len(line_str) + 1 <= max_chars:
            selected_indices.append(idx)
            total_len += len(line_str) + 1
        if len(selected_indices) >= 12:
            break

    # Giữ nguyên thứ tự xuất hiện tự nhiên trong Rulebook để LLM dễ đọc
    selected_indices.sort()
    return "\n".join(clauses[i].format_compact() for i in selected_indices)


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
    global _RULEBOOK_CACHE, _PARSED_RULEBOOK_CACHE
    _RULEBOOK_CACHE.clear()
    _PARSED_RULEBOOK_CACHE.clear()
