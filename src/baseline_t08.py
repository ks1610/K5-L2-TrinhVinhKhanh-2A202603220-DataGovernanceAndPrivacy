# """YOUR PoC PIPELINE — this is the file your group owns.

# Lab contract = 5 automated steps, run by `python -m src.main ...`:
#     01 load      input + provenance check (manifest.csv)
#     02 process   your algorithm / model (the research part)
#     03 rank      prioritise for a fixed review budget B
#     04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
#     05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

# Required output: out/<pred_file> with the columns listed for your track in
# docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
#     python -m src.evaluate --track tXX --pred out/<pred_file>

# Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
# no network calls; fail loudly on missing models instead of downloading.
# See src/examples/random_baseline.py for a minimal end-to-end wiring example.
# """
# from __future__ import annotations

# import pandas as pd

# from .common.context import RunContext
# from .common.decision import Decision, write_decision
# from .common.manifest import verify_manifest
# from .common.review import load_review_decisions, make_review_queue, write_review_queue
# from .metrics.tracks import get_track


# # ---------------------------------------------------------------- 01 load
# def load(ctx: RunContext) -> dict:
#     manifest = ctx.input_dir / "manifest.csv"
#     problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
#     if problems:
#         ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
#         if ctx.config.get("strict_provenance", True):
#             raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
#     data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
#     # TODO: load the tables/images your track needs, e.g.
#     # data["images"] = pd.read_csv(ctx.input_dir / "images.csv")
#     return data


# # ---------------------------------------------------------------- 02 process
# def process(ctx: RunContext, data: dict) -> pd.DataFrame:
#     spec = get_track(ctx.track)
#     raise NotImplementedError(
#         f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
#         f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
#     )


# # ---------------------------------------------------------------- 03 rank
# def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
#     """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
#     budget = int(ctx.param("budget", 20))
#     if "score" not in scored.columns:
#         raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
#                          "or adapt rank() to your track")
#     q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
#                           reason_col="reason" if "reason" in scored.columns else None)
#     write_review_queue(q, ctx.out("review_queue.csv"))
#     return q


# # ---------------------------------------------------------------- 04 review
# def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
#     """If a reviewed queue exists (out/review_queue_reviewed.csv), apply it. Otherwise pass through.

#     TODO: decide what an `edit` / `reject` means for your track and apply it
#     (e.g. via common.review.apply_overrides), logging every change to ctx.audit.
#     """
#     reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
#     if reviewed_path.exists():
#         reviewed = load_review_decisions(reviewed_path)
#         ctx.stats["n_reviewed"] = len(reviewed)
#         # TODO: apply overrides
#     return scored


# # ---------------------------------------------------------------- 05 decide
# def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
#     # TODO: replace with your policy (thresholds frozen BEFORE looking at eval results)
#     return Decision(status="HOLD", reason_code="POLICY_NOT_IMPLEMENTED", reason="Decision policy not implemented yet",
#                     owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track)


# def run(ctx: RunContext) -> None:
#     spec = get_track(ctx.track)
#     data = load(ctx)
#     scored = process(ctx, data)
#     ctx.stats["n_items"] = len(scored)
#     queue = rank(ctx, scored)
#     final = review(ctx, scored, queue)
#     final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
#     write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))


