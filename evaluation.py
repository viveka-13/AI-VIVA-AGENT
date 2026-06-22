def evaluation_agent(data):
    if len(data) == 0:
        return 0

    total_score = 0
    for result in data:
        result_lower = result.lower()
        if "partially correct" in result_lower:
            total_score += 1
        elif "incorrect" in result_lower:
            total_score += 0
        elif "correct" in result_lower:
            total_score += 2
        else:
            # Fallback for unexpected LLM output
            print(f"Warning: Unexpected LLM validation result: '{result}'. Defaulting to incorrect.")
            total_score += 0

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