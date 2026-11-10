"""
mc_grader.py — Authoritative Server-Side Grading Pipeline for Mistake Correction (MC)
Zero trust for browser-submitted correctness. Operates 100% deterministically.
Implements the exact 6-tier grading normalization and validation pipeline.
"""

import re
import math
from typing import Any, Union, List, Optional


def normalize_algebraic(s: Any) -> str:
    """Normalize algebraic expressions and mathematical strings."""
    if s is None:
        return ""
    st = str(s).strip().lower()
    # Normalize unicode operators and spaces
    st = st.replace("−", "-").replace("×", "*").replace("÷", "/")
    st = re.sub(r"\s+", "", st)
    return st


def strip_units_and_prefixes(s: Any) -> str:
    """Strips variable prefixes (x=, b=) and common math unit suffixes (₹, %, cm, kg)."""
    if s is None:
        return ""
    st = str(s).strip()
    # Strip variable assignments like "x=", "ans=", "b="
    st = re.sub(r"^[a-zA-Z_]\w*\s*=\s*", "", st)
    st = re.sub(r"^ans(?:wer)?\s*=\s*", "", st, flags=re.IGNORECASE)
    # Strip currency signs
    st = st.replace("₹", "").replace("rs.", "").replace("rs", "")
    # Strip common word endings like "of whole pizza", "degrees", etc.
    st = re.sub(r"(?i)\s*of\s+whole\s+pizza", "", st)
    st = re.sub(r"(?i)\s*degrees?", "", st)
    st = re.sub(r"(?i)\s*celsius", "", st)
    st = re.sub(r"[°cCF]", "", st)
    return st.strip()


def parse_numeric_or_fraction(s: Any) -> Optional[float]:
    """Parses a string as a float, integer, or fraction a/b."""
    if s is None:
        return None
    st = str(s).strip()
    # Strip leading +
    if st.startswith("+"):
        st = st[1:].strip()
    # Check simple fraction
    frac_match = re.match(r"^(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)$", st)
    if frac_match:
        num = float(frac_match.group(1))
        den = float(frac_match.group(2))
        if abs(den) < 1e-9:
            return None
        return num / den
    # Check float/int
    num_match = re.match(r"^-?\d+(?:\.\d+)?$", st)
    if num_match:
        try:
            return float(st)
        except ValueError:
            return None
    return None


def simplify_linear_expression(s: Any) -> Optional[str]:
    """
    Parses and canonicalizes linear expressions of one variable, e.g.
    '3x + 2y' or '5x - 3x - 10' -> '2x - 10'.
    Returns canonical form 'ax+b' or 'ax-b' or None if not a simple linear expression.
    """
    if s is None:
        return None
    st = normalize_algebraic(s)
    # Check if expression contains only one variable, digits, +, -, *, /, ()
    vars_found = set(re.findall(r"[a-zA-Z]", st))
    if len(vars_found) > 1:
        # Multiple variables: canonicalize terms alphabetically
        # E.g., 3x+2y+5x-y -> 8x+y
        tokens = re.findall(r"([+-]?[^+-]+)", st)
        var_coeffs = {}
        const_val = 0
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            m = re.match(r"^([+-]?\d*)([a-zA-Z])$", tok)
            if m:
                c_str, v = m.group(1), m.group(2)
                c = -1 if c_str == "-" else (1 if c_str in ("", "+") else int(c_str))
                var_coeffs[v] = var_coeffs.get(v, 0) + c
            else:
                try:
                    const_val += int(tok)
                except ValueError:
                    return None
        parts = []
        for v in sorted(var_coeffs.keys()):
            c = var_coeffs[v]
            if c == 0:
                continue
            if c == 1:
                parts.append(f"+{v}" if parts else v)
            elif c == -1:
                parts.append(f"-{v}")
            else:
                parts.append(f"+{c}{v}" if c > 0 and parts else f"{c}{v}")
        if const_val != 0 or not parts:
            if const_val > 0 and parts:
                parts.append(f"+{const_val}")
            else:
                parts.append(str(const_val))
        return "".join(parts)
    elif len(vars_found) == 1:
        v = list(vars_found)[0]
        # Linear expression in single variable v
        # Parse tokens
        tokens = re.findall(r"([+-]?[^+-]+)", st)
        coeff = 0
        const_val = 0
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            m = re.match(r"^([+-]?\d*)([a-zA-Z])$", tok)
            if m:
                c_str = m.group(1)
                c = -1 if c_str == "-" else (1 if c_str in ("", "+") else int(c_str))
                coeff += c
            else:
                try:
                    const_val += int(tok)
                except ValueError:
                    return None
        parts = []
        if coeff != 0:
            if coeff == 1:
                parts.append(v)
            elif coeff == -1:
                parts.append(f"-{v}")
            else:
                parts.append(f"{coeff}{v}")
        if const_val != 0 or not parts:
            if const_val > 0 and parts:
                parts.append(f"+{const_val}")
            else:
                parts.append(str(const_val))
        return "".join(parts)
    return None


