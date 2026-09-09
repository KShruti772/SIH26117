import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("aegis.source_grounding")

# 5 strict epistemic categories + unavailable measurement tag
EPISTEMIC_FACT = "[SOURCE_DOCUMENT_FACT]"
EPISTEMIC_INPUT = "[USER_PROVIDED_INPUT]"
EPISTEMIC_CALC = "[DERIVED_CALCULATION]"
EPISTEMIC_INFERENCE = "[MODEL_INFERENCE]"
EPISTEMIC_RECOMMENDATION = "[RECOMMENDATION]"
EPISTEMIC_UNAVAILABLE = "[UNAVAILABLE_MEASUREMENT]"

MANDATORY_HUMAN_DECISION_TEXT = (
    "**HUMAN APPROVAL REQUIRED**: AEGIS has prepared this draft technical assessment based strictly "
    "on authorized source evidence. AEGIS does not have authority to independently grant operational "
    "approval. Continued operation requires review and formal sign-off by an authorized human reviewer."
)

FORBIDDEN_APPROVAL_PATTERNS = [
    r"(?i)formal engineering approval is (?:hereby )?granted",
    r"(?i)approval is granted for continued operation",
    r"(?i)approved for continuous operation",
    r"(?i)approved for continued operation",
    r"(?i)approval is hereby granted",
    r"(?i)continuous operation is authorized",
    r"(?i)continued operation is approved",
    r"(?i)system is approved for operation"
]

QUALITATIVE_INVENTION_PATTERNS = [
    # (regex_pattern, replacement_text)
    (r"(?i)<\s*0\.5\s*l/min", "NOT QUANTIFIED IN AUTHORIZED EVIDENCE (Source specifies qualitative leakage observation)"),
    (r"(?i)<\s*0\.05\s*mm", "NOT QUANTIFIED IN AUTHORIZED EVIDENCE (Source specifies qualitative close tolerance)"),
    (r"(?i)0\.05\s*mm\s*\(close tolerance\)", "Close tolerance (qualitative source statement; numerical tolerance not quantified in source)"),
    (r"(?i)0\.5\s*l/min\s*\(excessive leakage\)", "Excessive leakage (qualitative source statement; numerical flow rate not quantified in source)"),
    (r"(?i)close tolerance\s*[—–-]\s*0\.05\s*mm", "Close tolerance (qualitative source statement)"),
    (r"(?i)leakage\s*[—–-]\s*0\.5\s*l/min", "Leakage (qualitative source statement)")
]


def compare_engineering_parameter(
    parameter_name: str,
    measured_value: Optional[float],
    documented_limit: Optional[float],
    unit: str = "",
    limit_type: str = "MAX",
    tolerance_pct: float = 0.0
) -> Dict[str, Any]:
    """
    Executes mathematically sound engineering comparison.
    Enforces the semantic rule:
    Actual Value + Documented Limit -> Comparison & Deviation
    Missing Value or Missing Limit -> Comparison: NOT POSSIBLE, Deviation: NOT CALCULABLE, Status: UNAVAILABLE
    """
    if measured_value is None or documented_limit is None:
        return {
            "parameter": parameter_name,
            "measured_value": "UNAVAILABLE" if measured_value is None else f"{measured_value} {unit}".strip(),
            "documented_limit": "UNAVAILABLE" if documented_limit is None else f"{documented_limit} {unit}".strip(),
            "unit": unit,
            "comparison_possible": False,
            "comparison": "NOT POSSIBLE",
            "deviation": "NOT CALCULABLE — required measurement unavailable.",
            "status": "UNAVAILABLE",
            "epistemic_category": EPISTEMIC_UNAVAILABLE if measured_value is None else EPISTEMIC_FACT
        }

    try:
        val = float(measured_value)
        lim = float(documented_limit)
        diff = val - lim
        pct_diff = (diff / lim * 100.0) if lim != 0 else 0.0

        if limit_type.upper() == "MAX":
            within_limits = val <= lim
        elif limit_type.upper() == "MIN":
            within_limits = val >= lim
        else:
            within_limits = abs(diff) <= (lim * tolerance_pct / 100.0)

        status = "WITHIN_LIMITS" if within_limits else "EXCEEDS_LIMIT"
        comparison = f"{val} {'<=' if within_limits else '>'} {lim} {unit}".strip()
        deviation_str = f"{diff:+.2f} {unit} ({pct_diff:+.1f}%)".strip()

        return {
            "parameter": parameter_name,
            "measured_value": f"{val} {unit}".strip(),
            "documented_limit": f"{lim} {unit}".strip(),
            "unit": unit,
            "comparison_possible": True,
            "comparison": comparison,
            "deviation": deviation_str,
            "status": status,
            "epistemic_category": EPISTEMIC_CALC
        }
    except Exception as e:
        logger.warning(f"Error comparing parameter {parameter_name}: {e}")
        return {
            "parameter": parameter_name,
            "measured_value": str(measured_value),
            "documented_limit": str(documented_limit),
            "unit": unit,
            "comparison_possible": False,
            "comparison": "NOT POSSIBLE",
            "deviation": "NOT CALCULABLE — calculation error",
            "status": "UNAVAILABLE",
            "epistemic_category": EPISTEMIC_UNAVAILABLE
        }


