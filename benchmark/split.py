"""Tạo các partition train/validation materialized cho benchmark DataMate.

Mô-đun đọc cặp ``questions.jsonl``/``answers.jsonl``, xác thực ID, schema và
alias, rồi sinh một trong hai chiến lược:

* ``within_business``: chia câu hỏi riêng trong từng doanh nghiệp;
* ``business_holdout``: chia nguyên doanh nghiệp thành các validation folds.

Mỗi partition có train/validation IDs, questions, answers và manifest. Output
được staging trong thư mục tạm rồi rename khi đầy đủ; đích đã tồn tại sẽ không
bị ghi đè. Cả hai chiến lược mặc định dùng dữ liệu train của challenge.

Chạy từ thư mục gốc repository::

    python -m benchmark.split --strategy within_business
    python -m benchmark.split --strategy business_holdout --folds 5

Các hàm ``create_split`` và ``create_business_holdout_folds`` cũng có thể được
gọi trực tiếp trong Python khi cần cấu hình nguồn, output path, ratio hoặc seed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Dùng chung validator với evaluator để gold hợp lệ theo cùng một schema.
from benchmark.evaluate import validate_gold_record

# Giá trị mặc định cho CLI; output được chia theo strategy dưới splits root.
DEFAULT_QUESTIONS = Path("competition_data/train/questions.jsonl")
DEFAULT_ANSWERS = Path("competition_data/train/answers.jsonl")
DEFAULT_SPLITS_ROOT = Path("benchmark/splits")
# Type được phép trong gold; abstain chỉ xuất hiện ở phía prediction.
ANSWER_TYPES = {
    "number",
    "percent",
    "string",
    "date",
    "boolean",
    "list",
    "table",
    "unanswerable",
}
GENERATOR_VERSION = "1.0.0"

# Bảo đảm thông báo lỗi tiếng Việt đọc được trong Windows console.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Kiểm tra nguồn và tạo dấu vết để có thể tái lập split
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    """Tính SHA-256 theo từng khối để không cần nạp cả file nguồn vào RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_ids(ids: list[str]) -> str:
    """Hash danh sách ID theo thứ tự ghi, mỗi ID trên một dòng UTF-8."""
    return hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()


def _read_jsonl(path: Path, required_fields: set[str]) -> list[dict[str, Any]]:
    """Đọc JSONL nghiêm ngặt, kiểm tra object, ID duy nhất và trường bắt buộc."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file: {path}")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: JSON không hợp lệ: {exc.msg}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_no}: mỗi dòng phải là JSON object")
            qid = item.get("id")
            if not isinstance(qid, str) or not qid.strip():
                raise ValueError(f"{path}:{line_no}: thiếu ID string không rỗng")
            if qid in seen_ids:
                raise ValueError(f"{path}:{line_no}: ID trùng {qid!r}")
            missing = required_fields - item.keys()
            if missing:
                raise ValueError(f"{path}:{line_no}: thiếu trường {sorted(missing)}")
            seen_ids.add(qid)
            records.append(item)
    return records


def _load_source(
    questions_file: Path | str,
    answers_file: Path | str,
) -> tuple[Path, Path, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Nạp hai nguồn, kiểm tra question-answer khớp một-một và gold hợp lệ.

    Trả lại paths để ghi manifest, danh sách questions giữ nguyên thứ tự nguồn
    và mapping answers theo ID để lọc chính xác từng partition.
    """
    questions_path = Path(questions_file)
    answers_path = Path(answers_file)
    questions = _read_jsonl(
        questions_path,
        {"id", "business_id", "question", "as_of_date"},
    )
    answers = _read_jsonl(answers_path, {"id", "type", "answer"})

    for question in questions:
        for field in ("business_id", "question", "as_of_date"):
            if not isinstance(question[field], str) or not question[field].strip():
                raise ValueError(f"Question {question['id']!r}: {field} phải là string không rỗng")

    # So tập ID hai file trước khi tạo split để không làm rơi hoặc thêm mẫu.
    answers_by_id = {item["id"]: item for item in answers}
    question_ids = {item["id"] for item in questions}
    answer_ids = set(answers_by_id)
    missing_answers = sorted(question_ids - answer_ids)
    extra_answers = sorted(answer_ids - question_ids)
    if missing_answers or extra_answers:
        raise ValueError(
            "Questions/answers lệch ID: "
            f"thiếu answers={missing_answers[:5]}, answers ngoài questions={extra_answers[:5]}"
        )

    # Dùng chung validator với evaluator để split không materialize gold lỗi.
    for item in answers:
        if not isinstance(item["type"], str) or item["type"] not in ANSWER_TYPES:
            raise ValueError(f"Answer {item['id']!r}: type không hợp lệ {item['type']!r}")
        validate_gold_record(item["id"], item)

    return questions_path, answers_path, questions, answers_by_id


