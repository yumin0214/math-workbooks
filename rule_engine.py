"""
rule_engine.py — Deterministic, Zero-Cost Rule Engine for Student Performance Reports.

Generates personalized, evidence-based performance reports for:
1. Calculation Speed Booster (CSB)
2. Mistake Correction (MC)

Operates 100% locally using existing database records with zero external API calls,
zero third-party dependencies, and zero financial cost.

Strict Constraints Followed:
- CSB: Does NOT claim to know operation-level breakdown (e.g., add vs sub) or
  calculation speed per item because the database does not store them.
- MC: Does NOT confuse question formats (fill, radio, tf, findMistake) with
  mathematical concepts, and does not claim to diagnose unrecorded misconceptions.
- Output: Preserves the exact 4 section headings expected by dashboard.js parser.
"""

from typing import List, Dict, Any, Optional


CSB_UNIT_NAMES = {
    1: 'Unit 1: Mental Math Foundations',
    2: 'Unit 2: Multiplication Tables & Patterns',
    3: 'Unit 3: Fractions, Decimals & Percentages',
    4: 'Unit 4: Algebra Speed Drills',
    5: 'Unit 5: Mixed Speed Challenge',
}

CSB_UNIT_SHORT = {
    1: 'Mental Math',
    2: 'Multiplication Tables',
    3: 'Fractions & Percentages',
    4: 'Algebra Drills',
    5: 'Mixed Challenge',
}

CSB_UNIT_TOTALS = {1: 20, 2: 20, 3: 20, 4: 20, 5: 30}

MC_UNIT_NAMES = {
    1: 'Unit 1: Fractions Mistakes',
    2: 'Unit 2: Integers Mistakes',
    3: 'Unit 3: Algebra Mistakes',
    4: 'Unit 4: Percentages & Decimals Mistakes',
    5: 'Unit 5: Grand Challenge',
}

MC_UNIT_SHORT = {
    1: 'Fractions',
    2: 'Integers',
    3: 'Algebra',
    4: 'Percentages & Decimals',
    5: 'Grand Challenge',
}

MC_TYPE_NAMES = {
    'findMistake': 'Find the Mistake (Step Diagnosis)',
    'tf':          'True or False (Statement Verification)',
    'radio':       'Which One is Right (Option Comparison)',
    'fill':        'Fill the Step / Fix & Solve (Active Calculation)',
}

MC_TYPE_TIPS = {
    'findMistake': 'Work through each solution step-by-step from the top before choosing which step holds the error.',
    'tf':          'Test statements independently with a small example number to verify whether the rule holds.',
    'radio':       'Solve the problem independently on rough paper first, then match your answer with the given options.',
    'fill':        'Write out the full mathematical step on rough paper before entering your final value into the blank.',
}


def _get_user_info(user: Any) -> Dict[str, Any]:
    """Safely extract user profile fields whether user is a Model or dict."""
    if isinstance(user, dict):
        fname = user.get('fname') or 'Student'
        lname = user.get('lname') or ''
        grade = user.get('grade') or 7
        city = user.get('city') or ''
        streak = user.get('streak') or 0
    else:
        fname = getattr(user, 'fname', None) or 'Student'
        lname = getattr(user, 'lname', None) or ''
        grade = getattr(user, 'grade', None) or 7
        city = getattr(user, 'city', None) or ''
        streak = getattr(user, 'streak', None) or 0

    return {
        'fname': fname,
        'lname': lname,
        'grade': grade,
        'city': city,
        'streak': streak,
    }


def _calculate_trend(sessions: List[Any]) -> str:
    """
    Evaluates score accuracy trajectory across recent sessions.
    Returns: 'improving', 'declining', 'consistent', or 'insufficient'.
    """
    if len(sessions) < 2:
        return 'insufficient'

    pcts = []
    for s in sessions:
        score = getattr(s, 'score', None) if not isinstance(s, dict) else s.get('score')
        total = getattr(s, 'total', None) if not isinstance(s, dict) else s.get('total')
        if total and total > 0:
            pcts.append((score / total) * 100)

    if len(pcts) < 2:
        return 'insufficient'

    window = pcts[-6:]
    mid = len(window) // 2
    first_half = window[:mid]
    second_half = window[mid:]

    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)
    diff = avg_second - avg_first

    if diff >= 6.0:
        return 'improving'
    elif diff <= -6.0:
        return 'declining'
    else:
        return 'consistent'


