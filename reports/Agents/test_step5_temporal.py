"""
Unit tests cho Bước 5 — Temporal Grounder đưa vào prompt:
1. Bảng test thuần túy "biểu thức -> khoảng ngày" [start_date, end_date] và kỳ so sánh [comparison_start, comparison_end]
   không cần nạp dữ liệu doanh nghiệp:
   - hôm nay / bữa nay / hnay
   - hôm qua / bữa qua / hqua / hom qua / bua qua
   - tuần này / tuần trước (có dấu và không dấu)
   - tháng này / từ đầu tháng này đến hết hôm nay (tránh lỗi chỉ lấy 1 ngày hôm nay so với nửa tháng trước)
   - N ngày gần nhất / N ngày qua (vắt qua ranh giới tháng, ví dụ 28/05 -> 03/06, tránh lỗi day >= 27 & day <= 3)
   - Tết năm Y và trước Tết năm Y theo calendar.csv
   - Các khoảng so sánh: cùng kỳ tháng trước, kỳ trước / tháng trước, cùng kỳ năm trước, N ngày kể từ ngày X so với N ngày ngay trước ngày đó.
2. Kiểm tra prompt đưa sẵn các hằng số START_DATE, END_DATE, COMP_START_DATE, COMP_END_DATE vào prompt để LLM không tự tính ngày.
"""

from pathlib import Path
import pytest

from datamate.grounding_feasibility.temporal import resolve_temporal_context
from datamate.llm_execution.prompt import build_prompt


CALENDAR_PATH = Path(__file__).resolve().parents[2] / "competition_data" / "train" / "calendar.csv"


@pytest.mark.parametrize(
    "expression,as_of_date,expected_start,expected_end,expected_comp_start,expected_comp_end",
    [
        # 1. Hôm qua / bữa qua (có dấu & không dấu)
        ("Doanh thu hôm qua là bao nhiêu?", "2025-07-25", "2025-07-24", "2025-07-24", None, None),
        ("bữa qua cửa hàng bán được bao nhiêu tiền vậy", "2025-04-30", "2025-04-29", "2025-04-29", None, None),
        ("so tien ban duoc hom qua la bn", "2026-03-01", "2026-02-28", "2026-02-28", None, None),
        # 2. Tuần này / tuần trước
        ("Doanh thu tuần này là bao nhiêu?", "2026-06-10", "2026-06-08", "2026-06-10", None, None),
        ("Doanh thu tuần trước là bao nhiêu?", "2026-06-10", "2026-06-01", "2026-06-07", None, None),
        ("tong doanh thu tuan truoc la bao nhieu", "2026-06-10", "2026-06-01", "2026-06-07", None, None),
        # 3. Tháng này & "từ đầu tháng này đến hết hôm nay" (kèm so sánh cùng kỳ tháng trước)
        ("Doanh thu tháng này là bao nhiêu?", "2025-03-15", "2025-03-01", "2025-03-15", None, None),
        (
            "tu dau thang nay den het hôm nay doanh thu hon hay kem cung ky thang trước may %",
            "2025-03-15",
            "2025-03-01",
            "2025-03-15",
            "2025-02-01",
            "2025-02-15",
        ),
        # 4. N ngày gần nhất / N ngày qua vắt qua ranh giới 2 tháng (28/05 -> 03/06)
        ("Trong 7 ngày gần nhất cửa hàng bán được bao nhiêu đơn?", "2026-06-03", "2026-05-28", "2026-06-03", None, None),
        ("doanh thu 7 ngay qua so voi 7 ngay truoc do tang hay giam may %", "2026-06-03", "2026-05-28", "2026-06-03", "2026-05-21", "2026-05-27"),
        # 5. Tết năm Y và so với trước Tết năm Y theo calendar.csv
        ("Doanh thu dịp Tết năm 2025 là bao nhiêu?", "2025-06-01", "2025-01-22", "2025-02-07", None, None),
        ("Doanh thu Tết năm 2026 so với trước Tết năm 2026 tăng bao nhiêu %?", "2026-06-01", "2026-02-10", "2026-02-26", "2026-01-24", "2026-02-09"),
        # 6. So sánh tháng cụ thể với tháng trước / cùng kỳ năm trước
        ("Doanh thu tháng 5/2026 so với tháng trước tăng hay giảm bao nhiêu %?", "2026-06-15", "2026-05-01", "2026-05-31", "2026-04-01", "2026-04-30"),
        ("Doanh thu tháng 5/2026 so với cùng kỳ năm ngoái tăng bao nhiêu %?", "2026-06-15", "2026-05-01", "2026-05-31", "2025-05-01", "2025-05-31"),
        # 7. N ngày kể từ ngày X so với N ngày ngay trước ngày đó (Q22)
        (
            "So số viên Strepsils Cool hộp 2 vỉ x 12 viên bán ra trong 30 ngày kể từ ngày 05/03/2026, ngày tăng giá lên 1.800đ, với 30 ngày ngay trước ngày đó: tăng hay giảm bao nhiêu %?",
            "2026-07-17",
            "2026-03-05",
            "2026-04-03",
            "2026-02-03",
            "2026-03-04",
        ),
    ],
)
def test_temporal_grounder_expression_to_date_range_table(
    expression: str,
    as_of_date: str,
    expected_start: str,
    expected_end: str,
    expected_comp_start: str | None,
    expected_comp_end: str | None,
):
    ctx = resolve_temporal_context(expression, as_of_date, calendar_path=CALENDAR_PATH)
    assert ctx["start_date"] == expected_start, f"start_date sai cho '{expression}': {ctx}"
    assert ctx["end_date"] == expected_end, f"end_date sai cho '{expression}': {ctx}"
    assert ctx["comparison_start"] == expected_comp_start, f"comparison_start sai cho '{expression}': {ctx}"
    assert ctx["comparison_end"] == expected_comp_end, f"comparison_end sai cho '{expression}': {ctx}"