"""Track T08 — Retention & Delete Request Simulator."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import (
    load_review_decisions,
    make_review_queue,
    write_review_queue,
)
from .metrics.tracks import get_track


# ----------------------------------------------------------------
# 01 LOAD
# ----------------------------------------------------------------

def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"

    problems = (
        verify_manifest(manifest)
        if manifest.exists()
        else [{"problem": "no_manifest"}]
    )

    if problems:
        ctx.audit.log(
            actor="pipeline",
            action="provenance_problems",
            item_id=str(manifest),
            after=problems[:20],
        )

        if ctx.config.get("strict_provenance", True):
            raise ValueError(
                f"provenance check failed ({len(problems)} problems)"
            )

    graph_path = ctx.input_dir / "data_graph.json"
    requests_path = ctx.input_dir / "requests.json"

    with graph_path.open("r", encoding="utf-8") as f:
        graph = json.load(f)

    with requests_path.open("r", encoding="utf-8") as f:
        requests = json.load(f)

    artefacts = graph.get("artefacts", [])

    if not isinstance(artefacts, list):
        raise ValueError("data_graph.json: artefacts must be a list")

    if not isinstance(requests, list):
        raise ValueError("requests.json must contain a list")

    by_id = {}

    for artefact in artefacts:
        artefact_id = artefact.get("artefact_id")

        if not artefact_id:
            raise ValueError("Artefact missing artefact_id")

        if artefact_id in by_id:
            raise ValueError(f"Duplicate artefact_id: {artefact_id}")

        by_id[artefact_id] = artefact

    return {
        "manifest": pd.read_csv(manifest),
        "by_id": by_id,
        "requests": requests,
    }


# ----------------------------------------------------------------
# 02 PROCESS
# ----------------------------------------------------------------

def _build_children_index(by_id: dict) -> dict:
    children = {}

    for artefact_id, artefact in by_id.items():
        for parent_id in artefact.get("parent_ids", []):
            children.setdefault(parent_id, []).append(artefact_id)

    for parent_id in children:
        children[parent_id].sort()

    return children


def _find_affected_artefacts(
    subject_id: str,
    by_id: dict,
    children_of: dict,   # giữ signature cho khỏi lỗi
) -> list[str]:
    """Baseline: chỉ lấy raw_video của subject, không BFS lineage."""
    return sorted(
        artefact_id
        for artefact_id, artefact in by_id.items()
        if (
            artefact.get("type") == "raw_video"
            and subject_id in artefact.get("subject_ids", [])
        )
    )


def _decide_action(artefact: dict) -> tuple[str, str]:
    """
    T08 policy precedence:
    legal hold > unknown origin > multi-subject > delete.

    Permission must not be inferred from ACL/owner equality
    without an explicit permission policy.
    """

    if artefact.get("legal_hold", False):
        return "retain_legal_hold", "LEGAL_HOLD"

    if not artefact.get("origin_known", False):
        return "escalate", "UNKNOWN_ORIGIN"

    subjects = artefact.get("subject_ids", [])

    if len(subjects) > 1:
        return "escalate", "MULTI_SUBJECT"

    return "delete", "SUBJECT_DATA"


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    by_id = data["by_id"]
    requests = data["requests"]

    children_of = _build_children_index(by_id)

    rows = []

    seen_pairs = set()

    for request in requests:
        request_id = request["request_id"]
        subject_id = request["subject_id"]

        if not request.get("identity_verified", False):
            raise ValueError(
                f"Identity not verified for request {request_id}"
            )

        affected = _find_affected_artefacts(
            subject_id,
            by_id,
            children_of,
        )

        for artefact_id in affected:
            pair = (request_id, artefact_id)

            if pair in seen_pairs:
                continue

            seen_pairs.add(pair)

            artefact = by_id[artefact_id]

            action, reason = _decide_action(artefact)

            rows.append({
                "request_id": request_id,
                "artefact_id": artefact_id,
                "action": action,
                "reason": reason,
                "artefact_type": artefact.get("type", "unknown"),
                "score": (
                    1.0 if action in {
                        "retain_legal_hold",
                        "escalate",
                    } else 0.0
                ),
            })

    columns = [
        "request_id",
        "artefact_id",
        "action",
        "reason",
        "artefact_type",
        "score",
    ]

    result = pd.DataFrame(rows, columns=columns)

    if not result.empty:
        result = result.sort_values(
            ["request_id", "artefact_id"]
        ).reset_index(drop=True)

    return result


# ----------------------------------------------------------------
# 03 RANK
# ----------------------------------------------------------------

def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))

    if budget < 0:
        raise ValueError("Review budget must be non-negative")

    if scored.empty:
        queue = scored.copy()
        queue["item_id"] = pd.Series(dtype="object")
        write_review_queue(queue, ctx.out("review_queue.csv"))
        ctx.stats["n_review_candidates"] = 0
        ctx.stats["n_reviewed_queue"] = 0
        return queue

    exceptions = scored[
        scored["action"].isin([
            "retain_legal_hold",
            "escalate",
        ])
    ].copy()

    exceptions["review_id"] = (
        exceptions["request_id"].astype(str)
        + ":"
        + exceptions["artefact_id"].astype(str)
    )

    candidate_count = len(exceptions)

    # Never silently omit exceptions from human review.
    if budget < candidate_count:
        raise ValueError(
            f"Review budget ({budget}) is smaller than "
            f"the number of review candidates ({candidate_count}). "
            "Increase params.budget in configs/lab.yaml."
        )

    if exceptions.empty:
        queue = make_review_queue(
            exceptions,
            id_col="review_id",
            score_col="score",
            budget=budget,
            reason_col="reason",
        )
    else:
        queue = make_review_queue(
            exceptions,
            id_col="review_id",
            score_col="score",
            budget=budget,
            reason_col="reason",
        )

    write_review_queue(queue, ctx.out("review_queue.csv"))

    ctx.stats["n_review_candidates"] = candidate_count
    ctx.stats["n_reviewed_queue"] = len(queue)

    return queue


def review(
    ctx: RunContext,
    scored: pd.DataFrame,
    queue: pd.DataFrame,
) -> pd.DataFrame:

    final = scored.copy()

    ctx.stats["n_reviewed"] = 0

    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"

    if reviewed_path.exists() and not queue.empty:
        reviewed = load_review_decisions(reviewed_path)

        ctx.stats["n_reviewed"] = len(reviewed)

        # The shared review module uses item_id.
        if "item_id" not in reviewed.columns:
            raise ValueError(
                "Reviewed queue must contain item_id"
            )

        if reviewed["item_id"].duplicated().any():
            raise ValueError(
                "Duplicate item_id in reviewed queue"
            )

        queue_ids = set(queue["item_id"].astype(str))
        reviewed_ids = set(reviewed["item_id"].astype(str))

        unknown_ids = reviewed_ids - queue_ids

        if unknown_ids:
            raise ValueError(
                f"Unknown review IDs: {sorted(unknown_ids)}"
            )

        for decision in reviewed.to_dict("records"):
            item_id = str(decision["item_id"])

            reviewer = str(decision.get("reviewer", "")).strip()
            decision_type = str(
                decision.get("reviewer_decision", "")
            ).strip().lower()

            review_note = str(
                decision.get("review_note", "")
            ).strip()

            reviewed_at = str(
                decision.get("reviewed_at", "")
            ).strip()

            if not review_note:
                raise ValueError(
                    f"Missing review_note for {item_id}"
                )

            if not reviewed_at:
                raise ValueError(
                    f"Missing reviewed_at for {item_id}"
                )

            matched = (
                final["request_id"].astype(str)
                + ":"
                + final["artefact_id"].astype(str)
            ) == item_id

            if not matched.any():
                raise ValueError(
                    f"Review target not found: {item_id}"
                )

            index = final.index[matched][0]

            original_action = final.at[index, "action"]
            original_reason = final.at[index, "reason"]

            if decision_type == "approve":
                # Preserve the original policy action.
                pass

            elif decision_type == "reject":
                if original_action == "delete":
                    raise ValueError(
                        "Normal delete actions cannot be rejected "
                        "through the exception review queue"
                    )

                final.at[index, "action"] = "escalate"
                final.at[index, "reason"] = "REVIEW_REJECTED"

            elif decision_type == "escalate":
                final.at[index, "action"] = "escalate"
                final.at[index, "reason"] = "HUMAN_ESCALATION"

            elif decision_type == "edit":
                override = str(
                    decision.get("override_value", "")
                ).strip()

                allowed_overrides = {
                    "delete",
                    "retain_legal_hold",
                    "escalate",
                }

                if override not in allowed_overrides:
                    raise ValueError(
                        f"Invalid action override for {item_id}: "
                        f"{override}"
                    )

                # Never bypass legal hold.
                if (
                    original_action == "retain_legal_hold"
                    and override == "delete"
                ):
                    raise ValueError(
                        f"Cannot delete legal-held artefact: {item_id}"
                    )

                # Deleting an exception requires supporting evidence.
                if (
                    original_action == "escalate"
                    and override == "delete"
                    and not str(
                        decision.get("evidence_path", "")
                    ).strip()
                ):
                    raise ValueError(
                        f"Evidence is required before overriding "
                        f"escalation to delete: {item_id}"
                    )

                final.at[index, "action"] = override
                final.at[index, "reason"] = "HUMAN_OVERRIDE"

            elif decision_type == "skip":
                final.at[index, "action"] = "escalate"
                final.at[index, "reason"] = "REVIEW_SKIPPED"

            else:
                raise ValueError(
                    f"Unsupported review decision: {decision_type}"
                )

            ctx.audit.log(
                actor=reviewer,
                action=f"review:{decision_type}",
                item_id=item_id,
                before=original_action,
                after=final.at[index, "action"],
                reason=review_note,
                reviewed_at=reviewed_at,
                original_reason=original_reason,
            )

    # Record every final action for evaluator audit completeness.
    for row in final.itertuples(index=False):
        ctx.audit.log(
            actor=ctx.config.get("owner", "pipeline"),
            action=f"final_action:{row.action}",
            item_id=row.artefact_id,
            after={
                "request_id": row.request_id,
                "reason": row.reason,
            },
        )

    return final


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = ctx.config.get("owner", "T08-pipeline")

    allowed_actions = {
        "delete",
        "retain_legal_hold",
        "escalate",
    }

    if final.empty:
        return Decision(
            status="HOLD",
            reason_code="NO_ACTIONS_GENERATED",
            reason="No deletion actions were generated",
            owner=owner,
            scope=ctx.track,
        )

    if not set(final["action"]).issubset(allowed_actions):
        return Decision(
            status="REWORK",
            reason_code="INVALID_ACTION",
            reason="Output contains an unsupported action",
            owner=owner,
            scope=ctx.track,
        )

    candidates = int(
        ctx.stats.get("n_review_candidates", 0)
    )

    queued = int(
        ctx.stats.get("n_reviewed_queue", 0)
    )

    reviewed = int(
        ctx.stats.get("n_reviewed", 0)
    )

    if queued < candidates:
        return Decision(
            status="HOLD",
            reason_code="INCOMPLETE_REVIEW_QUEUE",
            reason=(
                f"{candidates - queued} review candidates "
                "were not included in the review queue"
            ),
            owner=owner,
            scope=ctx.track,
        )

    if reviewed < candidates:
        return Decision(
            status="HOLD",
            reason_code="PENDING_HUMAN_REVIEW",
            reason=(
                f"{candidates - reviewed} review candidates "
                "have not been reviewed"
            ),
            owner=owner,
            scope=ctx.track,
        )

    escalations = int(
        (final["action"] == "escalate").sum()
    )

    if escalations:
        return Decision(
            status="HOLD",
            reason_code="PENDING_EXCEPTIONS",
            reason=f"{escalations} artefacts require escalation",
            owner=owner,
            scope=ctx.track,
        )

    return Decision(
        status="GO",
        reason_code="POLICY_CHECK_PASSED",
        reason="All generated actions satisfy the implemented policy",
        owner=owner,
        scope=ctx.track,
    )


# ----------------------------------------------------------------
# RUN
# ----------------------------------------------------------------

def run(ctx: RunContext) -> None:
    if ctx.track != "t08":
        raise NotImplementedError(
            f"Track {ctx.track} is not implemented by this pipeline. "
            "Only track t08 is supported."
        )

    data = load(ctx)

    spec = get_track(ctx.track)

    data = load(ctx)

    scored = process(ctx, data)

    ctx.stats["n_items"] = len(scored)

    queue = rank(ctx, scored)

    final = review(ctx, scored, queue)

    output_columns = (
        spec.pred_columns
        + [
            column
            for column in final.columns
            if column not in spec.pred_columns
        ]
    )

    final[output_columns].to_csv(
        ctx.out(spec.pred_file),
        index=False,
    )

    write_decision(
        decide(ctx, final),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )