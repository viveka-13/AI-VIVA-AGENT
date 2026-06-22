from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from datetime import datetime
from Laptop2 import generate_questions
from merge_answers import combine_responses
from flask import jsonify
from report_generator import generate_report
import subprocess
import multiprocessing
import os
import sys
import json
import hashlib
import re

# Faculty data paths
FACULTY_DATA_DIR = os.path.join(os.path.dirname(__file__), "faculty_data")
FACULTY_REGISTRY = os.path.join(FACULTY_DATA_DIR, "faculty_registry.json")
SUBJECTS_FILE = os.path.join(FACULTY_DATA_DIR, "subjects.json")
UPLOADS_DIR = os.path.join(FACULTY_DATA_DIR, "uploads")
SUBJECT_QUESTIONS_DIR = os.path.join(FACULTY_DATA_DIR, "subject_questions")

ALLOWED_EXTENSIONS = {'.pdf', '.pptx', '.docx', '.txt'}

venv_python = sys.executable

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for sessions


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower())


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def load_json(path: str, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_faculty_by_name(name: str):
    registry = load_json(FACULTY_REGISTRY)
    for fac in registry:
        if fac["name"].strip().lower() == name.strip().lower():
            return fac
    return None


def ensure_faculty_dirs():
    os.makedirs(FACULTY_DATA_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(SUBJECT_QUESTIONS_DIR, exist_ok=True)
    if not os.path.exists(FACULTY_REGISTRY):
        save_json(FACULTY_REGISTRY, [])
    if not os.path.exists(SUBJECTS_FILE):
        save_json(SUBJECTS_FILE, [])


ensure_faculty_dirs()


# ─────────────────────────────────────────────────────────────
# ORIGINAL STUDENT ROUTES (UNCHANGED)
# ─────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def index():
    session.clear()
    if request.method == 'POST':
        name = request.form['name']
        experiment = request.form['experiment']
        session['name'] = name
        session['experiment'] = experiment
        return redirect(url_for('questions'))
    return render_template('index.html')


@app.route("/start", methods=["POST"])
def start():
    name = request.form["name"]
    roll = request.form["roll"]
    experiment = request.form["experiment"]

    try:
        question_payload, _ = generate_questions(experiment)
    except Exception as e:
        return f"<h2>Error generating questions: {e}</h2>"

    return render_template(
        "questions.html",
        name=name,
        roll=roll,
        experiment=experiment,
        questions=question_payload["questions"]
    )


@app.route('/questions', methods=['GET', 'POST'])
def questions():
    name = session.get("name", "")
    experiment_number = session.get("experiment", "")

    if not name or not experiment_number:
        return redirect(url_for("index"))

    validation_filename = "validation.json"
    if os.path.exists(validation_filename):
        os.remove(validation_filename)

    question_payload, validation_payload = generate_questions(experiment_number)

    return render_template("questions.html", questions=question_payload, name=name, experiment=experiment_number)


@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    roll = request.form.get("roll", "").strip()
    experiment = request.form.get("experiment", "").strip()

    if not all([name, roll, experiment]):
        return redirect(url_for("index"))

    responses = []
    for i in range(10):
        question = request.form.get(f"question_{i}", "")
        answer = request.form.get(f"answer_{i}", "")
        if question:  # Only add if the question was actually presented
            responses.append({
                "question_number": len(responses) + 1,
                "question": question,
                "user_answer": answer
            })

    response_data = {
        "name": name,
        "roll": roll,
        "experiment": experiment,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "responses": responses
    }

    filepath = "response.json"
    with open(filepath, "w") as f:
        json.dump(response_data, f, indent=4)

    combine_responses()

    subprocess.run([sys.executable, os.path.join("llm_check.py")], check=True)

    report = generate_report(name, roll, experiment, responses)
    return render_template("report.html", report=report)


import pyttsx3


def speak_text(text):
    try:
        engine = pyttsx3.init(driverName='sapi5')
        engine.setProperty('rate', 160)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"[TTS ERROR]: {e}")


@app.route("/voice_intro", methods=["GET"])
def voice_intro():
    text = "Hello, I am Viva Agent. Please enter your details."
    multiprocessing.Process(target=speak_text, args=(text,)).start()
    return jsonify({"status": "ok", "message": text})


@app.route("/voice_question_intro", methods=["GET"])
def voice_question_intro():
    text = "Answer all the questions"
    multiprocessing.Process(target=speak_text, args=(text,)).start()
    return jsonify({"status": "ok", "message": text})


# ─────────────────────────────────────────────────────────────
# SUBJECTS API (used by student dropdown)
# ─────────────────────────────────────────────────────────────

@app.route("/get_subjects", methods=["GET"])
def get_subjects():
    """Returns list of available faculty subjects as JSON."""
    subjects = load_json(SUBJECTS_FILE)
    return jsonify(subjects)


# ─────────────────────────────────────────────────────────────
# FACULTY ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/faculty", methods=["GET"])
def faculty_home():
    """Faculty landing / login page."""
    if session.get("faculty_logged_in"):
        return redirect(url_for("faculty_dashboard"))
    error = session.pop("faculty_error", None)
    success = session.pop("faculty_success", None)
    return render_template("faculty_login.html", error=error, success=success)


@app.route("/faculty/login", methods=["POST"])
def faculty_login():
    """Authenticate (or register) a faculty member."""
    name = request.form.get("faculty_name", "").strip()
    password = request.form.get("faculty_password", "").strip()
    profile = request.form.get("faculty_profile", "").strip()

    if not name or not password:
        session["faculty_error"] = "Name and password are required."
        return redirect(url_for("faculty_home"))

    registry = load_json(FACULTY_REGISTRY)
    existing = next((f for f in registry if f["name"].strip().lower() == name.lower()), None)

    if existing:
        # Login: verify password
        if existing["password_hash"] != hash_password(password):
            session["faculty_error"] = "Incorrect password."
            return redirect(url_for("faculty_home"))
        # Update profile if provided
        if profile:
            existing["profile"] = profile
            save_json(FACULTY_REGISTRY, registry)
    else:
        # Register new faculty
        new_faculty = {
            "name": name,
            "password_hash": hash_password(password),
            "profile": profile,
            "created_at": datetime.now().isoformat()
        }
        registry.append(new_faculty)
        save_json(FACULTY_REGISTRY, registry)

    session["faculty_logged_in"] = True
    session["faculty_name"] = name
    return redirect(url_for("faculty_dashboard"))


@app.route("/faculty/dashboard", methods=["GET"])
def faculty_dashboard():
    """Faculty dashboard: view subjects and upload materials."""
    if not session.get("faculty_logged_in"):
        return redirect(url_for("faculty_home"))

    faculty_name = session.get("faculty_name", "")
    registry = load_json(FACULTY_REGISTRY)
    faculty_data = next((f for f in registry if f["name"].strip().lower() == faculty_name.lower()), {})

    # Get subjects belonging to this faculty
    all_subjects = load_json(SUBJECTS_FILE)
    my_subjects = [s for s in all_subjects if s.get("faculty", "").lower() == faculty_name.lower()]

    # Attach question counts
    for subj in my_subjects:
        qpath = os.path.join(SUBJECT_QUESTIONS_DIR, f"{slugify(subj['name'])}.json")
        if os.path.exists(qpath):
            with open(qpath, "r", encoding="utf-8") as f:
                subj["question_count"] = len(json.load(f))
        else:
            subj["question_count"] = 0

    error = session.pop("faculty_upload_error", None)
    success = session.pop("faculty_upload_success", None)

    return render_template(
        "faculty_dashboard.html",
        faculty=faculty_data,
        subjects=my_subjects,
        error=error,
        success=success
    )


@app.route("/faculty/add_subject", methods=["POST"])
def faculty_add_subject():
    """Add a new subject under the logged-in faculty."""
    if not session.get("faculty_logged_in"):
        return redirect(url_for("faculty_home"))

    subject_name = request.form.get("subject_name", "").strip()
    faculty_name = session.get("faculty_name", "")

    if not subject_name:
        session["faculty_upload_error"] = "Subject name cannot be empty."
        return redirect(url_for("faculty_dashboard"))

    all_subjects = load_json(SUBJECTS_FILE)
    # Check if subject already exists for this faculty
    exists = any(
        s["name"].strip().lower() == subject_name.lower() and
        s.get("faculty", "").lower() == faculty_name.lower()
        for s in all_subjects
    )
    if exists:
        session["faculty_upload_error"] = f"Subject '{subject_name}' already exists."
        return redirect(url_for("faculty_dashboard"))

    all_subjects.append({
        "name": subject_name,
        "slug": slugify(subject_name),
        "faculty": faculty_name,
        "created_at": datetime.now().isoformat()
    })
    save_json(SUBJECTS_FILE, all_subjects)

    session["faculty_upload_success"] = f"Subject '{subject_name}' added successfully!"
    return redirect(url_for("faculty_dashboard"))


@app.route("/faculty/upload", methods=["POST"])
def faculty_upload():
    """Handle file upload, extract text, generate questions via LLM."""
    if not session.get("faculty_logged_in"):
        return redirect(url_for("faculty_home"))

    subject_name = request.form.get("upload_subject", "").strip()
    faculty_name = session.get("faculty_name", "")

    if not subject_name:
        session["faculty_upload_error"] = "Please select a subject before uploading."
        return redirect(url_for("faculty_dashboard"))

    uploaded_file = request.files.get("material_file")
    if not uploaded_file or uploaded_file.filename == "":
        session["faculty_upload_error"] = "No file selected."
        return redirect(url_for("faculty_dashboard"))

    ext = os.path.splitext(uploaded_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        session["faculty_upload_error"] = f"Unsupported file type '{ext}'. Allowed: PDF, PPTX, DOCX, TXT."
        return redirect(url_for("faculty_dashboard"))

    # Save uploaded file
    subj_slug = slugify(subject_name)
    upload_folder = os.path.join(UPLOADS_DIR, subj_slug)
    os.makedirs(upload_folder, exist_ok=True)
    save_path = os.path.join(upload_folder, uploaded_file.filename)
    uploaded_file.save(save_path)

    # Extract text from file
    try:
        from file_extractor import extract_text
        text = extract_text(save_path)
    except Exception as e:
        session["faculty_upload_error"] = f"Failed to extract text: {e}"
        return redirect(url_for("faculty_dashboard"))

    if not text or len(text.strip()) < 50:
        session["faculty_upload_error"] = "The uploaded file appears to be empty or too short to generate questions."
        return redirect(url_for("faculty_dashboard"))

    # Generate questions from extracted text
    try:
        from question_generator import generate_and_save
        result = generate_and_save(text, subject_name, num_questions=10)
    except Exception as e:
        session["faculty_upload_error"] = f"Question generation failed: {e}"
        return redirect(url_for("faculty_dashboard"))

    session["faculty_upload_success"] = (
        f"✅ Uploaded '{uploaded_file.filename}' for subject '{subject_name}'. "
        f"Generated {result['questions_generated']} new questions "
        f"(total in bank: {result['total_in_bank']})."
    )
    return redirect(url_for("faculty_dashboard"))


@app.route("/faculty/logout", methods=["GET"])
def faculty_logout():
    """Clear faculty session and redirect to faculty login."""
    session.pop("faculty_logged_in", None)
    session.pop("faculty_name", None)
    return redirect(url_for("faculty_home"))


# ─────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