def check_single_blank_match(user_val: Any, authoritative_payload: Any) -> bool:
    """Evaluates a single blank value against an accepted payload."""
    u_raw = str(user_val).strip()
    if not u_raw:
        return False

    # Standardize accepted list
    if isinstance(authoritative_payload, (list, tuple, set)):
        raw_acc_list = [str(x).strip() for x in authoritative_payload]
    elif isinstance(authoritative_payload, str):
        raw_acc_list = [x.strip() for x in authoritative_payload.split(",") if x.strip()]
    else:
        raw_acc_list = [str(authoritative_payload).strip()]

    u_norm = normalize_algebraic(u_raw)
    acc_norm_list = [normalize_algebraic(a) for a in raw_acc_list]

    # Tier 1: Direct normalized match
    if u_norm in acc_norm_list:
        return True

    # Tier 2: Trailing % match
    for acc in acc_norm_list:
        u_pct = u_norm.rstrip("%")
        a_pct = acc.rstrip("%")
        if u_pct == a_pct:
            n1 = parse_numeric_or_fraction(u_pct)
            n2 = parse_numeric_or_fraction(a_pct)
            if n1 is not None and n2 is not None and abs(n1 - n2) < 0.005:
                return True

    # Tier 3: Unit and prefix stripping match
    u_stripped = strip_units_and_prefixes(u_raw)
    u_stripped_norm = normalize_algebraic(u_stripped)
    for raw_acc in raw_acc_list:
        acc_stripped = strip_units_and_prefixes(raw_acc)
        acc_stripped_norm = normalize_algebraic(acc_stripped)
        if u_stripped_norm == acc_stripped_norm:
            return True
        if not re.search(r"[a-zA-Z=]", u_stripped_norm) and not re.search(r"[a-zA-Z=]", acc_stripped_norm):
            n1 = parse_numeric_or_fraction(u_stripped)
            n2 = parse_numeric_or_fraction(acc_stripped)
            if n1 is not None and n2 is not None and abs(n1 - n2) < 0.005:
                return True

    # Tier 4: Linear algebraic simplification match
    u_simp = simplify_linear_expression(u_raw)
    if u_simp is not None:
        for raw_acc in raw_acc_list:
            a_simp = simplify_linear_expression(raw_acc)
            if a_simp is not None and u_simp == a_simp:
                return True
            if u_simp == normalize_algebraic(raw_acc):
                return True

    # Tier 5: Variable check (DO NOT do simplistic numeric comparison if variables are present)
    has_alg = any(re.search(r"[a-zA-Z=]", acc) for acc in acc_norm_list) or bool(re.search(r"[a-zA-Z=]", u_norm))
    if has_alg:
        return False

    # Tier 6: Numeric & fraction equivalence comparison
    u_num = parse_numeric_or_fraction(u_stripped_norm)
    if u_num is not None:
        for acc in acc_norm_list:
            acc_strp = normalize_algebraic(strip_units_and_prefixes(acc))
            if re.search(r"[a-zA-Z=]", acc_strp):
                continue
            a_num = parse_numeric_or_fraction(acc_strp)
            if a_num is not None and abs(u_num - a_num) < 0.005:
                return True

    return False


def is_correct_mc(
    user_val: Any,
    authoritative_payload: Any,
    grading_rule_key: str = "grader_v1_general",
    question_type: str = "fill"
) -> bool:
    """
    Authoritative server-side grading matching the 6-tier pipeline:
    1. Direct normalized match
    2. Trailing % tolerance match
    3. Unit and prefix stripping match
    4. Linear algebraic simplification match
    5. Variable check (prevents false numeric matches on algebraic letters)
    6. Numeric & fraction equivalence comparison (tolerance < 0.005)
    """
    if user_val is None:
        return False

    # Handle findMistake (step index matching)
    if question_type == "findMistake" or grading_rule_key == "grader_v1_find_mistake":
        try:
            u_idx = int(user_val)
            if isinstance(authoritative_payload, (int, float)):
                return u_idx == int(authoritative_payload)
            elif isinstance(authoritative_payload, str) and authoritative_payload.isdigit():
                return u_idx == int(authoritative_payload)
            elif isinstance(authoritative_payload, (list, tuple)):
                return any(u_idx == int(x) for x in authoritative_payload if str(x).isdigit())
        except (ValueError, TypeError):
            pass
        return False

    # Handle true/false
    if question_type == "tf" or grading_rule_key == "grader_v1_tf":
        u_str = str(user_val).strip().lower()
        if isinstance(authoritative_payload, bool):
            a_str = "true" if authoritative_payload else "false"
        else:
            a_str = str(authoritative_payload).strip().lower()
        # Normalization
        if u_str in ("true", "t", "1"):
            u_str = "true"
        elif u_str in ("false", "f", "0"):
            u_str = "false"
        if a_str in ("true", "t", "1"):
            a_str = "true"
        elif a_str in ("false", "f", "0"):
            a_str = "false"
        return u_str == a_str

    # Handle radio button
    if question_type == "radio" or grading_rule_key == "grader_v1_radio":
        u_str = str(user_val).strip().upper()
        if isinstance(authoritative_payload, (list, tuple)):
            acc_list = [str(x).strip().upper() for x in authoritative_payload]
            return u_str in acc_list
        return u_str == str(authoritative_payload).strip().upper()

    # Handle fill-in-the-blank (multi-tier pipeline)
    # Check if authoritative_payload is a multi-blank list (e.g. ['2/6', '2/6', '3/6,1/2'])
    if isinstance(authoritative_payload, (list, tuple)) and len(authoritative_payload) > 1:
        u_list = None
        if isinstance(user_val, (list, tuple)):
            u_list = list(user_val)
        elif isinstance(user_val, str):
            st = user_val.strip()
            if st.startswith("[") and st.endswith("]"):
                try:
                    import json
                    parsed = json.loads(st)
                    if isinstance(parsed, list):
                        u_list = parsed
                except Exception:
                    pass
            elif "|||" in st:
                u_list = [p.strip() for p in st.split("|||")]

        if u_list is not None and len(u_list) == len(authoritative_payload):
            return all(
                check_single_blank_match(u_list[i], authoritative_payload[i])
                for i in range(len(authoritative_payload))
            )

    return check_single_blank_match(user_val, authoritative_payload)
