import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase_three_evaluation_set_has_twenty_traceable_cases() -> None:
    cases = json.loads((ROOT / "evaluations" / "cases.json").read_text())
    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == 20
    assert {case["capability"] for case in cases} >= {
        "metadata_search",
        "lineage",
        "sql_review",
        "metric_discovery",
        "metric_validate",
        "metric_lineage",
        "chat",
    }
    assert all(case["input"] and case["expected"] for case in cases)
