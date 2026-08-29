"""
similarity_checker.py
---------------------
Embedding-based similarity checker for academic integrity.
Uses sentence-transformers (all-MiniLM-L6-v2) to compute cosine similarity
between student answers and (a) source material, (b) other students' answers.

All processing is local — no external API calls.
"""
import os
import json
import pickle
import numpy as np

# Configurable similarity threshold (0.0 - 1.0)
# Answers with similarity above this are flagged for faculty review
SIMILARITY_THRESHOLD = 0.85

# Cache directory for precomputed source embeddings
CACHE_DIR = os.path.join(os.path.dirname(__file__), "faculty_data", "embedding_cache")

# Lazy-loaded model (loaded once on first use)
_model = None


def _get_model():
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[SIMILARITY] Model loaded: all-MiniLM-L6-v2")
        except ImportError:
            print("[SIMILARITY] sentence-transformers not installed. Similarity checking disabled.")
            return None
        except Exception as e:
            print(f"[SIMILARITY] Error loading model: {e}")
            return None
    return _model


def _cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _chunk_text(text, chunk_size=200, overlap=50):
    """Split text into overlapping chunks of roughly chunk_size words."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk.strip())
        i += chunk_size - overlap
    return chunks if chunks else [text]


def get_source_embeddings(subject_slug):
    """
    Get precomputed embeddings for the source material of a subject.
    Loads from cache if available, otherwise computes and caches.
    Returns: list of (chunk_text, embedding) tuples, or empty list.
    """
    model = _get_model()
    if model is None:
        return []

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{subject_slug}.pkl")

    # Try loading from cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            return cached
        except Exception:
            pass  # Regenerate if cache is corrupt

    # Load source material text from uploaded files
    uploads_dir = os.path.join(os.path.dirname(__file__), "faculty_data", "uploads", subject_slug)
    if not os.path.exists(uploads_dir):
        return []

    from file_extractor import extract_text

    all_text = ""
    for fname in os.listdir(uploads_dir):
        fpath = os.path.join(uploads_dir, fname)
        try:
            all_text += extract_text(fpath) + "\n"
        except Exception:
            continue

    if not all_text.strip():
        return []

    # Chunk the text and compute embeddings
    chunks = _chunk_text(all_text)
    embeddings = model.encode(chunks, show_progress_bar=False)

    result = list(zip(chunks, embeddings.tolist()))

    # Cache the result
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(result, f)
    except Exception:
        pass

    return result


def invalidate_cache(subject_slug):
    """Remove cached embeddings for a subject (call after new material upload)."""
    cache_path = os.path.join(CACHE_DIR, f"{subject_slug}.pkl")
    if os.path.exists(cache_path):
        os.remove(cache_path)


def check_answer_similarity(student_answer, subject_slug, question_number,
                            other_answers=None, threshold=None):
    """
    Check a single student answer for similarity against:
    (a) Source material for the subject
    (b) Other students' answers (if provided)

    Args:
        student_answer: The student's answer text
        subject_slug: Subject identifier for source material lookup
        question_number: The question number being checked
        other_answers: List of dicts [{"student_name": ..., "answer": ...}] from other students
        threshold: Similarity threshold override (default: SIMILARITY_THRESHOLD)

    Returns:
        List of flag dicts: [{"flag_type": "source"|"student", "matched_text": ...,
                              "source_label": ..., "similarity_score": float}]
    """
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    model = _get_model()
    if model is None:
        return []

    if not student_answer or not student_answer.strip():
        return []

    flags = []
    answer_embedding = model.encode([student_answer], show_progress_bar=False)[0]

    # (a) Check against source material
    source_data = get_source_embeddings(subject_slug)
    for chunk_text, chunk_embedding in source_data:
        sim = _cosine_similarity(answer_embedding, chunk_embedding)
        if sim >= threshold:
            flags.append({
                "flag_type": "source",
                "matched_text": chunk_text[:500],  # Truncate for display
                "source_label": f"Source material (chunk)",
                "similarity_score": round(sim, 4)
            })
            break  # One source match is enough per answer

    # (b) Check against other students' answers
    if other_answers:
        other_texts = [oa["answer"] for oa in other_answers if oa["answer"].strip()]
        if other_texts:
            other_embeddings = model.encode(other_texts, show_progress_bar=False)
            for idx, (other_emb, oa) in enumerate(zip(other_embeddings, other_answers)):
                if not oa["answer"].strip():
                    continue
                sim = _cosine_similarity(answer_embedding, other_emb)
                if sim >= threshold:
                    flags.append({
                        "flag_type": "student",
                        "matched_text": oa["answer"][:500],
                        "source_label": f"Student: {oa['student_name']} (Q{question_number})",
                        "similarity_score": round(sim, 4)
                    })

    return flags


def check_session(session_id, answers_data, subject_slug):
    """
    Run similarity checks for an entire viva session.
    Called after LLM evaluation in the submit flow.

    Args:
        session_id: The DB session ID
        answers_data: List of dicts with "question", "student_answer" keys
        subject_slug: Subject identifier

    Returns:
        List of all flags found across all answers.
    """
    import database

    model = _get_model()
    if model is None:
        return []

    all_flags = []

    # Get other students' answers for this subject from previous sessions
    conn = database.get_db()
    previous_answers = conn.execute("""
        SELECT sa.question_number, sa.student_answer, vs.student_name
        FROM session_answers sa
        JOIN viva_sessions vs ON sa.session_id = vs.id
        WHERE vs.subject_slug = ? AND vs.id != ? AND vs.status = 'completed'
    """, (subject_slug, session_id)).fetchall()
    conn.close()

    # Group previous answers by question number
    prev_by_q = {}
    for pa in previous_answers:
        qn = pa["question_number"]
        if qn not in prev_by_q:
            prev_by_q[qn] = []
        prev_by_q[qn].append({
            "student_name": pa["student_name"],
            "answer": pa["student_answer"]
        })

    for i, ans in enumerate(answers_data):
        q_num = i + 1
        student_answer = ans.get("student_answer", "")

        other_answers = prev_by_q.get(q_num, [])

        flags = check_answer_similarity(
            student_answer, subject_slug, q_num,
            other_answers=other_answers
        )

        for flag in flags:
            database.save_similarity_flag(
                session_id=session_id,
                answer_id=None,
                question_number=q_num,
                flag_type=flag["flag_type"],
                student_answer_text=student_answer[:500],
                matched_text=flag["matched_text"],
                source_label=flag["source_label"],
                similarity_score=flag["similarity_score"]
            )
            all_flags.append(flag)

    return all_flags
