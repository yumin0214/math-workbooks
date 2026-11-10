import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
import hashlib

from app import create_app
from models import db, User, CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat


def normalize_algebraic(s):
    if s is None:
        return ''
    return (
        str(s).lower().strip()
        .replace('\u2212', '-').replace('\u2013', '-').replace('\u2014', '-')
        .replace('\u00d7', '*').replace('\u22c5', '*')
        .replace('\u00f7', '/')
        .replace(' ', '')
        .replace('\u20b9', '')
        .replace('rupees', '').replace('rupee', '')
        .lstrip('+')
    )


def parse_numeric_or_fraction(s):
    if s is None:
        return None
    cleaned = (
        str(s).strip()
        .replace('\u2212', '-').replace('\u2013', '-').replace('\u2014', '-')
        .replace(' ', '')
        .replace('\u20b9', '')
        .replace('rupees', '').replace('rupee', '')
        .lstrip('+')
    )

    frac_match = re.match(r'^([+-]?\d+(?:\.\d+)?)/([+-]?\d+(?:\.\d+)?)$', cleaned)
    if frac_match:
        try:
            num = float(frac_match.group(1))
            den = float(frac_match.group(2))
            if den == 0:
                return None
            return num / den
        except ValueError:
            return None

    num_match = re.match(r'^([+-]?\d+(?:\.\d+)?)$', cleaned)
    if num_match:
        try:
            return float(num_match.group(1))
        except ValueError:
            return None

    return None


