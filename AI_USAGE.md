# AI Usage Documentation & Evaluation Report

This document satisfies the challenge submission requirements for **AI Study Companion (v3.0)**, detailing the role of AI in building the system, the runtime AI architecture, prompts used, evaluation benchmarks, known limitations, and roadmap improvements.

---

## 1. Distinction: AI Used to Build vs. AI in Final Product

### A. AI Used to Build the Product (Development Phase)
- **Coding & Architecture Pairing**: Used agentic pair-programming (Antigravity with Google DeepMind agentic tools) for multi-file code scaffolding, SQLite schema migrations, modular Python service design, and frontend component composition.
- **Frontend Design & Glassmorphic UI**: Generated modern CSS layouts, responsive grids, and clean component styles.
- **Test Generation & Edge-Case Identification**: Formulated boundary tests for project isolation, unsupported question detection, and exponential moving average mastery calculations.

### B. AI Used by the Final Product (Runtime Production Pipeline)
1. **Document Understanding & Knowledge Extraction**:
   - Analyzes uploaded materials page-by-page.
   - Extracts 4–7 core concepts with concise technical definitions and initializes mastery tracking.
2. **Grounded AI Tutor**:
   - Performs project-scoped hybrid retrieval (TF-IDF + token overlap).
   - Verifies whether sufficient evidence exists in project documents.
   - Generates grounded explanations citing `Source: [Document] — Page [X]`.
   - **Unsupported Question Handling**: Accurately detects when questions fall outside project material and refuses to hallucinate, politely explaining the limitation and stating what the material covers.
3. **Adaptive Quiz Generator**:
   - Ingests learner context (weaknesses, repeated mistakes, low mastery scores).
   - Generates tailored Multiple-Choice Questions (MCQ) and Open-Ended Questions targeted to the appropriate difficulty level.
4. **Open-Ended Assessment Grader**:
   - Evaluates free-form student text across understanding, accuracy, key concepts covered, and missing concepts.
   - Generates explanatory, constructive feedback rather than just a numerical score.
5. **Targeted Recommendation Engine**:
   - Answers *"What should I do next?"* by generating structured action items with direct project links.
6. **Automated AI Evaluation Suite**:
   - Automated benchmark harness running structured test cases for tutor groundedness, unsupported question handling, grading quality, and recommendation relevance.

---

## 2. Material Prompts Used in AI Development

### Backend & Architectural Prompts
```
Prompt:
Design a clean, modular Python/Flask architecture for an AI Study Companion matching PRD v3.0.
Organize into separate services for AI gateway, asynchronous document processing, project-scoped retrieval,
grounded tutoring with citations, adaptive MCQ + open-ended quiz generation with AI grading,
concept mastery calculation with trend analysis (improving, stable, requiring_attention),
and an admin observability dashboard.
```

### Tutor Groundedness & Refusal Prompt
```
Prompt:
You are an AI Study Companion tutor who strictly follows evidence-based instruction.
You are operating within the student's learning project.
RULE: The user asked a question for which there is INSUFFICIENT or NO evidence in their uploaded project materials.
DO NOT fabricate or guess information as if it came from their materials.
Explicitly inform the student that their uploaded materials do not contain sufficient evidence to answer this question.
Mention what concepts their uploaded materials actually cover, and offer to explain foundational concepts if they wish,
while making it clear it is outside their current notes.
```

### Open-Ended AI Grader Prompt
```
Prompt:
Evaluate the student's answer to this open-ended question.
Question: {question_text}
Reference / Rubric: {rubric}
Expected Key Points: {expected_answer}
Student's Submitted Answer: "{user_answer}"

Evaluate the response thoroughly and objectively.
Return ONLY a JSON object:
{
  "score": 85, // Integer 0 to 100
  "is_correct": true, // Boolean (true if score >= 65)
  "key_concepts_covered": ["Concept A", "Concept B"],
  "missing_concepts": ["Concept C"],
  "feedback": "Constructive 2-3 sentence explanation detailing what the learner understood well, what was missing or inaccurate, and how to improve."
}
```

---

## 3. Evaluation Approach

We implemented an automated, multi-category evaluation suite (`services/evaluation_service.py`) directly executable from the Admin Dashboard:

| Evaluation Dimension | Metric / Criterion | Verification Method |
|---|---|---|
| **Tutor Groundedness** | Accurate citation format `Source: ... — Page X` | Regex & substring verification against source excerpts. |
| **Unsupported Question Handling** | Refusal / explanation without hallucination | Out-of-domain queries (e.g. baking recipes in an OS project) must trigger insufficient-evidence responses. |
| **Assessment Grading Quality** | Semantic score accuracy, concept coverage | Standardized student answers tested against rubric expectations. |
| **Recommendation Actionability** | Direct mapping to identified learner weaknesses | Concept-keyword presence in generated next steps. |

---

## 4. Known Limitations

1. **OCR on Heavily Degraded Scans**: Text extraction relies on PyPDF/pdfplumber for text-layer PDFs, with multi-modal LLM fallback for raw images. Unindexed physical scans require high-resolution image uploads.
2. **Local Vector Search Scale**: The current prototype employs an in-memory TF-IDF + token similarity index per project, ideal for projects up to 100 pages. For enterprise workloads exceeding 10,000 pages, a persistent Milvus, Qdrant, or Pinecone index should be plugged in.
3. **Single-Worker Threading**: Background jobs run on a lightweight Python `threading.Thread` daemon pool, suitable for prototype workloads. A production deployment would use Celery with Redis or AWS SQS.

---

## 5. Future Improvements

1. **Streaming AI Tutor**: Implement Server-Sent Events (SSE) for token-by-token streaming responses to enhance real-time perception.
2. **Interactive Concept Knowledge Graphs**: Visualize concepts as a node-link diagram with color-coded nodes reflecting mastery percentages.
3. **Audio / Voice Study Mode**: Support conversational voice questions using Web Audio API and Whisper speech-to-text.
4. **Automated Spaced Repetition (SRS)**: Integrate an Anki-style SuperMemo SM-2 algorithm to schedule review notifications automatically based on mastery decay curves.