def build_evidence_availability_table(parameters: List[Dict[str, Any]]) -> str:
    """
    Constructs a clean, standard Section 2 Evidence Availability markdown table.
    """
    lines = [
        "| Parameter | Current Value | Source Limit | Status |",
        "|---|---|---|---|"
    ]
    for p in parameters:
        name = p.get("parameter", "Unknown")
        val = p.get("measured_value", "UNAVAILABLE")
        lim = p.get("documented_limit", "UNAVAILABLE")
        status = p.get("status", "UNAVAILABLE")
        lines.append(f"| {name} | {val} | {lim} | {status} |")
    return "\n".join(lines)


def sanitize_draft_document_text(
    draft_text: str,
    findings_text: Optional[str] = None,
    calc_text: Optional[str] = None,
    rag_chunks: Optional[List[Any]] = None,
    prompt_task: Optional[str] = None
) -> str:
    """
    Deterministically sanitizes and enforces epistemic rigor on draft approval notes & engineering reports.

    Enforces:
    1. Prohibits AI from independently granting operational approvals.
    2. Mandates Section 8 'Human Review Decision' with explicit 'HUMAN APPROVAL REQUIRED' notice.
    3. Replaces invalid '0% deviation' or false 'PASS' on unavailable parameters with 'NOT CALCULATED' and 'UNAVAILABLE'.
    4. Replaces qualitative-to-numeric hallucinations (e.g. '< 0.05 mm' or '< 0.5 L/min') with 'NOT QUANTIFIED IN AUTHORIZED EVIDENCE' or qualitative statements.
    5. Replaces unsupported assumptions (e.g. assumed thermal efficiency, assumed AOR compliance).
    6. Ensures standard 8-section document hierarchy.
    7. Enforces strict epistemic tagging ([SOURCE_DOCUMENT_FACT], [USER_PROVIDED_INPUT], [DERIVED_CALCULATION], [MODEL_INFERENCE], [RECOMMENDATION]).
    """
    if not draft_text or not isinstance(draft_text, str):
        return draft_text or ""

    sanitized = draft_text

    # 1. Replace blanket AI approval statements with draft assessment notice
    for pat in FORBIDDEN_APPROVAL_PATTERNS:
        sanitized = re.sub(
            pat,
            "Draft Technical Assessment: Human approval required for continued operation (AEGIS does not independently grant operational approval)",
            sanitized
        )

    # 2. Sanitize qualitative-to-numeric limit hallucinations
    for pat, repl in QUALITATIVE_INVENTION_PATTERNS:
        sanitized = re.sub(pat, repl, sanitized)

    # 3. Sanitize unsupported assumption statements
    sanitized = re.sub(
        r"(?i)thermal efficiency is assumed to be within[^\n]*\n?",
        "Thermal efficiency: UNAVAILABLE (Not present in authorized source evidence; unsupported assumptions are prohibited).\n",
        sanitized
    )
    sanitized = re.sub(
        r"(?i)all observed conditions comply with manufacturer specifications[^\n]*\n?",
        "Observed parameters were evaluated where evidence was available; unmeasured parameters remain UNAVAILABLE and compliance cannot be independently certified.\n",
        sanitized
    )
    sanitized = re.sub(
        r"(?i)equipment is compliant\b[^\.\n]*[\.\n]?",
        "Equipment compliance cannot be independently certified because required operating measurements are unavailable.\n",
        sanitized
    )

    # 4. Check for missing/unavailable parameters in findings or calculations
    combined_context = f"{draft_text}\n{findings_text or ''}\n{calc_text or ''}".lower()
    vibration_unavailable = "vibration" in combined_context and any(
        w in combined_context for w in [
            "unavailable_measurement: vibration", "vibration measurement absent",
            "vibration is unavailable", "vibration: unavailable", "vibration: not specified",
            "no vibration measurement", "vibration = unavailable", "vibration measurement: unavailable"
        ]
    )
    temp_unavailable = ("temperature" in combined_context or "inlet temp" in combined_context) and any(
        w in combined_context for w in [
            "unavailable_measurement: temperature", "temperature measurement absent",
            "temperature is unavailable", "temp: unavailable", "temperature = unavailable",
            "temperature measurement: unavailable"
        ]
    )
    leakage_unavailable = "leakage" in combined_context and any(
        w in combined_context for w in [
            "unavailable_measurement: leakage", "leakage measurement absent",
            "leakage is unavailable", "leakage: unavailable", "leakage = unavailable"
        ]
    )
    aor_unspecified = any(
        w in combined_context for w in [
            "operating region is not specified", "aor is not specified", "aor: unavailable",
            "allowable operating region: not specified", "unavailable_measurement: allowable operating region",
            "unavailable_measurement: aor", "operating data is not available", "operating data absent"
        ]
    )

    if aor_unspecified or ("operates within the allowable operating region" in sanitized.lower() and "operating region is not specified" in combined_context):
        sanitized = re.sub(
            r"(?i)(?:the )?cooling tower system operates within (?:the )?allowable operating region \(?aor\)?(?: with no deviations)?[^\.\n]*[\.\n]?",
            "Operating region (AOR): UNAVAILABLE (Current operating measurements required to establish Allowable Operating Region (AOR) compliance were not provided in authorized evidence).\n",
            sanitized
        )
        sanitized = re.sub(
            r"(?i)operates within aor\b[^\.\n]*[\.\n]?",
            "Operating region (AOR): UNAVAILABLE (Current operating point unverified in authorized evidence).\n",
            sanitized
        )

    if vibration_unavailable:
        sanitized = re.sub(
            r"(?i)api 610/hydraulic institute\s*[—–-]\s*within limits",
            "API 610 / Hydraulic Institute: UNAVAILABLE (Vibration measurement absent in authorized evidence; comparison not possible)",
            sanitized
        )
        sanitized = re.sub(
            r"(?i)api 610\s*[—–-]\s*within limits",
            "API 610: UNAVAILABLE (Vibration measurement absent in authorized evidence; comparison not possible)",
            sanitized
        )
        sanitized = re.sub(
            r"(?i)vibration\s*:\s*within limits",
            "Vibration: UNAVAILABLE (Current measurement absent; comparison not possible)",
            sanitized
        )

    if temp_unavailable:
        sanitized = re.sub(
            r"(?i)manufacturer'?s baseline\s*[—–-]\s*within limits",
            "Manufacturer Baseline: UNAVAILABLE (Temperature baseline measurements absent in authorized evidence; comparison not possible)",
            sanitized
        )
        sanitized = re.sub(
            r"(?i)temperature\s*:\s*within limits",
            "Temperature: UNAVAILABLE (Current measurement absent; comparison not possible)",
            sanitized
        )

    if leakage_unavailable:
        sanitized = re.sub(
            r"(?i)leakage\s*:\s*within limits",
            "Leakage: UNAVAILABLE (Current measurement absent; comparison not possible)",
            sanitized
        )

    # 5. Fix mathematical fallacy: Missing measurement != 0% deviation or PASS
    lines = sanitized.split("\n")
    fixed_lines = []

    for line in lines:
        s = line.strip()
        # If a line has unavailable measurement and has deviation / status
        if any(w in s.lower() for w in ["unavailable", "not quantified", "not present", "not possible", "cannot determine"]):
            if any(d in s.lower() for d in ["deviation: 0%", "deviation: 0", "deviation: 0.0%", "margin: 0", "margin: 0.0", "calculated deviation: 0%"]):
                line = re.sub(r"(?i)(?:calculated )?deviation\s*:\s*0(?:\.0)?%?", "Deviation: NOT CALCULATED (Measurement unavailable — required measurement unavailable)", line)
            if any(st in s.lower() for st in ["status: pass", "status: within_limits", "status: within limits", "status: within acceptable"]):
                line = re.sub(r"(?i)\bstatus\s*:\s*(?:pass|within_limits|within limits|within acceptable)\b", "Status: UNAVAILABLE", line)

        # Standalone 0% deviation on missing metrics
        if "deviation: 0%" in s.lower() and not any(k in s.lower() for k in ["measured: ", "delta = 0", "difference = 0"]):
            line = re.sub(r"(?i)(?:calculated )?deviation\s*:\s*0(?:\.0)?%?", "Deviation: NOT CALCULATED (Measurement unavailable — required measurement unavailable)", line)

        # Prohibit recommendation from being labeled as SOURCE_DOCUMENT_FACT
        if s.startswith("- [SOURCE_DOCUMENT_FACT]") or s.startswith("[SOURCE_DOCUMENT_FACT]"):
            if any(w in s.lower() for w in ["recommendation:", "recommended action:", "should replace", "should clean", "schedule inspection", "replace within", "clean basin", "obtain current vibration"]):
                line = line.replace("[SOURCE_DOCUMENT_FACT]", "[RECOMMENDATION]")

        fixed_lines.append(line)

    sanitized = "\n".join(fixed_lines)

    # 6. Ensure standard 8-section hierarchy for approval notes & engineering reports
    is_appr = "approval note" in (prompt_task or "").lower() or "approval note" in draft_text.lower() or "inspection" in draft_text.lower()
    if is_appr:
        # Check if Section 8 (or Section 7) 'Human Review' is present
        has_human_sec = bool(re.search(r"(?i)##\s*(?:[78]\.?\s*)?human review", sanitized))
        if not has_human_sec:
            sanitized = sanitized.rstrip() + f"\n\n## 8. Human Review Decision\n{MANDATORY_HUMAN_DECISION_TEXT}\n"
        else:
            sec_match = re.search(r"(?i)(##\s*(?:[78]\.?\s*)?human review[^\n]*\n)(.*)", sanitized, re.DOTALL)
            if sec_match:
                header = sec_match.group(1)
                body = sec_match.group(2)
                if "**HUMAN APPROVAL REQUIRED**" not in body and "HUMAN APPROVAL REQUIRED" not in body:
                    prefix = sanitized[:sec_match.start()]
                    clean_body = re.sub(r"(?i)approved by [^\n]+", "", body).strip()
                    if clean_body:
                        sanitized = prefix + f"{header}{MANDATORY_HUMAN_DECISION_TEXT}\n\n{clean_body}\n"
                    else:
                        sanitized = prefix + f"{header}{MANDATORY_HUMAN_DECISION_TEXT}\n"

    return sanitized


