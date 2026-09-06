import json
import re
import ollama
import sys
import os

SESSION_FILE = os.path.join("combined_output.json")
QUESTION_BANK_FILE = os.path.join("combined_output.json")
OUTPUT_FILE = os.path.join("output.txt")
STRUCTURED_OUTPUT_FILE = os.path.join("output_structured.json")


# =============================================
# STRUCTURED EVALUATION PROMPT
# =============================================

STRUCTURED_EVAL_PROMPT = """You are a strict validation agent. Compare the user's answer to the correct answer and return your evaluation as valid JSON ONLY.

You MUST return ONLY a JSON object in this exact format (no extra text, no markdown):
{{"verdict": "correct" or "partially correct" or "incorrect", "matched_concepts": ["concept1", "concept2"], "missing_concepts": ["concept3"], "reasoning": "Brief 1-sentence explanation"}}

Rules for verdict:
- "correct" if the user's answer fully matches or covers the key terms in the correct answer.
- "partially correct" if the user's answer is somewhat related but incomplete.
- "incorrect" if the user's answer is unrelated, wrong, random, or just greetings/single characters.

Rules for concepts:
- matched_concepts: List the key terms/concepts from the correct answer that ARE present in the user's answer.
- missing_concepts: List the key terms/concepts from the correct answer that are MISSING from the user's answer.
- If the answer is fully correct, missing_concepts should be an empty list.
- If the answer is fully incorrect, matched_concepts should be an empty list.

Question: {question}
User Answer: {user_answer}
Correct Answer: {correct_answer}

Return ONLY the JSON object, nothing else."""


def validate_with_llm(question, user_answer, correct_answer):
    """
    Call Ollama with the structured evaluation prompt.
    Returns a dict with verdict, matched_concepts, missing_concepts, reasoning.
    Falls back gracefully on parse failure.
    """
    prompt = STRUCTURED_EVAL_PROMPT.format(
        question=question,
        user_answer=user_answer,
        correct_answer=correct_answer
    )

    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response["message"]["content"].strip()
        return _parse_structured_response(raw)
    except Exception as e:
        print(f"[LLM_CHECK] Ollama call failed: {e}")
        return _fallback_result()


def _parse_structured_response(raw_text):
    """
    Extract and parse JSON from the LLM response.
    Handles markdown code blocks and messy formatting.
    """
    # Strip markdown code blocks if present
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
    if json_match:
        raw_text = json_match.group(1)

    # Try to find any JSON object
    brace_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if brace_match:
        raw_text = brace_match.group(0)

    try:
        data = json.loads(raw_text)
        # Validate expected keys
        verdict = data.get("verdict", "incorrect").lower().strip()
        # Normalize verdict
        if "partially" in verdict:
            verdict = "partially correct"
        elif "incorrect" in verdict:
            verdict = "incorrect"
        elif "correct" in verdict:
            verdict = "correct"
        else:
            verdict = "incorrect"

        return {
            "verdict": verdict,
            "matched_concepts": data.get("matched_concepts", []),
            "missing_concepts": data.get("missing_concepts", []),
            "reasoning": data.get("reasoning", "")
        }
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[LLM_CHECK] JSON parse failed: {e}")
        print(f"[LLM_CHECK] Raw: {raw_text[:300]}")
        # Try to extract verdict from raw text as fallback
        return _extract_verdict_fallback(raw_text)


def _extract_verdict_fallback(raw_text):
    """If JSON parsing fails, try to extract just the verdict from plain text."""
    lower = raw_text.lower()
    if "partially correct" in lower:
        verdict = "partially correct"
    elif "incorrect" in lower:
        verdict = "incorrect"
    elif "correct" in lower:
        verdict = "correct"
    else:
        verdict = "incorrect"

    return {
        "verdict": verdict,
        "matched_concepts": [],
        "missing_concepts": [],
        "reasoning": "(Structured extraction failed - verdict only)"
    }


def _fallback_result():
    """Complete fallback when LLM call itself fails."""
    return {
        "verdict": "incorrect",
        "matched_concepts": [],
        "missing_concepts": [],
        "reasoning": "(LLM evaluation failed)"
    }


def load_inputs():
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        session_data = json.load(f)
    with open(QUESTION_BANK_FILE, "r", encoding="utf-8") as f:
        question_bank = json.load(f)
    return session_data, question_bank


def find_correct_answer(question_text, question_bank):
    for item in question_bank:
        if item["question"].strip().lower() == question_text.strip().lower():
            return item["correct_answer"]
    return None


def main():
    try:
        session_data, question_bank = load_inputs()
    except Exception as e:
        print(f"[ERROR] Error loading input files: {e}")
        return

    result_lines = []
    structured_results = []

    for i, entry in enumerate(session_data):
        question = entry["question"]
        user_answer = entry["user_answer"]
        correct_answer = find_correct_answer(question, question_bank)

        if not correct_answer:
            result_lines.append(f"{i+1}. [ERROR] Question not found in viva.json: {question}")
            structured_results.append({
                "question_number": i + 1,
                "question": question,
                "user_answer": user_answer,
                "correct_answer": "",
                "verdict": "incorrect",
                "matched_concepts": [],
                "missing_concepts": [],
                "reasoning": "Question not found in bank"
            })
            continue

        result = validate_with_llm(question, user_answer, correct_answer)

        # Build traditional output line for backward compatibility
        verdict_text = f"Answer is {result['verdict']}."
        result_lines.append(f"{i+1}. {verdict_text}")

        # Build structured result
        structured_results.append({
            "question_number": i + 1,
            "question": question,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "verdict": result["verdict"],
            "matched_concepts": result["matched_concepts"],
            "missing_concepts": result["missing_concepts"],
            "reasoning": result["reasoning"]
        })

    # Write traditional output (backward compatibility)
    full_output = "\n\n".join(result_lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(full_output)

    # Write structured JSON output
    with open(STRUCTURED_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(structured_results, f, indent=2, ensure_ascii=False)

    print("[SUCCESS] Validation complete. Output written to output.txt")


if __name__ == "__main__":
    main()
    from evaluation import run_evaluation
    run_evaluation()
