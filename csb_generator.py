"""
csb_generator.py — Server-Side Deterministic Question Generator & Non-Commutative Fingerprinting
For Calculation Speed Booster (CSB).
Operates with zero paid dependencies.
"""

import random
import re
from typing import Dict, List, Any, Tuple, Optional


def compute_csb_fingerprint(operation_tag: str, operands: Tuple[Any, ...]) -> str:
    """
    Computes canonical fingerprint string:
    - Commutative ('add', 'mul'): sorts numeric operands.
    - Non-commutative ('sub', 'div', 'pct_of', algebra, etc.): preserves operand order.
    """
    op = operation_tag.strip().lower()
    if op in ("add", "mul"):
        try:
            sorted_ops = sorted(operands, key=lambda x: float(x))
        except (ValueError, TypeError):
            sorted_ops = sorted(operands, key=str)
        return f"{op}:" + ":".join(str(x) for x in sorted_ops)
    else:
        return f"{op}:" + ":".join(str(x) for x in operands)


def num_range_for_grade(grade: int = 7) -> Dict[str, Tuple[int, int]]:
    if grade <= 6:
        return {"small": (2, 9), "med": (10, 50), "big": (50, 200)}
    elif grade <= 8:
        return {"small": (2, 12), "med": (10, 99), "big": (100, 500)}
    else:
        return {"small": (2, 15), "med": (10, 150), "big": (200, 999)}


def generate_unit1_question(grade: int = 7, op_type: Optional[str] = None) -> Dict[str, Any]:
    r = num_range_for_grade(grade)
    types = ["add", "sub", "mul"]
    t = op_type if op_type in types else random.choice(types)
    if t == "add":
        a = random.randint(r["med"][0], r["med"][1])
        b = random.randint(r["med"][0], r["med"][1])
        q_text = f"{a} + {b} ="
        correct = str(a + b)
        fp = compute_csb_fingerprint("add", (a, b))
    elif t == "sub":
        b = random.randint(r["med"][0], r["med"][1])
        a = b + random.randint(r["small"][0], r["med"][1])
        q_text = f"{a} − {b} ="
        correct = str(a - b)
        fp = compute_csb_fingerprint("sub", (a, b))
    else:
        a = random.randint(r["small"][0], r["small"][1])
        b = random.randint(r["small"][0], r["small"][1])
        q_text = f"{a} × {b} ="
        correct = str(a * b)
        fp = compute_csb_fingerprint("mul", (a, b))

    return {
        "question_text": q_text,
        "correct_answer": correct,
        "operation_tag": t,
        "difficulty_band": "standard",
        "question_fingerprint": fp,
    }


def generate_unit2_question(grade: int = 7, op_type: Optional[str] = None) -> Dict[str, Any]:
    max_table = 12 if grade <= 6 else (15 if grade <= 8 else 20)
    t = op_type if op_type in ("table", "square") else ("table" if random.random() < 0.7 else "square")
    if t == "table":
        a = random.randint(11, max_table)
        b = random.randint(2, 12)
        q_text = f"{a} × {b} ="
        correct = str(a * b)
        fp = compute_csb_fingerprint("mul", (a, b))
    else:
        n = random.randint(11, min(max_table, 18))
        q_text = f"{n}² ="
        correct = str(n * n)
        fp = compute_csb_fingerprint("square", (n,))

    return {
        "question_text": q_text,
        "correct_answer": correct,
        "operation_tag": t,
        "difficulty_band": "standard",
        "question_fingerprint": fp,
    }


def generate_unit3_question(grade: int = 7, mode: Optional[int] = None) -> Dict[str, Any]:
    big_nums = [20, 40, 60, 80, 100] if grade <= 6 else ([50, 80, 120, 200, 250] if grade <= 8 else [60, 150, 200, 400, 500])
    frac_pairs = [
        {"f": "1/4", "d": "0.25", "p": "25%"},
        {"f": "1/2", "d": "0.5", "p": "50%"},
        {"f": "3/4", "d": "0.75", "p": "75%"},
        {"f": "1/5", "d": "0.2", "p": "20%"},
        {"f": "2/5", "d": "0.4", "p": "40%"},
        {"f": "3/5", "d": "0.6", "p": "60%"},
        {"f": "4/5", "d": "0.8", "p": "80%"},
        {"f": "1/8", "d": "0.125", "p": "12.5%"},
        {"f": "3/8", "d": "0.375", "p": "37.5%"},
        {"f": "7/10", "d": "0.7", "p": "70%"},
    ]
    pcts = [10, 20, 25, 30, 40, 50, 60, 75]
    m = mode if mode is not None and mode in (0, 1, 2, 3) else random.randint(0, 3)

    if m == 0:
        pct = random.choice(pcts)
        num = random.choice(big_nums)
        q_text = f"{pct}% of {num} ="
        correct = str(round(pct * num / 100))
        fp = compute_csb_fingerprint("pct_of", (pct, num))
        op = "pct_of"
    elif m == 1:
        fp_item = random.choice(frac_pairs)
        q_text = f"{fp_item['f']} as dec ="
        correct = fp_item["d"]
        fp = compute_csb_fingerprint("frac_to_dec", (fp_item["f"],))
        op = "frac_to_dec"
    elif m == 2:
        fp_item = random.choice(frac_pairs)
        q_text = f"{fp_item['d']} as % ="
        correct = fp_item["p"]
        fp = compute_csb_fingerprint("dec_to_pct", (fp_item["d"],))
        op = "dec_to_pct"
    else:
        fp_item = random.choice(frac_pairs)
        q_text = f"{fp_item['f']} as % ="
        correct = fp_item["p"]
        fp = compute_csb_fingerprint("frac_to_pct", (fp_item["f"],))
        op = "frac_to_pct"

    return {
        "question_text": q_text,
        "correct_answer": correct,
        "operation_tag": op,
        "difficulty_band": "standard",
        "question_fingerprint": fp,
    }


