"""Kiểm tra tạo split benchmark và materialize đủ train/validation.

Test bao phủ tính xác định theo seed, khớp ID/cặp Q-A, bảo vệ output cũ,
schema gold và nguyên tắc không giao business giữa các group folds.
"""

import json

import pytest

from benchmark.split import create_business_holdout_folds, create_split


def _write_source(tmp_path, *, business_count=6, questions_per_business=4):
    """Tạo nguồn questions/answers nhỏ để kiểm tra splitter độc lập."""
    questions_path = tmp_path / "questions.jsonl"
    answers_path = tmp_path / "answers.jsonl"
    questions = []
    answers = []
    for business_index in range(business_count):
        business_id = f"biz_{business_index:03d}"
        for question_index in range(questions_per_business):
            qid = f"q_{business_index:03d}_{question_index:03d}"
            questions.append(
                {
                    "id": qid,
                    "business_id": business_id,
                    "question": f"Doanh thu câu {question_index}?",
                    "as_of_date": "2026-08-24",
                }
            )
            answers.append(
                {
                    "id": qid,
                    "type": "number",
                    "answer": question_index,
                    "alias": [],
                }
            )
    questions_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in questions),
        encoding="utf-8",
    )
    answers_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in answers),
        encoding="utf-8",
    )
    return questions_path, answers_path


def _read_json(path):
    """Đọc JSON artifact trong thư mục tạm của test."""
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path):
    """Đọc các record JSONL của test thành list object."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_within_business_split_materializes_train_and_val_and_is_reproducible(tmp_path):
    """Cùng nguồn/seed cho cùng ID; mọi file train/val và manifest phải khớp."""
    questions, answers = _write_source(tmp_path)
    out1 = tmp_path / "split1"
    out2 = tmp_path / "split2"

    train1, val1 = create_split(questions, answers, out1, val_ratio=0.25, seed=42)
    train2, val2 = create_split(questions, answers, out2, val_ratio=0.25, seed=42)

    assert train1 == train2
    assert val1 == val2
    assert len(train1) == 18
    assert len(val1) == 6
    assert not (set(train1) & set(val1))
    assert set(train1) | set(val1) == {row["id"] for row in _read_jsonl(questions)}

    assert len(_read_jsonl(out1 / "train_questions.jsonl")) == len(train1)
    assert len(_read_jsonl(out1 / "train_answers.jsonl")) == len(train1)
    assert len(_read_jsonl(out1 / "val_questions.jsonl")) == len(val1)
    assert len(_read_jsonl(out1 / "val_answers.jsonl")) == len(val1)
    manifest = _read_json(out1 / "manifest.json")
    assert manifest["counts"] == {"total": 24, "train": 18, "validation": 6}
    assert manifest["generator_version"] == "1.0.0"
    assert manifest["strategy"] == "within_business_question_holdout"


def test_split_rejects_invalid_ratio_and_mismatched_answers(tmp_path):
    """Từ chối tỷ lệ ngoài miền và hai nguồn questions/answers lệch ID."""
    questions, answers = _write_source(tmp_path)
    with pytest.raises(ValueError, match="val_ratio"):
        create_split(questions, answers, tmp_path / "bad_ratio", val_ratio=1.0)

    rows = _read_jsonl(answers)
    answers.write_text(
        "".join(json.dumps(row) + "\n" for row in rows[:-1]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lệch ID"):
        create_split(questions, answers, tmp_path / "bad_answers")


def test_split_rejects_malformed_gold_aliases(tmp_path):
    """Không materialize partition nếu alias trong gold sai cấu trúc."""
    questions, answers = _write_source(tmp_path)
    rows = _read_jsonl(answers)
    rows[0]["alias"] = [["alias-for-list-item"]]
    answers.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="alias sai cấu trúc"):
        create_split(questions, answers, tmp_path / "bad_alias")


def test_split_does_not_overwrite_existing_output(tmp_path):
    """Output đã tồn tại được bảo vệ, không bị lần chạy mới ghi đè."""
    questions, answers = _write_source(tmp_path)
    output = tmp_path / "split"
    create_split(questions, answers, output)
    with pytest.raises(FileExistsError, match="không ghi đè"):
        create_split(questions, answers, output)


def test_business_holdout_folds_have_no_business_overlap_and_write_full_pairs(tmp_path):
    """Mỗi business chỉ ở train hoặc val mỗi fold; Q/A/IDs đủ và manifest đúng."""
    questions, answers = _write_source(tmp_path, business_count=6, questions_per_business=4)
    output = tmp_path / "group_folds"

    folds = create_business_holdout_folds(
        questions,
        answers,
        output,
        n_folds=3,
        seed=7,
    )
    question_by_id = {row["id"]: row for row in _read_jsonl(questions)}
    val_businesses = []

    assert len(folds) == 3
    for fold_index, (train_ids, val_ids) in enumerate(folds):
        train_biz = {question_by_id[qid]["business_id"] for qid in train_ids}
        val_biz = {question_by_id[qid]["business_id"] for qid in val_ids}
        assert not (train_biz & val_biz)
        val_businesses.extend(val_biz)

        fold_dir = output / f"fold_{fold_index}"
        assert set(_read_json(fold_dir / "train_ids.json")) == set(train_ids)
        assert set(_read_json(fold_dir / "val_ids.json")) == set(val_ids)
        assert len(_read_jsonl(fold_dir / "train_questions.jsonl")) == len(train_ids)
        assert len(_read_jsonl(fold_dir / "train_answers.jsonl")) == len(train_ids)
        assert len(_read_jsonl(fold_dir / "val_questions.jsonl")) == len(val_ids)
        assert len(_read_jsonl(fold_dir / "val_answers.jsonl")) == len(val_ids)
        manifest = _read_json(fold_dir / "manifest.json")
        assert manifest["fold_index"] == fold_index
        assert set(manifest["validation_business_ids"]) == val_biz

    assert set(val_businesses) == set(question["business_id"] for question in question_by_id.values())
    assert len(val_businesses) == len(set(val_businesses))
