import json
from models import get_db_connection
from services.ai_service import call_ai, clean_json_response

def generate_project_recommendations(project_id, user_id):
    """
    Generates tailored, actionable next steps answering: "What should I do next?".
    Considers weaknesses, repeated mistakes, mastery trends, and project goal.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Project info
    cursor.execute("SELECT name, learning_goal FROM projects WHERE id = ?", (project_id,))
    proj = cursor.fetchone()
    project_name = proj["name"] if proj else "Current Project"
    project_goal = proj["learning_goal"] if proj else "Master the topic"

    # Concepts needing attention
    cursor.execute("""
        SELECT c.name, cm.mastery_score, cm.trend 
        FROM concept_mastery cm
        JOIN concepts c ON cm.concept_id = c.id
        WHERE cm.project_id = ? AND cm.user_id = ?
        ORDER BY cm.mastery_score ASC
    """, (project_id, user_id))
    mastery_rows = cursor.fetchall()

    # Learner context
    cursor.execute("SELECT weaknesses_json, repeated_mistakes_json FROM learner_context WHERE project_id = ? AND user_id = ?", (project_id, user_id))
    l_context = cursor.fetchone()
    conn.close()

    weak_concepts = [r["name"] for r in mastery_rows if r["trend"] == "requiring_attention" or r["mastery_score"] < 50]
    repeated_mistakes = json.loads(l_context["repeated_mistakes_json"]) if l_context and l_context["repeated_mistakes_json"] else []

    prompt = f"""
    The student is working on Project: "{project_name}" with Goal: "{project_goal}".
    Concepts requiring attention / low mastery: {', '.join(weak_concepts[:4]) if weak_concepts else 'None identified yet'}
    Recent or repeated mistakes: {', '.join(repeated_mistakes[:3]) if repeated_mistakes else 'None'}
    
    Recommend 2 to 3 high-impact, specific learning actions answering "What should I do next?".
    Each recommendation should have a specific action type: 'quiz', 'tutor', or 'review'.

    Return ONLY a valid JSON object:
    {{
      "recommendations": [
        {{
          "title": "Clear action-oriented title",
          "description": "Specific 1-2 sentence rationale explaining why and what to focus on.",
          "action_type": "quiz", // 'quiz' | 'tutor' | 'review'
          "action_target": "Concept name or question to ask",
          "reason": "Targeting low mastery in ..."
        }}
      ]
    }}
    """
    try:
        response_text = call_ai(
            prompt=prompt,
            system_instruction="You are an expert AI learning coach. Provide actionable, supportive, targeted next steps.",
            feature="recommendation_generation",
            user_id=user_id,
            project_id=project_id,
            response_format="json"
        )
        parsed = clean_json_response(response_text)
        recs = parsed.get("recommendations", [])
    except Exception as e:
        print(f"Error generating recommendations via AI: {e}")
        recs = []

    # Fallback recommendations if empty
    if not recs:
        target_concept = weak_concepts[0] if weak_concepts else "Core Concepts"
        recs = [
            {
                "title": f"Reinforce {target_concept}",
                "description": f"Take a short adaptive quiz on {target_concept} to build confidence and reinforce key principles.",
                "action_type": "quiz",
                "action_target": target_concept,
                "reason": "Strengthen conceptual foundation"
            },
            {
                "title": f"Ask Tutor to explain nuances of {target_concept}",
                "description": "Have the AI Tutor explain practical examples and common pitfalls from your uploaded notes.",
                "action_type": "tutor",
                "action_target": f"Can you explain {target_concept} with a real-world example from my notes?",
                "reason": "Clarify tricky mechanisms"
            }
        ]

    # Save to database
    conn = get_db_connection()
    cursor = conn.cursor()
    # Keep previous completed recommendations, clear uncompleted old ones to avoid clutter
    cursor.execute("DELETE FROM recommendations WHERE project_id = ? AND user_id = ? AND is_completed = 0", (project_id, user_id))

    saved_recs = []
    for r in recs:
        cursor.execute("""
            INSERT INTO recommendations (project_id, user_id, title, description, action_type, action_target, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (project_id, user_id, r["title"], r["description"], r.get("action_type", "quiz"), r.get("action_target", ""), r.get("reason", "")))
        rec_id = cursor.lastrowid
        saved_recs.append({
            "id": rec_id,
            "title": r["title"],
            "description": r["description"],
            "action_type": r.get("action_type", "quiz"),
            "action_target": r.get("action_target", ""),
            "reason": r.get("reason", "")
        })

    # Log event
    cursor.execute("""
        INSERT INTO learning_events (user_id, project_id, event_type, event_data_json)
        VALUES (?, ?, 'recommendation_generated', ?)
    """, (user_id, project_id, json.dumps({"count": len(saved_recs)})))

    conn.commit()
    conn.close()

    return saved_recs

def get_project_recommendations(project_id, user_id):
    """Fetches active recommendations for a project."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, description, action_type, action_target, reason, is_completed, created_at
        FROM recommendations
        WHERE project_id = ? AND user_id = ?
        ORDER BY is_completed ASC, id DESC
    """, (project_id, user_id))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return generate_project_recommendations(project_id, user_id)

    return [dict(r) for r in rows]
