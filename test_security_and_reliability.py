import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import jwt

from app import create_app
from models import db, User, CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat


class SecurityAndReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary SQLite database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='_test.db')
        cls.test_secret = 'super-secure-test-jwt-secret-key-32-chars-long'

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

    def _create_synthetic_user(self, email, fname, lname, grade=8):
        res = self.client.post('/api/auth/signup', json={
            'email': email,
            'password': 'validPassword123',
            'fname': fname,
            'lname': lname,
            'grade': grade,
            'age': 13,
            'school': 'Test Public School',
            'city': 'Mumbai'
        })
        self.assertEqual(res.status_code, 201)
        return res.get_json()['token']

    # ─────────────────────────────────────────────────────────
    # 1. JWT TOKEN SECURITY TESTS
    # ─────────────────────────────────────────────────────────
    def test_missing_token_rejected(self):
        res = self.client.get('/api/user')
        self.assertEqual(res.status_code, 401)
        self.assertIn('token missing', res.get_json()['error'].lower())

    def test_malformed_token_rejected(self):
        res = self.client.get('/api/user', headers={'Authorization': 'Bearer not-a-valid-token'})
        self.assertEqual(res.status_code, 401)
        self.assertIn('invalid token', res.get_json()['error'].lower())

    def test_wrong_signature_token_rejected(self):
        # Signed with a different key
        bad_token = jwt.encode({'user_id': 1}, 'wrong-secret-key-that-does-not-match', algorithm='HS256')
        res = self.client.get('/api/user', headers={'Authorization': f'Bearer {bad_token}'})
        self.assertEqual(res.status_code, 401)
        self.assertIn('invalid token', res.get_json()['error'].lower())

    def test_expired_token_rejected(self):
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_token = jwt.encode({'user_id': 1, 'exp': past_time}, self.test_secret, algorithm='HS256')
        res = self.client.get('/api/user', headers={'Authorization': f'Bearer {expired_token}'})
        self.assertEqual(res.status_code, 401)
        self.assertIn('expired', res.get_json()['error'].lower())

    def test_non_integer_user_id_rejected(self):
        bad_token = jwt.encode({'user_id': 'malicious_string'}, self.test_secret, algorithm='HS256')
        res = self.client.get('/api/user', headers={'Authorization': f'Bearer {bad_token}'})
        self.assertEqual(res.status_code, 401)
        self.assertIn('invalid token', res.get_json()['error'].lower())

    # ─────────────────────────────────────────────────────────
    # 2. USER DATA ISOLATION TESTS
    # ─────────────────────────────────────────────────────────
    def test_data_isolation_between_two_users(self):
        token1 = self._create_synthetic_user('student1@isolation.local', 'Priya', 'Patel', 7)
        token2 = self._create_synthetic_user('student2@isolation.local', 'Rohan', 'Verma', 8)

        # Student 1 saves a CSB session
        post_res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token1}'}, json={
            'unit': 1,
            'score': 20,
            'total': 20,
            'mood': '🔥'
        })
        self.assertEqual(post_res.status_code, 200)

        # Student 2 checks their profile
        u2_res = self.client.get('/api/user', headers={'Authorization': f'Bearer {token2}'})
        self.assertEqual(u2_res.status_code, 200)
        u2_data = u2_res.get_json()

        # Student 2 must not see Student 1's scores or sessions
        self.assertEqual(u2_data['fname'], 'Rohan')
        self.assertEqual(u2_data['bestScores'][0], 0)
        self.assertEqual(len(u2_data['sessions']), 0)

        # Student 1 checks their profile
        u1_res = self.client.get('/api/user', headers={'Authorization': f'Bearer {token1}'})
        self.assertEqual(u1_res.status_code, 200)
        u1_data = u1_res.get_json()
        self.assertEqual(u1_data['fname'], 'Priya')
        self.assertEqual(u1_data['bestScores'][0], 20)
        self.assertEqual(len(u1_data['sessions']), 1)

    # ─────────────────────────────────────────────────────────
    # 3. SCORE, TOTAL, AND BOUNDARY VALIDATION (CSB)
    # ─────────────────────────────────────────────────────────
    def test_csb_negative_score_rejected(self):
        token = self._create_synthetic_user('csb_neg@test.local', 'Ananya', 'Iyer')
        res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': -5, 'total': 20
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('between 0 and 20', res.get_json()['error'])

    def test_csb_score_greater_than_total_rejected(self):
        token = self._create_synthetic_user('csb_high@test.local', 'Kabir', 'Mehta')
        res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': 25, 'total': 20
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('between 0 and 20', res.get_json()['error'])

    def test_csb_zero_total_rejected(self):
        token = self._create_synthetic_user('csb_zero@test.local', 'Sara', 'Khan')
        res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': 0, 'total': 0
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('must be 20', res.get_json()['error'])

    def test_csb_invalid_unit_numbers_rejected(self):
        token = self._create_synthetic_user('csb_unit@test.local', 'Dev', 'Nair')
        for bad_unit in [0, 6, 99, -1]:
            res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
                'unit': bad_unit, 'score': 10, 'total': 20
            })
            self.assertEqual(res.status_code, 400)

    def test_csb_boolean_values_rejected_as_integers(self):
        token = self._create_synthetic_user('csb_bool@test.local', 'Maya', 'Sen')
        res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': True, 'score': False, 'total': 20
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('must be an integer', res.get_json()['error'])

    def test_csb_non_numeric_score_rejected(self):
        token = self._create_synthetic_user('csb_str@test.local', 'Arjun', 'Reddy')
        res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': 'twenty', 'total': 20
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('must be an integer', res.get_json()['error'])

    def test_csb_unit_total_enforcement(self):
        token = self._create_synthetic_user('csb_tot@test.local', 'Neha', 'Kapoor')
        # Unit 1 must have total 20 (not 30)
        res1 = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': 15, 'total': 30
        })
        self.assertEqual(res1.status_code, 400)
        self.assertIn('must be 20', res1.get_json()['error'])

        # Unit 5 must have total 30 (not 20)
        res5 = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 5, 'score': 15, 'total': 20
        })
        self.assertEqual(res5.status_code, 400)
        self.assertIn('must be 30', res5.get_json()['error'])

    # ─────────────────────────────────────────────────────────
    # 4. MISTAKE CORRECTION VALIDATION & TYPE STATS
    # ─────────────────────────────────────────────────────────
    def test_mc_invalid_question_type_key_rejected(self):
        token = self._create_synthetic_user('mc_badkey@test.local', 'Tanvi', 'Bose')
        res = self.client.post('/api/sessions/mc', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1,
            'score': 5,
            'total': 5,
            'typeStats': {'maliciousTypeKey': 5},
            'typeCorrect': {'maliciousTypeKey': 5}
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid question type key', res.get_json()['error'])

    def test_mc_correct_greater_than_attempted_rejected(self):
        token = self._create_synthetic_user('mc_highcor@test.local', 'Kiran', 'Rao')
        res = self.client.post('/api/sessions/mc', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1,
            'score': 8,
            'total': 8,
            'typeStats': {'findMistake': 5, 'tf': 3},
            'typeCorrect': {'findMistake': 6, 'tf': 2}  # 6 > 5!
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Correct count cannot exceed attempted', res.get_json()['error'])

    def test_mc_negative_type_counts_rejected(self):
        token = self._create_synthetic_user('mc_neg@test.local', 'Aditya', 'Joshi')
        res = self.client.post('/api/sessions/mc', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1,
            'score': 5,
            'total': 5,
            'typeStats': {'tf': -5},
            'typeCorrect': {'tf': 0}
        })
        self.assertEqual(res.status_code, 400)

    def test_mc_mismatched_stats_sums_rejected(self):
        token = self._create_synthetic_user('mc_sum@test.local', 'Meera', 'Das')
        res = self.client.post('/api/sessions/mc', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1,
            'score': 5,
            'total': 10,
            'typeStats': {'findMistake': 4, 'tf': 4},  # sum is 8 != total 10
            'typeCorrect': {'findMistake': 3, 'tf': 2}
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Sum of question type attempts', res.get_json()['error'])

    # ─────────────────────────────────────────────────────────
    # 5. SIGNUP VALIDATION TESTS
    # ─────────────────────────────────────────────────────────
    def test_signup_invalid_email_format_rejected(self):
        for bad_email in ['notanemail', 'test@', '@domain.com', 'user@domain']:
            res = self.client.post('/api/auth/signup', json={
                'email': bad_email,
                'password': 'password123',
                'fname': 'Test',
                'lname': 'Student',
                'grade': 7
            })
            self.assertEqual(res.status_code, 400)
            self.assertIn('valid email', res.get_json()['error'].lower())

    def test_signup_whitespace_names_rejected(self):
        res = self.client.post('/api/auth/signup', json={
            'email': 'whitespace@test.local',
            'password': 'password123',
            'fname': '   ',
            'lname': 'Student',
            'grade': 7
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('first and last name', res.get_json()['error'].lower())

    def test_signup_invalid_grades_rejected(self):
        for bad_grade in [5, 11, 0, -1, 'eight']:
            res = self.client.post('/api/auth/signup', json={
                'email': f'grade_{bad_grade}@test.local',
                'password': 'password123',
                'fname': 'Test',
                'lname': 'Student',
                'grade': bad_grade
            })
            self.assertEqual(res.status_code, 400)

    def test_signup_excessive_password_length_rejected(self):
        long_password = 'A' * 73  # > 72 bytes
        res = self.client.post('/api/auth/signup', json={
            'email': 'longpw@test.local',
            'password': long_password,
            'fname': 'Test',
            'lname': 'Student',
            'grade': 8
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('72 bytes', res.get_json()['error'])

    def test_signup_duplicate_email_rejected_with_409(self):
        email = 'duplicate@test.local'
        self._create_synthetic_user(email, 'First', 'User')

        res = self.client.post('/api/auth/signup', json={
            'email': email,
            'password': 'anotherPassword123',
            'fname': 'Second',
            'lname': 'User',
            'grade': 9
        })
        self.assertEqual(res.status_code, 409)
        self.assertIn('already exists', res.get_json()['error'])

    # ─────────────────────────────────────────────────────────
    # 6. BEST-SCORE INTEGRITY
    # ─────────────────────────────────────────────────────────
    def test_best_score_does_not_regress(self):
        token = self._create_synthetic_user('bestscore@test.local', 'Vikram', 'Singh')

        # First session: score 18/20
        res1 = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 2, 'score': 18, 'total': 20
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()['bestScores'][1], 18)

        # Second session: lower score 12/20
        res2 = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 2, 'score': 12, 'total': 20
        })
        self.assertEqual(res2.status_code, 200)
        # Best score MUST remain 18!
        self.assertEqual(res2.get_json()['bestScores'][1], 18)

    # ─────────────────────────────────────────────────────────
    # 7. TRANSACTION ROLLBACK BEHAVIOR
    # ─────────────────────────────────────────────────────────
    def test_database_rollback_on_failed_write(self):
        token = self._create_synthetic_user('rollback@test.local', 'Simulated', 'Error')

        # Simulate a database failure during commit
        with patch.object(db.session, 'commit', side_effect=Exception("Simulated Database Error")):
            res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
                'unit': 1, 'score': 15, 'total': 20
            })
            self.assertEqual(res.status_code, 500)
            self.assertIn('error occurred', res.get_json()['error'].lower())

        # Ensure session was rolled back and subsequent normal operations succeed cleanly
        res_after = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': 17, 'total': 20
        })
        self.assertEqual(res_after.status_code, 200)
        self.assertEqual(res_after.get_json()['bestScores'][0], 17)

    # ─────────────────────────────────────────────────────────
    # 8. SUCCESSFUL REALISTIC SESSIONS
    # ─────────────────────────────────────────────────────────
    def test_successful_csb_and_mc_sessions(self):
        token = self._create_synthetic_user('fullflow@test.local', 'Divya', 'Sharma', 8)

        # CSB Unit 1 Success
        csb_res = self.client.post('/api/sessions/csb', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1, 'score': 19, 'total': 20, 'mood': 'Good'
        })
        self.assertEqual(csb_res.status_code, 200)
        csb_data = csb_res.get_json()
        self.assertEqual(csb_data['streak'], 1)
        self.assertEqual(csb_data['bestScores'][0], 19)

        # MC Unit 1 Success (10 attempted out of 15 exercises)
        mc_res = self.client.post('/api/sessions/mc', headers={'Authorization': f'Bearer {token}'}, json={
            'unit': 1,
            'score': 8,
            'total': 10,
            'typeStats': {'findMistake': 3, 'tf': 3, 'radio': 2, 'fill': 2},
            'typeCorrect': {'findMistake': 2, 'tf': 3, 'radio': 2, 'fill': 1},
            'mood': '-'
        })
        self.assertEqual(mc_res.status_code, 200)
        mc_data = mc_res.get_json()
        self.assertEqual(mc_data['mcBestScores'][0], 8)
        self.assertEqual(mc_data['mcTypeStats']['findMistake']['a'], 3)
        self.assertEqual(mc_data['mcTypeStats']['findMistake']['c'], 2)


if __name__ == '__main__':
    unittest.main()
