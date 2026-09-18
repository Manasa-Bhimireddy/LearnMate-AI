import json
import random
from models import get_db_connection
from services.ai_service import call_ai, clean_json_response

def select_target_concepts_and_difficulty(project_id, user_id, num_questions=4):
    """
    Adaptive question selection logic:
    Prioritizes concepts with 'requiring_attention' trend, lower mastery score,
    or flagged in repeated mistakes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.name, c.description, cm.mastery_score, cm.trend
        FROM concepts c
        LEFT JOIN concept_mastery cm ON c.id = cm.concept_id AND cm.user_id = ?
        WHERE c.project_id = ?
    """, (user_id, project_id))
    concepts = [dict(r) for r in cursor.fetchall()]

    # Fetch repeated mistakes / weaknesses from learner context
    cursor.execute("SELECT weaknesses_json, repeated_mistakes_json FROM learner_context WHERE project_id = ? AND user_id = ?", (project_id, user_id))
    l_context = cursor.fetchone()
    conn.close()

    weaknesses = json.loads(l_context["weaknesses_json"]) if l_context and l_context["weaknesses_json"] else []
    mistakes = json.loads(l_context["repeated_mistakes_json"]) if l_context and l_context["repeated_mistakes_json"] else []

    if not concepts:
        return [], "medium"

    # Score each concept based on need for practice
    def need_score(c):
        score = 0
        trend = c.get("trend") or "stable"
        mastery = c.get("mastery_score") if c.get("mastery_score") is not None else 30
        
        # Lower mastery -> higher priority for quiz
        score += (100 - mastery)

        # Requiring attention bonus
        if trend == "requiring_attention":
            score += 40
        elif trend == "stable":
            score += 10

        # Mentioned in weaknesses or mistakes bonus
        c_name = c["name"].lower()
        if any(c_name in w.lower() for w in weaknesses):
            score += 30
        if any(c_name in m.lower() for m in mistakes):
            score += 35

        return score

    concepts.sort(key=need_score, reverse=True)
    selected_concepts = concepts[:num_questions]

    # Decide overall quiz difficulty
    avg_mastery = sum([c.get("mastery_score", 30) for c in selected_concepts]) / float(len(selected_concepts))
    if avg_mastery < 40:
        difficulty = "fundamental"
    elif avg_mastery < 70:
        difficulty = "intermediate"
    else:
        difficulty = "advanced"

    return selected_concepts, difficulty