def strip_units_and_prefixes(s):
    if not s or not isinstance(s, str):
        return ''
    cleaned = (
        s.strip()
        .replace('\u2212', '-').replace('\u2013', '-').replace('\u2014', '-')
    )
    cleaned = re.sub(r'^(?:₹|rs\.?|rupees?)\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*(?:₹|rs\.?|rupees?)$', '', cleaned, flags=re.IGNORECASE)

    m = re.match(r'^[a-zA-Z]\s*=\s*(.+)$', cleaned)
    if m:
        cleaned = m.group(1).strip()

    unit_pattern = (
        r'\s*(?:of\s+(?:the\s+|a\s+|whole\s+)?pizza|pizza|boys|girls|students|people|items|units|'
        r'years?|months?|days?|hours?|hrs?|mins?|seconds?|secs?|deg(?:rees?)?(?:\s*c)?|°c|°)\s*$'
    )
    cleaned = re.sub(unit_pattern, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def simplify_linear_expression(s):
    if not s or not isinstance(s, str):
        return None
    cleaned = (
        s.replace(' ', '')
        .replace('\u2212', '-').replace('\u2013', '-').replace('\u2014', '-')
    )
    if any(ch in cleaned for ch in '=*/^()'):
        return None
    letters = set(re.findall(r'[a-zA-Z]', cleaned))
    if len(letters) != 1:
        return None
    var = list(letters)[0].lower()
    cleaned = cleaned.lower()

    tokens = re.findall(r'[+-]?[^+-]+', cleaned)
    if not tokens or ''.join(tokens) != cleaned:
        return None

    var_coeff = 0.0
    const_val = 0.0
    for t in tokens:
        if var in t:
            parts = t.replace(var, '')
            if parts in ('', '+'):
                c = 1.0
            elif parts == '-':
                c = -1.0
            else:
                try:
                    c = float(parts)
                except ValueError:
                    return None
            var_coeff += c
        else:
            try:
                const_val += float(t)
            except ValueError:
                return None

    def fmt(n):
        return f'{int(n)}' if n.is_integer() else f'{n:.4g}'

    parts = []
    if abs(var_coeff) > 1e-9:
        if var_coeff == 1.0:
            parts.append(var)
        elif var_coeff == -1.0:
            parts.append(f'-{var}')
        else:
            parts.append(f'{fmt(var_coeff)}{var}')

    if abs(const_val) > 1e-9 or not parts:
        if parts:
            if const_val > 0:
                parts.append(f'+{fmt(const_val)}')
            else:
                parts.append(f'{fmt(const_val)}')
        else:
            parts.append(f'{fmt(const_val)}')

    return ''.join(parts)


def is_correct_py(user_val, accepted):
    if user_val is None:
        return False
    u_raw = str(user_val).strip()
    if not u_raw:
        return False

    u_norm = normalize_algebraic(u_raw)
    raw_acc_list = accepted.split(',')
    acc_norm_list = [normalize_algebraic(a) for a in raw_acc_list]

    # 1. Direct normalized match
    if u_norm in acc_norm_list:
        return True

    # 2. Trailing % comparison
    for acc in acc_norm_list:
        if u_norm.rstrip('%') == acc.rstrip('%'):
            n1 = parse_numeric_or_fraction(u_norm.rstrip('%'))
            n2 = parse_numeric_or_fraction(acc.rstrip('%'))
            if n1 is not None and n2 is not None and abs(n1 - n2) < 0.005:
                return True

    # 3. Unit and prefix stripping match
    u_stripped = strip_units_and_prefixes(u_raw)
    u_stripped_norm = normalize_algebraic(u_stripped)
    for raw_acc in raw_acc_list:
        acc_stripped = strip_units_and_prefixes(raw_acc)
        acc_stripped_norm = normalize_algebraic(acc_stripped)
        if u_stripped_norm == acc_stripped_norm:
            return True
        if not re.search(r'[a-z=]', u_stripped_norm) and not re.search(r'[a-z=]', acc_stripped_norm):
            n1 = parse_numeric_or_fraction(u_stripped)
            n2 = parse_numeric_or_fraction(acc_stripped)
            if n1 is not None and n2 is not None and abs(n1 - n2) < 0.005:
                return True

    # 4. Linear algebraic simplification match
    u_simp = simplify_linear_expression(u_raw)
    if u_simp is not None:
        for raw_acc in raw_acc_list:
            a_simp = simplify_linear_expression(raw_acc)
            if a_simp is not None and u_simp == a_simp:
                return True
            if u_simp == normalize_algebraic(raw_acc):
                return True

    # 5. Reject simplistic numeric coercion for algebraic/variable expressions
    has_algebraic = any(re.search(r'[a-z=]', a) for a in acc_norm_list) or bool(re.search(r'[a-z=]', u_norm))
    if has_algebraic:
        return False

    # 6. Numeric & fraction equivalence comparison
    u_num = parse_numeric_or_fraction(u_stripped_norm)
    if u_num is not None:
        for acc in acc_norm_list:
            acc_strp = normalize_algebraic(strip_units_and_prefixes(acc))
            if re.search(r'[a-z=]', acc_strp):
                continue
            a_num = parse_numeric_or_fraction(acc_strp)
            if a_num is not None:
                if abs(u_num - a_num) < 0.005:
                    return True

    return False


class WorkbookImprovementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary SQLite database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='_improvements_test.db')
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

    def _create_user(self, email):
        res = self.client.post('/api/auth/signup', json={
            'email': email,
            'password': 'Password123!',
            'fname': 'Student',
            'lname': 'Test',
            'grade': 8,
            'age': 13,
            'school': 'Test School',
            'city': 'Delhi'
        })
        self.assertEqual(res.status_code, 201)
        return res.get_json()['token']

    # ── Requirement 1: Mistake Correction Answer Validation ──
    def test_mc_fraction_equivalence(self):
        # 1/2 equivalents
        self.assertTrue(is_correct_py('1/2', '1/2'))
        self.assertTrue(is_correct_py('2/4', '1/2'))
        self.assertTrue(is_correct_py('4/8', '1/2'))
        self.assertTrue(is_correct_py('3/6', '1/2'))
        self.assertTrue(is_correct_py('0.5', '1/2'))
        self.assertTrue(is_correct_py('1/2', '0.5'))

        # 5/6 equivalents
        self.assertTrue(is_correct_py('5/6', '100/120,5/6'))
        self.assertTrue(is_correct_py('10/12', '100/120,5/6'))
        self.assertTrue(is_correct_py('50/60', '100/120,5/6'))

        # 1/4 equivalents
        self.assertTrue(is_correct_py('1/4', '1/4'))
        self.assertTrue(is_correct_py('2/8', '1/4'))
        self.assertTrue(is_correct_py('0.25', '1/4'))

        # Incorrect fractions must fail
        self.assertFalse(is_correct_py('5/7', '100/120,5/6'))
        self.assertFalse(is_correct_py('3/8', '1/2'))
        self.assertFalse(is_correct_py('1/3', '1/2'))

    def test_mc_negative_fractions(self):
        self.assertTrue(is_correct_py('-6/8', '-6/8'))
        self.assertTrue(is_correct_py('-3/4', '-6/8'))
        self.assertTrue(is_correct_py('-0.75', '-6/8'))
        self.assertTrue(is_correct_py('-5/8', '-5/8'))
        self.assertTrue(is_correct_py('-10/16', '-5/8'))

        # Positive should not match negative
        self.assertFalse(is_correct_py('3/4', '-6/8'))
        self.assertFalse(is_correct_py('5/8', '-5/8'))

    def test_mc_approximation_tolerances(self):
        # 13/3 vs 4.33
        self.assertTrue(is_correct_py('13/3', '13/3,4.33'))
        self.assertTrue(is_correct_py('4.33', '13/3,4.33'))
        self.assertTrue(is_correct_py('4.333', '13/3,4.33'))

        # -80/23 vs -3.48
        self.assertTrue(is_correct_py('-80/23', '-80/23,-3.48'))
        self.assertTrue(is_correct_py('-3.48', '-80/23,-3.48'))

    def test_mc_algebraic_expressions_not_coerced_numerically(self):
        # Correct matches
        self.assertTrue(is_correct_py('10x+750=12x', '10x+750=12x'))
        self.assertTrue(is_correct_py('10x + 750 = 12x', '10x+750=12x'))
        self.assertTrue(is_correct_py('6x+2', '6x-2+4,6x+2'))
        self.assertTrue(is_correct_py('6x - 2 + 4', '6x-2+4,6x+2'))
        self.assertTrue(is_correct_py('3x', '3x'))
        self.assertTrue(is_correct_py('y', 'y,1y'))
        self.assertTrue(is_correct_py('1y', 'y,1y'))
        self.assertTrue(is_correct_py('2x/3', '2x/3'))
        self.assertTrue(is_correct_py('4x/5', '0.8x,4x/5'))
        self.assertTrue(is_correct_py('0.8x', '0.8x,4x/5'))

        # Critical: Algebraic equations must NEVER match partially stripped numbers!
        self.assertFalse(is_correct_py('10x+750=12', '10x+750=12x'))
        self.assertFalse(is_correct_py('1075012', '10x+750=12x'))
        self.assertFalse(is_correct_py('3', '3x'))
        self.assertFalse(is_correct_py('6x+3', '6x+2'))
        self.assertFalse(is_correct_py('8', '8x'))
        self.assertFalse(is_correct_py('5x', '8x'))

    def test_mc_word_answers(self):
        self.assertTrue(is_correct_py('dropped', 'dropped,decreased,fell'))
        self.assertTrue(is_correct_py('decreased', 'dropped,decreased,fell'))
        self.assertTrue(is_correct_py('fell', 'dropped,decreased,fell'))
        self.assertFalse(is_correct_py('rose', 'dropped,decreased,fell'))

    # ── Requirement 2: Unit Completion & Navigation ──
    def test_no_forced_redirect_in_client_scripts(self):
        # speed_booster.js must not force redirect to dashboard
        with open('static/js/speed_booster.js', 'r', encoding='utf-8') as f:
            sb_content = f.read()
        self.assertNotIn("window.location.href = '/dashboard'", sb_content)
        self.assertIn('showCompletionModal', sb_content)
        self.assertIn('goToNextUnit', sb_content)

        # mistake_correction.js must not force redirect to dashboard
        with open('static/js/mistake_correction.js', 'r', encoding='utf-8') as f:
            mc_content = f.read()
        self.assertNotIn("window.location.href = '/dashboard'", mc_content)
        self.assertIn('showCompletionModal', mc_content)
        self.assertIn('goToNextUnit', mc_content)

    def test_completion_modals_exist_in_html(self):
        with open('templates/calculation_speed_booster.html', 'r', encoding='utf-8') as f:
            sb_html = f.read()
        self.assertIn('id="completion-modal"', sb_html)
        self.assertIn('id="btn-next-unit"', sb_html)
        self.assertIn('Review Answers', sb_html)

        with open('templates/mistake_correction.html', 'r', encoding='utf-8') as f:
            mc_html = f.read()
        self.assertIn('id="completion-modal"', mc_html)
        self.assertIn('id="btn-next-unit"', mc_html)
        self.assertIn('Review Answers', mc_html)

    def test_final_unit_does_not_navigate_to_nonexistent_unit(self):
        # In both JS files, when unit >= 5, nextBtn.style.display must be 'none'
        with open('static/js/speed_booster.js', 'r', encoding='utf-8') as f:
            sb_js = f.read()
        self.assertIn("unit >= 5", sb_js)
        self.assertIn("nextBtn.style.display = 'none'", sb_js)

        with open('static/js/mistake_correction.js', 'r', encoding='utf-8') as f:
            mc_js = f.read()
        self.assertIn("unit >= 5", mc_js)
        self.assertIn("nextBtn.style.display = 'none'", mc_js)

    # ── Requirement 3: Mistake Correction Tips and Hints ──
    def test_tips_hidden_by_default_and_toggable(self):
        with open('static/css/mistake_correction.css', 'r', encoding='utf-8') as f:
            mc_css = f.read()
        self.assertIn('.tip-box{display:none', mc_css)
        self.assertIn('.tip-box.visible{display:flex}', mc_css)
        self.assertIn('.tip-toggle-btn', mc_css)

        with open('static/js/mistake_correction.js', 'r', encoding='utf-8') as f:
            mc_js = f.read()
        self.assertIn('initTipsAndHints', mc_js)
        self.assertIn('toggleTip', mc_js)

    def test_hints_locked_until_check_clicked(self):
        with open('static/css/mistake_correction.css', 'r', encoding='utf-8') as f:
            mc_css = f.read()
        self.assertIn('.hint-btn:disabled', mc_css)

        with open('static/js/mistake_correction.js', 'r', encoding='utf-8') as f:
            mc_js = f.read()
        self.assertIn('unlockHint', mc_js)
        self.assertIn('if (btn.disabled) return;', mc_js)

    # ── Requirement 4: State Preservation Across Reloads/Dates ──
    def test_daily_state_keying_and_storage(self):
        with open('static/js/speed_booster.js', 'r', encoding='utf-8') as f:
            sb_js = f.read()
        self.assertIn('getTodayDateIST', sb_js)
        self.assertIn('csb_state_', sb_js)
        self.assertIn('saveCSBState', sb_js)

        with open('static/js/mistake_correction.js', 'r', encoding='utf-8') as f:
            mc_js = f.read()
        self.assertIn('getTodayDateIST', mc_js)
        self.assertIn('mc_state_', mc_js)
        self.assertIn('saveMCState', mc_js)
        self.assertIn('restoreSavedMCState', mc_js)

    # ── Requirement 5: Clean Warm-Up Removal ──
    def test_csb_warmups_completely_removed(self):
        with open('templates/calculation_speed_booster.html', 'r', encoding='utf-8') as f:
            sb_html = f.read()
        self.assertNotIn('id="wu1"', sb_html)
        self.assertNotIn('id="wu2"', sb_html)
        self.assertNotIn('id="wu3"', sb_html)
        self.assertNotIn('id="wu4"', sb_html)
        self.assertNotIn('Warm-Up — No Timer', sb_html)

        with open('static/js/speed_booster.js', 'r', encoding='utf-8') as f:
            sb_js = f.read()
        self.assertNotIn('genWarmup1', sb_js)
        self.assertNotIn('genWarmup2', sb_js)
        self.assertNotIn('genWarmup3', sb_js)
        self.assertNotIn('genWarmup4', sb_js)
        self.assertNotIn('renderWarmup', sb_js)

    # ── Backend API Integration with Isolated Database ──
    def test_csb_session_submission_flow(self):
        token = self._create_user('csb_student@test.com')
        headers = {'Authorization': f'Bearer {token}'}

        # Submit Unit 1
        res1 = self.client.post('/api/sessions/csb', json={
            'unit': 1,
            'score': 18,
            'total': 20,
            'mood': '😊'
        }, headers=headers)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertEqual(data1['bestScores'][0], 18)

        # Submit Unit 5 (Final challenge)
        res5 = self.client.post('/api/sessions/csb', json={
            'unit': 5,
            'score': 28,
            'total': 30,
            'mood': '🔥'
        }, headers=headers)
        self.assertEqual(res5.status_code, 200)
        data5 = res5.get_json()
        self.assertEqual(data5['bestScores'][4], 28)

    def test_mc_session_submission_flow(self):
        token = self._create_user('mc_student@test.com')
        headers = {'Authorization': f'Bearer {token}'}

        # Submit MC Unit 1 with type statistics
        res = self.client.post('/api/sessions/mc', json={
            'unit': 1,
            'score': 12,
            'total': 15,
            'typeStats': {'findMistake': 3, 'tf': 3, 'fill': 6, 'radio': 3},
            'typeCorrect': {'findMistake': 3, 'tf': 2, 'fill': 4, 'radio': 3},
            'mood': 'Good'
        }, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['mcBestScores'][0], 12)


if __name__ == '__main__':
    unittest.main()