def generate_unit4_question(grade: int = 7, mode: Optional[int] = None) -> Dict[str, Any]:
    max_x = 10 if grade <= 6 else (20 if grade <= 8 else 30)
    m = mode if mode is not None and mode in range(5) else random.randint(0, 4)

    if m == 0:
        x = random.randint(2, max_x)
        a = random.randint(2, 20)
        q_text = f"x + {a} = {x + a}"
        correct = f"x={x}"
        fp = compute_csb_fingerprint("alg_x_add_a", (a, x + a))
        op = "alg_x_add_a"
    elif m == 1:
        a = random.randint(2, 9)
        x = random.randint(2, max_x)
        q_text = f"{a}x = {a * x}"
        correct = f"x={x}"
        fp = compute_csb_fingerprint("alg_ax", (a, a * x))
        op = "alg_ax"
    elif m == 2:
        x = random.randint(5, max_x + 5)
        a = random.randint(2, 10)
        q_text = f"x − {a} = {x - a}"
        correct = f"x={x}"
        fp = compute_csb_fingerprint("alg_x_sub_a", (a, x - a))
        op = "alg_x_sub_a"
    elif m == 3:
        a = random.randint(2, 6)
        x = random.randint(2, 10)
        b = random.randint(1, 10)
        q_text = f"{a}x + {b} = {a * x + b}"
        correct = f"x={x}"
        fp = compute_csb_fingerprint("alg_ax_b", (a, b, a * x + b))
        op = "alg_ax_b"
    else:
        a = random.randint(2, 8)
        x = a * random.randint(2, max_x)
        q_text = f"x / {a} = {x // a}"
        correct = f"x={x}"
        fp = compute_csb_fingerprint("alg_x_div_a", (a, x // a))
        op = "alg_x_div_a"

    return {
        "question_text": q_text,
        "correct_answer": correct,
        "operation_tag": op,
        "difficulty_band": "standard",
        "question_fingerprint": fp,
    }


def generate_csb_unit_pool(unit: int, grade: int = 7, pending_retries: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    Generates a full 20-question (or 30-question for Unit 5) pool.
    Interleaves eligible retries while guaranteeing zero duplicate fingerprints within the session.
    """
    total = 30 if unit == 5 else 20
    pool = []
    seen_fps = set()

    # 1. Interleave up to 3 pending retries first
    if pending_retries:
        for r in pending_retries[:3]:
            fp = r.get("question_fingerprint")
            if fp and fp not in seen_fps:
                seen_fps.add(fp)
                pool.append({
                    "question_text": r.get("question_text"),
                    "correct_answer": r.get("correct_answer"),
                    "operation_tag": r.get("operation_tag", "retry"),
                    "difficulty_band": r.get("difficulty_band", "standard"),
                    "question_fingerprint": fp,
                    "is_retry": True,
                    "retry_source_id": r.get("id"),
                })

    # 2. Fill the remainder of the pool
    while len(pool) < total:
        idx = len(pool)
        if unit == 1:
            q = generate_unit1_question(grade, op_type=["add", "sub", "mul"][idx % 3])
        elif unit == 2:
            q = generate_unit2_question(grade)
        elif unit == 3:
            q = generate_unit3_question(grade, mode=idx % 4)
        elif unit == 4:
            q = generate_unit4_question(grade, mode=idx % 5)
        elif unit == 5:
            # Unit 5 mixed: 0..7 Unit 1, 8..15 Unit 2, 16..22 Unit 3, 23..29 Unit 4
            if idx < 8:
                q = generate_unit1_question(grade, op_type=["add", "sub", "mul"][idx % 3])
            elif idx < 16:
                q = generate_unit2_question(grade)
            elif idx < 23:
                q = generate_unit3_question(grade, mode=(idx - 16) % 4)
            else:
                q = generate_unit4_question(grade, mode=(idx - 23) % 5)

        fp = q["question_fingerprint"]
        if fp not in seen_fps:
            seen_fps.add(fp)
            q["is_retry"] = False
            q["retry_source_id"] = None
            pool.append(q)

    # Assign positions 0 to total - 1
    for pos, item in enumerate(pool):
        item["position"] = pos

    return pool


def grade_csb_question(submitted_answer: Any, correct_answer: str, operation_tag: str = "") -> bool:
    """
    Authoritative server-side grading for Calculation Speed Booster questions.
    Normalizes spaces, case, handles 'x=5' vs '5', and handles percentage strings.
    """
    if submitted_answer is None:
        return False
    u = str(submitted_answer).strip().lower()
    c = str(correct_answer).strip().lower()

    if not u:
        return False

    # Exact string match
    if u == c:
        return True

    # Strip variable assignments e.g. x=5 vs 5
    u_strip = re.sub(r"^[a-zA-Z_]\w*\s*=\s*", "", u)
    c_strip = re.sub(r"^[a-zA-Z_]\w*\s*=\s*", "", c)
    if u_strip == c_strip:
        return True

    # Handle percentage: 25% vs 25
    u_pct = u.rstrip("%").strip()
    c_pct = c.rstrip("%").strip()
    if u_pct == c_pct:
        return True

    # Numeric equivalence
    try:
        if abs(float(u_strip) - float(c_strip)) < 0.005:
            return True
    except (ValueError, TypeError):
        pass

    return False
