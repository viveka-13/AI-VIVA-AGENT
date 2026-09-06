"""
database.py
-----------
Lightweight SQLite data layer for the Viva Agent.
Stores viva session history and per-question evaluation results.

DB file location: faculty_data/viva_agent.db
"""
import sqlite3
import os
import json
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "faculty_data")
DB_PATH = os.path.join(DB_DIR, "viva_agent.db")


def get_db():
    """Get a database connection with row_factory set for dict-like access."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every app startup."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS viva_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            roll_no     TEXT NOT NULL,
            subject     TEXT NOT NULL,
            subject_slug TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            total_score INTEGER NOT NULL DEFAULT 0,
            max_marks   INTEGER NOT NULL DEFAULT 0,
            grade       TEXT NOT NULL DEFAULT 'F',
            passed      INTEGER NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'completed'
        );

        CREATE TABLE IF NOT EXISTS session_answers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            question_number INTEGER NOT NULL,
            question    TEXT NOT NULL,
            student_answer TEXT NOT NULL DEFAULT '',
            correct_answer TEXT NOT NULL DEFAULT '',
            verdict     TEXT NOT NULL DEFAULT 'incorrect',
            score       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES viva_sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS similarity_flags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            answer_id       INTEGER,
            question_number INTEGER NOT NULL,
            flag_type       TEXT NOT NULL DEFAULT 'source',
            student_answer_text TEXT NOT NULL DEFAULT '',
            matched_text    TEXT NOT NULL DEFAULT '',
            source_label    TEXT NOT NULL DEFAULT '',
            similarity_score REAL NOT NULL DEFAULT 0.0,
            FOREIGN KEY (session_id) REFERENCES viva_sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS integrity_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            event_type      TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            duration_seconds REAL NOT NULL DEFAULT 0.0,
            details         TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (session_id) REFERENCES viva_sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS exam_schedules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_slug    TEXT NOT NULL UNIQUE,
            start_time      TEXT NOT NULL,
            end_time        TEXT NOT NULL,
            time_limit      INTEGER NOT NULL DEFAULT 20,
            pool_size       INTEGER NOT NULL DEFAULT 30
        );

        CREATE TABLE IF NOT EXISTS assigned_questions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            question_number INTEGER NOT NULL,
            question        TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES viva_sessions(id) ON DELETE CASCADE
        );
    """)


    try:
        cursor.execute("ALTER TABLE session_answers ADD COLUMN matched_concepts TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE session_answers ADD COLUMN missing_concepts TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE session_answers ADD COLUMN reasoning TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE viva_sessions ADD COLUMN feedback_summary TEXT")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()


def _compute_grade(total_score, max_marks):
    """Compute letter grade and pass/fail from score."""
    if max_marks == 0:
        return "F", False
    pct = (total_score / max_marks) * 100
    if pct >= 90:
        grade = "A"
    elif pct >= 75:
        grade = "B"
    elif pct >= 60:
        grade = "C"
    elif pct >= 50:
        grade = "D"
    else:
        grade = "F"
    passed = pct >= 50
    return grade, passed


def _parse_verdict(raw_verdict):
    """Parse an LLM verdict string into a clean verdict and numeric score."""
    v = raw_verdict.lower().strip()
    if "partially correct" in v:
        return "partially correct", 1
    elif "incorrect" in v:
        return "incorrect", 0
    elif "correct" in v:
        return "correct", 2
    else:
        return "incorrect", 0


