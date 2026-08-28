# combine_json.py
import json
import os
from datetime import datetime

def combine_responses(validation_file="validation.json", response_file="response.json", output_file="combined_output.json"):
    # Load validation data (correct answers)
    with open(validation_file, "r") as vfile:
        validation_data = json.load(vfile)
        validation_pairs = {item["question"]: item["answer"] for item in validation_data["qa_pairs"]}

    # Load user response data
    with open(response_file, "r") as rfile:
        user_data = json.load(rfile)

    # Combine both
    combined_data = {
        "name": user_data["name"],
        "roll": user_data["roll"],
        "experiment": user_data["experiment"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": []
    }

    for response in user_data["responses"]:
        question_text = response["question"]
        user_answer = response["user_answer"]
        correct_answer = validation_pairs.get(question_text, "N/A")

        combined_data["results"].append({
            "question": question_text,
            "user_answer": user_answer,
            "correct_answer": correct_answer
        })

    # Save to new JSON file
    with open(output_file, "w") as outfile:
        json.dump(combined_data, outfile, indent=4)

    print(f"[SUCCESS] Combined data saved to '{output_file}'")
