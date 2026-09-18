import re
import math
from models import get_db_connection
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def tokenize(text):
    """Simple alphanumeric tokenizer."""
    return set(re.findall(r'\b[a-zA-Z0-9_]{3,}\b', text.lower()))

def retrieve_project_context(project_id, query, top_k=4, min_similarity_threshold=0.10):
    """
    Strictly isolated retrieval within a specific Project.
    Returns:
    {
        "has_sufficient_evidence": bool,
        "evidence_chunks": list of {
            "page_number": int,
            "filename": str,
            "content": str,
            "similarity": float
        },
        "all_project_concepts": list of str,
        "combined_context_text": str
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch chunks for this specific project only
    cursor.execute("""
        SELECT mc.id, mc.page_number, mc.content, m.filename
        FROM material_chunks mc
        JOIN materials m ON mc.material_id = m.id
        WHERE mc.project_id = ? AND m.status = 'ready'
    """, (project_id,))
    rows = cursor.fetchall()

    # Also fetch concepts in this project to understand project domain
    cursor.execute("SELECT name FROM concepts WHERE project_id = ?", (project_id,))
    concept_rows = cursor.fetchall()
    all_concepts = [c["name"] for c in concept_rows]
    conn.close()

    if not rows:
        return {
            "has_sufficient_evidence": False,
            "evidence_chunks": [],
            "all_project_concepts": all_concepts,
            "combined_context_text": "",
            "reason": "No processed materials available in this Project."
        }

    chunk_texts = [r["content"] for r in rows]

    # Calculate TF-IDF Cosine Similarity
    try:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
        tfidf_matrix = vectorizer.fit_transform(chunk_texts + [query])
        query_vec = tfidf_matrix[-1]
        doc_vecs = tfidf_matrix[:-1]
        similarities = cosine_similarity(query_vec, doc_vecs)[0]
    except Exception as e:
        print(f"TF-IDF similarity error: {e}")
        similarities = [0.0] * len(chunk_texts)

    scored_chunks = []
    query_tokens = tokenize(query)

    for idx, row in enumerate(rows):
        sim = float(similarities[idx])
        chunk_text = row["content"]
        chunk_tokens = tokenize(chunk_text)
        
        # Keyword overlap bonus
        if query_tokens:
            overlap = len(query_tokens.intersection(chunk_tokens)) / float(len(query_tokens))
        else:
            overlap = 0.0

        combined_score = round(sim * 0.7 + overlap * 0.3, 4)

        if combined_score >= min_similarity_threshold or sim >= 0.08:
            scored_chunks.append({
                "page_number": row["page_number"],
                "filename": row["filename"],
                "content": chunk_text,
                "similarity": combined_score
            })

    # Sort by score descending
    scored_chunks.sort(key=lambda x: x["similarity"], reverse=True)
    top_chunks = scored_chunks[:top_k]

    # Check evidence threshold
    # Core PRD requirement: If Project material does not contain enough evidence, Tutor must not fabricate
    has_sufficient = False
    if top_chunks:
        best_score = top_chunks[0]["similarity"]
        if best_score >= 0.12 or (len(top_chunks) >= 2 and best_score >= 0.08):
            has_sufficient = True

    # Build structured context string for prompt
    context_parts = []
    for c in top_chunks:
        context_parts.append(
            f"[Source: {c['filename']} — Page {c['page_number']}]\n{c['content']}"
        )

    return {
        "has_sufficient_evidence": has_sufficient,
        "evidence_chunks": top_chunks,
        "all_project_concepts": all_concepts,
        "combined_context_text": "\n\n---\n\n".join(context_parts)
    }