def create_pending_session(student_name, roll_no, subject, subject_slug):
    """Create a pending session when the student starts the viva (before submission).
    Returns the session_id so proctoring events can be logged during the exam."""
    timestamp = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO viva_sessions
            (student_name, roll_no, subject, subject_slug, timestamp,
             total_score, max_marks, grade, passed, status)
        VALUES (?, ?, ?, ?, ?, 0, 0, 'F', 0, 'pending')
    """, (student_name, roll_no, subject, subject_slug, timestamp))
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def finalize_session(session_id, answers_data, total_score, max_marks, feedback_summary=None):
    """Finalize a pending session with scores and answers after submission."""
    grade, passed = _compute_grade(total_score, max_marks)
    feedback_str = json.dumps(feedback_summary) if feedback_summary else None
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE viva_sessions
        SET total_score = ?, max_marks = ?, grade = ?, passed = ?, status = 'completed',
            timestamp = ?, feedback_summary = ?
        WHERE id = ?
    """, (total_score, max_marks, grade, int(passed), datetime.now().isoformat(), feedback_str, session_id))

    for i, ans in enumerate(answers_data):
        verdict, score = _parse_verdict(ans.get("raw_verdict", "incorrect"))
        matched = json.dumps(ans.get("matched_concepts", []))
        missing = json.dumps(ans.get("missing_concepts", []))
        reasoning = ans.get("reasoning", "")
        cursor.execute("""
            INSERT INTO session_answers
                (session_id, question_number, question, student_answer,
                 correct_answer, verdict, score, matched_concepts, missing_concepts, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, i + 1, ans["question"], ans.get("student_answer", ""),
              ans.get("correct_answer", ""), verdict, score, matched, missing, reasoning))

    conn.commit()
    conn.close()
    return session_id


def save_viva_session(student_name, roll_no, subject, subject_slug,
                      answers_data, total_score, max_marks, feedback_summary=None):
    """
    Persist a completed viva session with all per-question answers.
    """
    grade, passed = _compute_grade(total_score, max_marks)
    timestamp = datetime.now().isoformat()
    feedback_str = json.dumps(feedback_summary) if feedback_summary else None

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO viva_sessions
            (student_name, roll_no, subject, subject_slug, timestamp,
             total_score, max_marks, grade, passed, status, feedback_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
    """, (student_name, roll_no, subject, subject_slug, timestamp,
          total_score, max_marks, grade, int(passed), feedback_str))

    session_id = cursor.lastrowid

    for i, ans in enumerate(answers_data):
        verdict, score = _parse_verdict(ans.get("raw_verdict", "incorrect"))
        matched = json.dumps(ans.get("matched_concepts", []))
        missing = json.dumps(ans.get("missing_concepts", []))
        reasoning = ans.get("reasoning", "")
        cursor.execute("""
            INSERT INTO session_answers
                (session_id, question_number, question, student_answer,
                 correct_answer, verdict, score, matched_concepts, missing_concepts, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, i + 1, ans["question"], ans.get("student_answer", ""),
              ans.get("correct_answer", ""), verdict, score, matched, missing, reasoning))

    conn.commit()
    conn.close()
    return session_id


def save_similarity_flag(session_id, answer_id, question_number, flag_type,
                         student_answer_text, matched_text, source_label, similarity_score):
    """Save a similarity/plagiarism flag for a specific answer."""
    conn = get_db()
    conn.execute("""
        INSERT INTO similarity_flags
            (session_id, answer_id, question_number, flag_type,
             student_answer_text, matched_text, source_label, similarity_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, answer_id, question_number, flag_type,
          student_answer_text, matched_text, source_label, similarity_score))
    conn.commit()
    conn.close()


def get_similarity_flags(session_id):
    """Get all similarity flags for a session."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM similarity_flags WHERE session_id = ? ORDER BY question_number",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_integrity_event(session_id, event_type, timestamp, duration_seconds=0.0, details=""):
    """Save a proctoring integrity event."""
    conn = get_db()
    conn.execute("""
        INSERT INTO integrity_events
            (session_id, event_type, timestamp, duration_seconds, details)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, event_type, timestamp, duration_seconds, details))
    conn.commit()
    conn.close()


