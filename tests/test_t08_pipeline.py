import json
import subprocess
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "fixtures" / "t08_deletion"
CONFIG_PATH = PROJECT_ROOT / "configs" / "lab.yaml"


def _run_cli(output_dir: Path) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "src.main",
        "--track",
        "t08",
        "--input",
        str(FIXTURE_DIR),
        "--config",
        str(CONFIG_PATH),
        "--output",
        str(output_dir),
        "--offline",
        "--seed",
        "42",
    ]
    return subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)


def test_t08_pipeline_e2e_and_guardrail_success(tmp_path: Path):
    out_dir = tmp_path / "out_success"
    res = _run_cli(out_dir)
    assert res.returncode == 0, f"Pipeline failed unexpectedly:\n{res.stderr}"

    actions_file = out_dir / "actions.csv"
    queue_file = out_dir / "review_queue.csv"
    run_info_file = out_dir / "run_info.json"

    assert actions_file.exists()
    assert queue_file.exists()
    assert run_info_file.exists()

    df_actions = pd.read_csv(actions_file)
    expected_cols = {"request_id", "artefact_id", "action", "reason", "artefact_type", "score"}
    assert expected_cols.issubset(set(df_actions.columns))
    assert len(df_actions) > 0

    legal_hold_rows = df_actions[df_actions["reason"].astype(str).str.upper() == "LEGAL_HOLD"]
    if len(legal_hold_rows) > 0:
        deleted_in_hold = legal_hold_rows[legal_hold_rows["action"].astype(str).str.lower() == "delete"]
        assert len(deleted_in_hold) == 0

    run_info = json.loads(run_info_file.read_text(encoding="utf-8"))
    assert run_info.get("status") == 0
    assert run_info.get("seed") == 42
    assert run_info.get("offline") is True


def test_t08_hitl_review_override_and_audit_log_success(tmp_path: Path):
    out_dir = tmp_path / "out_hitl"
    first_run = _run_cli(out_dir)
    assert first_run.returncode == 0

    df_queue = pd.read_csv(out_dir / "review_queue.csv", dtype=str).fillna("")
    assert len(df_queue) > 0

    target_item_id = str(df_queue.loc[0, "item_id"])
    req_id, art_id = target_item_id.split(":", 1)
    valid_action = str(df_queue.loc[0, "suggested_action"]).strip() or "retain"

    df_queue.loc[0, "reviewer"] = "trinh_vinh_khanh"
    df_queue.loc[0, "reviewer_decision"] = "approve"
    df_queue.loc[0, "override_value"] = valid_action
    df_queue.loc[0, "review_note"] = "Verified by reviewer"
    df_queue.loc[0, "reviewed_at"] = "2026-11-15T00:00:00Z"

    df_queue.to_csv(out_dir / "review_queue_reviewed.csv", index=False)

    second_run = _run_cli(out_dir)
    assert second_run.returncode == 0, f"HITL rerun failed:\n{second_run.stderr}"

    audit_file = out_dir / "audit_log.jsonl"
    assert audit_file.exists()
    audit_lines = [line for line in audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(audit_lines) >= 1

    df_actions_after = pd.read_csv(out_dir / "actions.csv")
    matched = df_actions_after[
        (df_actions_after["request_id"] == req_id) & (df_actions_after["artefact_id"] == art_id)
    ]
    assert len(matched) == 1
    assert str(matched.iloc[0]["action"]).strip() == "escalate"


def test_t08_failure_missing_reviewer_or_invalid_action_blocks_execution(tmp_path: Path):
    out_dir = tmp_path / "out_fail"
    first_run = _run_cli(out_dir)
    assert first_run.returncode == 0

    df_queue = pd.read_csv(out_dir / "review_queue.csv", dtype=str).fillna("")
    assert len(df_queue) > 0

    # Case 1: Missing reviewer
    df_missing_reviewer = df_queue.copy()
    df_missing_reviewer.loc[0, "reviewer"] = ""
    df_missing_reviewer.loc[0, "reviewer_decision"] = "approve"
    df_missing_reviewer.loc[0, "reviewed_at"] = "2026-11-15T00:00:00Z"
    df_missing_reviewer.to_csv(out_dir / "review_queue_reviewed.csv", index=False)

    run_missing = _run_cli(out_dir)
    assert run_missing.returncode != 0

    # Case 2: Invalid action override
    df_bad_action = df_queue.copy()
    df_bad_action.loc[0, "reviewer"] = "trinh_vinh_khanh"
    df_bad_action.loc[0, "reviewer_decision"] = "edit"
    df_bad_action.loc[0, "override_value"] = "INVALID_ACTION_XYZ"
    df_bad_action.loc[0, "reviewed_at"] = "2026-11-15T00:00:00Z"
    df_bad_action.to_csv(out_dir / "review_queue_reviewed.csv", index=False)

    run_bad_action = _run_cli(out_dir)
    assert run_bad_action.returncode != 0
