"""
test_entity_linker.py — Kiểm thử bộ liên kết thực thể tiếng Việt (grounding_feasibility).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pandas as pd

from datamate.grounding_feasibility.entity_linker import (
    expand_abbreviations,
    extract_candidates_from_business,
    link_entities,
    normalize_entity_text,
    remove_accents,
    best_phrase_similarity,
)
from datamate.ingestion_schema.loader import BusinessData, TableInfo


class TestEntityLinker(unittest.TestCase):
    def test_normalization_and_accents(self):
        text = "  Cà Phê Sữa Đá (L)!! "
        norm = normalize_entity_text(text)
        self.assertIn("cà phê sữa đá", norm)
        self.assertIn("(l)", norm)

        unacc = remove_accents(norm)
        self.assertIn("ca phe sua da", unacc)

    def test_abbreviation_expansion(self):
        query = "cf sữa đá size l và sp mới"
        exp = expand_abbreviations(query)
        self.assertIn("cà phê", exp)
        self.assertIn("sản phẩm", exp)

    def test_exact_and_fuzzy_link_entities(self):
        candidates = [
            "Cà phê sữa đá",
            "Trà đào cam sả",
            "Nước ngọt Sting dâu chai 330ml",
            "Bạc xỉu nóng",
        ]

        m1 = link_entities("Cho mình 1 ly cf sữa với", candidates, threshold=0.5)
        self.assertGreater(len(m1), 0)
        self.assertEqual(m1[0].matched_value, "Cà phê sữa đá")

        m2 = link_entities("Giá của sting dau chai 330ml", candidates, threshold=0.5)
        self.assertGreater(len(m2), 0)
        self.assertEqual(m2[0].matched_value, "Nước ngọt Sting dâu chai 330ml")

    def test_diluted_similarity_long_query(self):
        candidates = [
            "Cà phê sữa đá",
            "Trà đào cam sả",
            "Bạc xỉu nóng",
        ]
        long_query = "Cho mình hỏi giá 1 ly cf sữa ở quán là bao nhiêu tiền vậy shop"
        m = link_entities(long_query, candidates, threshold=0.6)
        self.assertGreater(len(m), 0)
        self.assertEqual(m[0].matched_value, "Cà phê sữa đá")
        self.assertGreaterEqual(m[0].score, 0.7)

    def test_word_boundary_avoids_substring_false_positive(self):
        candidates = ["Ao", "Quan"]

        m_neg = link_entities("Shop báo giá cho tôi sản phẩm mới", candidates, threshold=0.5)
        self.assertEqual(len(m_neg), 0)

        m_pos = link_entities("Shop có bán áo thun không", candidates, threshold=0.5)
        self.assertGreater(len(m_pos), 0)
        self.assertEqual(m_pos[0].matched_value, "Ao")

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
        self.assertIn("Cà phê đen", cand_values)
        self.assertIn("Bạc xỉu", cand_values)

    def test_exclude_measure_units_and_quantity_columns(self):
        # Kiểm tra không trích xuất đơn vị/số lượng từ cột Số lượng sản phẩm hay Đơn vị tính
        df_order = pd.DataFrame({
            "Mã đơn hàng": ["ORD01", "ORD02"],
            "Tên sản phẩm": ["Trà sữa trân châu", "Trà đào"],
            "Số lượng sản phẩm": ["1 ly", "2 ly"],
            "Đơn vị tính": ["ly", "ly"],
        })
        t1 = TableInfo(
            table_id="t_01",
            source_file=Path("orders.csv"),
            fixed_file_name="orders.csv",
            sheet_name=None,
            df=df_order,
            header_row_detected=0,
            n_rows=2,
            columns=list(df_order.columns),
        )
        bd = BusinessData(business_id="tea_shop", tables=[t1])
        cands = extract_candidates_from_business(bd)
        cand_values = [c.value for c in cands]

        # Phải có sản phẩm trà
        self.assertIn("Trà sữa trân châu", cand_values)
        self.assertIn("Trà đào", cand_values)
        # Tuyệt đối KHÔNG có '1 ly', '2 ly', 'ly'
        self.assertNotIn("1 ly", cand_values)
        self.assertNotIn("2 ly", cand_values)
        self.assertNotIn("ly", cand_values)

        # Kiểm tra link_entities không khớp nhầm 'ly' trong câu hỏi
        m = link_entities("nhóm trà có mặt hàng nào bán được nhiều ly nhất?", cands)
        matched_values = [item.matched_value for item in m]
        self.assertNotIn("1 ly", matched_values)
        self.assertNotIn("2 ly", matched_values)
        self.assertNotIn("ly", matched_values)


if __name__ == "__main__":
    unittest.main()