def generate_adaptive_quiz(project_id, user_id, num_questions=4, include_open_ended=True):
    """
    Generates a personalized, adaptive quiz containing both MCQs and Open-ended questions.
    """
    selected_concepts, difficulty = select_target_concepts_and_difficulty(project_id, user_id, num_questions)
    
    if not selected_concepts:
        # Fallback to general concepts if no project concepts exist yet
        selected_concepts = [
            {"id": None, "name": "Core Principles", "description": "Foundational theory and core concepts."}
        ]

    # Fetch excerpt from project materials for grounded questions
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content FROM material_chunks 
        WHERE project_id = ? 
        ORDER BY RANDOM() LIMIT 3
    """, (project_id,))
    chunks = cursor.fetchall()
    material_context = "\n".join([r["content"][:400] for r in chunks])

    concepts_summary = "\n".join([f"- {c['name']}: {c.get('description', '')}" for c in selected_concepts])

    prompt = f"""
    Create a high-quality adaptive assessment for a student with target difficulty level: '{difficulty}'.
    Target Learning Concepts:
    {concepts_summary}

    Supporting Project Notes Context:
    {material_context[:3000]}

    Create a total of {num_questions} questions:
    - At least {max(1, num_questions - 2)} Multiple-Choice Questions (MCQs) with 4 realistic options and an explanation.
    - At least 1 Open-Ended Question that prompts the student to explain a mechanism, synthesize concepts, or reason through a scenario.

    Return ONLY a valid JSON object matching this schema:
    {{
      "quiz_title": "Adaptive Assessment: {selected_concepts[0]['name']}",
      "questions": [
        {{
          "concept_name": "Concept Name",
          "question_type": "mcq",
          "question_text": "Clear question text?",
          "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
          "correct_answer": "A. ...",
          "explanation": "Why this answer is correct",
          "difficulty": "{difficulty}"
        }},
        {{
          "concept_name": "Concept Name",
          "question_type": "open_ended",
          "question_text": "Explain how ... and what happens when ...",
          "options": [],
          "correct_answer": "Key points expected in a complete answer",
          "rubric": "Expected key concepts, reasoning steps, and technical accuracy required",
          "difficulty": "{difficulty}"
        }}
      ]
    }}
    """

    ai_response = call_ai(
        prompt=prompt,
        system_instruction="You are an expert psychometrician and computer science / academic evaluator. Create thoughtful, diagnostic assessments.",
        feature="quiz_generation",
        user_id=user_id,
        project_id=project_id,
        response_format="json"
    )

    parsed = clean_json_response(ai_response)
    quiz_title = parsed.get("quiz_title", f"Adaptive Assessment - {difficulty.capitalize()}")
    questions = parsed.get("questions", [])

    # Store quiz and questions in DB
    cursor.execute("""
        INSERT INTO quizzes (project_id, user_id, title, quiz_type)
        VALUES (?, ?, ?, 'adaptive')
    """, (project_id, user_id, quiz_title))
    quiz_id = cursor.lastrowid

    # Concept name to ID mapping
    concept_map = {c["name"].lower(): c.get("id") for c in selected_concepts}

    persisted_questions = []
    for q in questions:
        c_name = q.get("concept_name", "General")
        c_id = concept_map.get(c_name.lower())
        q_type = q.get("question_type", "mcq")
        q_text = q.get("question_text", "")
        options = json.dumps(q.get("options", []))
        correct_ans = q.get("correct_answer", "")
        rubric = q.get("rubric") or q.get("explanation", "")
        diff = q.get("difficulty", difficulty)

        cursor.execute("""
            INSERT INTO quiz_questions (quiz_id, concept_id, concept_name, question_type, question_text, options_json, correct_answer, rubric, difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (quiz_id, c_id, c_name, q_type, q_text, options, correct_ans, rubric, diff))
        q_id = cursor.lastrowid

        persisted_questions.append({
            "id": q_id,
            "concept_name": c_name,
            "question_type": q_type,
            "question_text": q_text,
            "options": q.get("options", []),
            "difficulty": diff
        })

    conn.commit()
    conn.close()

    return {
        "quiz_id": quiz_id,
        "title": quiz_title,
        "difficulty": difficulty,
        "questions": persisted_questions
    }

def evaluate_open_ended_answer(question_text, rubric, expected_answer, user_answer, user_id=None, project_id=None):
    """
    Evaluates an open-ended response using AI across:
    - Understanding & Accuracy
    - Key concepts covered
    - Missing concepts
    - Constructive feedback explaining what was understood vs what was missing
    """
    prompt = f"""
    Evaluate the student's answer to this open-ended question.
    
    Question: {question_text}
    Reference / Rubric: {rubric}
    Expected Key Points: {expected_answer}
    
    Student's Submitted Answer:
    "{user_answer}"
    
    Evaluate the response thoroughly and objectively.
    Return ONLY a JSON object:
    {{
      "score": 85, // Integer 0 to 100
      "is_correct": true, // Boolean (true if score >= 65)
      "key_concepts_covered": ["Concept A", "Concept B"],
      "missing_concepts": ["Concept C"],
      "feedback": "Constructive 2-3 sentence explanation detailing what the learner understood well, what was missing or inaccurate, and how to improve."
    }}
    """
    try:
        response_text = call_ai(
            prompt=prompt,
            system_instruction="You are an expert academic evaluator. Grade answers fairly, identifying accurately covered points and missing elements.",
            feature="open_ended_evaluation",
            user_id=user_id,
            project_id=project_id,
            response_format="json"
        )
        return clean_json_response(response_text)
    except Exception as e:
        print(f"Error evaluating open ended answer: {e}")
        # Rule-based fallback
        has_content = len(user_answer.strip().split()) >= 10
        return {
            "score": 75 if has_content else 40,
            "is_correct": has_content,
            "key_concepts_covered": ["Basic Explanation"],
            "missing_concepts": ["Detailed Nuance & Synthesis"],
            "feedback": "Your answer demonstrates general awareness of the topic. Deepen your explanation by including more technical terminology and concrete examples."
        }
