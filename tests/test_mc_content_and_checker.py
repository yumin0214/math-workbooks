import os
import re
import unittest
from tests.test_workbook_improvements import (
    normalize_algebraic,
    parse_numeric_or_fraction,
    strip_units_and_prefixes,
    simplify_linear_expression,
    is_correct_py
)
from questions_mc_registry import MC_QUESTIONS


class TestMCContentIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'templates',
            'mistake_correction.html'
        )
        with open(html_path, 'r', encoding='utf-8') as f:
            cls.html = f.read()

    def test_all_75_questions_exist(self):
        for unit in range(1, 6):
            for q in range(1, 16):
                qid = f'u{unit}q{q}'
                self.assertIn(f'id="{qid}"', self.html, f'Missing question container for {qid}')

    def test_no_answer_leaks_or_giveaways(self):
        forbidden_phrases = [
            '(wrong!)',
            '(wrong setup)',
            '(wrong order!)',
            '(wrong base used)',
            '← error',
            '← wrong step',
            '← expansion error',
            '(should be',
            '(should subtract',
            '(method is fine)',
            '(all steps are actually correct here)'
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, self.html, f'Found giveaway phrase: "{phrase}"')
        # Ensure zero data-ans answer keys exist in the client HTML
        self.assertNotIn('data-ans=', self.html, 'Found leaked data-ans grading key in HTML!')

    def test_radio_buttons_have_data_val(self):
        # Every <label class="radio-btn" ...> must have data-val="[A-Z]"
        radio_labels = re.findall(r'<label class="radio-btn"[^>]*>', self.html)
        self.assertGreater(len(radio_labels), 0, 'No radio buttons found')
        for label in radio_labels:
            self.assertRegex(label, r'data-val="[A-Z0-9]+"', f'Radio button missing data-val: {label}')

    def test_tf_buttons_have_valid_boolean_arguments(self):
        tf_calls = re.findall(r"selectTF\(this,\s*'[^']+',\s*('[^']+')\)", self.html)
        self.assertGreater(len(tf_calls), 0, 'No selectTF calls found')
        for arg in tf_calls:
            self.assertIn(arg, ["'true'", "'false'"], f'Invalid selectTF argument: {arg}')

    def test_specific_question_corrections(self):
        # u1q6: step buttons should not leak
        self.assertNotIn('Step 3 is the mistake', self.html)

        # u1q8: two distinct step inputs with no leak
        self.assertIn('id="u1q8-b1"', self.html)
        self.assertIn('id="u1q8-b2"', self.html)

        # u1q10: accepts both 9/15 and 10/15 in registry
        u1q10_payload = str(MC_QUESTIONS['u1q10']['authoritative_answer_payload'])
        self.assertIn('9,9/15', u1q10_payload)
        self.assertIn('10,10/15', u1q10_payload)

        # u1q11: Step 3 has genuine mathematical error and registry uses index 2
        self.assertIn('6/18', self.html)
        self.assertEqual(MC_QUESTIONS['u1q11']['authoritative_answer_payload'], 2)

        # u1q12: True statement with registry payload True
        self.assertEqual(MC_QUESTIONS['u1q12']['authoritative_answer_payload'], True)

        # u1q14: Box 2 has 24/36, Box 4 has 1/1,36/36,72/72 in registry
        u1q14_payload = str(MC_QUESTIONS['u1q14']['authoritative_answer_payload'])
        self.assertIn('24/36', u1q14_payload)
        self.assertIn('1/1,36/36,72/72', u1q14_payload)

        # u1q15: pizza phrasing accepted in registry
        u1q15_payload = str(MC_QUESTIONS['u1q15']['authoritative_answer_payload'])
        self.assertIn('1/4 of whole pizza', u1q15_payload)

        # u2q2: no giveaways in buttons
        self.assertNotIn('(correct setup)', self.html)

        # u2q6: 2 step buttons
        u2q6_card = self.html.split('id="u2q6"')[1].split('class="ex-card"')[0]
        step_btns = re.findall(r'class="step-btn"', u2q6_card)
        self.assertEqual(len(step_btns), 2)

        # u2q7: false answer in registry
        self.assertEqual(MC_QUESTIONS['u2q7']['authoritative_answer_payload'], False)

        # u2q10: free-text synonyms for temperature in registry
        u2q10_payload = str(MC_QUESTIONS['u2q10']['authoritative_answer_payload'])
        self.assertIn('dropped,decreased,fell', u2q10_payload)

        # u3q8: accepts simplified and expanded algebraic expressions in registry
        u3q8_payload = str(MC_QUESTIONS['u3q8']['authoritative_answer_payload'])
        self.assertIn('2x-10,5x-3x-10', u3q8_payload)

        # u3q11: Step 2 error in registry
        self.assertEqual(MC_QUESTIONS['u3q11']['authoritative_answer_payload'], 1)

        # u4q10: boys and girls distinct inputs
        self.assertIn('id="u4q10-b1"', self.html)
        self.assertIn('id="u4q10-b2"', self.html)

        # u5q8: accepts b=25 in registry
        u5q8_payload = str(MC_QUESTIONS['u5q8']['authoritative_answer_payload'])
        self.assertIn('b=25', u5q8_payload)

        # u5q15: integer solution -4 in registry
        u5q15_payload = str(MC_QUESTIONS['u5q15']['authoritative_answer_payload'])
        self.assertIn('-4,n=-4', u5q15_payload)