# ---------------------------------------------------------------------------
# Ghi artifact, thống kê và manifest
# ---------------------------------------------------------------------------
def _write_json(path: Path, value: Any) -> None:
    """Ghi JSON UTF-8 có indent để IDs/manifest dễ đọc và kiểm tra bằng tay."""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Ghi một JSON object trên mỗi dòng theo chuẩn JSONL UTF-8."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _counts_by_business(
    ids: list[str],
    questions_by_id: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Đếm số câu của mỗi business trong một danh sách IDs."""
    counts = Counter(questions_by_id[qid]["business_id"] for qid in ids)
    return dict(sorted(counts.items()))


def _counts_by_type(ids: list[str], answers_by_id: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Đếm phân bố answer type tương ứng với các IDs đã chọn."""
    counts = Counter(answers_by_id[qid]["type"] for qid in ids)
    return dict(sorted(counts.items()))


def _manifest(
    *,
    strategy: str,
    seed: int,
    questions_path: Path,
    answers_path: Path,
    train_ids: list[str],
    val_ids: list[str],
    questions_by_id: dict[str, dict[str, Any]],
    answers_by_id: dict[str, dict[str, Any]],
    val_ratio: float | None = None,
    fold_index: int | None = None,
    fold_business_ids: list[str] | None = None,
    n_folds: int | None = None,
) -> dict[str, Any]:
    """Tạo metadata có thể dùng để truy vết nguồn và xác minh split.

    Hash ID phụ thuộc thứ tự ID được ghi; các count theo business/type giúp
    kiểm tra độ cân bằng mà không phải đọc lại toàn bộ JSONL.
    """
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "strategy": strategy,
        "seed": seed,
        "source": {
            "questions_file": questions_path.as_posix(),
            "questions_sha256": _sha256_file(questions_path),
            "answers_file": answers_path.as_posix(),
            "answers_sha256": _sha256_file(answers_path),
        },
        "counts": {
            "total": len(train_ids) + len(val_ids),
            "train": len(train_ids),
            "validation": len(val_ids),
        },
        "train_ids_sha256": _sha256_ids(train_ids),
        "val_ids_sha256": _sha256_ids(val_ids),
        "train_business_counts": _counts_by_business(train_ids, questions_by_id),
        "val_business_counts": _counts_by_business(val_ids, questions_by_id),
        "train_answer_type_counts": _counts_by_type(train_ids, answers_by_id),
        "val_answer_type_counts": _counts_by_type(val_ids, answers_by_id),
    }
    if val_ratio is not None:
        manifest["val_ratio_target"] = val_ratio
        manifest["rounding"] = "Python round() per business; clamp to keep at least one record on each side"
    if n_folds is not None:
        manifest["n_folds"] = n_folds
    if fold_index is not None:
        manifest["fold_index"] = fold_index
        manifest["validation_business_ids"] = fold_business_ids or []
    return manifest


# ---------------------------------------------------------------------------
# Materialize partition an toàn, không ghi đè dữ liệu cũ
# ---------------------------------------------------------------------------
def _populate_split_directory(
    output_dir: Path,
    *,
    train_ids: list[str],
    val_ids: list[str],
    questions_by_id: dict[str, dict[str, Any]],
    answers_by_id: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """Ghi trọn bộ bảy files vào thư mục mới, lọc Q/A theo cùng danh sách IDs."""
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "train_ids.json", train_ids)
    _write_json(output_dir / "val_ids.json", val_ids)
    _write_jsonl(
        output_dir / "train_questions.jsonl",
        [questions_by_id[qid] for qid in train_ids],
    )
    _write_jsonl(
        output_dir / "train_answers.jsonl",
        [answers_by_id[qid] for qid in train_ids],
    )
    _write_jsonl(
        output_dir / "val_questions.jsonl",
        [questions_by_id[qid] for qid in val_ids],
    )
    _write_jsonl(
        output_dir / "val_answers.jsonl",
        [answers_by_id[qid] for qid in val_ids],
    )
    _write_json(output_dir / "manifest.json", manifest)


def _atomic_materialize_split(
    output_dir: Path | str,
    *,
    train_ids: list[str],
    val_ids: list[str],
    questions_by_id: dict[str, dict[str, Any]],
    answers_by_id: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> Path:
    """Tạo một split đơn lẻ trong staging rồi rename nguyên thư mục.

    Kiểm tra đích trước khi ghi để không ghi đè kết quả cũ; temp directory nằm
    cạnh output để rename ở cùng filesystem.
    """
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(
            f"Output đã tồn tại, không ghi đè artifact: {target}. "
            "Chọn thư mục phiên bản mới."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{target.name}.", dir=target.parent) as temp_root:
        staged = Path(temp_root) / target.name
        _populate_split_directory(
            staged,
            train_ids=train_ids,
            val_ids=val_ids,
            questions_by_id=questions_by_id,
            answers_by_id=answers_by_id,
            manifest=manifest,
        )
        staged.rename(target)
    return target


# ---------------------------------------------------------------------------
# Chiến lược 1: chia câu hỏi trong từng doanh nghiệp
# ---------------------------------------------------------------------------
def create_split(
    questions_file: Path | str = DEFAULT_QUESTIONS,
    answers_file: Path | str = DEFAULT_ANSWERS,
    output_dir: Path | str = DEFAULT_SPLITS_ROOT / "within_business_v1",
    val_ratio: float = 0.20,
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    """Tạo question holdout trong từng doanh nghiệp và materialize đủ train/val.

    Mỗi business được xáo trộn bằng một RNG chung với seed cố định; số val làm
    tròn riêng theo nhóm và bị chặn để giữ ít nhất một mẫu ở mỗi phía.
    """
    if isinstance(val_ratio, bool) or not isinstance(val_ratio, (int, float)) or not 0 < val_ratio < 1:
        raise ValueError("val_ratio phải nằm trong khoảng (0, 1)")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed phải là số nguyên")

    questions_path, answers_path, questions, answers_by_id = _load_source(
        questions_file,
        answers_file,
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        grouped[question["business_id"]].append(question)

    # Tách riêng từng doanh nghiệp để mọi business đều có mặt ở train lẫn val.
    rng = random.Random(seed)
    train_ids: list[str] = []
    val_ids: list[str] = []
    for business_id in sorted(grouped):
        business_questions = list(grouped[business_id])
        if len(business_questions) < 2:
            raise ValueError(
                f"Doanh nghiệp {business_id!r} có dưới 2 câu; "
                "không thể giữ dữ liệu ở cả train và validation"
            )
        rng.shuffle(business_questions)
        val_count = int(round(len(business_questions) * float(val_ratio)))
        val_count = max(1, min(len(business_questions) - 1, val_count))
        val_ids.extend(item["id"] for item in business_questions[:val_count])
        train_ids.extend(item["id"] for item in business_questions[val_count:])

    questions_by_id = {item["id"]: item for item in questions}
    manifest = _manifest(
        strategy="within_business_question_holdout",
        seed=seed,
        questions_path=questions_path,
        answers_path=answers_path,
        train_ids=train_ids,
        val_ids=val_ids,
        questions_by_id=questions_by_id,
        answers_by_id=answers_by_id,
        val_ratio=float(val_ratio),
    )
    output_path = _atomic_materialize_split(
        output_dir,
        train_ids=train_ids,
        val_ids=val_ids,
        questions_by_id=questions_by_id,
        answers_by_id=answers_by_id,
        manifest=manifest,
    )
    print(f"Split within-business hoàn tất tại {output_path}")
    print(f"- Train: {len(train_ids)} | validation: {len(val_ids)} | seed: {seed}")
    return train_ids, val_ids


# ---------------------------------------------------------------------------
# Chiến lược 2: gán nguyên doanh nghiệp vào các group folds
# ---------------------------------------------------------------------------
def _assign_businesses_to_folds(
    questions: list[dict[str, Any]],
    answers_by_id: dict[str, dict[str, Any]],
    n_folds: int,
    seed: int,
) -> list[list[str]]:
    """Gán mỗi business nguyên vẹn vào đúng một validation fold.

    Nhóm lớn được xếp trước; mỗi nhóm vào fold đang có ít câu nhất. Khi số câu
    bằng nhau, phân bố answer type gần mục tiêu hơn được ưu tiên; seed chỉ dùng
    để quyết định thứ tự khi kích thước business bằng nhau.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        grouped[question["business_id"]].append(question)
    if n_folds < 2 or n_folds > len(grouped):
        raise ValueError(f"n_folds phải từ 2 đến {len(grouped)}")

    # Tính mục tiêu cân bằng gần đúng theo số câu và answer type cho mọi fold.
    total_questions = len(questions)
    total_types = Counter(answers_by_id[q["id"]]["type"] for q in questions)
    target_questions = total_questions / n_folds
    target_types = {ans_type: count / n_folds for ans_type, count in total_types.items()}

    rng = random.Random(seed)
    shuffled_businesses = sorted(grouped)
    rng.shuffle(shuffled_businesses)
    tie_order = {business_id: index for index, business_id in enumerate(shuffled_businesses)}
    ordered_businesses = sorted(
        grouped,
        key=lambda business_id: (-len(grouped[business_id]), tie_order[business_id]),
    )

    fold_businesses: list[list[str]] = [[] for _ in range(n_folds)]
    fold_questions = [0] * n_folds
    fold_types = [Counter() for _ in range(n_folds)]

    # Gán greedy theo nhóm, không chia nhỏ business để ép kích thước bằng nhau.
    for business_id in ordered_businesses:
        group_questions = grouped[business_id]
        group_types = Counter(answers_by_id[q["id"]]["type"] for q in group_questions)

        def fold_score(fold_index: int) -> tuple[int, float, int]:
            # Luôn lấp fold ít câu nhất trước; nếu tải câu bằng nhau, ưu tiên
            # fold có phân bố type ít lệch hơn mục tiêu toàn cục.
            type_score = 0.0
            for ans_type, target in target_types.items():
                after = fold_types[fold_index][ans_type] + group_types[ans_type]
                type_score += ((after - target) / max(target, 1)) ** 2
            return (fold_questions[fold_index], type_score, fold_index)

        chosen = min(range(n_folds), key=fold_score)
        fold_businesses[chosen].append(business_id)
        fold_questions[chosen] += len(group_questions)
        fold_types[chosen].update(group_types)

    return [sorted(business_ids) for business_ids in fold_businesses]


def create_business_holdout_folds(
    questions_file: Path | str = DEFAULT_QUESTIONS,
    answers_file: Path | str = DEFAULT_ANSWERS,
    output_dir: Path | str = DEFAULT_SPLITS_ROOT / "business_holdout_v1",
    n_folds: int = 5,
    seed: int = 42,
) -> list[tuple[list[str], list[str]]]:
    """Tạo group folds và files độc lập cho từng fold.

    Mỗi fold dùng một tập business validation; train gồm mọi business còn lại.
    Tất cả fold được tạo trong staging root và chỉ được publish khi hoàn tất.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed phải là số nguyên")
    if isinstance(n_folds, bool) or not isinstance(n_folds, int):
        raise ValueError("n_folds phải là số nguyên")

    questions_path, answers_path, questions, answers_by_id = _load_source(
        questions_file,
        answers_file,
    )
    fold_business_ids = _assign_businesses_to_folds(
        questions,
        answers_by_id,
        n_folds=n_folds,
        seed=seed,
    )
    questions_by_id = {item["id"]: item for item in questions}
    all_business_ids = {item["business_id"] for item in questions}

    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(
            f"Output đã tồn tại, không ghi đè artifact: {target}. "
            "Chọn thư mục phiên bản mới."
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    # Dùng staging chung để tránh để lại một phần các fold nếu có lỗi giữa chừng.
    result: list[tuple[list[str], list[str]]] = []
    with tempfile.TemporaryDirectory(prefix=f".{target.name}.", dir=target.parent) as temp_root:
        staged_root = Path(temp_root) / target.name
        staged_root.mkdir(parents=True, exist_ok=False)

        # Materialize từng fold từ group IDs; Q/A luôn được lọc đồng bộ.
        for fold_index, val_businesses in enumerate(fold_business_ids):
            val_business_set = set(val_businesses)
            train_business_set = all_business_ids - val_business_set
            train_ids = [
                question["id"]
                for question in questions
                if question["business_id"] in train_business_set
            ]
            val_ids = [
                question["id"]
                for question in questions
                if question["business_id"] in val_business_set
            ]
            if not train_ids or not val_ids:
                raise ValueError(f"Fold {fold_index} tạo train hoặc validation rỗng")

            manifest = _manifest(
                strategy="business_group_holdout",
                seed=seed,
                questions_path=questions_path,
                answers_path=answers_path,
                train_ids=train_ids,
                val_ids=val_ids,
                questions_by_id=questions_by_id,
                answers_by_id=answers_by_id,
                fold_index=fold_index,
                fold_business_ids=val_businesses,
                n_folds=n_folds,
            )
            _populate_split_directory(
                staged_root / f"fold_{fold_index}",
                train_ids=train_ids,
                val_ids=val_ids,
                questions_by_id=questions_by_id,
                answers_by_id=answers_by_id,
                manifest=manifest,
            )
            result.append((train_ids, val_ids))

        staged_root.rename(target)

    print(f"Business holdout hoàn tất tại {target}")
    for fold_index, (train_ids, val_ids) in enumerate(result):
        print(f"- fold_{fold_index}: train={len(train_ids)}, validation={len(val_ids)}")
    return result


# ---------------------------------------------------------------------------
# CLI: chọn strategy và chuyển tham số tới bộ sinh tương ứng
# ---------------------------------------------------------------------------
def main() -> None:
    """Khai báo CLI và chuyển tham số tới bộ sinh split tương ứng."""
    parser = argparse.ArgumentParser(description="Tạo split có manifest cho benchmark DataMate")
    parser.add_argument(
        "--strategy",
        choices=("within_business", "business_holdout"),
        default="within_business",
    )
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--answers", default=str(DEFAULT_ANSWERS))
    parser.add_argument("--output-dir", default=str(DEFAULT_SPLITS_ROOT))
    parser.add_argument("--val-ratio", type=float, default=0.20)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    if args.strategy == "within_business":
        create_split(
            questions_file=args.questions,
            answers_file=args.answers,
            output_dir=output_root / "within_business_v1",
            val_ratio=args.val_ratio,
            seed=args.seed,
        )
    else:
        create_business_holdout_folds(
            questions_file=args.questions,
            answers_file=args.answers,
            output_dir=output_root / "business_holdout_v1",
            n_folds=args.folds,
            seed=args.seed,
        )


if __name__ == "__main__":
    # Cho phép chạy trực tiếp bằng ``python -m benchmark.split``.
    main()