# ─────────────────────────────────────────────────────────────
# CALCULATION SPEED BOOSTER (CSB) REPORT GENERATOR
# ─────────────────────────────────────────────────────────────
def generate_csb_report(user: Any, sessions: List[Any], best_scores: List[Any]) -> str:
    """
    Builds a deterministic CSB performance report matching the exact 4 headings:
    📊 Overall Performance Summary
    💪 What You're Good At
    ⚠️ Areas to Focus On
    🎯 This Week's Action Plan
    """
    u = _get_user_info(user)
    fname = u['fname']

    # ── Handle Zero Sessions (First-practice onboarding message) ──
    if not sessions:
        return (
            f"📊 Overall Performance Summary\n"
            f"Welcome to your Calculation Speed Booster report, {fname}! You have not completed "
            f"any timed drills yet. Once you complete your first practice session, this section will track "
            f"your overall accuracy, completion trends, and personal best scores across all 5 units.\n\n"
            f"💪 What You're Good At\n"
            f"Taking the initiative to begin daily practice is the foundation of rapid mental math. "
            f"As a Grade {u['grade']} student, building quick number recall now will give you an advantage "
            f"in exams and regular classwork.\n\n"
            f"⚠️ Areas to Focus On\n"
            f"Your immediate focus is to establish a starting baseline. We recommend beginning with "
            f"Unit 1: Mental Math Foundations to get comfortable with the timed drill format.\n\n"
            f"🎯 This Week's Action Plan\n"
            f"1. Open Unit 1 (Mental Math Foundations) and review the Worked Examples at the top.\n"
            f"2. Start the 5-minute timer and solve all 20 drill questions in your head.\n"
            f"3. Click Check My Answers to save your score and unlock your detailed performance metrics."
        )

    # ── Aggregate Performance Metrics ──
    total_sessions = len(sessions)
    total_attempted = 0
    total_correct = 0

    unit_attempts: Dict[int, int] = {i: 0 for i in range(1, 6)}
    unit_total_score: Dict[int, int] = {i: 0 for i in range(1, 6)}
    unit_max_possible: Dict[int, int] = {i: 0 for i in range(1, 6)}

    for s in sessions:
        unit = getattr(s, 'unit', None) if not isinstance(s, dict) else s.get('unit')
        score = getattr(s, 'score', None) if not isinstance(s, dict) else s.get('score')
        total = getattr(s, 'total', None) if not isinstance(s, dict) else s.get('total')

        if unit in range(1, 6) and score is not None and total:
            total_attempted += total
            total_correct += score
            unit_attempts[unit] += 1
            unit_total_score[unit] += score
            unit_max_possible[unit] += total

    overall_pct = round((total_correct / total_attempted) * 100) if total_attempted > 0 else 0

    # Best scores extraction
    best_by_unit: Dict[int, int] = {i: 0 for i in range(1, 6)}
    for b in (best_scores or []):
        unit = getattr(b, 'unit', None) if not isinstance(b, dict) else b.get('unit')
        score = getattr(b, 'best_score', None) if not isinstance(b, dict) else b.get('best_score')
        if unit in range(1, 6) and score is not None:
            best_by_unit[unit] = max(best_by_unit[unit], score)

    attempted_units = [u_num for u_num, count in unit_attempts.items() if count > 0]
    unattempted_units = [u_num for u_num, count in unit_attempts.items() if count == 0]

    unit_pcts: Dict[int, int] = {}
    for u_num in attempted_units:
        unit_pcts[u_num] = round((unit_total_score[u_num] / unit_max_possible[u_num]) * 100)

    if attempted_units:
        strongest_unit = max(attempted_units, key=lambda x: (unit_pcts[x], best_by_unit[x]))
        strongest_name = CSB_UNIT_SHORT[strongest_unit]
        strongest_pct = unit_pcts[strongest_unit]
        strongest_best = best_by_unit[strongest_unit]
        strongest_max = CSB_UNIT_TOTALS[strongest_unit]

        weakest_unit = min(attempted_units, key=lambda x: (unit_pcts[x], best_by_unit[x]))
        weakest_name = CSB_UNIT_SHORT[weakest_unit]
        weakest_pct = unit_pcts[weakest_unit]
        weakest_best = best_by_unit[weakest_unit]
        weakest_max = CSB_UNIT_TOTALS[weakest_unit]
    else:
        strongest_unit = weakest_unit = 1
        strongest_name = weakest_name = CSB_UNIT_SHORT[1]
        strongest_pct = weakest_pct = overall_pct
        strongest_best = weakest_best = 0
        strongest_max = weakest_max = 20

    trend = _calculate_trend(sessions)
    if trend == 'improving':
        trend_desc = "Scores across your recent sessions show an upward trend, showing that consistent repetition is helping you solve drills with greater accuracy."
    elif trend == 'declining':
        trend_desc = "Recent drill scores show a slight dip compared to your earlier sessions, which commonly happens when tackling harder units or practising while fatigued."
    elif trend == 'consistent':
        trend_desc = "Your scores remain steady across recent sessions, reflecting dependable calculation habits across the units you have attempted."
    else:
        trend_desc = "With your first drill completed, you have set an initial benchmark to measure your progress against in upcoming sessions."

    streak_count = u['streak']
    streak_msg = f"You are currently on a {streak_count} day practice streak." if streak_count > 1 else "Completing a drill each day will build your active streak."

    # Section 1: Overall Performance Summary
    summary_text = (
        f"{fname}, you have completed {total_sessions} Speed Booster "
        f"{'session' if total_sessions == 1 else 'sessions'} with an overall cumulative accuracy of {overall_pct}% "
        f"({total_correct}/{total_attempted} total drill questions answered correctly). {trend_desc} {streak_msg}"
    )

    # Section 2: What You're Good At
    if strongest_pct >= 80:
        strength_text = (
            f"Your highest performance is in {strongest_name}, where you achieved an average accuracy of {strongest_pct}% "
            f"and a personal best of {strongest_best}/{strongest_max}. Your solid recall in this unit demonstrates strong "
            f"numerical confidence and reliable accuracy under timed conditions."
        )
    else:
        strength_text = (
            f"Your most successful unit so far is {strongest_name}, achieving an average accuracy of {strongest_pct}% "
            f"and a top score of {strongest_best}/{strongest_max}. This shows you have established a working foundation here "
            f"that you can build upon across the remaining drills."
        )

    # Section 3: Areas to Focus On
    if len(attempted_units) == 1 and unattempted_units:
        focus_text = (
            f"You have concentrated your practice on {strongest_name} ({strongest_best}/{strongest_max}). "
            f"To develop well-rounded calculation fluency for Grade {u['grade']}, your key growth area is to explore the "
            f"unattempted units, beginning with {CSB_UNIT_NAMES[unattempted_units[0]]}."
        )
    elif weakest_pct < 70:
        focus_text = (
            f"Your scores indicate that {weakest_name} currently has the greatest scope for progress, with an average "
            f"accuracy of {weakest_pct}% and a best score of {weakest_best}/{weakest_max}. Spending focused time reviewing the "
            f"worked examples and tricks of the day in this unit will help raise your accuracy."
        )
    else:
        focus_text = (
            f"All your attempted units show consistent scores above 70%. Your primary focus now is converting scores from "
            f"the 70% to 80% range into near-perfect 90%+ performances, especially in {weakest_name} (currently {weakest_best}/{weakest_max})."
        )

    # Section 4: This Week's Action Plan (3 numbered recommendations)
    tip1 = (
        f"Revisit {weakest_name} and complete one full 20-question drill without rushing to ensure every answer is double-checked."
        if weakest_unit != 5 else
        f"Revisit Unit 1 (Mental Math) and Unit 2 (Tables) to strengthen core calculation accuracy before attempting the Mixed Challenge."
    )

    if unattempted_units:
        next_u = unattempted_units[0]
        tip2 = f"Unlock {CSB_UNIT_NAMES[next_u]} to expand your coverage beyond the units you have already practiced."
    else:
        tip2 = f"Attempt Unit 5 (Mixed Speed Challenge) to test your ability to switch between different math topics under a single timer."

    tip3 = "Maintain your practice habit by dedicating 10 to 15 minutes at the same time each day to preserve your streak."

    action_text = f"1. {tip1}\n2. {tip2}\n3. {tip3}"

    return (
        f"📊 Overall Performance Summary\n{summary_text}\n\n"
        f"💪 What You're Good At\n{strength_text}\n\n"
        f"⚠️ Areas to Focus On\n{focus_text}\n\n"
        f"🎯 This Week's Action Plan\n{action_text}"
    )


