"""
tests/test_frontend_integration_verification.py — Integration Verification Suite
Verifies:
1. Frontend static contracts (no legacy endpoints, no leaked answers).
2. Adaptive retry queues population from submitted sessions.
3. Replacement questions appearing in correct assigned slots.
4. Session recovery across midnight IST boundaries.
5. Dashboard (/api/user) and AI report (/api/ai/*-report) consistency.
"""

import os
import re
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


class FrontendIntegrationVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='_verification_test.db')
        cls.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{cls.temp_db_path}',
            'SECRET_KEY': 'super-secret-jwt-key-for-verification-tests-32-chars',
        })
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        os.close(cls.temp_db_fd)
        if os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except OSError:
                pass

    def _auth_user(self, email):
        res = self.client.post('/api/auth/signup', json={
            'fname': 'Verify', 'lname': 'User', 'grade': 7, 'age': 12,
            'school': 'KV', 'city': 'Delhi', 'email': email, 'password': 'password123'
        })
        token = res.get_json()['token']
        return {'Authorization': f'Bearer {token}'}

    # ─────────────────────────────────────────────────────────
    # 1. No Legacy Submission Endpoints in Active Frontend JS
    # ─────────────────────────────────────────────────────────
    def test_01_no_legacy_endpoints_in_active_frontend(self):
        with open('static/js/speed_booster.js', 'r', encoding='utf-8') as f:
            sb_code = f.read()
        with open('static/js/mistake_correction.js', 'r', encoding='utf-8') as f:
            mc_code = f.read()

        sb_endpoints = [m.strip("'\"") for m in re.findall(r"['\"]/api/sessions/csb(?:/[a-z]+)?['\"]", sb_code)]
        mc_endpoints = [m.strip("'\"") for m in re.findall(r"['\"]/api/sessions/mc(?:/[a-z]+)?['\"]", mc_code)]

        self.assertNotIn('/api/sessions/csb', sb_endpoints, "speed_booster.js must not call legacy /api/sessions/csb!")
        self.assertNotIn('/api/sessions/mc', mc_endpoints, "mistake_correction.js must not call legacy /api/sessions/mc!")

        self.assertIn('/api/sessions/csb/start', sb_endpoints)
        self.assertIn('/api/sessions/csb/submit', sb_endpoints)
        self.assertIn('/api/sessions/csb/cancel', sb_endpoints)

        self.assertIn('/api/sessions/mc/start', mc_endpoints)
        self.assertIn('/api/sessions/mc/attempt', mc_endpoints)
        self.assertIn('/api/sessions/mc/submit', mc_endpoints)
        self.assertIn('/api/sessions/mc/cancel', mc_endpoints)

    # ─────────────────────────────────────────────────────────
    # 2. No Leaked Answers or data-ans Keys in HTML
    # ─────────────────────────────────────────────────────────
    def test_02_no_data_ans_or_exposed_answers_in_html(self):
        with open('templates/mistake_correction.html', 'r', encoding='utf-8') as f:
            html = f.read()

        self.assertNotIn('data-ans=', html, "HTML contains leaked data-ans grading keys!")
        self.assertEqual(len(re.findall(r"checkFTM\('[^']+',\s*\d+\)", html)), 0)
        self.assertEqual(len(re.findall(r"checkTF\('[^']+',\s*'[^']+'\)", html)), 0)
        self.assertEqual(len(re.findall(r"checkRadio\('[^']+',\s*'[^']+'\)", html)), 0)

    # ─────────────────────────────────────────────────────────
    # 3. Confirm Adaptive Retry Queues Receive Records
    # ─────────────────────────────────────────────────────────
    def test_03_retry_queues_receive_records_on_mistakes(self):
        headers = self._auth_user('retry_test@test.com')

        # CSB: start Unit 1, submit with incorrect answers
        res_csb_start = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        csb_sid = res_csb_start.get_json()['session_id']

        csb_answers = [{'position': i, 'answer': 'wrong_ans'} for i in range(20)]
        res_csb_sub = self.client.post('/api/sessions/csb/submit', json={
            'session_id': csb_sid,
            'answers': csb_answers,
            'mood': '–'
        }, headers=headers)
        self.assertEqual(res_csb_sub.status_code, 200)

        # MC: start Unit 1, submit slot 1 with incorrect answer
        res_mc_start = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        mc_sid = res_mc_start.get_json()['session_id']

        # Slot 1 is u1q1 (findMistake, mistake is Step 2 -> index 1), submit wrong answer 0
        self.client.post('/api/sessions/mc/attempt', json={
            'session_id': mc_sid, 'slot_number': 1, 'answer': 0
        }, headers=headers)

        for s_num in range(2, 16):
            self.client.post('/api/sessions/mc/attempt', json={
                'session_id': mc_sid, 'slot_number': s_num, 'answer': 'sample'
            }, headers=headers)

        res_mc_sub = self.client.post('/api/sessions/mc/submit', json={
            'session_id': mc_sid, 'mood': '–'
        }, headers=headers)
        self.assertEqual(res_mc_sub.status_code, 200)

        with self.app.app_context():
            csb_retries = CSBRetryQueue.query.filter_by(unit=1, status='pending').all()
            self.assertGreater(len(csb_retries), 0, "CSB Retry queue must receive records on mistakes!")

            mc_retries = MCRetryQueue.query.filter_by(unit=1, status='pending').all()
            self.assertGreater(len(mc_retries), 0, "MC Retry queue must receive records on mistakes!")
            self.assertTrue(any(r.question_id == 'u1q1' for r in mc_retries))

    # ─────────────────────────────────────────────────────────
    # 4. Confirm Replacement Questions Appear in Correct Slots
    # ─────────────────────────────────────────────────────────
    def test_04_replacement_questions_appear_in_correct_slot(self):
        headers = self._auth_user('replacement_test@test.com')

        # Session 1: Day 1
        with patch('sessions_adaptive.get_current_ist_date', return_value='2026-11-01'):
            res1 = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
            sid1 = res1.get_json()['session_id']
            # Answer slot 8 incorrectly (native u1q8)
            for s in range(1, 16):
                self.client.post('/api/sessions/mc/attempt', json={
                    'session_id': sid1, 'slot_number': s, 'answer': 'wrong'
                }, headers=headers)
            self.client.post('/api/sessions/mc/submit', json={'session_id': sid1}, headers=headers)

        # Session 2: Day 2 (Second failure triggers replacement requirement)
        with patch('sessions_adaptive.get_current_ist_date', return_value='2026-11-02'):
            res2 = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
            sid2 = res2.get_json()['session_id']
            for s in range(1, 16):
                self.client.post('/api/sessions/mc/attempt', json={
                    'session_id': sid2, 'slot_number': s, 'answer': 'wrong'
                }, headers=headers)
            self.client.post('/api/sessions/mc/submit', json={'session_id': sid2}, headers=headers)

        # Session 3: Day 3 (Slot 8 must receive replacement variant u1q8_v1)
        with patch('sessions_adaptive.get_current_ist_date', return_value='2026-11-03'):
            res3 = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
            self.assertEqual(res3.status_code, 200)
            data3 = res3.get_json()
            slots = data3['slots']
            slot8 = next(s for s in slots if s['slot_number'] == 8)

            self.assertEqual(slot8['slot_number'], 8, "Replacement must occupy exact slot 8!")
            self.assertEqual(slot8['presented_question_id'], 'u1q8_v1')
            self.assertEqual(slot8['replacement_for_id'], 'u1q8')

    # ─────────────────────────────────────────────────────────
    # 5. Confirm Session Recovery Across Midnight
    # ─────────────────────────────────────────────────────────
    def test_05_session_recovery_across_midnight(self):
        headers = self._auth_user('midnight_test@test.com')

        # Day 1: Start CSB and MC sessions, do not submit
        with patch('sessions_adaptive.get_current_ist_date', return_value='2026-11-01'):
            res_csb1 = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
            csb_sid1 = res_csb1.get_json()['session_id']
            csb_q1 = res_csb1.get_json()['questions']

            res_mc1 = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
            mc_sid1 = res_mc1.get_json()['session_id']
            # Answer slot 1 on Day 1
            self.client.post('/api/sessions/mc/attempt', json={
                'session_id': mc_sid1, 'slot_number': 1, 'answer': 1
            }, headers=headers)

        # Day 2: Midnight has passed!
        with patch('sessions_adaptive.get_current_ist_date', return_value='2026-11-02'):
            # CSB resumes Day 1 session with exact question pool
            res_csb2 = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
            self.assertEqual(res_csb2.status_code, 200)
            data_csb2 = res_csb2.get_json()
            self.assertTrue(data_csb2['resumed'])
            self.assertEqual(data_csb2['session_id'], csb_sid1)
            self.assertEqual(data_csb2['questions'], csb_q1)

            # MC resumes Day 1 session with slot 1 answer preserved
            res_mc2 = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
            self.assertEqual(res_mc2.status_code, 200)
            data_mc2 = res_mc2.get_json()
            self.assertTrue(data_mc2['resumed'])
            self.assertEqual(data_mc2['session_id'], mc_sid1)
            slot1 = next(s for s in data_mc2['slots'] if s['slot_number'] == 1)
            self.assertTrue(slot1['answered'])

    # ─────────────────────────────────────────────────────────
    # 6. Confirm Dashboard and AI Reports Remain Accurate
    # ─────────────────────────────────────────────────────────
    def test_06_dashboard_and_ai_reports_accuracy(self):
        headers = self._auth_user('dash_ai_test@test.com')

        # Submit CSB Unit 1
        res_csb = self.client.post('/api/sessions/csb/start', json={'unit': 1}, headers=headers)
        csb_sid = res_csb.get_json()['session_id']
        csb_ans = [{'position': i, 'answer': '99'} for i in range(20)]
        self.client.post('/api/sessions/csb/submit', json={'session_id': csb_sid, 'answers': csb_ans}, headers=headers)

        # Submit MC Unit 1
        res_mc = self.client.post('/api/sessions/mc/start', json={'unit': 1}, headers=headers)
        mc_sid = res_mc.get_json()['session_id']
        for s in range(1, 16):
            self.client.post('/api/sessions/mc/attempt', json={'session_id': mc_sid, 'slot_number': s, 'answer': '99'}, headers=headers)
        self.client.post('/api/sessions/mc/submit', json={'session_id': mc_sid}, headers=headers)

        # 1. Test GET /api/user dashboard data
        res_user = self.client.get('/api/user', headers=headers)
        self.assertEqual(res_user.status_code, 200)
        user_data = res_user.get_json()
        self.assertEqual(len(user_data['sessions']), 1)
        self.assertEqual(len(user_data['mcSessions']), 1)
        self.assertIn('mcTypeStats', user_data)
        self.assertEqual(user_data['streak'], 1)

        # 2. Test POST /api/ai/csb-report
        res_csb_report = self.client.post('/api/ai/csb-report', headers=headers)
        self.assertEqual(res_csb_report.status_code, 200)
        report_text = res_csb_report.get_json()['report']
        self.assertIn('Overall Performance Summary', report_text)
        self.assertIn("What You're Good At", report_text)
        self.assertIn('Areas to Focus On', report_text)
        self.assertIn("This Week's Action Plan", report_text)

        # 3. Test POST /api/ai/mc-report
        res_mc_report = self.client.post('/api/ai/mc-report', headers=headers)
        self.assertEqual(res_mc_report.status_code, 200)
        mc_report_text = res_mc_report.get_json()['report']
        self.assertIn('Error Pattern Summary', mc_report_text)
        self.assertIn('What You Understand Well', mc_report_text)
        self.assertIn('Recurring Mistake Types', mc_report_text)
        self.assertIn('Targeted Practice Plan', mc_report_text)


if __name__ == '__main__':
    unittest.main()
