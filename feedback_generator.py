"""
feedback_generator.py
---------------------
Generates personalized post-session study feedback using Ollama (llama3.2).
Called once per completed session, aggregating all missing concepts
from the explainable evaluation to produce actionable study recommendations.
"""
import json
import ollama


FEEDBACK_PROMPT_TEMPLATE = """You are an academic study advisor. A student just completed a viva (oral exam) on the subject "{subject}".

Below is a JSON list of concepts/keywords that were MISSING from the student's answers across all questions. These represent knowledge gaps:

{missing_concepts_json}

Based on these gaps, generate a short, constructive study feedback summary in the following JSON format ONLY (no extra text before or after):

{{
  "weak_areas": ["area1", "area2", "area3"],
  "explanation": "A 2-3 sentence plain-language explanation of why these areas matter and how they connect to the subject.",
  "study_recommendations": "A 2-3 sentence suggestion of what to review next, referencing specific topics from the gaps."
}}

Rules:
- Identify the 2-4 weakest topic areas by grouping related missing concepts.
- Keep your explanation encouraging and constructive, not punitive.
- Be specific in recommendations — name the topics, not just "study more".
- Return ONLY valid JSON, nothing else.
"""


def generate_session_feedback(subject, all_missing_concepts):
    """
    Generate personalized feedback for a completed viva session.

    Args:
        subject: The subject/experiment name
        all_missing_concepts: List of lists — missing concepts per question
                              e.g. [["concept1", "concept2"], ["concept3"], ...]

    Returns:
        dict with keys: weak_areas, explanation, study_recommendations
        Falls back to a generic message if LLM fails.
    """
    # Flatten and deduplicate
    flat_missing = []
    for concepts in all_missing_concepts:
        if isinstance(concepts, list):
            flat_missing.extend(concepts)
        elif isinstance(concepts, str):
            flat_missing.append(concepts)

    # Remove duplicates while preserving order
    seen = set()
    unique_missing = []
    for c in flat_missing:
        c_lower = c.strip().lower()
        if c_lower and c_lower not in seen:
            seen.add(c_lower)
            unique_missing.append(c.strip())

    if not unique_missing:
        return {
            "weak_areas": [],
            "explanation": "Great job! You covered all the key concepts in your answers.",
            "study_recommendations": "Keep up the good work. Consider reviewing edge cases and advanced topics to deepen your understanding."
        }

    prompt = FEEDBACK_PROMPT_TEMPLATE.format(
        subject=subject,
        missing_concepts_json=json.dumps(unique_missing, indent=2)
    )

    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response["message"]["content"].strip()
        return _parse_feedback_json(raw)
    except Exception as e:
        print(f"[FEEDBACK] LLM call failed: {e}")
        return _fallback_feedback(unique_missing)


def _parse_feedback_json(raw_text):
    """
    Extract and parse JSON from the LLM response.
    Handles cases where the model wraps JSON in markdown code blocks.
    """
    import re

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
    if json_match:
        raw_text = json_match.group(1)

    # Try to find a JSON object directly
    brace_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if brace_match:
        raw_text = brace_match.group(0)

    try:
        data = json.loads(raw_text)
        return {
            "weak_areas": data.get("weak_areas", []),
            "explanation": data.get("explanation", ""),
            "study_recommendations": data.get("study_recommendations", "")
        }
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[FEEDBACK] JSON parse failed: {e}")
        print(f"[FEEDBACK] Raw text was: {raw_text[:300]}")
        return _fallback_feedback([])


def _fallback_feedback(missing_concepts):
    """Generate a basic fallback feedback when LLM fails."""
    if missing_concepts:
        topics = ", ".join(missing_concepts[:5])
        return {
            "weak_areas": missing_concepts[:4],
            "explanation": f"Based on your answers, you may want to strengthen your understanding of: {topics}.",
            "study_recommendations": "Review these topics in your course material and try practice questions to build confidence."
        }
    return {
        "weak_areas": [],
        "explanation": "Your session has been evaluated.",
        "study_recommendations": "Review the source material for deeper understanding."
    }