def test_prompt_injects_precomputed_temporal_constants():
    """Prompt phải chứa sẵn các hằng số START_DATE, END_DATE, COMP_START_DATE, COMP_END_DATE để LLM không tự tính ngày."""
    prompt_str = build_prompt(
        schema_str="Bảng don_hang: ['Ngày bán', 'Thành tiền', 'Trạng thái']",
        question="tu dau thang nay den het hôm nay doanh thu hon hay kem cung ky thang trước may %",
        as_of_date="2025-03-15",
        calendar_path=str(CALENDAR_PATH),
    )
    assert "START_DATE = '2025-03-01'" in prompt_str or 'START_DATE = "2025-03-01"' in prompt_str
    assert "END_DATE = '2025-03-15'" in prompt_str or 'END_DATE = "2025-03-15"' in prompt_str
    assert "COMP_START_DATE = '2025-02-01'" in prompt_str or 'COMP_START_DATE = "2025-02-01"' in prompt_str
    assert "COMP_END_DATE = '2025-02-15'" in prompt_str or 'COMP_END_DATE = "2025-02-15"' in prompt_str


def test_detect_asymmetric_comparison_semantic_check():
    """Kiểm tra cổng semantic phát hiện lỗi so sánh 1 ngày với nửa tháng (như q_4cb3efa8bd01)."""
    from datamate.output_abstention.abstention import evaluate_semantic_rule_compliance

    bad_code = """
def solution(data):
    df_ord = data['So_chi_tiet_ban_hang_1'].copy()
    df_ord['clean_date'] = clean_date(df_ord['Ngày'])
    mask_current = (df_ord['clean_date'] >= pd.Timestamp('2025-03-15')) & (df_ord['clean_date'] <= pd.Timestamp('2025-03-15 23:59:59'))
    mask_previous = (df_ord['clean_date'] >= pd.Timestamp('2025-02-01')) & (df_ord['clean_date'] <= pd.Timestamp('2025-02-15 23:59:59'))
    total_current = clean_num(df_ord.loc[mask_current, 'Thành tiền']).sum()
    total_previous = clean_num(df_ord.loc[mask_previous, 'Thành tiền']).sum()
    return ((total_current - total_previous) / total_previous) * 100
"""
    eval_res = evaluate_semantic_rule_compliance(
        code_text=bad_code,
        question="tu dau thang nay den het hnay, dthu hon hay kem cung ky thang trc may %",
        sub_ans={"type": "percent", "answer": -93.71},
        as_of_date="2025-03-15",
    )
    assert not eval_res["is_compliant"]
    assert any("so sánh một ngày với nửa tháng" in v for v in eval_res["violations"])
    assert eval_res["semantic_penalty"] >= 0.60

