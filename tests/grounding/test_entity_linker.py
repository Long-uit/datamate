"""
test_entity_linker.py — Kiểm thử bộ liên kết thực thể tiếng Việt (Task 2 Phase 3).
"""

from pathlib import Path
import pandas as pd
import pytest

from datamate.grounding.entity_linker import (
    expand_abbreviations,
    extract_candidates_from_business,
    link_entities,
    normalize_entity_text,
    remove_accents,
)
from datamate.ingestion.loader import BusinessData, TableInfo
from datamate.types import Candidate


class TestEntityLinker:
    def test_normalization_and_accents(self):
        text = "  Cà Phê Sữa Đá (L)!! "
        norm = normalize_entity_text(text)
        assert "cà phê sữa đá" in norm
        assert "(l)" in norm

        unacc = remove_accents(norm)
        assert "ca phe sua da" in unacc

    def test_abbreviation_expansion(self):
        query = "cf sữa đá size l và sp mới"
        exp = expand_abbreviations(query)
        assert "cà phê" in exp
        assert "sản phẩm" in exp

    def test_exact_and_fuzzy_link_entities(self):
        candidates = [
            "Cà phê sữa đá",
            "Trà đào cam sả",
            "Nước ngọt Sting dâu chai 330ml",
            "Bạc xỉu nóng",
        ]

        # 1. Khớp gần chính xác với viết tắt: "cf sữa"
        m1 = link_entities("Cho mình 1 ly cf sữa với", candidates, threshold=0.5)
        assert len(m1) > 0
        assert m1[0].matched_value == "Cà phê sữa đá"

        # 2. Khớp không dấu: "sting dau"
        m2 = link_entities("Giá của sting dau chai 330ml", candidates, threshold=0.5)
        assert len(m2) > 0
        assert m2[0].matched_value == "Nước ngọt Sting dâu chai 330ml"

    def test_extract_candidates_from_business(self):
        df_prod = pd.DataFrame({
            "Mã SKU": ["SKU01", "SKU02"],
            "Tên sản phẩm": ["Cà phê đen", "Bạc xỉu"],
        })
        t1 = TableInfo(
            table_id="t_01",
            source_file=Path("menu.csv"),
            fixed_file_name="menu.csv",
            sheet_name=None,
            df=df_prod,
            header_row_detected=0,
            n_rows=2,
            columns=list(df_prod.columns),
        )
        bd = BusinessData(business_id="cafe_shop", tables=[t1])

        cands = extract_candidates_from_business(bd)
        cand_values = [c.value for c in cands]
        assert "Cà phê đen" in cand_values
        assert "Bạc xỉu" in cand_values