class TestMCAnswerChecker(unittest.TestCase):
    def test_fraction_equivalence(self):
        # Baseline fraction equivalence must pass
        self.assertTrue(is_correct_py('3/6', '1/2'))
        self.assertTrue(is_correct_py('1/2', '3/6'))
        self.assertTrue(is_correct_py('2/4', '1/2'))
        self.assertTrue(is_correct_py('4/8', '1/2'))
        self.assertTrue(is_correct_py('0.5', '1/2'))
        self.assertTrue(is_correct_py('1/2', '0.5'))
        self.assertTrue(is_correct_py('5/6', '100/120'))
        self.assertTrue(is_correct_py('10/12', '5/6'))
        self.assertTrue(is_correct_py('1/4', '2/8'))
        self.assertTrue(is_correct_py('-6/8', '-3/4'))
        self.assertTrue(is_correct_py('-0.75', '-3/4'))

    def test_false_match_rejections(self):
        # Strict rejection of glued or malformed numbers
        self.assertFalse(is_correct_py('12', '1/2'))
        self.assertFalse(is_correct_py('15', '1/5'))
        self.assertFalse(is_correct_py('14', '1/4'))
        self.assertFalse(is_correct_py('36', '3/6'))
        self.assertFalse(is_correct_py('57', '5/7'))
        self.assertFalse(is_correct_py('24', '2/4'))
        self.assertFalse(is_correct_py('3/4', '-3/4'))
        self.assertFalse(is_correct_py('5/8', '5/7'))

    def test_linear_algebraic_simplification(self):
        # Algebraic expressions that simplify to the same linear form
        self.assertTrue(is_correct_py('5x-3x-10', '2x-10'))
        self.assertTrue(is_correct_py('2x-10', '5x-3x-10'))
        self.assertTrue(is_correct_py('5x - 3x - 10', '2x - 10'))
        self.assertTrue(is_correct_py('6x-2+4', '6x+2'))
        self.assertTrue(is_correct_py('x-5+3x+2', '4x-3'))
        self.assertTrue(is_correct_py('4x-3', 'x-5+3x+2'))
        # Non-equivalent expressions must fail
        self.assertFalse(is_correct_py('2x-5', '2x-10'))
        self.assertFalse(is_correct_py('3x-10', '2x-10'))

    def test_variable_prefix_stripping(self):
        # Assignment prefix stripping
        self.assertTrue(is_correct_py('b=25', '25'))
        self.assertTrue(is_correct_py('25', 'b=25'))
        self.assertTrue(is_correct_py('b = 25', '25'))
        self.assertTrue(is_correct_py('x = 5', '5'))
        self.assertTrue(is_correct_py('n = -4', '-4'))
        # Incorrect values must fail
        self.assertFalse(is_correct_py('b=25', '26'))
        self.assertFalse(is_correct_py('b=25', 'b=26'))

    def test_explanatory_units_stripping(self):
        # Stripping units and explanatory nouns
        self.assertTrue(is_correct_py('1/4 of whole pizza', '1/4'))
        self.assertTrue(is_correct_py('1/4', '1/4 of whole pizza'))
        self.assertTrue(is_correct_py('1/4 pizza', '1/4'))
        self.assertTrue(is_correct_py('1/4 of the pizza', '1/4'))
        self.assertTrue(is_correct_py('12 boys', '12'))
        self.assertTrue(is_correct_py('28 girls', '28'))
        self.assertTrue(is_correct_py('₹300', '300'))
        self.assertTrue(is_correct_py('300 rupees', '300'))
        self.assertTrue(is_correct_py('-4°C', '-4'))
        self.assertTrue(is_correct_py('-4 degrees', '-4'))
        self.assertTrue(is_correct_py('-4 deg C', '-4'))
        self.assertFalse(is_correct_py('12 boys', '28'))

    def test_free_text_synonyms(self):
        self.assertTrue(is_correct_py('dropped', 'dropped,decreased,fell'))
        self.assertTrue(is_correct_py('decreased', 'dropped,decreased,fell'))
        self.assertTrue(is_correct_py('fell', 'dropped,decreased,fell'))
        self.assertTrue(is_correct_py('went down', 'dropped,decreased,fell,went down'))
        self.assertFalse(is_correct_py('colder', 'dropped,decreased,fell,went down'))

    def test_equations_not_coerced_numerically(self):
        # Full equations with variables must not match arbitrary floats
        self.assertTrue(is_correct_py('10x+750=12x', '10x+750=12x'))
        self.assertFalse(is_correct_py('10x+750=12x', '12'))
        self.assertFalse(is_correct_py('2(n+0.5)+0.5n=-9', '-4'))
        self.assertFalse(is_correct_py('2x+3=7', '2'))


if __name__ == '__main__':
    unittest.main()
