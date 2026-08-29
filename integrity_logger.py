"""
integrity_logger.py
-------------------
Receives and stores proctoring integrity events (face-not-detected,
tab-switch, focus-loss) in the SQLite database.

Events are purely advisory flags for faculty review, never automatic penalties.
"""
import database
from datetime import datetime


def log_event(session_id, event_type, timestamp=None, duration_seconds=0.0, details=""):
    """
    Log an integrity event for a viva session.

    Args:
        session_id: The viva session ID
        event_type: "face_lost" | "tab_switch" | "focus_loss"
        timestamp: ISO format timestamp string (defaults to now)
        duration_seconds: How long the event lasted (for tab switches)
        details: Any extra details (e.g. "switched to another tab for 15s")
    """
    if timestamp is None:
        timestamp = datetime.now().isoformat()

    database.save_integrity_event(
        session_id=session_id,
        event_type=event_type,
        timestamp=timestamp,
        duration_seconds=duration_seconds,
        details=details
    )


def get_events(session_id):
    """Get all integrity events for a session, sorted by timestamp."""
    return database.get_integrity_events(session_id)


def get_event_summary(session_id):
    """
    Get a summary of integrity events for a session.
    Returns counts and total duration by event type.
    """
    events = get_events(session_id)

    summary = {
        "total_events": len(events),
        "face_lost_count": 0,
        "face_lost_total_seconds": 0.0,
        "tab_switch_count": 0,
        "tab_switch_total_seconds": 0.0,
        "events": events
    }

    for e in events:
        if e["event_type"] == "face_lost":
            summary["face_lost_count"] += 1
            summary["face_lost_total_seconds"] += e.get("duration_seconds", 0)
        elif e["event_type"] in ("tab_switch", "focus_loss"):
            summary["tab_switch_count"] += 1
            summary["tab_switch_total_seconds"] += e.get("duration_seconds", 0)

    return summary