def get_integrity_events(session_id):
    """Get all integrity events for a session."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM integrity_events WHERE session_id = ? ORDER BY timestamp",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_by_id(session_id):
    """Get a single viva session with all its answers."""
    conn = get_db()
    session_row = conn.execute(
        "SELECT * FROM viva_sessions WHERE id = ?", (session_id,)
    ).fetchone()

    if not session_row:
        conn.close()
        return None

    answers_raw = conn.execute(
        "SELECT * FROM session_answers WHERE session_id = ? ORDER BY question_number",
        (session_id,)
    ).fetchall()

    answers = []
    # Group answers
    for row in answers_raw:
        try:
            matched = json.loads(row["matched_concepts"]) if row["matched_concepts"] else []
        except:
            matched = []
        try:
            missing = json.loads(row["missing_concepts"]) if row["missing_concepts"] else []
        except:
            missing = []
            
        answers.append({
            "question_number": row["question_number"],
            "question": row["question"],
            "student_answer": row["student_answer"],
            "correct_answer": row["correct_answer"],
            "verdict": row["verdict"],
            "score": row["score"],
            "matched_concepts": matched,
            "missing_concepts": missing,
            "reasoning": row["reasoning"] or ""
        })

    try:
        feedback = json.loads(session_row["feedback_summary"]) if session_row["feedback_summary"] else None
    except:
        feedback = None

    conn.close()

    return {
        "session": dict(session_row),
        "answers": answers,
        "feedback": feedback
    }


def get_sessions_by_subject(subject_slug):
    """Get all viva sessions for a given subject."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM viva_sessions WHERE subject_slug = ? AND status = 'completed' ORDER BY timestamp DESC",
        (subject_slug,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_sessions_for_faculty_subjects(subject_slugs):
    """Get all sessions across multiple subjects owned by a faculty."""
    if not subject_slugs:
        return []
    placeholders = ",".join("?" * len(subject_slugs))
    conn = get_db()
    rows = conn.execute(
        f"SELECT * FROM viva_sessions WHERE subject_slug IN ({placeholders}) AND status = 'completed' ORDER BY timestamp DESC",
        subject_slugs
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analytics_for_subject(subject_slug):
    """Compute analytics data for a subject: avg score, distribution, pass/fail, count."""
    conn = get_db()

    sessions = conn.execute(
        "SELECT * FROM viva_sessions WHERE subject_slug = ? AND status = 'completed'", (subject_slug,)
    ).fetchall()

    if not sessions:
        conn.close()
        return {
            "session_count": 0,
            "avg_score": 0,
            "avg_percentage": 0,
            "score_distribution": [],
            "pass_count": 0,
            "fail_count": 0,
            "question_stats": []
        }

    total_sessions = len(sessions)
    total_pct = 0
    pass_count = 0
    fail_count = 0
    score_list = []

    for s in sessions:
        max_m = s["max_marks"] if s["max_marks"] > 0 else 1
        pct = round((s["total_score"] / max_m) * 100, 1)
        score_list.append(pct)
        total_pct += pct
        if s["passed"]:
            pass_count += 1
        else:
            fail_count += 1

    avg_pct = round(total_pct / total_sessions, 1)

    # Score distribution buckets: 0-20, 20-40, 40-60, 60-80, 80-100
    buckets = [0, 0, 0, 0, 0]
    for pct in score_list:
        if pct < 20:
            buckets[0] += 1
        elif pct < 40:
            buckets[1] += 1
        elif pct < 60:
            buckets[2] += 1
        elif pct < 80:
            buckets[3] += 1
        else:
            buckets[4] += 1

    # Per-question stats
    question_rows = conn.execute("""
        SELECT
            sa.question,
            COUNT(*) as times_asked,
            SUM(CASE WHEN sa.verdict = 'correct' THEN 1 ELSE 0 END) as correct_count,
            SUM(CASE WHEN sa.verdict = 'partially correct' THEN 1 ELSE 0 END) as partial_count,
            SUM(CASE WHEN sa.verdict = 'incorrect' THEN 1 ELSE 0 END) as incorrect_count
        FROM session_answers sa
        JOIN viva_sessions vs ON sa.session_id = vs.id
        WHERE vs.subject_slug = ?
        GROUP BY sa.question
        ORDER BY times_asked DESC
    """, (subject_slug,)).fetchall()

    question_stats = []
    for q in question_rows:
        total = q["times_asked"]
        correct_pct = round((q["correct_count"] / total) * 100, 1) if total > 0 else 0
        partial_pct = round((q["partial_count"] / total) * 100, 1) if total > 0 else 0
        incorrect_pct = round((q["incorrect_count"] / total) * 100, 1) if total > 0 else 0
        difficulty = round((q["incorrect_count"] + 0.5 * q["partial_count"]) / total, 2) if total > 0 else 0

        question_stats.append({
            "question": q["question"],
            "times_asked": total,
            "correct_pct": correct_pct,
            "partial_pct": partial_pct,
            "incorrect_pct": incorrect_pct,
            "difficulty_score": difficulty
        })

    # Sort by difficulty (hardest first)
    question_stats.sort(key=lambda x: x["difficulty_score"], reverse=True)

    conn.close()

    return {
        "session_count": total_sessions,
        "avg_score": avg_pct,
        "avg_percentage": avg_pct,
        "score_distribution": buckets,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "question_stats": question_stats
    }


def get_student_history(student_name, roll_no):
    """Get all historical sessions for a specific student."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, subject, subject_slug, timestamp, total_score, max_marks, grade, passed
        FROM viva_sessions
        WHERE student_name = ? AND roll_no = ? AND status = 'completed'
        ORDER BY timestamp ASC
    """, (student_name, roll_no)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_gradebook_data(subject_slug):
    """Get all student results for a subject (for CSV/Excel export)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT student_name, roll_no, timestamp, total_score, max_marks, grade, passed
        FROM viva_sessions
        WHERE subject_slug = ? AND status = 'completed'
        ORDER BY timestamp DESC
    """, (subject_slug,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_exam_schedule(subject_slug):
    conn = get_db()
    row = conn.execute("SELECT * FROM exam_schedules WHERE subject_slug = ?", (subject_slug,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_exam_schedule(subject_slug, start_time, end_time, time_limit, pool_size):
    conn = get_db()
    conn.execute("""
        INSERT INTO exam_schedules (subject_slug, start_time, end_time, time_limit, pool_size)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(subject_slug) DO UPDATE SET
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            time_limit=excluded.time_limit,
            pool_size=excluded.pool_size
    """, (subject_slug, start_time, end_time, time_limit, pool_size))
    conn.commit()
    conn.close()

def save_assigned_questions(session_id, questions):
    conn = get_db()
    for q in questions:
        conn.execute("""
            INSERT INTO assigned_questions (session_id, question_number, question)
            VALUES (?, ?, ?)
        """, (session_id, q["question_number"], q["question"]))
    conn.commit()
    conn.close()

def get_assigned_questions(session_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM assigned_questions WHERE session_id = ? ORDER BY question_number", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_assigned_sequences(subject_slug, limit=50):
    conn = get_db()
    rows = conn.execute("""
        SELECT aq.session_id, aq.question_number, aq.question
        FROM assigned_questions aq
        JOIN viva_sessions vs ON aq.session_id = vs.id
        WHERE vs.subject_slug = ?
        ORDER BY aq.session_id DESC
    """, (subject_slug,)).fetchall()
    conn.close()
    
    sequences = {}
    for r in rows:
        sid = r["session_id"]
        if sid not in sequences:
            sequences[sid] = []
        sequences[sid].append(r["question"])
    return list(sequences.values())[:limit]
