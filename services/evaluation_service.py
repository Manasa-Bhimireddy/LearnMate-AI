import time
import json
from models import get_db_connection
from services.ai_service import call_ai, clean_json_response
from services.retrieval_service import retrieve_project_context
from services.assessment_service import evaluate_open_ended_answer

EVALUATION_TEST_CASES = [
    {
        "test_name": "Tutor Grounded Citation Verification",
        "category": "tutor_groundedness",
        "input_prompt": "Explain the concept based on the document and provide source and page citations.",
        "expected_behavior": "Must cite source name and page number format: 'Source: [Name] — Page [X]'.",
        "type": "format_and_relevance"
    },
    {
        "test_name": "Unsupported Question Rejection Check",
        "category": "unsupported_question",
        "input_prompt": "What is the secret baking recipe for Parisian chocolate soufflé?",
        "expected_behavior": "Must recognize absence of evidence in technical learning notes and state insufficient evidence without hallucinating a recipe as part of the project notes.",
        "type": "unsupported_rejection"
    },
    {
        "test_name": "Open-Ended Semantic Grading Rubric",
        "category": "assessment_grading",
        "input_prompt": "Question: Explain paging in virtual memory.\nStudent Answer: Paging divides memory into fixed-size frames and virtual address space into pages, translating with a page table.",
        "expected_behavior": "Must award passing score (>70), identify key concepts (frames, pages, translation), and provide constructive feedback.",
        "type": "grading_quality"
    },
    {
        "test_name": "Targeted Next-Action Recommendation Validity",
        "category": "recommendations",
        "input_prompt": "Student has 35% mastery in Page Replacement Algorithms and repeated mistakes on LRU vs FIFO.",
        "expected_behavior": "Must recommend a specific, actionable task targeting Page Replacement Algorithms (e.g. adaptive quiz or review).",
        "type": "actionability"
    }
]

def run_evaluation_suite(user_id=None, project_id=None):
    """
    Executes the automated AI evaluation benchmark suite and saves results in ai_evaluations table.
    Returns comprehensive evaluation summary.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    passed_count = 0

    for test in EVALUATION_TEST_CASES:
        t_start = time.time()
        test_name = test["test_name"]
        category = test["category"]
        expected = test["expected_behavior"]
        actual_output = ""
        score = 0
        passed = False

        try:
            if category == "unsupported_question":
                # Test unsupported question handling
                prompt = (
                    "Student Question: 'What is the secret baking recipe for Parisian chocolate soufflé?'\n"
                    "Context: [Available notes cover Operating Systems, Virtual Memory, and Linux Kernel].\n"
                    "RULE: If the question is unsupported by the context notes, do not hallucinate; explicitly state that the uploaded materials do not contain this information."
                )
                output = call_ai(
                    prompt=prompt,
                    system_instruction="You are an evidence-grounded academic tutor. Strictly reject queries outside the study material.",
                    feature="eval_unsupported_test",
                    user_id=user_id,
                    project_id=project_id
                )
                actual_output = output
                # Check for explicit refusal or clarification of insufficient evidence
                output_lower = output.lower()
                if any(kw in output_lower for kw in ["do not contain", "insufficient", "not covered", "outside", "no information", "notes do not"]):
                    passed = True
                    score = 95
                else:
                    passed = False
                    score = 40

            elif category == "assessment_grading":
                # Test assessment grading quality
                grade_res = evaluate_open_ended_answer(
                    question_text="Explain paging in virtual memory and the role of page tables.",
                    rubric="Must explain division of virtual memory into pages, physical memory into frames, and translation via page tables.",
                    expected_answer="Virtual memory is divided into pages; physical memory into frames. The page table maps virtual pages to physical frames.",
                    user_answer="Paging divides memory into fixed-size frames and virtual address space into pages, translating with a page table.",
                    user_id=user_id,
                    project_id=project_id
                )
                actual_output = json.dumps(grade_res)
                if grade_res.get("is_correct") and grade_res.get("score", 0) >= 70 and grade_res.get("feedback"):
                    passed = True
                    score = grade_res.get("score", 85)
                else:
                    passed = False
                    score = 50

            elif category == "tutor_groundedness":
                prompt = (
                    "Using only the following evidence: '[Source: OS_Notes.pdf — Page 14] Demand paging brings pages into physical memory only when accessed.'\n"
                    "Answer: What is demand paging and where is it cited?"
                )
                output = call_ai(
                    prompt=prompt,
                    system_instruction="Provide answers strictly grounded in the given text with citations.",
                    feature="eval_groundedness_test",
                    user_id=user_id,
                    project_id=project_id
                )
                actual_output = output
                if "page 14" in output.lower() or "source:" in output.lower():
                    passed = True
                    score = 98
                else:
                    passed = False
                    score = 55

            elif category == "recommendations":
                prompt = (
                    "Student has 35% mastery in Page Replacement Algorithms and repeated mistakes on LRU vs FIFO.\n"
                    "Recommend a targeted learning action answering 'What should I do next?'. Return JSON with 'action' and 'target'."
                )
                output = call_ai(
                    prompt=prompt,
                    system_instruction="Generate targeted learning recommendations.",
                    feature="eval_recommendation_test",
                    user_id=user_id,
                    project_id=project_id,
                    response_format="json"
                )
                actual_output = output
                if "page replacement" in output.lower() or "lru" in output.lower() or "fifo" in output.lower():
                    passed = True
                    score = 92
                else:
                    passed = False
                    score = 60

        except Exception as ex:
            actual_output = f"Evaluation Execution Error: {str(ex)}"
            score = 0
            passed = False

        latency_ms = int((time.time() - t_start) * 1000)
        if passed:
            passed_count += 1

        # Store in DB
        cursor.execute("""
            INSERT INTO ai_evaluations (test_name, category, input_prompt, expected_behavior, actual_output, score, passed, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (test_name, category, test["input_prompt"], expected, actual_output[:1000], score, 1 if passed else 0, latency_ms))

        results.append({
            "test_name": test_name,
            "category": category,
            "expected_behavior": expected,
            "actual_output": actual_output[:300] + "..." if len(actual_output) > 300 else actual_output,
            "score": score,
            "passed": passed,
            "latency_ms": latency_ms
        })

    conn.commit()
    conn.close()

    pass_rate = round((passed_count / float(len(EVALUATION_TEST_CASES))) * 100, 1)
    return {
        "pass_rate": pass_rate,
        "total_tests": len(EVALUATION_TEST_CASES),
        "passed": passed_count,
        "failed": len(EVALUATION_TEST_CASES) - passed_count,
        "details": results
    }

def get_latest_evaluations(limit=20):
    """Retrieves recent evaluation runs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, test_name, category, expected_behavior, actual_output, score, passed, latency_ms, created_at
        FROM ai_evaluations
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
