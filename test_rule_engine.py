import os
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from models import db, User, CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat
from rule_engine import generate_csb_report, generate_mc_report, _calculate_trend


class RuleEngineUnitTests(unittest.TestCase):
    """Direct unit tests for rule_engine.py functions."""

    def setUp(self):
        self.mock_user = {
            'fname': 'Aarav',
            'lname': 'Sharma',
            'grade': 8,
            'city': 'Bengaluru',
            'streak': 5
        }

    def test_csb_report_no_completed_sessions(self):
        report = generate_csb_report(self.mock_user, [], [])
        self.assertIn('📊 Overall Performance Summary', report)
        self.assertIn("💪 What You're Good At", report)
        self.assertIn('⚠️ Areas to Focus On', report)
        self.assertIn("🎯 This Week's Action Plan", report)
        self.assertIn('Aarav', report)
        self.assertIn('have not completed any timed drills yet', report)
        self.assertIn('1.', report)
        self.assertIn('2.', report)
        self.assertIn('3.', report)

    def test_mc_report_no_completed_sessions(self):
        report = generate_mc_report(self.mock_user, [], [], {})
        self.assertIn('🔍 Error Pattern Summary', report)
        self.assertIn('💪 What You Understand Well', report)
        self.assertIn('⚠️ Recurring Mistake Types', report)
        self.assertIn('🎯 Targeted Practice Plan', report)
        self.assertIn('Aarav', report)
        self.assertIn('have not submitted any mistake analysis exercises yet', report)
        self.assertIn('1.', report)
        self.assertIn('2.', report)
        self.assertIn('3.', report)

    def test_csb_single_session_baseline(self):
        sessions = [{'unit': 1, 'score': 18, 'total': 20, 'date': '3 Nov 2026'}]
        best_scores = [{'unit': 1, 'best_score': 18}]
        report = generate_csb_report(self.mock_user, sessions, best_scores)

        self.assertIn('📊 Overall Performance Summary', report)
        self.assertIn('completed 1 Speed Booster session', report)
        self.assertIn('90%', report)  # 18/20
        self.assertIn('initial benchmark', report)
        self.assertIn('1.', report)
        self.assertIn('2.', report)
        self.assertIn('3.', report)

    def test_mc_single_session_baseline(self):
        sessions = [{'unit': 1, 'score': 12, 'total': 15, 'date': '3 Nov 2026'}]
        best_scores = [{'unit': 1, 'best_score': 12}]
        type_stats = {
            'findMistake': {'a': 3, 'c': 3},
            'tf': {'a': 3, 'c': 2},
            'radio': {'a': 3, 'c': 3},
            'fill': {'a': 6, 'c': 4}
        }
        report = generate_mc_report(self.mock_user, sessions, best_scores, type_stats)

        self.assertIn('🔍 Error Pattern Summary', report)
        self.assertIn('completed 1 Mistake Correction session', report)
        self.assertIn('80%', report)  # 12/15
        self.assertIn('12/15', report)
        self.assertIn('1.', report)

    def test_csb_strong_and_weak_unit_identification(self):
        sessions = [
            {'unit': 1, 'score': 20, 'total': 20, 'date': '1 Nov 2026'},
            {'unit': 2, 'score': 18, 'total': 20, 'date': '2 Nov 2026'},
            {'unit': 3, 'score': 10, 'total': 20, 'date': '3 Nov 2026'},
        ]
        best_scores = [
            {'unit': 1, 'best_score': 20},
            {'unit': 2, 'best_score': 18},
            {'unit': 3, 'best_score': 10},
        ]
        report = generate_csb_report(self.mock_user, sessions, best_scores)

        # Strongest is Unit 1 (Mental Math), Weakest is Unit 3 (Fractions & Percentages)
        self.assertIn('Mental Math', report)
        self.assertIn('Fractions & Percentages', report)
        self.assertIn('10/20', report)
        self.assertIn('20/20', report)

    def test_mc_strong_and_weak_unit_identification(self):
        sessions = [
            {'unit': 1, 'score': 15, 'total': 15, 'date': '1 Nov 2026'},
            {'unit': 2, 'score': 8, 'total': 15, 'date': '2 Nov 2026'},
        ]
        best_scores = [
            {'unit': 1, 'best_score': 15},
            {'unit': 2, 'best_score': 8},
        ]
        type_stats = {}
        report = generate_mc_report(self.mock_user, sessions, best_scores, type_stats)

        self.assertIn('Fractions', report)
        self.assertIn('15/15', report)
        self.assertIn('Integers', report)
        self.assertIn('8/15', report)

    def test_trend_calculation_improving_declining_consistent(self):
        # Improving
        improving_sessions = [
            {'score': 10, 'total': 20},
            {'score': 11, 'total': 20},
            {'score': 12, 'total': 20},
            {'score': 17, 'total': 20},
            {'score': 18, 'total': 20},
            {'score': 19, 'total': 20},
        ]
        self.assertEqual(_calculate_trend(improving_sessions), 'improving')

        # Declining
        declining_sessions = [
            {'score': 19, 'total': 20},
            {'score': 18, 'total': 20},
            {'score': 17, 'total': 20},
            {'score': 12, 'total': 20},
            {'score': 11, 'total': 20},
            {'score': 10, 'total': 20},
        ]
        self.assertEqual(_calculate_trend(declining_sessions), 'declining')

        # Consistent
        consistent_sessions = [
            {'score': 15, 'total': 20},
            {'score': 16, 'total': 20},
            {'score': 15, 'total': 20},
            {'score': 16, 'total': 20},
            {'score': 15, 'total': 20},
            {'score': 16, 'total': 20},
        ]
        self.assertEqual(_calculate_trend(consistent_sessions), 'consistent')

    def test_mc_format_statistics_and_concept_clarity(self):
        sessions = [{'unit': 1, 'score': 12, 'total': 15}]
        best_scores = [{'unit': 1, 'best_score': 12}]
        type_stats = {
            'findMistake': {'a': 10, 'c': 9},   # 90%
            'tf':          {'a': 10, 'c': 8},   # 80%
            'radio':       {'a': 10, 'c': 7},   # 70%
            'fill':        {'a': 10, 'c': 4},   # 40% (lowest)
        }
        report = generate_mc_report(self.mock_user, sessions, best_scores, type_stats)

        # Confirm highest format and lowest format are identified
        self.assertIn('Find the Mistake', report)
        self.assertIn('Fill the Step', report)
        self.assertIn('40%', report)

        # Must explicitly note that these are question interaction formats, not math concepts
        self.assertIn('interaction format', report)

    def test_missing_or_incomplete_statistics_handled_safely(self):
        # Empty/None values should never crash the engine
        report_csb = generate_csb_report({}, None, None)
        self.assertIn('📊 Overall Performance Summary', report_csb)

        report_mc = generate_mc_report(None, None, None, None)
        self.assertIn('🔍 Error Pattern Summary', report_mc)

    def test_no_unsupported_claims_made(self):
        sessions = [
            {'unit': 1, 'score': 16, 'total': 20, 'date': '1 Nov 2026'},
            {'unit': 2, 'score': 18, 'total': 20, 'date': '2 Nov 2026'}
        ]
        best_scores = [{'unit': 1, 'best_score': 16}, {'unit': 2, 'best_score': 18}]
        report_csb = generate_csb_report(self.mock_user, sessions, best_scores)

        # Check negative constraints:
        # 1. Do NOT claim to know operation-level breakdown (e.g. addition vs multiplication error)
        self.assertNotIn('addition errors', report_csb.lower())
        self.assertNotIn('subtraction weakness', report_csb.lower())
        # 2. Do NOT claim to know elapsed time or calculation seconds
        self.assertNotIn('seconds per question', report_csb.lower())
        self.assertNotIn('calculation speed was', report_csb.lower())