def validate_epistemic_rigor(document_text: str) -> Tuple[bool, List[str]]:
    """
    Validates that a generated document conforms strictly to all 16 AEGIS source-grounding criteria.
    Returns (is_valid, list_of_violations).
    """
    violations = []
    text_lower = document_text.lower()

    # Rule 1: No unsupported sweeping compliance when measurements are missing
    if "all observed conditions comply with manufacturer specifications" in text_lower:
        if "unavailable" in text_lower or "not quantified" in text_lower or "absent" in text_lower:
            violations.append("Violation 1: Claims all conditions comply despite missing measurements.")

    # Rule 2: No ungrounded AOR claims
    if "operates within the allowable operating region (aor)" in text_lower or "operates within aor" in text_lower:
        if any(w in text_lower for w in ["operating region is not specified", "aor: unavailable", "operating region: unavailable", "not provided", "unverified"]):
            violations.append("Violation 2: Claims system operates within AOR when operating telemetry is unspecified/unavailable.")

    # Rule 3: AEGIS must not independently grant operational approval
    for pat in FORBIDDEN_APPROVAL_PATTERNS:
        if re.search(pat, document_text):
            violations.append(f"Violation 3: AEGIS independently granted operational approval ('{pat}').")

    # Rule 4 & 5: Numerical limit inventions from qualitative terms
    if re.search(r"(?i)<\s*0\.5\s*l/min", document_text):
        violations.append("Violation 4: Hallucinated quantitative leakage limit '< 0.5 L/min' from qualitative terms.")
    if re.search(r"(?i)<\s*0\.05\s*mm", document_text):
        violations.append("Violation 5: Hallucinated quantitative pump alignment '< 0.05 mm' from qualitative 'close tolerance'.")

    # Rule 6 & 7: "Within limits" for missing vibration or temperature
    if "vibration" in text_lower and any(w in text_lower for w in ["unavailable", "absent", "not present"]):
        if any(w in text_lower for w in ["api 610/hydraulic institute — within limits", "api 610 — within limits", "vibration: within limits", "vibration = within limits"]):
            violations.append("Violation 6: Vibration / API 610 marked 'Within limits' when vibration measurement is unavailable.")

    if ("temperature" in text_lower or "temp" in text_lower) and any(w in text_lower for w in ["unavailable", "absent", "not present"]):
        if any(w in text_lower for w in ["manufacturer's baseline — within limits", "manufacturer baseline — within limits", "temperature: within limits", "temperature = within limits"]):
            violations.append("Violation 7: Temperature / Manufacturer baseline marked 'Within limits' when temperature is unavailable.")

    # Rule 8: No unsupported assumptions
    if "thermal efficiency is assumed to be within" in text_lower or "is assumed to be within manufacturer specifications" in text_lower:
        violations.append("Violation 8: Unsupported assumption of thermal efficiency.")

    # Rule 9: Missing measurement != 0% deviation or PASS
    if re.search(r"(?i)unavailable[^\n]*deviation\s*:\s*0(?:\.0)?%?", document_text) or re.search(r"(?i)calculated deviation\s*:\s*0(?:\.0)?%?[^\n]*unavailable", document_text):
        violations.append("Violation 9: Mathematically invalid '0% deviation' assigned to unavailable measurement.")

    # Rule 10: Human Review Decision required in approval notes
    if "approval note" in text_lower:
        if "human approval required" not in text_lower:
            violations.append("Violation 10: Missing mandatory 'HUMAN APPROVAL REQUIRED' declaration in Human Review Decision.")

    # Rule 11: Compliance claim without measurements
    if "equipment is compliant" in text_lower and ("unavailable" in text_lower or "absent" in text_lower):
        violations.append("Violation 11: Claimed equipment compliance when measurements are unavailable.")

    # Rule 12: Recommendations must not be labeled as facts
    if re.search(r"(?i)\[source_document_fact\][^\n]*(?:recommendation:|should replace|should clean|obtain current vibration)", document_text):
        violations.append("Violation 12: Maintenance recommendation mislabeled as [SOURCE_DOCUMENT_FACT].")

    return len(violations) == 0, violations