# ─────────────────────────────────────────────────────────────
# MISTAKE CORRECTION (MC) REPORT GENERATOR
# ─────────────────────────────────────────────────────────────
def generate_mc_report(
    user: Any,
    sessions: List[Any],
    best_scores: List[Any],
    type_stats: Any
) -> str:
    """
    Builds a deterministic MC performance report matching the exact 4 headings:
    🔍 Error Pattern Summary
    💪 What You Understand Well
    ⚠️ Recurring Mistake Types
    🎯 Targeted Practice Plan
    """
    u = _get_user_info(user)
    fname = u['fname']

    # ── Handle Zero Sessions (First-practice onboarding message) ──
    if not sessions:
        return (
            f"🔍 Error Pattern Summary\n"
            f"Welcome to your Mistake Correction diagnostic report, {fname}! You have not submitted "
            f"any mistake analysis exercises yet. Once you complete your first unit, this report will identify "
            f"your diagnostic accuracy and format-specific verification habits.\n\n"
            f"💪 What You Understand Well\n"
            f"Analyzing someone else's mathematical working requires sharp critical thinking. Learning to spot "
            f"hidden errors trains your eye to catch slips in your own homework and exams before submitting.\n\n"
            f"⚠️ Recurring Mistake Types\n"
            f"No error patterns have been recorded yet. As you attempt the exercises, this section will analyze "
            f"how well you perform across different question formats, such as finding faulty steps versus evaluating statements.\n\n"
            f"🎯 Targeted Practice Plan\n"
            f"1. Open Unit 1 (Fractions Mistakes) and read through the Worked Examples carefully.\n"
            f"2. Solve at least 5 exercises, checking your answer after each one to inspect any hints.\n"
            f"3. Submit the unit to save your score and unlock your personalized mistake pattern analysis."
        )

    total_sessions = len(sessions)
    total_attempted = sum((getattr(s, 'total', 0) if not isinstance(s, dict) else s.get('total', 0)) for s in sessions)
    total_correct = sum((getattr(s, 'score', 0) if not isinstance(s, dict) else s.get('score', 0)) for s in sessions)
    overall_pct = round((total_correct / total_attempted) * 100) if total_attempted > 0 else 0

    best_by_unit: Dict[int, int] = {i: 0 for i in range(1, 6)}
    for b in (best_scores or []):
        unit = getattr(b, 'unit', None) if not isinstance(b, dict) else b.get('unit')
        score = getattr(b, 'best_score', None) if not isinstance(b, dict) else b.get('best_score')
        if unit in range(1, 6) and score is not None:
            best_by_unit[unit] = max(best_by_unit[unit], score)

    unit_counts: Dict[int, int] = {i: 0 for i in range(1, 6)}
    for s in sessions:
        unit = getattr(s, 'unit', None) if not isinstance(s, dict) else s.get('unit')
        if unit in range(1, 6):
            unit_counts[unit] += 1

    attempted_units = [u_num for u_num, count in unit_counts.items() if count > 0]
    unattempted_units = [u_num for u_num, count in unit_counts.items() if count == 0]

    if attempted_units:
        strongest_unit = max(attempted_units, key=lambda x: best_by_unit[x])
        strongest_name = MC_UNIT_SHORT[strongest_unit]
        strongest_score = best_by_unit[strongest_unit]
        strongest_pct = round((strongest_score / 15) * 100)

        weakest_unit = min(attempted_units, key=lambda x: best_by_unit[x])
        weakest_name = MC_UNIT_SHORT[weakest_unit]
        weakest_score = best_by_unit[weakest_unit]
        weakest_pct = round((weakest_score / 15) * 100)
    else:
        strongest_unit = weakest_unit = 1
        strongest_name = weakest_name = MC_UNIT_SHORT[1]
        strongest_score = weakest_score = 0
        strongest_pct = weakest_pct = 0

    # Question Format Statistics extraction
    format_data: Dict[str, Dict[str, int]] = {}
    if isinstance(type_stats, dict):
        for k, v in type_stats.items():
            if isinstance(v, dict):
                format_data[k] = {'a': v.get('a') or v.get('attempted') or 0, 'c': v.get('c') or v.get('correct') or 0}
            else:
                att = getattr(v, 'attempted', 0)
                cor = getattr(v, 'correct', 0)
                format_data[k] = {'a': att, 'c': cor}
    elif isinstance(type_stats, list):
        for row in type_stats:
            k = getattr(row, 'type_key', None) if not isinstance(row, dict) else row.get('type_key')
            att = getattr(row, 'attempted', 0) if not isinstance(row, dict) else row.get('attempted', 0)
            cor = getattr(row, 'correct', 0) if not isinstance(row, dict) else row.get('correct', 0)
            if k:
                format_data[k] = {'a': att, 'c': cor}

    evaluated_formats = []
    for key, name in MC_TYPE_NAMES.items():
        st = format_data.get(key, {'a': 0, 'c': 0})
        a, c = st['a'], st['c']
        pct = round((c / a) * 100) if a > 0 else None
        evaluated_formats.append({'key': key, 'name': name, 'attempted': a, 'correct': c, 'pct': pct})

    attempted_formats = [f for f in evaluated_formats if f['pct'] is not None]
    if attempted_formats:
        best_format = max(attempted_formats, key=lambda x: x['pct'])
        lowest_format = min(attempted_formats, key=lambda x: x['pct'])
    else:
        best_format = lowest_format = None

    trend = _calculate_trend(sessions)
    if trend == 'improving':
        trend_msg = "Your recent submissions show steady score improvement as you become more familiar with common problem traps."
    elif trend == 'declining':
        trend_msg = "Your recent submissions reflect more challenging exercises where errors were harder to detect on first reading."
    elif trend == 'consistent':
        trend_msg = "Your diagnostic accuracy has remained stable across your submitted units."
    else:
        trend_msg = "Your first unit submission gives an initial snapshot of your error-detection skills."

    # Section 1: Error Pattern Summary
    summary_text = (
        f"{fname}, you have completed {total_sessions} Mistake Correction "
        f"{'session' if total_sessions == 1 else 'sessions'} with an overall score accuracy of {overall_pct}% "
        f"({total_correct}/{total_attempted} exercises solved correctly). {trend_msg} "
        f"Your highest recorded unit score is {strongest_score}/15 ({strongest_pct}%) in {strongest_name}."
    )

    # Section 2: What You Understand Well
    if best_format and best_format['pct'] >= 70:
        well_text = (
            f"You demonstrate strong proficiency in {best_format['name']}, achieving {best_format['pct']}% accuracy "
            f"({best_format['correct']}/{best_format['attempted']}). In addition, your performance in {strongest_name} "
            f"({strongest_score}/15) shows that you can reliably detect flaws and verify reasoning when evaluating this topic."
        )
    elif best_format:
        well_text = (
            f"Your most dependable question format is {best_format['name']} with {best_format['pct']}% accuracy "
            f"({best_format['correct']}/{best_format['attempted']}). In unit practice, {strongest_name} represents your "
            f"strongest showing with a score of {strongest_score}/15."
        )
    else:
        well_text = (
            f"In your completed work, {strongest_name} stands out as your top unit with a score of {strongest_score}/15. "
            f"Continuing to complete exercises across different question formats will help identify your specific analytical strengths."
        )

    # Section 3: Recurring Mistake Types
    if lowest_format and lowest_format['pct'] < 70 and lowest_format != best_format:
        mistake_text = (
            f"Question format analysis shows that {lowest_format['name']} currently yields the lowest accuracy at "
            f"{lowest_format['pct']}% ({lowest_format['correct']}/{lowest_format['attempted']}). Note that this refers to "
            f"the interaction format rather than a specific math concept: active calculation and step correction questions "
            f"typically require independent scratchpad work before finalizing an answer."
        )
    elif lowest_format:
        mistake_text = (
            f"Across question formats, your accuracy is relatively balanced. Your lowest format is {lowest_format['name']} "
            f"at {lowest_format['pct']}%. In unit terms, {weakest_name} (score {weakest_score}/15) contains the most exercises "
            f"where subtle calculation or sign slips went unspotted."
        )
    else:
        mistake_text = (
            f"More session data across different question formats is needed to map recurring error types. In your current work, "
            f"{weakest_name} (best score {weakest_score}/15) provides the clearest opportunity to practice spotting hidden traps."
        )

    # Section 4: Targeted Practice Plan (3 numbered recommendations)
    if lowest_format and lowest_format['key'] in MC_TYPE_TIPS:
        tip1 = f"For {lowest_format['name']}: {MC_TYPE_TIPS[lowest_format['key']]}"
    else:
        tip1 = "Before selecting an answer, write down your own solution step-by-step to compare against the student's working."

    if unattempted_units:
        tip2 = f"Advance to {MC_UNIT_NAMES[unattempted_units[0]]} to test your error-spotting ability on new topics."
    elif weakest_score < 13:
        tip2 = f"Re-attempt exercises in {weakest_name} to turn your current best score ({weakest_score}/15) into a mastery score."
    else:
        tip2 = "Challenge yourself with Unit 5 (Grand Challenge) to test multi-step problems combining multiple topics."

    tip3 = "Always click Show Hint after checking your answer to read the explanation, even on exercises you answered correctly."

    plan_text = f"1. {tip1}\n2. {tip2}\n3. {tip3}"

    return (
        f"🔍 Error Pattern Summary\n{summary_text}\n\n"
        f"💪 What You Understand Well\n{well_text}\n\n"
        f"⚠️ Recurring Mistake Types\n{mistake_text}\n\n"
        f"🎯 Targeted Practice Plan\n{plan_text}"
    )
