"""
sessions_adaptive.py — Adaptive Learning Session Handlers for CSB and MC
Implements persistent sessions, multi-day resumption, server-side grading,
retry queues, replacement variant chains, and atomic legacy synchronization.
Operates inside SQLite BEGIN IMMEDIATE transactions.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
from flask import jsonify, g, request

from models import (
    db, User, CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat,
    LearningSession, CSBQuestionAttempt, MCSessionSlot, MCQuestionAttempt,
    CSBRetryQueue, MCRetryQueue, utc_now
)
from user import build_user_response
import csb_generator
import questions_mc_registry
import mc_grader

logger = logging.getLogger(__name__)

try:
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))


def get_current_ist_date() -> str:
    """Returns 'YYYY-MM-DD' server-enforced IST date."""
    return datetime.now(IST).strftime("%Y-%m-%d")


def format_display_date_ist() -> str:
    d = datetime.now(IST)
    return f"{d.day} {d.strftime('%b %Y')}"


def update_streak_ist(user: User) -> None:
    today_dt = datetime.now(IST).date()
    today = today_dt.isoformat()
    yesterday = (today_dt - timedelta(days=1)).isoformat()

    if user.last_date == today:
        return
    if user.last_date == yesterday:
        user.streak = (user.streak or 0) + 1
    else:
        user.streak = 1
    user.last_date = today


# ─────────────────────────────────────────────────────────
# CSB ADAPTIVE ENDPOINTS
# ─────────────────────────────────────────────────────────

def handle_csb_start():
    data = request.get_json(silent=True) or {}
    try:
        unit = int(data.get("unit", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Unit must be an integer between 1 and 5."}), 400

    if unit not in range(1, 6):
        return jsonify({"error": "Unit must be between 1 and 5."}), 400

    user = g.user
    today_ist = get_current_ist_date()
    expected_total = 30 if unit == 5 else 20

    try:
        # Atomic transaction
        db.session.execute(db.text("BEGIN IMMEDIATE"))

        # 1. Enforce IST Daily Completed Quota
        completed_today = LearningSession.query.filter_by(
            user_id=user.id,
            workbook="CSB",
            unit=unit,
            completed_ist_date=today_ist,
            status="submitted"
        ).first()
        if completed_today:
            db.session.rollback()
            return jsonify({"error": "Unit already completed today."}), 400

        # 2. Check for active session (multi-day resumption)
        active_session = LearningSession.query.filter_by(
            user_id=user.id,
            workbook="CSB",
            unit=unit,
            status="active"
        ).first()

        if active_session:
            # Restore exact persisted question pool
            attempts = (
                CSBQuestionAttempt.query
                .filter_by(learning_session_id=active_session.id)
                .order_by(CSBQuestionAttempt.position.asc())
                .all()
            )
            questions = [
                {
                    "position": a.position,
                    "question_text": a.question_text,
                    "operation_tag": a.operation_tag,
                    "difficulty_band": a.difficulty_band,
                    "is_retry": a.is_retry,
                }
                for a in attempts
            ]
            session_id = active_session.id
            db.session.commit()
            return jsonify({
                "session_id": session_id,
                "unit": unit,
                "total": active_session.total,
                "resumed": True,
                "questions": questions
            }), 200

        # 3. Create new session
        new_session = LearningSession(
            user_id=user.id,
            workbook="CSB",
            unit=unit,
            total=expected_total,
            status="active",
            started_at=utc_now()
        )
        db.session.add(new_session)
        db.session.flush()

        # Load pending retries
        pending_retries = (
            CSBRetryQueue.query
            .filter_by(user_id=user.id, unit=unit, status="pending")
            .order_by(CSBRetryQueue.incorrect_session_count.desc(), CSBRetryQueue.id.asc())
            .limit(3)
            .all()
        )
        retries_data = [
            {
                "id": r.id,
                "question_fingerprint": r.question_fingerprint,
                "question_text": r.question_text,
                "correct_answer": r.correct_answer,
                "operation_tag": r.operation_tag,
                "difficulty_band": r.difficulty_band,
            }
            for r in pending_retries
        ]

        pool = csb_generator.generate_csb_unit_pool(unit, grade=user.grade or 7, pending_retries=retries_data)

        # Pre-populate all attempts
        for item in pool:
            attempt_row = CSBQuestionAttempt(
                user_id=user.id,
                learning_session_id=new_session.id,
                unit=unit,
                position=item["position"],
                question_fingerprint=item["question_fingerprint"],
                question_text=item["question_text"],
                correct_answer=item["correct_answer"],
                operation_tag=item["operation_tag"],
                difficulty_band=item["difficulty_band"],
                is_retry=item.get("is_retry", False),
                retry_source_id=item.get("retry_source_id"),
                submitted_answer=None,
                is_correct=None
            )
            db.session.add(attempt_row)

        db.session.commit()

        client_questions = [
            {
                "position": q["position"],
                "question_text": q["question_text"],
                "operation_tag": q["operation_tag"],
                "difficulty_band": q["difficulty_band"],
                "is_retry": q.get("is_retry", False),
            }
            for q in pool
        ]
        return jsonify({
            "session_id": new_session.id,
            "unit": unit,
            "total": expected_total,
            "resumed": False,
            "questions": client_questions
        }), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("CSB start failed for user %s: %s", user.id, exc)
        return jsonify({"error": "Failed to start or resume CSB session."}), 500


def handle_csb_cancel():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required."}), 400

    user = g.user
    try:
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        session = LearningSession.query.filter_by(id=session_id, user_id=user.id).first()
        if not session:
            db.session.rollback()
            return jsonify({"error": "Session not found."}), 404

        if session.status == "submitted":
            db.session.rollback()
            return jsonify({"error": "Cannot cancel an already submitted session."}), 409

        if session.status == "cancelled":
            db.session.rollback()
            return jsonify({"message": "Session already cancelled.", "idempotent": True}), 200

        session.status = "cancelled"
        session.cancelled_at = utc_now()
        db.session.commit()
        return jsonify({"message": "Session successfully cancelled."}), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("CSB cancel failed for user %s, session %s: %s", user.id, session_id, exc)
        return jsonify({"error": "Failed to cancel session."}), 500


def handle_csb_submit():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    answers_list = data.get("answers")
    mood = str(data.get("mood") or "–")[:20]

    if not session_id or not isinstance(answers_list, list):
        return jsonify({"error": "session_id and answers array are required."}), 400

    user = g.user
    today_ist = get_current_ist_date()

    try:
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        session = LearningSession.query.filter_by(id=session_id, user_id=user.id).first()
        if not session:
            db.session.rollback()
            return jsonify({"error": "Session not found."}), 404

        # Replay Protection (Idempotent Resubmission)
        if session.status == "submitted":
            # Check if payload matches existing
            existing_attempts = (
                CSBQuestionAttempt.query
                .filter_by(learning_session_id=session.id)
                .order_by(CSBQuestionAttempt.position.asc())
                .all()
            )
            answers_by_pos = {a.get("position"): str(a.get("answer", "")).strip() for a in answers_list if isinstance(a, dict)}
            is_matching = True
            for ea in existing_attempts:
                if ea.submitted_answer != answers_by_pos.get(ea.position, ""):
                    is_matching = False
                    break

            if is_matching:
                db.session.rollback()
                return jsonify({
                    "score": session.score,
                    "total": session.total,
                    "completed_ist_date": session.completed_ist_date,
                    "idempotent": True,
                    "user": build_user_response(user)
                }), 200
            else:
                db.session.rollback()
                return jsonify({"error": "Session already submitted with different answers."}), 409

        if session.status == "cancelled":
            db.session.rollback()
            return jsonify({"error": "Cannot submit a cancelled session."}), 409

        if session.status != "active":
            db.session.rollback()
            return jsonify({"error": "Session is not active."}), 400

        # Check Daily Quota at submission time
        already_done = LearningSession.query.filter_by(
            user_id=user.id,
            workbook="CSB",
            unit=session.unit,
            completed_ist_date=today_ist,
            status="submitted"
        ).first()
        if already_done:
            db.session.rollback()
            return jsonify({"error": "Unit already completed today."}), 400

        # Check all positions provided
        expected_positions = set(range(session.total))
        answers_dict = {}
        for item in answers_list:
            if isinstance(item, dict) and "position" in item:
                answers_dict[int(item["position"])] = str(item.get("answer", "")).strip()

        if set(answers_dict.keys()) != expected_positions:
            db.session.rollback()
            return jsonify({"error": f"All positions 0 to {session.total - 1} must be provided."}), 400

        attempts = (
            CSBQuestionAttempt.query
            .filter_by(learning_session_id=session.id)
            .order_by(CSBQuestionAttempt.position.asc())
            .all()
        )

        score = 0
        now = utc_now()
        for att in attempts:
            user_ans = answers_dict.get(att.position, "")
            is_corr = csb_generator.grade_csb_question(user_ans, att.correct_answer, att.operation_tag)
            att.submitted_answer = user_ans
            att.is_correct = is_corr
            att.submitted_at = now
            att.completed_ist_date = today_ist
            if is_corr:
                score += 1

        # Update learning_sessions
        session.status = "submitted"
        session.submitted_at = now
        session.completed_ist_date = today_ist
        session.score = score

        # Atomic Legacy Insert
        legacy_csb = CSBSession(
            user_id=user.id,
            unit=session.unit,
            score=score,
            total=session.total,
            mood=mood,
            date=format_display_date_ist(),
            created_at=now
        )
        db.session.add(legacy_csb)
        db.session.flush()

        session.legacy_session_id = legacy_csb.id
        for att in attempts:
            att.csb_session_id = legacy_csb.id

        # Atomic Best Score Upsert
        best_row = CSBBestScore.query.filter_by(user_id=user.id, unit=session.unit).first()
        if best_row:
            if score > best_row.best_score:
                best_row.best_score = score
        else:
            db.session.add(CSBBestScore(user_id=user.id, unit=session.unit, best_score=score))

        update_streak_ist(user)

        # Process Retry Queues
        for att in attempts:
            if att.is_retry and att.retry_source_id:
                retry_item = db.session.get(CSBRetryQueue, att.retry_source_id)
                if retry_item and retry_item.status == "pending":
                    if att.is_correct:
                        retry_item.status = "resolved"
                        retry_item.resolved_at = now
                    else:
                        retry_item.incorrect_session_count += 1
                        retry_item.last_incorrect_date = today_ist
                        if retry_item.incorrect_session_count >= 2:
                            retry_item.status = "replaced"
            elif not att.is_correct:
                existing_retry = CSBRetryQueue.query.filter_by(
                    user_id=user.id,
                    unit=session.unit,
                    question_fingerprint=att.question_fingerprint,
                    status="pending"
                ).first()
                if existing_retry:
                    existing_retry.incorrect_session_count += 1
                    existing_retry.last_incorrect_date = today_ist
                    if existing_retry.incorrect_session_count >= 2:
                        existing_retry.status = "replaced"
                else:
                    new_retry = CSBRetryQueue(
                        user_id=user.id,
                        unit=session.unit,
                        question_fingerprint=att.question_fingerprint,
                        question_text=att.question_text,
                        correct_answer=att.correct_answer,
                        operation_tag=att.operation_tag,
                        difficulty_band=att.difficulty_band,
                        incorrect_session_count=1,
                        first_incorrect_date=today_ist,
                        last_incorrect_date=today_ist,
                        status="pending"
                    )
                    db.session.add(new_retry)

        db.session.commit()

        return jsonify({
            "score": score,
            "total": session.total,
            "completed_ist_date": today_ist,
            "user": build_user_response(user)
        }), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("CSB submit failed for user %s, session %s: %s", user.id, session_id, exc)
        return jsonify({"error": "Failed to submit CSB session."}), 500


# ─────────────────────────────────────────────────────────
# MC ADAPTIVE ENDPOINTS
# ─────────────────────────────────────────────────────────

def handle_mc_start():
    data = request.get_json(silent=True) or {}
    try:
        unit = int(data.get("unit", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Unit must be an integer between 1 and 5."}), 400

    if unit not in range(1, 6):
        return jsonify({"error": "Unit must be between 1 and 5."}), 400

    user = g.user
    today_ist = get_current_ist_date()

    try:
        db.session.execute(db.text("BEGIN IMMEDIATE"))

        # 1. Daily Quota Check
        completed_today = LearningSession.query.filter_by(
            user_id=user.id,
            workbook="MC",
            unit=unit,
            completed_ist_date=today_ist,
            status="submitted"
        ).first()
        if completed_today:
            db.session.rollback()
            return jsonify({"error": "Unit already completed today."}), 400

        # 2. Check for Active Session
        active_session = LearningSession.query.filter_by(
            user_id=user.id,
            workbook="MC",
            unit=unit,
            status="active"
        ).first()

        if active_session:
            slots = (
                MCSessionSlot.query
                .filter_by(learning_session_id=active_session.id)
                .order_by(MCSessionSlot.slot_number.asc())
                .all()
            )
            attempts = (
                MCQuestionAttempt.query
                .filter_by(learning_session_id=active_session.id)
                .all()
            )
            attempts_by_slot = {a.slot_id: a for a in attempts}

            sanitized_slots = []
            for s in slots:
                snap = json.loads(s.question_snapshot_json)
                clean_snap = questions_mc_registry.sanitize_question_for_client(snap)
                clean_snap["slot_number"] = s.slot_number
                clean_snap["presented_question_id"] = s.presented_question_id
                clean_snap["replacement_for_id"] = s.replacement_for_id
                att = attempts_by_slot.get(s.id)
                clean_snap["answered"] = att is not None
                clean_snap["is_correct"] = att.is_correct if att else None
                clean_snap["submitted_answer"] = att.submitted_answer if att else None
                sanitized_slots.append(clean_snap)

            session_id = active_session.id
            db.session.commit()
            return jsonify({
                "session_id": session_id,
                "unit": unit,
                "total": 15,
                "resumed": True,
                "slots": sanitized_slots
            }), 200

        # 3. Create New MC Session
        new_session = LearningSession(
            user_id=user.id,
            workbook="MC",
            unit=unit,
            total=15,
            status="active",
            started_at=utc_now()
        )
        db.session.add(new_session)
        db.session.flush()

        # Check for unresolved replacements and see if variants were authored
        unresolved_items = MCRetryQueue.query.filter_by(
            user_id=user.id,
            unit=unit,
            status="unresolved_replacement"
        ).all()
        for unres in unresolved_items:
            candidate_variants = questions_mc_registry.get_replacement_variants_for_slot(unit, unres.question_id)
            if candidate_variants:
                # Variant authored! Transition to replaced
                chosen = candidate_variants[0]
                unres.status = "replaced"
                unres.replacement_question_id = chosen["variant_id"]
                # Add retry for new variant
                var_retry = MCRetryQueue(
                    user_id=user.id,
                    unit=unit,
                    question_id=chosen["variant_id"],
                    concept_tag=chosen["concept_tag"],
                    difficulty_tier=chosen["cognitive_tier"],
                    incorrect_session_count=1,
                    first_incorrect_date=today_ist,
                    last_incorrect_date=today_ist,
                    status="pending",
                    replaces_question_id=unres.question_id
                )
                db.session.add(var_retry)

        # Allocate 15 Slots
        native_questions = questions_mc_registry.get_native_unit_questions(unit)
        assigned_slots = []

        for q in native_questions:
            slot_num = q["slot_number"]
            native_id = q["question_id"]

            # Check if this native question was permanently replaced
            active_replacement = MCRetryQueue.query.filter(
                MCRetryQueue.user_id == user.id,
                MCRetryQueue.unit == unit,
                MCRetryQueue.replaces_question_id.isnot(None),
                MCRetryQueue.status.in_(["pending", "resolved", "unresolved_replacement"])
            ).all()

            # Follow replacement chain if any originates from native_id
            target_qid = native_id
            replacement_for = None
            retry_source = None

            # Check if native item has 2 failures requiring replacement
            native_retry = MCRetryQueue.query.filter_by(
                user_id=user.id,
                unit=unit,
                question_id=native_id
            ).first()

            if native_retry:
                if native_retry.status == "replaced" and native_retry.replacement_question_id:
                    # Trace down to active leaf
                    curr_qid = native_retry.replacement_question_id
                    while True:
                        next_node = MCRetryQueue.query.filter_by(
                            user_id=user.id,
                            unit=unit,
                            question_id=curr_qid,
                            status="replaced"
                        ).first()
                        if next_node and next_node.replacement_question_id:
                            curr_qid = next_node.replacement_question_id
                        else:
                            break
                    target_qid = curr_qid
                    replacement_for = native_id
                    leaf_retry = MCRetryQueue.query.filter_by(user_id=user.id, unit=unit, question_id=target_qid).first()
                    retry_source = leaf_retry.id if leaf_retry else None
                elif native_retry.status == "pending" and native_retry.incorrect_session_count >= 2:
                    # Needs replacement now!
                    cand_variants = questions_mc_registry.get_replacement_variants_for_slot(unit, native_id)
                    verified_variants = [v for v in cand_variants if v.get("audit_status") == "verified"]
                    if verified_variants:
                        chosen = verified_variants[0]
                        native_retry.status = "replaced"
                        native_retry.replacement_question_id = chosen["variant_id"]
                        native_retry.resolved_at = utc_now()

                        var_retry = MCRetryQueue(
                            user_id=user.id,
                            unit=unit,
                            question_id=chosen["variant_id"],
                            concept_tag=chosen["concept_tag"],
                            difficulty_tier=chosen["cognitive_tier"],
                            incorrect_session_count=1,
                            first_incorrect_date=today_ist,
                            last_incorrect_date=today_ist,
                            status="pending",
                            replaces_question_id=native_id
                        )
                        db.session.add(var_retry)
                        db.session.flush()

                        target_qid = chosen["variant_id"]
                        replacement_for = native_id
                        retry_source = var_retry.id
                    else:
                        native_retry.status = "unresolved_replacement"
                        target_qid = native_id
                        retry_source = native_retry.id
                else:
                    retry_source = native_retry.id

            q_def = questions_mc_registry.get_mc_question(target_qid)
            if not q_def:
                q_def = q  # Fallback to native

            snap_json = json.dumps(q_def)
            slot_row = MCSessionSlot(
                learning_session_id=new_session.id,
                slot_number=slot_num,
                presented_question_id=target_qid,
                replacement_for_id=replacement_for,
                retry_source_id=retry_source,
                question_snapshot_json=snap_json,
                content_version=questions_mc_registry.CONTENT_VERSION,
                assigned_at=utc_now()
            )
            db.session.add(slot_row)

            clean_q = questions_mc_registry.sanitize_question_for_client(q_def)
            clean_q["slot_number"] = slot_num
            clean_q["presented_question_id"] = target_qid
            clean_q["replacement_for_id"] = replacement_for
            clean_q["answered"] = False
            clean_q["is_correct"] = None
            assigned_slots.append(clean_q)

        db.session.commit()

        return jsonify({
            "session_id": new_session.id,
            "unit": unit,
            "total": 15,
            "resumed": False,
            "slots": assigned_slots
        }), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("MC start failed for user %s: %s", user.id, exc)
        return jsonify({"error": "Failed to start or resume MC session."}), 500


def handle_mc_attempt():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    slot_number = data.get("slot_number")
    answer = data.get("answer")

    if not session_id or slot_number is None or answer is None:
        return jsonify({"error": "session_id, slot_number, and answer are required."}), 400

    try:
        slot_number = int(slot_number)
    except (ValueError, TypeError):
        return jsonify({"error": "slot_number must be an integer between 1 and 15."}), 400

    user = g.user

    try:
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        session = LearningSession.query.filter_by(id=session_id, user_id=user.id).first()
        if not session or session.status != "active":
            db.session.rollback()
            return jsonify({"error": "Active session not found."}), 400

        slot = MCSessionSlot.query.filter_by(
            learning_session_id=session.id,
            slot_number=slot_number
        ).first()
        if not slot:
            db.session.rollback()
            return jsonify({"error": f"Slot {slot_number} not found in this session."}), 404

        existing_att = MCQuestionAttempt.query.filter_by(slot_id=slot.id).first()
        submitted_str = str(answer).strip()

        if existing_att:
            if existing_att.submitted_answer == submitted_str:
                db.session.rollback()
                return jsonify({
                    "slot_number": slot_number,
                    "is_correct": existing_att.is_correct,
                    "idempotent": True
                }), 200
            else:
                db.session.rollback()
                return jsonify({"error": "Slot already answered in this session."}), 409

        # Authoritative Server-Side Grading
        snapshot = json.loads(slot.question_snapshot_json)
        payload = snapshot.get("authoritative_answer_payload")
        rule_key = snapshot.get("grading_rule_key", "grader_v1_fill")
        q_type = snapshot.get("question_type", "fill")

        is_corr = mc_grader.is_correct_mc(answer, payload, rule_key, q_type)

        attempt = MCQuestionAttempt(
            user_id=user.id,
            learning_session_id=session.id,
            slot_id=slot.id,
            submitted_answer=submitted_str,
            is_correct=is_corr,
            submitted_at=utc_now()
        )
        db.session.add(attempt)
        db.session.commit()

        return jsonify({
            "slot_number": slot_number,
            "is_correct": is_corr,
            "idempotent": False
        }), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("MC attempt failed for user %s, slot %s: %s", user.id, slot_number, exc)
        return jsonify({"error": "Failed to grade attempt."}), 500


def handle_mc_cancel():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required."}), 400

    user = g.user
    try:
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        session = LearningSession.query.filter_by(id=session_id, user_id=user.id).first()
        if not session:
            db.session.rollback()
            return jsonify({"error": "Session not found."}), 404

        if session.status == "submitted":
            db.session.rollback()
            return jsonify({"error": "Cannot cancel an already submitted session."}), 409

        if session.status == "cancelled":
            db.session.rollback()
            return jsonify({"message": "Session already cancelled.", "idempotent": True}), 200

        session.status = "cancelled"
        session.cancelled_at = utc_now()
        db.session.commit()
        return jsonify({"message": "Session successfully cancelled."}), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("MC cancel failed for user %s, session %s: %s", user.id, session_id, exc)
        return jsonify({"error": "Failed to cancel session."}), 500


def handle_mc_submit():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    mood = str(data.get("mood") or "–")[:20]

    if not session_id:
        return jsonify({"error": "session_id is required."}), 400

    user = g.user
    today_ist = get_current_ist_date()

    try:
        db.session.execute(db.text("BEGIN IMMEDIATE"))
        session = LearningSession.query.filter_by(id=session_id, user_id=user.id).first()
        if not session:
            db.session.rollback()
            return jsonify({"error": "Session not found."}), 404

        # Replay Protection
        if session.status == "submitted":
            db.session.rollback()
            return jsonify({
                "score": session.score,
                "total": session.total,
                "completed_ist_date": session.completed_ist_date,
                "idempotent": True,
                "user": build_user_response(user)
            }), 200

        if session.status == "cancelled":
            db.session.rollback()
            return jsonify({"error": "Cannot submit a cancelled session."}), 409

        if session.status != "active":
            db.session.rollback()
            return jsonify({"error": "Session is not active."}), 400

        # Enforce IST Daily Quota
        already_done = LearningSession.query.filter_by(
            user_id=user.id,
            workbook="MC",
            unit=session.unit,
            completed_ist_date=today_ist,
            status="submitted"
        ).first()
        if already_done:
            db.session.rollback()
            return jsonify({"error": "Unit already completed today."}), 400

        # Strict 100% Completion: all 15 slots must have an attempt
        attempts = (
            MCQuestionAttempt.query
            .filter_by(learning_session_id=session.id)
            .all()
        )
        if len(attempts) < 15:
            db.session.rollback()
            return jsonify({"error": "All 15 questions must be answered before submitting."}), 400

        score = sum(1 for a in attempts if a.is_correct)
        now = utc_now()

        # Update learning_sessions
        session.status = "submitted"
        session.submitted_at = now
        session.completed_ist_date = today_ist
        session.score = score

        # Atomic Legacy Insert
        legacy_mc = MCSession(
            user_id=user.id,
            unit=session.unit,
            score=score,
            total=15,
            mood=mood,
            date=format_display_date_ist(),
            created_at=now
        )
        db.session.add(legacy_mc)
        db.session.flush()

        session.legacy_session_id = legacy_mc.id
        for att in attempts:
            att.mc_session_id = legacy_mc.id

        # Atomic Best Score Upsert
        best_row = MCBestScore.query.filter_by(user_id=user.id, unit=session.unit).first()
        if best_row:
            if score > best_row.best_score:
                best_row.best_score = score
        else:
            db.session.add(MCBestScore(user_id=user.id, unit=session.unit, best_score=score))

        # Atomic MC Format Statistics Upsert
        # Group attempts by question type from slot snapshot
        slots = MCSessionSlot.query.filter_by(learning_session_id=session.id).all()
        slots_by_id = {s.id: s for s in slots}

        type_stats_tally = {"findMistake": [0, 0], "tf": [0, 0], "radio": [0, 0], "fill": [0, 0]}
        for att in attempts:
            slot = slots_by_id.get(att.slot_id)
            if slot:
                snap = json.loads(slot.question_snapshot_json)
                qtype = snap.get("question_type", "fill")
                if qtype in type_stats_tally:
                    type_stats_tally[qtype][0] += 1
                    if att.is_correct:
                        type_stats_tally[qtype][1] += 1

        for type_key, (att_count, corr_count) in type_stats_tally.items():
            if att_count > 0:
                t_row = MCTypeStat.query.filter_by(user_id=user.id, type_key=type_key).first()
                if t_row:
                    t_row.attempted += att_count
                    t_row.correct += corr_count
                else:
                    db.session.add(MCTypeStat(
                        user_id=user.id,
                        type_key=type_key,
                        attempted=att_count,
                        correct=corr_count
                    ))

        update_streak_ist(user)

        # Process MC Retry Queues & Replacements
        for att in attempts:
            slot = slots_by_id.get(att.slot_id)
            if not slot:
                continue
            snap = json.loads(slot.question_snapshot_json)
            qid = slot.presented_question_id
            audit_status = snap.get("audit_status", "proposed")
            concept_tag = snap.get("concept_tag", "general_math")
            tier = snap.get("difficulty_tier", "standard")

            if att.is_correct:
                if slot.retry_source_id:
                    retry_item = db.session.get(MCRetryQueue, slot.retry_source_id)
                    if retry_item and retry_item.status in ("pending", "unresolved_replacement"):
                        retry_item.status = "resolved"
                        retry_item.resolved_at = now
            else:
                # Question answered incorrectly
                if slot.retry_source_id:
                    retry_item = db.session.get(MCRetryQueue, slot.retry_source_id)
                    if retry_item and retry_item.status == "pending":
                        retry_item.incorrect_session_count += 1
                        retry_item.last_incorrect_date = today_ist

                        if retry_item.incorrect_session_count >= 2:
                            if audit_status == "verified":
                                # Find next verified variant
                                cand_vars = questions_mc_registry.get_replacement_variants_for_slot(session.unit, slot.replacement_for_id or qid)
                                verified_vars = [v for v in cand_vars if v.get("audit_status") == "verified" and v["variant_id"] != qid]
                                if verified_vars:
                                    chosen = verified_vars[0]
                                    retry_item.status = "replaced"
                                    retry_item.replacement_question_id = chosen["variant_id"]
                                    retry_item.resolved_at = now

                                    new_var_retry = MCRetryQueue(
                                        user_id=user.id,
                                        unit=session.unit,
                                        question_id=chosen["variant_id"],
                                        concept_tag=chosen["concept_tag"],
                                        difficulty_tier=chosen["cognitive_tier"],
                                        incorrect_session_count=1,
                                        first_incorrect_date=today_ist,
                                        last_incorrect_date=today_ist,
                                        status="pending",
                                        replaces_question_id=qid
                                    )
                                    db.session.add(new_var_retry)
                                else:
                                    retry_item.status = "unresolved_replacement"
                            else:
                                # Proposed or Unresolved -> transitions to unresolved_replacement
                                retry_item.status = "unresolved_replacement"
                else:
                    # First failure for question not previously queued
                    existing_retry = MCRetryQueue.query.filter_by(
                        user_id=user.id,
                        unit=session.unit,
                        question_id=qid,
                        status="pending"
                    ).first()
                    if existing_retry:
                        existing_retry.incorrect_session_count += 1
                        existing_retry.last_incorrect_date = today_ist
                        if existing_retry.incorrect_session_count >= 2:
                            if audit_status == "verified":
                                cand_vars = questions_mc_registry.get_replacement_variants_for_slot(session.unit, qid)
                                verified_vars = [v for v in cand_vars if v.get("audit_status") == "verified"]
                                if verified_vars:
                                    chosen = verified_vars[0]
                                    existing_retry.status = "replaced"
                                    existing_retry.replacement_question_id = chosen["variant_id"]
                                    existing_retry.resolved_at = now

                                    new_var_retry = MCRetryQueue(
                                        user_id=user.id,
                                        unit=session.unit,
                                        question_id=chosen["variant_id"],
                                        concept_tag=chosen["concept_tag"],
                                        difficulty_tier=chosen["cognitive_tier"],
                                        incorrect_session_count=1,
                                        first_incorrect_date=today_ist,
                                        last_incorrect_date=today_ist,
                                        status="pending",
                                        replaces_question_id=qid
                                    )
                                    db.session.add(new_var_retry)
                                else:
                                    existing_retry.status = "unresolved_replacement"
                            else:
                                existing_retry.status = "unresolved_replacement"
                    else:
                        new_r = MCRetryQueue(
                            user_id=user.id,
                            unit=session.unit,
                            question_id=qid,
                            concept_tag=concept_tag,
                            difficulty_tier=tier,
                            incorrect_session_count=1,
                            first_incorrect_date=today_ist,
                            last_incorrect_date=today_ist,
                            status="pending"
                        )
                        db.session.add(new_r)

        db.session.commit()

        return jsonify({
            "score": score,
            "total": 15,
            "completed_ist_date": today_ist,
            "user": build_user_response(user)
        }), 200

    except Exception as exc:
        db.session.rollback()
        logger.error("MC submit failed for user %s, session %s: %s", user.id, session_id, exc)
        return jsonify({"error": "Failed to submit MC session."}), 500
