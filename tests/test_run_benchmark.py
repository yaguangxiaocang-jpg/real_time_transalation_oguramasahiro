"""evaluation/run_benchmark.py のオフラインで検証できる部分（API呼び出しなし）のテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evaluation"))

from run_benchmark import (  # noqa: E402
    load_benchmark,
    merge_raw_utterances,
    score_against_reference,
)

BENCHMARK_PATH = ROOT / "evaluation" / "benchmarks" / "economics_federal_funds_rate.json"


def test_seed_benchmark_merges_to_expected_segment_count() -> None:
    benchmark = load_benchmark(BENCHMARK_PATH)

    merged = merge_raw_utterances(benchmark)

    assert len(merged) == benchmark["expected_merged_count"]
    assert len(merged) == len(benchmark["reference_ja"])
    assert merged[0]["transcript"] == (
        "So this this is the shortest term interest rate in The United States. "
        "It's called the federal funds rate,"
    )


def test_score_against_reference_is_high_for_identical_text() -> None:
    refs = ["これは米国における最短期間の金利です。"]
    score = score_against_reference(refs, refs)

    assert score > 0.99


def test_score_against_reference_is_lower_for_different_text() -> None:
    refs = ["これは米国における最短期間の金利です。"]
    hyps = ["猫が椅子の上で眠っています。"]

    score = score_against_reference(hyps, refs)

    assert score < 0.3
