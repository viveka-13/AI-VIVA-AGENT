def evaluation_agent(data):
    score_map = {
        "correct.": 2,
        "correct": 2,
        "partially correct.": 1,
        "partially correct": 1,
        "incorrect.": 0,
        "incorrect": 0
    }

    if len(data) != 5:
        raise ValueError("Exactly 5 validation results are expected.")

    total_score = 0
    for result in data:
        if result not in score_map:
            raise ValueError(f"Invalid validation result: {result}")
        total_score += score_map[result]

    return total_score


def run_evaluation():
    results = []
    with open("output.txt", "r") as f:
        for line in f:
            if '.' in line:
                _, result = line.split('.', 1)
                cleaned = result.strip().replace("Answer is", "").strip().lower().rstrip('.')
                results.append(cleaned)

    score = evaluation_agent(results)
    print("Total Score:", score)
    return score