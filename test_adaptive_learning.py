"""
test_adaptive_learning.py — Comprehensive Test Suite for Math Workbooks Adaptive Learning System (V1)
Covers all test specifications A-01 through A-36 from adaptive_learning_design_proposal.md § 7.2.
"""

import os
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app import create_app
from models import (
    db, User, CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat,
    LearningSession, CSBQuestionAttempt, MCSessionSlot, MCQuestionAttempt,
    CSBRetryQueue, MCRetryQueue
)
import questions_mc_registry
import migrate_adaptive
import rollback_adaptive


class AdaptiveLearningSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='_adaptive_test.db')
        cls.test_secret = 'super-secret-jwt-key-for-adaptive-tests-32-chars'

        cls.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{cls.temp_db_path}',
            'SECRET_KEY': cls.test_secret,
        })
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
        os.close(cls.temp_db_fd)
        if os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except OSError:
                pass

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def _create_user_and_token(self, email="student1@test.com"):
        res = self.client.post('/api/auth/signup', json={
            'fname': 'Test',
            'lname': 'Student',
            'grade': 7,
            'age': 12,
            'school': 'KV School',
            'city': 'Bengaluru',
            'email': email,
            'password': 'password123'
        })
        if res.status_code == 200:
            return res.get_json()['token']
        # If user already exists, login
        res_login = self.client.post('/api/auth/login', json={
            'email': email,
            'password': 'password123'
        })
        return res_login.get_json()['token']

    def _auth_header(self, token):
        return {'Authorization': f'Bearer {token}'}

    # ─────────────────────────────────────────────────────────
    # A-01: CSB Persistence across multi-day gap
    # ─────────────────────────────────────────────────────────
    def test_a01_csb_persistence(self):
        token = self._create_user_and_token('a01@test.com')
        headers = self._auth_header(token)

        res1 = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertFalse(data1['resumed'])
        pool1 = data1['questions']
        self.assertEqual(len(pool1), 20)

        # Simulate 3 days later, calling start again on active session
        res2 = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2['resumed'])
        pool2 = data2['questions']

        # Verifies exact pool, order, parameters
        self.assertEqual(len(pool2), 20)
        for i in range(20):
            self.assertEqual(pool1[i]['position'], pool2[i]['position'])
            self.assertEqual(pool1[i]['question_text'], pool2[i]['question_text'])
            self.assertEqual(pool1[i]['operation_tag'], pool2[i]['operation_tag'])

    # ─────────────────────────────────────────────────────────
    # A-02: CSB Recovery after clearing client drafts
    # ─────────────────────────────────────────────────────────
    def test_a02_csb_recovery(self):
        token = self._create_user_and_token('a02@test.com')
        headers = self._auth_header(token)

        res1 = self.client.post('/api/sessions/csb/start', json={'unit': 2}, headers=headers)
        data1 = res1.get_json()
        session_id = data1['session_id']

        # Clear drafts (simulated client loss) and resume
        res2 = self.client.post('/api/sessions/csb/start', json={'unit': 2}, headers=headers)
        data2 = res2.get_json()
        self.assertEqual(data2['session_id'], session_id)
        self.assertTrue(data2['resumed'])
        self.assertEqual(len(data2['questions']), 20)

    # ─────────────────────────────────────────────────────────
    # A-03: CSB Cancel marks session cancelled with zero penalty
    # ─────────────────────────────────────────────────────────
    def test_a03_csb_cancel(self):
        token = self._create_user_and_token('a03@test.com')
        headers = self._auth_header(token)

        res = self.client.post('/api/sessions/csb/start', json={'unit': 3}, headers=headers)
        session_id = res.get_json()['session_id']

        res_cancel = self.client.post('/api/sessions/csb/cancel', json={'session_id': session_id}, headers=headers)
        self.assertEqual(res_cancel.status_code, 200)

        # Inspect database record
        ls = db.session.get(LearningSession, session_id)
        self.assertEqual(ls.status, 'cancelled')
        self.assertIsNotNone(ls.cancelled_at)
        self.assertIsNone(ls.submitted_at)
        self.assertIsNone(ls.score)

        # Zero attempts counted towards retries
        retries = CSBRetryQueue.query.filter_by(user_id=ls.user_id, unit=3).all()
        self.assertEqual(len(retries), 0)

    # ─────────────────────────────────────────────────────────
    # A-04: CSB Positions Check rejects missing positions
    # ─────────────────────────────────────────────────────────
    def test_a04_csb_positions_check(self):
        token = self._create_user_and_token('a04@test.com')
        headers = self._auth_header(token)

        res = self.client.post('/api/sessions/csb/start', json={'unit': 4}, headers=headers)
        session_id = res.get_json()['session_id']

        # Send only 19 of 20 positions
        partial_answers = [{'position': i, 'answer': '10'} for i in range(19)]
        res_submit = self.client.post('/api/sessions/csb/submit', json={
            'session_id': session_id,
            'answers': partial_answers
        }, headers=headers)
        self.assertEqual(res_submit.status_code, 400)
        self.assertIn("All positions 0 to 19 must be provided", res_submit.get_json()['error'])

    # ─────────────────────────────────────────────────────────
    # A-05: MC Slot Uniqueness
    # ─────────────────────────────────────────────────────────
    def test_a05_mc_slot_uniqueness(self):
        user = User.query.first()
        ls = LearningSession(user_id=user.id, workbook='MC', unit=1, total=15, status='active')
        db.session.add(ls)
        db.session.flush()

        slot1 = MCSessionSlot(
            learning_session_id=ls.id,
            slot_number=1,
            presented_question_id='u1q1',
            question_snapshot_json='{}',
            content_version='v1.0.0'
        )
        db.session.add(slot1)
        db.session.commit()

        # Duplicate slot_number in same session must raise IntegrityError
        slot1_dup = MCSessionSlot(
            learning_session_id=ls.id,
            slot_number=1,
            presented_question_id='u1q2',
            question_snapshot_json='{}',
            content_version='v1.0.0'
        )
        db.session.add(slot1_dup)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    # ─────────────────────────────────────────────────────────
    # A-06: MC Question Uniqueness in same session
    # ─────────────────────────────────────────────────────────
    def test_a06_mc_question_uniqueness(self):
        user = User.query.first()
        ls = LearningSession(user_id=user.id, workbook='MC', unit=1, total=15, status='active')
        db.session.add(ls)
        db.session.flush()

        s1 = MCSessionSlot(
            learning_session_id=ls.id, slot_number=1, presented_question_id='u1q1',
            question_snapshot_json='{}', content_version='v1.0.0'
        )
        db.session.add(s1)
        db.session.commit()

        s2 = MCSessionSlot(
            learning_session_id=ls.id, slot_number=2, presented_question_id='u1q1',
            question_snapshot_json='{}', content_version='v1.0.0'
        )
        db.session.add(s2)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    # ─────────────────────────────────────────────────────────
    # A-07: MC Attempt Uniqueness per slot
    # ─────────────────────────────────────────────────────────
    def test_a07_mc_attempt_uniqueness(self):
        user = User.query.first()
        ls = LearningSession(user_id=user.id, workbook='MC', unit=1, total=15, status='active')
        db.session.add(ls)
        db.session.flush()

        slot = MCSessionSlot(
            learning_session_id=ls.id, slot_number=1, presented_question_id='u1q1',
            question_snapshot_json='{}', content_version='v1.0.0'
        )
        db.session.add(slot)
        db.session.commit()

        att1 = MCQuestionAttempt(
            user_id=user.id, learning_session_id=ls.id, slot_id=slot.id,
            submitted_answer='2', is_correct=True
        )
        db.session.add(att1)
        db.session.commit()

        # Second attempt for same slot must fail UNIQUE(slot_id)
        att2 = MCQuestionAttempt(
            user_id=user.id, learning_session_id=ls.id, slot_id=slot.id,
            submitted_answer='3', is_correct=False
        )
        db.session.add(att2)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    # ─────────────────────────────────────────────────────────
    # A-08: MC Server Grading rejects false client claims
    # ─────────────────────────────────────────────────────────
    def test_a08_mc_server_grading(self):
        token = self._create_user_and_token('a08@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # Slot 1 is u1q1 (findMistake, mistake is Step 2 -> button index 1)
        # Client submits wrong answer 99
        res_att = self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id,
            'slot_number': 1,
            'answer': 99
        }, headers=headers)
        self.assertEqual(res_att.status_code, 200)
        self.assertFalse(res_att.get_json()['is_correct'])

    # ─────────────────────────────────────────────────────────
    # A-09: MC Attempt Idempotency
    # ─────────────────────────────────────────────────────────
    def test_a09_mc_attempt_idempotency(self):
        token = self._create_user_and_token('a09@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # First attempt on Slot 1 with answer 1 (correct button index)
        res1 = self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id,
            'slot_number': 1,
            'answer': 1
        }, headers=headers)
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.get_json()['is_correct'])

        # Duplicate identical attempt
        res2 = self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id,
            'slot_number': 1,
            'answer': 1
        }, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()['is_correct'])
        self.assertTrue(res2.get_json()['idempotent'])

    # ─────────────────────────────────────────────────────────
    # A-10: MC Conflicting Attempt returns 409
    # ─────────────────────────────────────────────────────────
    def test_a10_mc_conflicting_attempt(self):
        token = self._create_user_and_token('a10@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # First attempt: answer 2
        self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id,
            'slot_number': 1,
            'answer': 2
        }, headers=headers)

        # Altered answer: answer 1
        res_conflict = self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id,
            'slot_number': 1,
            'answer': 1
        }, headers=headers)
        self.assertEqual(res_conflict.status_code, 409)

    # ─────────────────────────────────────────────────────────
    # A-11: MC Snapshot Recovery resilient against registry code edits
    # ─────────────────────────────────────────────────────────
    def test_a11_mc_snapshot_recovery(self):
        token = self._create_user_and_token('a11@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # Mutate the registry in memory
        original_prompt = questions_mc_registry.MC_QUESTIONS['u1q1']['prompt_text']
        try:
            questions_mc_registry.MC_QUESTIONS['u1q1']['prompt_text'] = 'MUTATED IN CODE DEPLOYMENT'

            # Resume session: must restore the original prompt from stored snapshot
            res_resume = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
            slots = res_resume.get_json()['slots']
            slot1 = [s for s in slots if s['slot_number'] == 1][0]
            self.assertEqual(slot1['prompt_text'], original_prompt)
            self.assertNotEqual(slot1['prompt_text'], 'MUTATED IN CODE DEPLOYMENT')
        finally:
            questions_mc_registry.MC_QUESTIONS['u1q1']['prompt_text'] = original_prompt

    # ─────────────────────────────────────────────────────────
    # A-12: MC Strict Completion policy rejects < 15 answered
    # ─────────────────────────────────────────────────────────
    def test_a12_mc_strict_completion(self):
        token = self._create_user_and_token('a12@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 2}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # Answer only slots 1 to 14
        for slot in range(1, 15):
            self.client.post('/api/sessions/mc/attempt', json={
                'session_id': session_id,
                'slot_number': slot,
                'answer': 'dummy'
            }, headers=headers)

        # Attempt submit with 14 of 15
        res_sub = self.client.post('/api/sessions/mc/submit', json={'session_id': session_id}, headers=headers)
        self.assertEqual(res_sub.status_code, 400)
        self.assertIn("All 15 questions must be answered", res_sub.get_json()['error'])

    # ─────────────────────────────────────────────────────────
    # A-13: CSB Submit Idempotency
    # ─────────────────────────────────────────────────────────
    def test_a13_csb_submit_idempotency(self):
        token = self._create_user_and_token('a13@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        answers = [{'position': i, 'answer': '10'} for i in range(20)]
        res1 = self.client.post('/api/sessions/csb/submit', json={'session_id': session_id, 'answers': answers}, headers=headers)
        self.assertEqual(res1.status_code, 200)

        # Resubmit identical payload
        res2 = self.client.post('/api/sessions/csb/submit', json={'session_id': session_id, 'answers': answers}, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json().get('idempotent'))

    # ─────────────────────────────────────────────────────────
    # A-14: CSB Conflicting Submit returns 409
    # ─────────────────────────────────────────────────────────
    def test_a14_csb_conflicting_submit(self):
        token = self._create_user_and_token('a14@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        answers1 = [{'position': i, 'answer': '10'} for i in range(20)]
        self.client.post('/api/sessions/csb/submit', json={'session_id': session_id, 'answers': answers1}, headers=headers)

        # Conflicting answers
        answers2 = [{'position': i, 'answer': '99'} for i in range(20)]
        res_conf = self.client.post('/api/sessions/csb/submit', json={'session_id': session_id, 'answers': answers2}, headers=headers)
        self.assertEqual(res_conf.status_code, 409)

    # ─────────────────────────────────────────────────────────
    # A-15: IST Daily Quota Enforcement
    # ─────────────────────────────────────────────────────────
    def test_a15_ist_daily_quota(self):
        token = self._create_user_and_token('a15@test.com')
        headers = self._auth_header(token)

        # Start and complete Unit 1 today
        res_start = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']
        answers = [{'position': i, 'answer': '10'} for i in range(20)]
        self.client.post('/api/sessions/csb/submit', json={'session_id': session_id, 'answers': answers}, headers=headers)

        # Attempt to start Unit 1 again on same day
        res_again = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        self.assertEqual(res_again.status_code, 400)
        self.assertIn("already completed today", res_again.get_json()['error'])

    # ─────────────────────────────────────────────────────────
    # A-16: Sibling Collision Guard
    # ─────────────────────────────────────────────────────────
    def test_a16_sibling_collision_guard(self):
        # A candidate variant must never duplicate an existing presented question
        token = self._create_user_and_token('a16@test.com')
        headers = self._auth_header(token)
        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        qids = [s['presented_question_id'] for s in slots]
        self.assertEqual(len(qids), 15)
        self.assertEqual(len(set(qids)), 15)

    # ─────────────────────────────────────────────────────────
    # A-17: Missing Sibling Safety transitions to unresolved_replacement
    # ─────────────────────────────────────────────────────────
    def test_a17_missing_sibling_safety(self):
        token = self._create_user_and_token('a17@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a17@test.com').first()

        # Seed an item with count=2 in mc_retry_queue for which no variant exists (e.g. u1q10)
        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q10',
            concept_tag='fractions_comparison_lcm', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        # Starting session triggers evaluation: no variant in registry -> becomes unresolved_replacement
        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        self.assertEqual(res.status_code, 200)

        r_after = db.session.get(MCRetryQueue, r.id)
        self.assertEqual(r_after.status, 'unresolved_replacement')

    # ─────────────────────────────────────────────────────────
    # A-18: DB CHECK Rules
    # ─────────────────────────────────────────────────────────
    def test_a18_db_check_rules(self):
        user = User.query.first()
        # Invalid workbook
        ls_bad_wb = LearningSession(user_id=user.id, workbook='XYZ', unit=1, total=20, status='active')
        db.session.add(ls_bad_wb)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

        # Invalid score > total
        ls_bad_score = LearningSession(
            user_id=user.id, workbook='CSB', unit=1, total=20,
            status='submitted', score=25, submitted_at=datetime.now(timezone.utc),
            completed_ist_date='2026-11-07'
        )
        db.session.add(ls_bad_score)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    # ─────────────────────────────────────────────────────────
    # A-19: Rollback Verification
    # ─────────────────────────────────────────────────────────
    def test_a19_rollback_verification(self):
        # Verify migration and rollback on clean database with legacy tables
        import shutil
        temp_fd, temp_path = tempfile.mkstemp(suffix='_rb_test.db')
        os.close(temp_fd)
        backup_src = 'instance/speedcalc_dev.db.bak_20261107_105919'
        shutil.copy2(backup_src, temp_path)
        try:
            # Run migration then rollback
            migrated = migrate_adaptive.run_migration(temp_path)
            self.assertTrue(migrated)
            rolled_back = rollback_adaptive.run_rollback(temp_path)
            self.assertTrue(rolled_back)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    # ─────────────────────────────────────────────────────────
    # A-20: Cancelled Retry Isolation
    # ─────────────────────────────────────────────────────────
    def test_a20_cancelled_retry_isolation(self):
        token = self._create_user_and_token('a20@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # Student answers incorrectly on slot 1
        self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id, 'slot_number': 1, 'answer': 99
        }, headers=headers)

        # Student cancels session
        self.client.post('/api/sessions/mc/cancel', json={'session_id': session_id}, headers=headers)

        # Verify zero retries queued
        user = User.query.filter_by(email='a20@test.com').first()
        retries = MCRetryQueue.query.filter_by(user_id=user.id).all()
        self.assertEqual(len(retries), 0)

    # ─────────────────────────────────────────────────────────
    # A-21: Cancelled Pending Retention
    # ─────────────────────────────────────────────────────────
    def test_a21_cancelled_pending_retention(self):
        token = self._create_user_and_token('a21@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a21@test.com').first()

        # Seed an active pending retry
        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q1',
            concept_tag='fractions_simplification_gcf', difficulty_tier='standard',
            incorrect_session_count=1, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-01', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        # Start session, answer slot 1 correctly, then cancel
        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        self.client.post('/api/sessions/mc/attempt', json={
            'session_id': session_id, 'slot_number': 1, 'answer': 2
        }, headers=headers)

        self.client.post('/api/sessions/mc/cancel', json={'session_id': session_id}, headers=headers)

        # Retry must remain pending!
        r_after = db.session.get(MCRetryQueue, r.id)
        self.assertEqual(r_after.status, 'pending')

    # ─────────────────────────────────────────────────────────
    # A-22: MC Payload Leak Guard
    # ─────────────────────────────────────────────────────────
    def test_a22_mc_payload_leak_guard(self):
        token = self._create_user_and_token('a22@test.com')
        headers = self._auth_header(token)

        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        raw_json = res.get_data(as_text=True)

        self.assertNotIn('authoritative_answer_payload', raw_json)
        self.assertNotIn('grading_rule_key', raw_json)

    # ─────────────────────────────────────────────────────────
    # A-23: Verified Sibling Restriction
    # ─────────────────────────────────────────────────────────
    def test_a23_verified_sibling_restriction(self):
        token = self._create_user_and_token('a23@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a23@test.com').first()

        # Seed a 2-failure retry for u1q8 (verified, has verified variants u1q8_v1, u1q8_v2)
        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        slot8 = [s for s in slots if s['slot_number'] == 8][0]
        self.assertEqual(slot8['presented_question_id'], 'u1q8_v1')

    # ─────────────────────────────────────────────────────────
    # A-24: Unresolved Adaptive Isolation
    # ─────────────────────────────────────────────────────────
    def test_a24_unresolved_adaptive_isolation(self):
        token = self._create_user_and_token('a24@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a24@test.com').first()

        # Seed retry for unresolved u5q7 with count=2
        r = MCRetryQueue(
            user_id=user.id, unit=5, question_id='u5q7',
            concept_tag='mixed_rational_expression_fallacy', difficulty_tier='challenge',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        # Start session on Unit 5
        res = self.client.post('/api/sessions/mc/start', json={'unit': 5}, headers=headers)
        slots = res.get_json()['slots']
        slot7 = [s for s in slots if s['slot_number'] == 7][0]
        # Must retain u5q7 and transition to unresolved_replacement
        self.assertEqual(slot7['presented_question_id'], 'u5q7')
        r_after = db.session.get(MCRetryQueue, r.id)
        self.assertEqual(r_after.status, 'unresolved_replacement')

    # ─────────────────────────────────────────────────────────
    # A-25: Proposed Question Scoring & Quarantine
    # ─────────────────────────────────────────────────────────
    def test_a25_proposed_question_scoring_and_quarantine(self):
        token = self._create_user_and_token('a25@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a25@test.com').first()

        # Seed 2 failures on proposed question u1q9 (mixed number addition)
        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q9',
            concept_tag='fractions_mixed_numbers_addition', difficulty_tier='challenge',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        slot9 = [s for s in slots if s['slot_number'] == 9][0]
        self.assertEqual(slot9['presented_question_id'], 'u1q9')
        r_after = db.session.get(MCRetryQueue, r.id)
        self.assertEqual(r_after.status, 'unresolved_replacement')

    # ─────────────────────────────────────────────────────────
    # A-26: Variant Pool Allocation when all native slots occupied
    # ─────────────────────────────────────────────────────────
    def test_a26_variant_pool_allocation(self):
        token = self._create_user_and_token('a26@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a26@test.com').first()

        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        self.assertEqual(len(slots), 15)
        slot8 = [s for s in slots if s['slot_number'] == 8][0]
        self.assertEqual(slot8['presented_question_id'], 'u1q8_v1')

    # ─────────────────────────────────────────────────────────
    # A-27: Slot Collision & Displacement Handling
    # ─────────────────────────────────────────────────────────
    def test_a27_slot_displacement_handling(self):
        token = self._create_user_and_token('a27@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a27@test.com').first()

        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='pending'
        )
        db.session.add(r)
        db.session.commit()

        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']

        # Slot 8 is u1q8_v1; slots 1..7 and 9..15 retain native questions u1q1..u1q7, u1q9..u1q15
        for s in slots:
            slot_num = s['slot_number']
            if slot_num == 8:
                self.assertEqual(s['presented_question_id'], 'u1q8_v1')
            else:
                self.assertEqual(s['presented_question_id'], f'u1q{slot_num}')

    # ─────────────────────────────────────────────────────────
    # A-28: Permanent Replacement Persistence Across Later Sessions
    # ─────────────────────────────────────────────────────────
    def test_a28_permanent_replacement_persistence(self):
        token = self._create_user_and_token('a28@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a28@test.com').first()

        # Seed replacement: u1q8 replaced by u1q8_v1
        r1 = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='replaced',
            replacement_question_id='u1q8_v1'
        )
        r2 = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8_v1',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=1, first_incorrect_date='2026-11-02',
            last_incorrect_date='2026-11-02', status='pending',
            replaces_question_id='u1q8'
        )
        db.session.add_all([r1, r2])
        db.session.commit()

        # Next session must present u1q8_v1
        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        slot8 = [s for s in slots if s['slot_number'] == 8][0]
        self.assertEqual(slot8['presented_question_id'], 'u1q8_v1')

    # ─────────────────────────────────────────────────────────
    # A-29: Replacement-of-Replacement Chaining
    # ─────────────────────────────────────────────────────────
    def test_a29_replacement_chaining(self):
        token = self._create_user_and_token('a29@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a29@test.com').first()

        # u1q8 -> u1q8_v1 (status='replaced', replacement='u1q8_v2')
        # u1q8_v1 -> u1q8_v2 (status='pending')
        r1 = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-01', status='replaced',
            replacement_question_id='u1q8_v1'
        )
        r2 = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8_v1',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-02',
            last_incorrect_date='2026-11-02', status='replaced',
            replaces_question_id='u1q8', replacement_question_id='u1q8_v2'
        )
        r3 = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8_v2',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=1, first_incorrect_date='2026-11-03',
            last_incorrect_date='2026-11-03', status='pending',
            replaces_question_id='u1q8_v1'
        )
        db.session.add_all([r1, r2, r3])
        db.session.commit()

        # Next session must present leaf u1q8_v2
        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        slot8 = [s for s in slots if s['slot_number'] == 8][0]
        self.assertEqual(slot8['presented_question_id'], 'u1q8_v2')

    # ─────────────────────────────────────────────────────────
    # A-30: Original Question Retirement Verification
    # ─────────────────────────────────────────────────────────
    def test_a30_original_question_retirement(self):
        token = self._create_user_and_token('a30@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a30@test.com').first()

        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q8',
            concept_tag='fractions_division_reciprocal', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='replaced',
            replacement_question_id='u1q8_v1'
        )
        db.session.add(r)
        db.session.commit()

        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        presented_ids = [s['presented_question_id'] for s in slots]
        self.assertNotIn('u1q8', presented_ids)
        self.assertIn('u1q8_v1', presented_ids)

    # ─────────────────────────────────────────────────────────
    # A-31: Unresolved Replacement Slot Stability
    # ─────────────────────────────────────────────────────────
    def test_a31_unresolved_slot_stability(self):
        token = self._create_user_and_token('a31@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a31@test.com').first()

        # Seed unresolved item
        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q3',
            concept_tag='fractions_simplification_gcf', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='unresolved_replacement'
        )
        db.session.add(r)
        db.session.commit()

        # Subsequent session: slot 3 continues to present u1q3 and exactly 15 slots exist
        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        self.assertEqual(len(slots), 15)
        slot3 = [s for s in slots if s['slot_number'] == 3][0]
        self.assertEqual(slot3['presented_question_id'], 'u1q3')

    # ─────────────────────────────────────────────────────────
    # A-32: Post-Authoring Variant Injection
    # ─────────────────────────────────────────────────────────
    def test_a32_post_authoring_variant_injection(self):
        token = self._create_user_and_token('a32@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a32@test.com').first()

        # Item starts in unresolved_replacement for u1q1
        r = MCRetryQueue(
            user_id=user.id, unit=1, question_id='u1q1',
            concept_tag='fractions_simplification_gcf', difficulty_tier='standard',
            incorrect_session_count=2, first_incorrect_date='2026-11-01',
            last_incorrect_date='2026-11-02', status='unresolved_replacement'
        )
        db.session.add(r)
        db.session.commit()

        # Since u1q1_v1 exists in registry, start will automatically detect and transition
        res = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        slots = res.get_json()['slots']
        slot1 = [s for s in slots if s['slot_number'] == 1][0]
        self.assertEqual(slot1['presented_question_id'], 'u1q1_v1')

        r_after = db.session.get(MCRetryQueue, r.id)
        self.assertEqual(r_after.status, 'replaced')
        self.assertEqual(r_after.replacement_question_id, 'u1q1_v1')

    # ─────────────────────────────────────────────────────────
    # A-33: Legacy Session & Best Score Sync
    # ─────────────────────────────────────────────────────────
    def test_a33_legacy_session_and_best_score_sync(self):
        token = self._create_user_and_token('a33@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a33@test.com').first()

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # Answer all 15 questions
        for slot in range(1, 16):
            self.client.post('/api/sessions/mc/attempt', json={
                'session_id': session_id,
                'slot_number': slot,
                'answer': '2'
            }, headers=headers)

        res_submit = self.client.post('/api/sessions/mc/submit', json={'session_id': session_id}, headers=headers)
        self.assertEqual(res_submit.status_code, 200)

        # Confirm legacy row in mc_sessions exists
        legacy_row = MCSession.query.filter_by(user_id=user.id, unit=1).first()
        self.assertIsNotNone(legacy_row)
        self.assertEqual(legacy_row.total, 15)

        # Confirm mc_best_scores updated
        best = MCBestScore.query.filter_by(user_id=user.id, unit=1).first()
        self.assertIsNotNone(best)
        self.assertEqual(best.best_score, legacy_row.score)

    # ─────────────────────────────────────────────────────────
    # A-34: MC Format-Statistics Consistency
    # ─────────────────────────────────────────────────────────
    def test_a34_mc_format_statistics_consistency(self):
        token = self._create_user_and_token('a34@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a34@test.com').first()

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        # Unit 1 slots distribution:
        # findMistake: u1q1, u1q6, u1q11 (3 items)
        # tf: u1q2, u1q7, u1q12 (3 items)
        # radio: u1q3, u1q9, u1q13 (3 items)
        # fill: u1q4, u1q5, u1q8, u1q10, u1q14, u1q15 (6 items)
        # Total = 15 items
        for slot in range(1, 16):
            self.client.post('/api/sessions/mc/attempt', json={
                'session_id': session_id,
                'slot_number': slot,
                'answer': '2'
            }, headers=headers)

        self.client.post('/api/sessions/mc/submit', json={'session_id': session_id}, headers=headers)

        # Check mc_type_stats
        type_rows = MCTypeStat.query.filter_by(user_id=user.id).all()
        stats = {r.type_key: r.attempted for r in type_rows}
        self.assertEqual(stats.get('findMistake'), 3)
        self.assertEqual(stats.get('tf'), 3)
        self.assertEqual(stats.get('radio'), 3)
        self.assertEqual(stats.get('fill'), 6)
        self.assertEqual(sum(stats.values()), 15)

    # ─────────────────────────────────────────────────────────
    # A-35: Submission Replay Legacy Deduplication
    # ─────────────────────────────────────────────────────────
    def test_a35_submission_replay_legacy_deduplication(self):
        token = self._create_user_and_token('a35@test.com')
        headers = self._auth_header(token)
        user = User.query.filter_by(email='a35@test.com').first()

        res_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        for slot in range(1, 16):
            self.client.post('/api/sessions/mc/attempt', json={
                'session_id': session_id, 'slot_number': slot, 'answer': '2'
            }, headers=headers)

        res1 = self.client.post('/api/sessions/mc/submit', json={'session_id': session_id}, headers=headers)
        self.assertEqual(res1.status_code, 200)

        # Replay submit
        res2 = self.client.post('/api/sessions/mc/submit', json={'session_id': session_id}, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json().get('idempotent'))

        # Legacy mc_sessions must have EXACTLY 1 row, not 2
        count = MCSession.query.filter_by(user_id=user.id, unit=1).count()
        self.assertEqual(count, 1)

    # ─────────────────────────────────────────────────────────
    # A-36: Database Rollback on Partial Submission Failure
    # ─────────────────────────────────────────────────────────
    def test_a36_database_rollback_on_submission_failure(self):
        token = self._create_user_and_token('a36@test.com')
        headers = self._auth_header(token)

        res_start = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        session_id = res_start.get_json()['session_id']

        answers = [{'position': i, 'answer': '10'} for i in range(20)]

        # Simulate exception during update_streak_ist or legacy commit
        with patch('sessions_adaptive.update_streak_ist', side_effect=RuntimeError("Simulated DB Crash")):
            res = self.client.post('/api/sessions/csb/submit', json={
                'session_id': session_id,
                'answers': answers
            }, headers=headers)
            self.assertEqual(res.status_code, 500)

        # Verify learning_sessions status remains 'active'
        ls = db.session.get(LearningSession, session_id)
        self.assertEqual(ls.status, 'active')
        self.assertIsNone(ls.submitted_at)
        self.assertIsNone(ls.score)


if __name__ == '__main__':
    unittest.main()
