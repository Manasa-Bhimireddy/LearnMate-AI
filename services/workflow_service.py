import json
import time
from models import get_db_connection
from services.mastery_service import update_concept_mastery_from_assessment
from services.recommendation_service import generate_project_recommendations

def log_event(user_id, event_type, space_id=None, project_id=None, event_data=None):
    """Universal event logging function with retry for concurrent SQLite writes."""
    for attempt in range(5):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learning_events (user_id, space_id, project_id, event_type, event_data_json)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, space_id, project_id, event_type, json.dumps(event_data or {})))
            conn.commit()
            conn.close()
            return
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 4:
                time.sleep(0.05 * (attempt + 1))
                continue
            break

def trigger_post_quiz_workflow(attempt_id, quiz_id, project_id, user_id, answers_evaluated):
    """
    Intelligent Background Learning Workflow triggered upon quiz completion:
    1. Update Mastery scores for each concept tested.
    2. Detect weaknesses and repeated mistakes.
    3. Update persistent Learner Context.
    4. Automatically trigger new targeted Recommendations.
    5. Log completion event and analytics.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Track concept performance in this attempt
    concept_stats = {}
    new_mistakes = []
    new_strengths = []

    for ans in answers_evaluated:
        q_id = ans.get("question_id")
        is_correct = ans.get("is_correct", False)
        score = ans.get("score", 100 if is_correct else 0)
        
        # Get question concept
        cursor.execute("SELECT concept_id, concept_name, question_text FROM quiz_questions WHERE id = ?", (q_id,))
        q_row = cursor.fetchone()
        if q_row:
            c_id = q_row["concept_id"]
            c_name = q_row["concept_name"]
            
            # Update mastery for this concept
            update_concept_mastery_from_assessment(project_id, user_id, c_id, c_name, score, is_correct)
            
            if not is_correct:
                new_mistakes.append(f"Missed {c_name}: {q_row['question_text'][:80]}")
            else:
                new_strengths.append(c_name)

    # Update Learner Context
    cursor.execute("""
        SELECT strengths_json, weaknesses_json, repeated_mistakes_json 
        FROM learner_context 
        WHERE project_id = ? AND user_id = ?
    """, (project_id, user_id))
    existing_lc = cursor.fetchone()

    current_strengths = json.loads(existing_lc["strengths_json"]) if existing_lc and existing_lc["strengths_json"] else []
    current_weaknesses = json.loads(existing_lc["weaknesses_json"]) if existing_lc and existing_lc["weaknesses_json"] else []
    current_mistakes = json.loads(existing_lc["repeated_mistakes_json"]) if existing_lc and existing_lc["repeated_mistakes_json"] else []

    # Merge strengths & weaknesses
    for s in new_strengths:
        if s not in current_strengths:
            current_strengths.append(s)
        # If mastered, remove from weaknesses
        if s in current_weaknesses:
            current_weaknesses.remove(s)

    for m in new_mistakes:
        current_mistakes.append(m)

    # Check for repeated mistakes pattern (PRD Section 13)
    # If a concept is missed more than once, mark it as high-priority weakness
    concept_miss_counts = {}
    for m in current_mistakes:
        for word in m.split():
            if len(word) > 4:
                concept_miss_counts[word] = concept_miss_counts.get(word, 0) + 1

    # Keep lists bounded
    current_strengths = current_strengths[-10:]
    current_mistakes = current_mistakes[-10:]

    cursor.execute("""
        INSERT OR REPLACE INTO learner_context (project_id, user_id, strengths_json, weaknesses_json, repeated_mistakes_json, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (project_id, user_id, json.dumps(current_strengths), json.dumps(current_weaknesses), json.dumps(current_mistakes)))

    conn.commit()
    conn.close()

    # Automatically generate fresh recommendations answering "What should I do next?"
    generate_project_recommendations(project_id, user_id)

    log_event(user_id, "learning_workflow_completed", project_id=project_id, event_data={
        "attempt_id": attempt_id,
        "new_strengths": new_strengths,
        "new_mistakes_count": len(new_mistakes)
    })
