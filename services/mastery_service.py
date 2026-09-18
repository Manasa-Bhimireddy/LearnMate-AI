import json
import time
from datetime import datetime
from models import get_db_connection

def update_concept_mastery_from_assessment(project_id, user_id, concept_id, concept_name, question_score, is_correct):
    """
    Updates a concept's estimated mastery score (0-100) and trend (improving, stable, requiring_attention).
    Uses exponential moving average and historical trajectory.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find concept_id if not provided
    if not concept_id and concept_name:
        cursor.execute("SELECT id FROM concepts WHERE project_id = ? AND LOWER(name) = LOWER(?)", (project_id, concept_name.strip()))
        row = cursor.fetchone()
        if row:
            concept_id = row["id"]
        else:
            # Create concept if new
            cursor.execute("""
                INSERT INTO concepts (project_id, name, description)
                VALUES (?, ?, 'Auto-identified from assessment.')
            """, (project_id, concept_name.strip()))
            concept_id = cursor.lastrowid

    if not concept_id:
        conn.close()
        return

    # Fetch existing mastery record
    cursor.execute("""
        SELECT id, mastery_score, trend, history_json
        FROM concept_mastery
        WHERE project_id = ? AND user_id = ? AND concept_id = ?
    """, (project_id, user_id, concept_id))
    existing = cursor.fetchone()

    current_score = existing["mastery_score"] if existing else 30
    history = json.loads(existing["history_json"]) if existing and existing["history_json"] else []

    # Update score: 60% existing score + 40% new question score
    new_score = int(round(0.6 * current_score + 0.4 * question_score))
    new_score = max(5, min(100, new_score))

    # Append to history (keep last 10 points)
    history.append({"score": new_score, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")})
    history = history[-10:]

    # Classify trend: improving, stable, requiring_attention
    if len(history) >= 2:
        prev_score = history[-2]["score"]
        diff = new_score - prev_score
        if diff >= 8:
            trend = "improving"
        elif diff <= -8 or new_score < 45:
            trend = "requiring_attention"
        else:
            trend = "stable"
    else:
        trend = "requiring_attention" if new_score < 45 else "stable"

    if existing:
        cursor.execute("""
            UPDATE concept_mastery 
            SET mastery_score = ?, trend = ?, history_json = ?, last_assessed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_score, trend, json.dumps(history), existing["id"]))
    else:
        cursor.execute("""
            INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend, history_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, user_id, concept_id, new_score, trend, json.dumps(history)))

    # Update overall project progress %
    cursor.execute("""
        SELECT AVG(mastery_score) as avg_score FROM concept_mastery 
        WHERE project_id = ? AND user_id = ?
    """, (project_id, user_id))
    avg_row = cursor.fetchone()
    if avg_row and avg_row["avg_score"] is not None:
        project_progress = int(round(avg_row["avg_score"]))
        cursor.execute("UPDATE projects SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_progress, project_id))

    conn.commit()
    conn.close()

def get_project_mastery_and_growth(project_id, user_id):
    """
    Returns full mastery and growth analytics for all concepts in a project:
    - Mastery score (0-100)
    - Trend (improving, stable, requiring_attention)
    - Historical trajectory
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id as concept_id, c.name, c.description,
               COALESCE(cm.mastery_score, 25) as mastery_score,
               COALESCE(cm.trend, 'requiring_attention') as trend,
               COALESCE(cm.history_json, '[]') as history_json,
               cm.last_assessed_at
        FROM concepts c
        LEFT JOIN concept_mastery cm ON c.id = cm.concept_id AND cm.user_id = ?
        WHERE c.project_id = ?
        ORDER BY cm.mastery_score DESC
    """, (user_id, project_id))
    rows = cursor.fetchall()
    conn.close()

    results = []
    improving_count = 0
    stable_count = 0
    attention_count = 0

    for r in rows:
        trend = r["trend"]
        if trend == "improving":
            improving_count += 1
        elif trend == "stable":
            stable_count += 1
        else:
            attention_count += 1

        history = json.loads(r["history_json"])
        results.append({
            "concept_id": r["concept_id"],
            "name": r["name"],
            "description": r["description"],
            "mastery_score": r["mastery_score"],
            "trend": trend,
            "history": history,
            "last_assessed_at": r["last_assessed_at"]
        })

    return {
        "concepts": results,
        "summary": {
            "total_concepts": len(results),
            "improving": improving_count,
            "stable": stable_count,
            "requiring_attention": attention_count,
            "average_mastery": int(round(sum(c["mastery_score"] for c in results) / len(results))) if results else 0
        }
    }
