from datetime import datetime
from evaluation import run_evaluation  # ✅ Make sure this function accepts 'responses'

def generate_report(name, roll, experiment, responses):
    total = run_evaluation()  # ✅ pass responses here
    max_marks = len(responses) * 2

    report = {
        "timestamp": datetime.now().isoformat(),
        "name": name,
        "roll": roll,
        "experiment": experiment,
        "total": total,
        "max_marks": max_marks
    }

    return report
