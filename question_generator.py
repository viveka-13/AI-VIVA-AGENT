"""
question_generator.py
---------------------
Uses the local Ollama LLM (llama3.1:8b) to generate a bank of questions
and correct answers from extracted document text.

Generated questions are saved to:
  faculty_data/subject_questions/<subject_slug>.json

Format (same as questions.json so existing pipeline works unchanged):
[
  {
    "experiment": "<subject_slug>",
    "question_number": 1,
    "question": "...",
    "answer": "..."
  },
  ...
]
"""
import json
import os
import re
import ollama


FACULTY_DATA_DIR = os.path.join(os.path.dirname(__file__), "faculty_data")
SUBJECT_QUESTIONS_DIR = os.path.join(FACULTY_DATA_DIR, "subject_questions")


def slugify(name: str) -> str:
    """Convert a subject name to a safe filename key."""
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower())


def get_subject_questions_path(subject_name: str) -> str:
    os.makedirs(SUBJECT_QUESTIONS_DIR, exist_ok=True)
    return os.path.join(SUBJECT_QUESTIONS_DIR, f"{slugify(subject_name)}.json")


def generate_questions_from_text(text: str, subject_name: str, num_questions: int = 10) -> list:
    """
    Calls Ollama to generate `num_questions` Q&A pairs from the given text.
    Returns a list of dicts: [{experiment, question_number, question, answer}, ...]
    """
    slug = slugify(subject_name)

    # Truncate very long text to avoid overwhelming the context window and system memory
    max_chars = 3000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[...text truncated for context limit...]"

    prompt = (
        f"You are an expert academic question generator for the subject: '{subject_name}'.\n\n"
        f"Based ONLY on the following study material, generate exactly {num_questions} "
        f"unique exam/viva questions with their correct answers.\n\n"
        "IMPORTANT RULES:\n"
        "- Questions must be based strictly on the provided material.\n"
        "- Each answer must be concise (1–3 sentences) but complete.\n"
        "- Questions should vary in type: factual, conceptual, and applied.\n"
        "- Return ONLY a valid JSON array with NO extra text before or after.\n"
        "- Each item in the array must have exactly two keys: \"question\" and \"answer\".\n\n"
        "REQUIRED OUTPUT FORMAT (return ONLY this JSON, nothing else):\n"
        "[\n"
        "  {\"question\": \"...\", \"answer\": \"...\"},\n"
        "  {\"question\": \"...\", \"answer\": \"...\"}\n"
        "]\n\n"
        f"STUDY MATERIAL:\n{text}\n\n"
        "Now generate the JSON array:"
    )

    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 2048}  # Restrict context window memory to prevent OOM
        )
        raw = response["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Ollama call failed: {e}")

    # Robust JSON extraction
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    start_idx = raw.find('[')
    if start_idx != -1:
        raw_json = raw[start_idx:]
        if not raw_json.rstrip().endswith(']'):
            last_brace = raw_json.rfind('}')
            if last_brace != -1:
                raw_json = raw_json[:last_brace+1] + ']'
    else:
        raw_json = raw

    qa_pairs = []
    try:
        qa_pairs = json.loads(raw_json)
        # Ensure it's a list
        if isinstance(qa_pairs, dict):
            qa_pairs = [qa_pairs]
    except json.JSONDecodeError as e:
        # Fallback: brutal regex extraction for cut-off or malformed json
        matches = re.finditer(r'"question"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"answer"\s*:\s*"((?:\\.|[^"\\])*)"', raw, re.IGNORECASE)
        for m in matches:
            qa_pairs.append({
                "question": m.group(1).replace('\\"', '"').replace('\\n', '\n'),
                "answer": m.group(2).replace('\\"', '"').replace('\\n', '\n')
            })
        
        if not qa_pairs:
            raise ValueError(f"Failed to parse LLM JSON response. Error: {e}\nRaw: {raw[:500]}")

    # Validate and format
    formatted = []
    for i, item in enumerate(qa_pairs):
        if "question" not in item or "answer" not in item:
            continue
        formatted.append({
            "experiment": slug,
            "question_number": i + 1,
            "question": item["question"].strip(),
            "answer": item["answer"].strip()
        })

    if len(formatted) == 0:
        raise ValueError("LLM returned an empty or invalid question list.")

    return formatted


def save_questions(questions: list, subject_name: str) -> str:
    """
    Saves (or appends to) the subject question bank JSON.
    Returns the filepath written to.
    """
    path = get_subject_questions_path(subject_name)

    # Load existing questions if file already exists (accumulate over multiple uploads)
    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    # Renumber starting after existing
    start_num = len(existing) + 1
    for i, q in enumerate(questions):
        q["question_number"] = start_num + i

    merged = existing + questions

    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4, ensure_ascii=False)

    return path


def generate_and_save(text: str, subject_name: str, num_questions: int = 10) -> dict:
    """
    Full pipeline: generate questions from text and save them.
    Returns summary dict: {subject, questions_generated, total_in_bank, filepath}
    """
    questions = generate_questions_from_text(text, subject_name, num_questions)
    filepath = save_questions(questions, subject_name)

    # Count total in bank after save
    with open(filepath, "r", encoding="utf-8") as f:
        total = len(json.load(f))

    return {
        "subject": subject_name,
        "questions_generated": len(questions),
        "total_in_bank": total,
        "filepath": filepath
    }


def load_subject_questions(subject_name: str) -> list:
    """
    Load all questions for a given subject from the faculty question bank.
    Returns empty list if subject not found.
    """
    path = get_subject_questions_path(subject_name)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
