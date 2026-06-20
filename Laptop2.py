import json
import random
import os

# Faculty subject questions directory
SUBJECT_QUESTIONS_DIR = os.path.join(os.path.dirname(__file__), "faculty_data", "subject_questions")


def slugify(name: str) -> str:
    """Convert a subject name to a safe filename key (mirrors question_generator.py)."""
    import re
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower())


def generate_questions(experiment_number, filepath="questions.json", num_questions=5):
    """
    Generate questions for a given subject or experiment number.

    Priority:
    1. If a faculty-generated question bank exists for this subject/experiment, use it.
    2. Otherwise fall back to the static questions.json (original behaviour, unchanged).
    """

    # --- 1. Try faculty subject question bank first ---
    slug = slugify(str(experiment_number))
    subject_path = os.path.join(SUBJECT_QUESTIONS_DIR, f"{slug}.json")

    if os.path.exists(subject_path):
        with open(subject_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if len(data) < num_questions:
            # If the bank has fewer questions than needed, use all of them
            selected = data
        else:
            selected = random.sample(data, num_questions)

        question_payload = {
            "experiment_name": str(experiment_number),
            "questions": [
                {
                    "question_number": q["question_number"],
                    "question": q["question"]
                } for q in selected
            ]
        }

        validation_payload = {
            "experiment": str(experiment_number),
            "qa_pairs": [
                {
                    "question_number": q["question_number"],
                    "question": q["question"],
                    "answer": q["answer"]
                } for q in selected
            ]
        }

    else:
        # --- 2. Fallback: original static questions.json behaviour ---
        full_path = os.path.join(os.path.dirname(__file__), filepath)

        with open(full_path, "r") as f:
            data = json.load(f)

        # Filter questions for the selected experiment (original logic)
        filtered_questions = [q for q in data if str(q["experiment"]) == str(experiment_number)]

        if len(filtered_questions) < num_questions:
            if len(filtered_questions) == 0:
                raise ValueError(f"No questions found for '{experiment_number}'. If this is a new faculty subject, please upload a document in the Faculty Portal first so the AI can generate questions.")
            else:
                raise ValueError(f"Not enough questions available for '{experiment_number}'. Found {len(filtered_questions)}, need {num_questions}.")

        selected = random.sample(filtered_questions, num_questions)

        question_payload = {
            "experiment_name": f"Experiment-{experiment_number}",
            "questions": [
                {
                    "question_number": q["question_number"],
                    "question": q["question"]
                } for q in selected
            ]
        }

        validation_payload = {
            "experiment": experiment_number,
            "qa_pairs": [
                {
                    "question_number": q["question_number"],
                    "question": q["question"],
                    "answer": q["answer"]
                } for q in selected
            ]
        }

    # Save validation payload to JSON file (used by merge_answers.py → llm_check.py)
    os.makedirs("validation_data", exist_ok=True)
    validation_path = "validation.json"
    with open(validation_path, "w") as f:
        json.dump(validation_payload, f, indent=4)

    return question_payload, validation_payload
