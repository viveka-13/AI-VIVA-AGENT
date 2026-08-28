import json
import ollama
import sys
import os
# FOLDER = "app_ui"
SESSION_FILE = os.path.join("combined_output.json")
QUESTION_BANK_FILE = os.path.join("combined_output.json")
OUTPUT_FILE = os.path.join("output.txt")


def validate_with_llm(question, user_answer,correct_answer):
   prompt = (
    f"You are a strict validation agent. Your only task is to compare the user's answer to the correct answer provided.\n"
    "You do not generate new answers, provide suggestions, or explain concepts. You do not assign marks. You must not include any explanation or reasoning.\n\n"
    "Compare user_answer to correct_answer and return only one of these **exact outputs**:\n"
    "- Answer is correct.\n"
    "- Answer is partially correct.\n"
    "- Answer is incorrect.\n\n"
    "Rules:\n"
    "- If user_answer fully matches or matches key terms in correct_answer → Answer is correct.\n"
    "- If user_answer is somewhat related but incomplete → Answer is partially correct.\n"
    "- If user_answer is unrelated or wrong or anything random which is out of the topic related to answer such as greetings and single characters→ Answer is incorrect.\n\n"
    f"Question: {question}\n"
    f"User Answer: {user_answer}\n"
    f"Correct Answer: {correct_answer}\n"
    )
   response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": prompt}]
    )
   return response["message"]["content"].strip()

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
        print(f"❌ Error loading input files: {e}")
        return

    result_lines = []
    for i, entry in enumerate(session_data):
        question = entry["question"]
        user_answer = entry["user_answer"]
        correct_answer = find_correct_answer(question, question_bank)

        if not correct_answer:
            result_lines.append(f"{i+1}. ❌ Question not found in viva.json: {question}")
            continue

        explanation = validate_with_llm(question, user_answer, correct_answer)
        result_lines.append(f"{i+1}. {explanation}")

    full_output = "\n\n".join(result_lines)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(full_output)

    print("[SUCCESS] Validation complete. Output written to output.txt")



if __name__ == "__main__":
    main()
    from evaluation import run_evaluation
    run_evaluation()
