import json
from models import get_db_connection
from services.ai_service import call_ai
from services.retrieval_service import retrieve_project_context

def get_project_and_learner_context(project_id, user_id):
    """Fetches Project details and persistent learner context."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Project metadata
    cursor.execute("SELECT name, description, learning_goal FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    project = cursor.fetchone()

    # Learner context
    cursor.execute("SELECT strengths_json, weaknesses_json, repeated_mistakes_json FROM learner_context WHERE project_id = ? AND user_id = ?", (project_id, user_id))
    l_context = cursor.fetchone()

    # Concept mastery levels
    cursor.execute("""
        SELECT c.name, cm.mastery_score, cm.trend
        FROM concept_mastery cm
        JOIN concepts c ON cm.concept_id = c.id
        WHERE cm.project_id = ? AND cm.user_id = ?
    """, (project_id, user_id))
    mastery_rows = cursor.fetchall()
    
    # Recent conversation history (last 6 messages)
    cursor.execute("""
        SELECT role, content FROM tutor_messages 
        WHERE project_id = ? AND user_id = ? 
        ORDER BY id DESC LIMIT 6
    """, (project_id, user_id))
    history_rows = cursor.fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]

    conn.close()

    mastery_list = [f"{r['name']}: {r['mastery_score']}% ({r['trend']})" for r in mastery_rows]
    strengths = json.loads(l_context["strengths_json"]) if l_context and l_context["strengths_json"] else []
    weaknesses = json.loads(l_context["weaknesses_json"]) if l_context and l_context["weaknesses_json"] else []
    mistakes = json.loads(l_context["repeated_mistakes_json"]) if l_context and l_context["repeated_mistakes_json"] else []

    return {
        "project_name": project["name"] if project else "General Project",
        "project_goal": project["learning_goal"] if project else "",
        "mastery_summary": ", ".join(mastery_list) if mastery_list else "Not yet assessed",
        "strengths": strengths,
        "weaknesses": weaknesses,
        "repeated_mistakes": mistakes,
        "history": history
    }

def ask_tutor(project_id, user_id, question):
    """
    Core AI Tutor flow adhering to PRD Groundedness and Unsupported Question rules:
    1. Retrieve project context and check evidence threshold.
    2. If insufficient evidence: return clear explanation without hallucinating.
    3. If sufficient evidence: generate grounded answer citing exact Source and Page.
    4. Save conversation and citations in DB.
    """
    context_data = get_project_and_learner_context(project_id, user_id)
    retrieval_result = retrieve_project_context(project_id, question)

    has_evidence = retrieval_result["has_sufficient_evidence"]
    evidence_chunks = retrieval_result["evidence_chunks"]
    evidence_text = retrieval_result["combined_context_text"]
    project_concepts = retrieval_result["all_project_concepts"]

    citations = []
    for chunk in evidence_chunks:
        citations.append({
            "source": chunk["filename"],
            "page": chunk["page_number"],
            "excerpt": chunk["content"][:200] + "..."
        })

    # Deduplicate citations for display
    unique_citations = []
    seen_refs = set()
    for c in citations:
        ref = f"{c['source']}-P{c['page']}"
        if ref not in seen_refs:
            seen_refs.add(ref)
            unique_citations.append(c)

    if not has_evidence:
        # PRD Section 7: Explain Insufficient Evidence rather than fabricating
        system_instruction = (
            "You are an AI Study Companion tutor who strictly follows evidence-based instruction. "
            "You are operating within the student's learning project. "
            "RULE: The user asked a question for which there is INSUFFICIENT or NO evidence in their uploaded project materials. "
            "DO NOT fabricate or guess information as if it came from their materials. "
            "Explicitly inform the student that their uploaded materials do not contain sufficient evidence to answer this question. "
            "Mention what concepts their uploaded materials actually cover, and offer to explain foundational concepts if they wish, "
            "while making it clear it is outside their current notes."
        )

        prompt = f"""
        Student Question: "{question}"
        Current Project: {context_data['project_name']}
        Project Learning Goal: {context_data['project_goal']}
        Available Project Concepts in uploaded materials: {', '.join(project_concepts) if project_concepts else 'None uploaded yet'}
        Retrieved context from materials (insufficient/unrelated):
        {evidence_text if evidence_text else 'No matching sections found in materials.'}

        Respond to the student clearly stating that this question cannot be reliably answered from their project materials.
        """

        response_text = call_ai(
            prompt=prompt,
            system_instruction=system_instruction,
            history=context_data["history"],
            feature="tutor_unsupported_query",
            user_id=user_id,
            project_id=project_id
        )

        # Store in DB
        _save_tutor_interaction(project_id, user_id, question, response_text, [], evidence_sufficient=0)

        return {
            "answer": response_text,
            "citations": [],
            "evidence_sufficient": False,
            "unsupported_question": True,
            "message": "Insufficient evidence in project materials."
        }

    # If Evidence IS Sufficient:
    system_instruction = (
        "You are the AI Study Companion Tutor. You help the student master their project material. "
        "Strict Requirements: "
        "1. GROUNDEDNESS: Prioritize and base your explanation on the provided Project Context excerpts. "
        "2. CITATIONS: At the end of your explanation or after referencing specific points, provide clear citations formatted as: "
        "`Source: [Document Name] — Page [X]`. "
        "3. LEARNER CONTEXT: Adapt your explanation to the student's mastery level and address any known weaknesses. "
        "4. CLARITY: Use Markdown with bold headers, bullet points, and code/math formatting where appropriate."
    )

    learner_summary = (
        f"Student Goal: {context_data['project_goal']}\n"
        f"Mastery Levels: {context_data['mastery_summary']}\n"
        f"Known Weaknesses: {', '.join(context_data['weaknesses']) if context_data['weaknesses'] else 'None'}\n"
        f"Repeated Mistakes: {', '.join(context_data['repeated_mistakes']) if context_data['repeated_mistakes'] else 'None'}"
    )

    prompt = f"""
    === RELEVANT PROJECT EVIDENCE ===
    {evidence_text}

    === STUDENT LEARNER CONTEXT ===
    {learner_summary}

    === STUDENT QUESTION ===
    {question}

    Provide a helpful, grounded explanation that directly answers the student's question using the evidence provided. Include source and page citations.
    """

    response_text = call_ai(
        prompt=prompt,
        system_instruction=system_instruction,
        history=context_data["history"],
        feature="tutor_grounded_answer",
        user_id=user_id,
        project_id=project_id
    )

    _save_tutor_interaction(project_id, user_id, question, response_text, unique_citations, evidence_sufficient=1)

    return {
        "answer": response_text,
        "citations": unique_citations,
        "evidence_sufficient": True,
        "unsupported_question": False
    }

def _save_tutor_interaction(project_id, user_id, user_msg, assistant_msg, citations, evidence_sufficient):
    """Saves user question, tutor response, and events to SQLite."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # User message
        cursor.execute("""
            INSERT INTO tutor_messages (project_id, user_id, role, content, citations_json, evidence_sufficient)
            VALUES (?, ?, 'user', ?, '[]', 1)
        """, (project_id, user_id, user_msg))

        # Assistant message
        cursor.execute("""
            INSERT INTO tutor_messages (project_id, user_id, role, content, citations_json, evidence_sufficient)
            VALUES (?, ?, 'assistant', ?, ?, ?)
        """, (project_id, user_id, assistant_msg, json.dumps(citations), evidence_sufficient))

        # Learning event
        cursor.execute("""
            INSERT INTO learning_events (user_id, project_id, event_type, event_data_json)
            VALUES (?, ?, 'tutor_interaction', ?)
        """, (user_id, project_id, json.dumps({
            "query_preview": user_msg[:80],
            "evidence_sufficient": bool(evidence_sufficient),
            "citations_count": len(citations)
        })))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving tutor interaction: {e}")