class RuleEngineIntegrationTests(unittest.TestCase):
    """End-to-end integration tests using isolated temporary SQLite DB."""

    @classmethod
    def setUpClass(cls):
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='_rule_engine_test.db')
        cls.test_secret = 'super-secure-test-jwt-secret-key-32-chars-long'

        cls.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{cls.temp_db_path}',
            'SECRET_KEY': cls.test_secret,
            'ANTHROPIC_API_KEY': '',  # Guarantee empty API key
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

    def _create_user(self, email, fname, lname):
        res = self.client.post('/api/auth/signup', json={
            'email': email,
            'password': 'Password123!',
            'fname': fname,
            'lname': lname,
            'grade': 8,
            'age': 13,
            'school': 'Test Vidya Mandir',
            'city': 'Pune'
        })
        self.assertEqual(res.status_code, 201)
        return res.get_json()['token']

    def test_unauthenticated_requests_rejected(self):
        res1 = self.client.post('/api/ai/csb-report')
        self.assertEqual(res1.status_code, 401)

        res2 = self.client.post('/api/ai/mc-report')
        self.assertEqual(res2.status_code, 401)

    def test_csb_report_endpoint_works_without_anthropic_key(self):
        token = self._create_user('student_csb_no_key@test.com', 'Rohan', 'Patel')
        headers = {'Authorization': f'Bearer {token}'}

        # Add a session
        sub_res = self.client.post('/api/sessions/csb', json={
            'unit': 1,
            'score': 17,
            'total': 20,
            'mood': '😊'
        }, headers=headers)
        self.assertEqual(sub_res.status_code, 200)

        # Call CSB report endpoint
        res = self.client.post('/api/ai/csb-report', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('report', data)
        report = data['report']

        # Confirm all 4 headings exist
        self.assertIn('📊 Overall Performance Summary', report)
        self.assertIn("💪 What You're Good At", report)
        self.assertIn('⚠️ Areas to Focus On', report)
        self.assertIn("🎯 This Week's Action Plan", report)
        self.assertIn('Rohan', report)
        self.assertIn('17/20', report)

    def test_mc_report_endpoint_works_without_anthropic_key(self):
        token = self._create_user('student_mc_no_key@test.com', 'Ananya', 'Iyer')
        headers = {'Authorization': f'Bearer {token}'}

        # Add an MC session
        sub_res = self.client.post('/api/sessions/mc', json={
            'unit': 1,
            'score': 13,
            'total': 15,
            'typeStats': {'findMistake': 3, 'tf': 3, 'fill': 6, 'radio': 3},
            'typeCorrect': {'findMistake': 3, 'tf': 3, 'fill': 4, 'radio': 3},
            'mood': 'Good'
        }, headers=headers)
        self.assertEqual(sub_res.status_code, 200)

        # Call MC report endpoint
        res = self.client.post('/api/ai/mc-report', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('report', data)
        report = data['report']

        self.assertIn('🔍 Error Pattern Summary', report)
        self.assertIn('💪 What You Understand Well', report)
        self.assertIn('⚠️ Recurring Mistake Types', report)
        self.assertIn('🎯 Targeted Practice Plan', report)
        self.assertIn('Ananya', report)
        self.assertIn('13/15', report)

    @patch('ai.call_anthropic')
    def test_no_external_api_called(self, mock_call):
        """Verifies external AI function is never invoked during report generation."""
        token = self._create_user('student_no_call@test.com', 'Pooja', 'Verma')
        headers = {'Authorization': f'Bearer {token}'}

        res = self.client.post('/api/ai/csb-report', headers=headers)
        self.assertEqual(res.status_code, 200)
        mock_call.assert_not_called()

        res_mc = self.client.post('/api/ai/mc-report', headers=headers)
        self.assertEqual(res_mc.status_code, 200)
        mock_call.assert_not_called()

    def test_user_data_isolation_between_students(self):
        # Student 1: Priya — Unit 1 high score
        token1 = self._create_user('priya@test.com', 'Priya', 'Nair')
        h1 = {'Authorization': f'Bearer {token1}'}
        self.client.post('/api/sessions/csb', json={'unit': 1, 'score': 20, 'total': 20}, headers=h1)

        # Student 2: Dev — Unit 4 score
        token2 = self._create_user('dev@test.com', 'Dev', 'Mehta')
        h2 = {'Authorization': f'Bearer {token2}'}
        self.client.post('/api/sessions/csb', json={'unit': 4, 'score': 11, 'total': 20}, headers=h2)

        # Priya's report
        rep1 = self.client.post('/api/ai/csb-report', headers=h1).get_json()['report']
        self.assertIn('Priya', rep1)
        self.assertNotIn('Dev', rep1)
        self.assertIn('20/20', rep1)
        self.assertNotIn('11/20', rep1)

        # Dev's report
        rep2 = self.client.post('/api/ai/csb-report', headers=h2).get_json()['report']
        self.assertIn('Dev', rep2)
        self.assertNotIn('Priya', rep2)
        self.assertIn('11/20', rep2)
        self.assertNotIn('20/20', rep2)


if __name__ == '__main__':
    unittest.main()