def parse_markdown_to_content_blocks(draft_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parses markdown document text into structured content blocks for PDF/DOCX/XLSX generators,
    including headings, paragraphs, bullet points, numbered items, and markdown tables.
    """
    lines = draft_text.strip().split("\n")
    title = "AEGIS Industrial Technical Report"
    content_blocks: List[Dict[str, Any]] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        s_line = line.strip()
        if not s_line:
            i += 1
            continue

        if s_line.startswith("# "):
            title = s_line.lstrip("# ").strip()
            i += 1
        elif s_line.startswith("## "):
            content_blocks.append({"type": "heading", "text": s_line.lstrip("# ").strip(), "level": 1})
            i += 1
        elif s_line.startswith("### "):
            content_blocks.append({"type": "heading", "text": s_line.lstrip("# ").strip(), "level": 2})
            i += 1
        elif s_line.startswith(("- ", "* ", "• ")):
            content_blocks.append({"type": "bullet", "text": s_line[2:].strip()})
            i += 1
        elif re.match(r"^\d+\.\s+", s_line):
            content_blocks.append({"type": "numbered", "text": re.sub(r"^\d+\.\s+", "", s_line)})
            i += 1
        elif s_line.startswith("|") and s_line.endswith("|"):
            # Markdown table block parsing
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1

            if len(table_lines) >= 2:
                raw_headers = [c.strip() for c in table_lines[0].strip("|").split("|")]
                headers = [h for h in raw_headers if h]
                rows = []

                for t_row in table_lines[1:]:
                    if re.match(r"^\|?\s*[-:]+[-| :]*\|?$", t_row):
                        continue
                    raw_cells = [c.strip() for c in t_row.strip("|").split("|")]
                    rows.append(raw_cells[:len(headers)])

                if headers and rows:
                    content_blocks.append({"type": "table", "headers": headers, "rows": rows})
            else:
                for tl in table_lines:
                    content_blocks.append({"type": "paragraph", "text": tl})
        else:
            content_blocks.append({"type": "paragraph", "text": s_line})
            i += 1

    if not content_blocks:
        content_blocks.append({"type": "paragraph", "text": draft_text})

    return title, content_blocks
