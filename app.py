import os
import re
import json
import uuid
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from skills_db import skills_list
from utils.pdf_reader import extract_text as extract_pdf_text_pypdf
from utils.docx_reader import extract_docx_text

# Load environment variables
load_dotenv()

# Database & Models
from models import init_db, get_db_connection

# Services
from services.ai_service import call_ai, get_configured_providers, log_ai_usage
from services.document_processor import queue_material_for_processing, start_background_processor
from services.retrieval_service import retrieve_project_context
from services.tutor_service import ask_tutor
from services.assessment_service import generate_adaptive_quiz, evaluate_open_ended_answer
from services.mastery_service import get_project_mastery_and_growth
from services.recommendation_service import get_project_recommendations, generate_project_recommendations
from services.workflow_service import log_event, trigger_post_quiz_workflow
from services.evaluation_service import run_evaluation_suite, get_latest_evaluations

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ai-study-companion-secret-key-9988!#")
CORS(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize DB and start background worker thread
init_db()
start_background_processor()

# Helper: Require Authentication
def get_current_user_id():
    user_id = session.get('user_id')
    if user_id:
        return user_id
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM users WHERE username = 'student' LIMIT 1")
        student = cursor.fetchone()
        conn.close()
        if student:
            session['user_id'] = student['id']
            session['username'] = student['username']
            session['role'] = student['role']
            session['is_demo'] = True
            return student['id']
    except Exception:
        pass
    return None

def require_auth():
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized. Please log in."}), 401)
    return user_id, None

def require_admin():
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized. Please log in."}), 401)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or row["role"] != "admin":
        return None, (jsonify({"error": "Forbidden. Administrator access required."}), 403)
    return user_id, None

# -------------------------------------------------------------
# Frontend Route
# -------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

# -------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'student').strip()
    if role not in ['student', 'admin']:
        role = 'student'

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        pw_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, pw_hash, role))
        user_id = cursor.lastrowid

        # Create a default "General Studies" space for user
        cursor.execute("""
            INSERT INTO spaces (user_id, name, description, icon, color)
            VALUES (?, 'General Studies', 'Your default learning space for subjects and certifications', 'book-open', '#06b6d4')
        """, (user_id,))
        space_id = cursor.lastrowid

        # Create a welcome project
        cursor.execute("""
            INSERT INTO projects (space_id, user_id, name, description, learning_goal)
            VALUES (?, ?, 'Introduction to AI & Systems', 'Explore foundations of intelligent systems and architecture', 'Understand core neural networks, memory models, and systems design')
        """, (space_id, user_id))
        proj_id = cursor.lastrowid

        # Insert starter concepts
        cursor.execute("INSERT INTO concepts (project_id, name, description) VALUES (?, 'Virtual Memory & Paging', 'Abstracts physical memory into pages mapped via page tables.')", (proj_id,))
        c1_id = cursor.lastrowid
        cursor.execute("INSERT INTO concepts (project_id, name, description) VALUES (?, 'Attention Mechanism', 'Allows neural models to dynamically weigh input tokens based on relevance.')", (proj_id,))
        c2_id = cursor.lastrowid

        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, ?, ?, 40, 'stable')", (proj_id, user_id, c1_id))
        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, ?, ?, 30, 'requiring_attention')", (proj_id, user_id, c2_id))

        log_event(user_id, "user_registered", space_id=space_id, project_id=proj_id, event_data={"username": username, "role": role})

        conn.commit()
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = role
        session['is_demo'] = False

        return jsonify({"success": True, "user": {"id": user_id, "username": username, "role": role}})
    except Exception as e:
        conn.rollback()
        if "UNIQUE constraint failed" in str(e):
            return jsonify({"error": "Username already exists."}), 400
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 400

    session['user_id'] = user["id"]
    session['username'] = user["username"]
    session['role'] = user["role"]
    session['is_demo'] = False

    log_event(user["id"], "user_logged_in", event_data={"username": user["username"]})

    return jsonify({"success": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}})

@app.route('/api/logout', methods=['POST'])
def logout():
    user_id = session.get('user_id')
    if user_id:
        log_event(user_id, "user_logged_out")
    session.clear()
    return jsonify({"success": True})

@app.route('/api/session', methods=['GET'])
def get_session():
    user_id = get_current_user_id()
    if user_id and 'user_id' in session:
        is_demo = bool(session.get('is_demo', False))
        return jsonify({
            "logged_in": not is_demo,
            "is_demo": is_demo,
            "user": {
                "id": session['user_id'],
                "username": session['username'],
                "role": session.get('role', 'student')
            }
        })
    return jsonify({"logged_in": False, "is_demo": False})

# -------------------------------------------------------------
# User Home: "Where was I, how am I doing, what should I do next?"
# -------------------------------------------------------------
@app.route('/api/user/home', methods=['GET'])
def get_user_home():
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Continue Learning: Most recently updated project
    cursor.execute("""
        SELECT p.id, p.name, p.description, p.learning_goal, p.progress, p.space_id, s.name as space_name, s.color as space_color
        FROM projects p
        JOIN spaces s ON p.space_id = s.id
        WHERE p.user_id = ?
        ORDER BY p.updated_at DESC LIMIT 1
    """, (user_id,))
    continue_project = cursor.fetchone()

    # 2. Recent Projects
    cursor.execute("""
        SELECT p.id, p.name, p.description, p.progress, p.space_id, s.name as space_name, s.color as space_color, p.updated_at
        FROM projects p
        JOIN spaces s ON p.space_id = s.id
        WHERE p.user_id = ?
        ORDER BY p.updated_at DESC LIMIT 4
    """, (user_id,))
    recent_projects = [dict(r) for r in cursor.fetchall()]

    # 3. Overall Progress & Mastery Stats
    cursor.execute("""
        SELECT AVG(mastery_score) as avg_mastery,
               COUNT(CASE WHEN trend = 'requiring_attention' THEN 1 END) as attention_count,
               COUNT(CASE WHEN trend = 'improving' THEN 1 END) as improving_count,
               COUNT(id) as total_concepts
        FROM concept_mastery
        WHERE user_id = ?
    """, (user_id,))
    stats_row = cursor.fetchone()

    # 4. Areas Requiring Attention (top weak concepts across projects)
    cursor.execute("""
        SELECT cm.concept_id, c.name as concept_name, cm.mastery_score, cm.trend, p.id as project_id, p.name as project_name
        FROM concept_mastery cm
        JOIN concepts c ON cm.concept_id = c.id
        JOIN projects p ON cm.project_id = p.id
        WHERE cm.user_id = ? AND (cm.trend = 'requiring_attention' OR cm.mastery_score < 50)
        ORDER BY cm.mastery_score ASC LIMIT 4
    """, (user_id,))
    attention_areas = [dict(r) for r in cursor.fetchall()]

    # 5. Recommended Next Action: Fetch active recommendation from latest active project
    recommendations = []
    if continue_project:
        recs = get_project_recommendations(continue_project["id"], user_id)
        recommendations = recs[:3]

    conn.close()

    return jsonify({
        "success": True,
        "continue_learning": dict(continue_project) if continue_project else None,
        "recent_projects": recent_projects,
        "overall_progress": {
            "average_mastery": int(round(stats_row["avg_mastery"])) if stats_row and stats_row["avg_mastery"] is not None else 0,
            "attention_count": stats_row["attention_count"] if stats_row else 0,
            "improving_count": stats_row["improving_count"] if stats_row else 0,
            "total_concepts": stats_row["total_concepts"] if stats_row else 0
        },
        "areas_requiring_attention": attention_areas,
        "recommendations": recommendations
    })

# -------------------------------------------------------------
# Spaces & Projects Endpoints
# -------------------------------------------------------------
@app.route('/api/spaces', methods=['GET', 'POST'])
def handle_spaces():
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        icon = data.get('icon', 'book-open').strip()
        color = data.get('color', '#06b6d4').strip()

        if not name:
            conn.close()
            return jsonify({"error": "Space name is required."}), 400

        cursor.execute("""
            INSERT INTO spaces (user_id, name, description, icon, color)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, description, icon, color))
        space_id = cursor.lastrowid
        conn.commit()

        log_event(user_id, "space_created", space_id=space_id, event_data={"name": name})
        conn.close()
        return jsonify({"success": True, "space": {"id": space_id, "name": name, "description": description, "icon": icon, "color": color}})

    # GET: List spaces with project count
    cursor.execute("""
        SELECT s.id, s.name, s.description, s.icon, s.color, s.created_at,
               COUNT(p.id) as project_count
        FROM spaces s
        LEFT JOIN projects p ON s.id = p.space_id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """, (user_id,))
    spaces = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "spaces": spaces})

@app.route('/api/spaces/<int:space_id>', methods=['GET', 'DELETE'])
def handle_single_space(space_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'DELETE':
        # Find all projects belonging to this space to clean up their child records
        cursor.execute("SELECT id FROM projects WHERE space_id = ? AND user_id = ?", (space_id, user_id))
        proj_rows = cursor.fetchall()
        for pr in proj_rows:
            pid = pr['id']
            cursor.execute("DELETE FROM materials WHERE project_id = ?", (pid,))
            cursor.execute("DELETE FROM concepts WHERE project_id = ?", (pid,))
            cursor.execute("DELETE FROM tutor_messages WHERE project_id = ?", (pid,))
            cursor.execute("DELETE FROM quizzes WHERE project_id = ?", (pid,))
            cursor.execute("DELETE FROM mastery_logs WHERE project_id = ?", (pid,))
            cursor.execute("DELETE FROM recommendations WHERE project_id = ?", (pid,))
        cursor.execute("DELETE FROM projects WHERE space_id = ? AND user_id = ?", (space_id, user_id))
        cursor.execute("DELETE FROM spaces WHERE id = ? AND user_id = ?", (space_id, user_id))
        conn.commit()
        log_event(user_id, "space_deleted", space_id=space_id)
        conn.close()
        return jsonify({"success": True})

    cursor.execute("SELECT * FROM spaces WHERE id = ? AND user_id = ?", (space_id, user_id))
    space = cursor.fetchone()
    if not space:
        conn.close()
        return jsonify({"error": "Space not found."}), 404

    # Projects in this space
    cursor.execute("""
        SELECT id, name, description, learning_goal, progress, status, created_at, updated_at
        FROM projects
        WHERE space_id = ? AND user_id = ?
        ORDER BY updated_at DESC
    """, (space_id, user_id))
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "space": dict(space), "projects": projects})

@app.route('/api/spaces/<int:space_id>/projects', methods=['POST'])
def create_project(space_id):
    user_id, err = require_auth()
    if err: return err

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    learning_goal = data.get('learning_goal', '').strip()

    if not name or not learning_goal:
        return jsonify({"error": "Project name and learning goal are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM spaces WHERE id = ? AND user_id = ?", (space_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Space not found."}), 404

    cursor.execute("""
        INSERT INTO projects (space_id, user_id, name, description, learning_goal)
        VALUES (?, ?, ?, ?, ?)
    """, (space_id, user_id, name, description, learning_goal))
    project_id = cursor.lastrowid

    # Initialize learner context for this project
    cursor.execute("""
        INSERT INTO learner_context (project_id, user_id, strengths_json, weaknesses_json, repeated_mistakes_json)
        VALUES (?, ?, '[]', '[]', '[]')
    """, (project_id, user_id))

    log_event(user_id, "project_created", space_id=space_id, project_id=project_id, event_data={"name": name, "goal": learning_goal})

    conn.commit()
    conn.close()
    return jsonify({"success": True, "project": {"id": project_id, "space_id": space_id, "name": name, "description": description, "learning_goal": learning_goal}})

@app.route('/api/projects', methods=['GET'])
def list_all_projects():
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.space_id, p.name, p.description, p.learning_goal, p.progress, p.status, p.created_at, p.updated_at,
               s.name as space_name, s.color as space_color,
               COUNT(DISTINCT m.id) as material_count,
               COUNT(DISTINCT c.id) as concept_count,
               AVG(cm.mastery_score) as avg_mastery
        FROM projects p
        JOIN spaces s ON p.space_id = s.id
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN concepts c ON p.id = c.project_id
        LEFT JOIN concept_mastery cm ON c.id = cm.concept_id AND cm.user_id = p.user_id
        WHERE p.user_id = ?
        GROUP BY p.id
        ORDER BY p.updated_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    projects = []
    for r in rows:
        p_dict = dict(r)
        p_dict['avg_mastery'] = int(round(p_dict['avg_mastery'])) if p_dict['avg_mastery'] is not None else 0
        projects.append(p_dict)
    conn.close()
    return jsonify({"success": True, "projects": projects})

@app.route('/api/projects/<int:project_id>', methods=['GET', 'DELETE'])
def handle_single_project(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'DELETE':
        # Clean up related records in child tables
        cursor.execute("DELETE FROM materials WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM concepts WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM tutor_messages WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM quizzes WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM mastery_logs WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM recommendations WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
        conn.commit()
        log_event(user_id, "project_deleted", project_id=project_id)
        conn.close()
        return jsonify({"success": True})

    cursor.execute("""
        SELECT p.*, s.name as space_name, s.color as space_color
        FROM projects p
        JOIN spaces s ON p.space_id = s.id
        WHERE p.id = ? AND p.user_id = ?
    """, (project_id, user_id))
    project = cursor.fetchone()
    conn.close()

    if not project:
        return jsonify({"error": "Project not found."}), 404

    return jsonify({"success": True, "project": dict(project)})

@app.route('/api/projects/<int:project_id>/dashboard', methods=['GET'])
def get_project_dashboard(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    project = cursor.fetchone()
    if not project:
        conn.close()
        return jsonify({"error": "Project not found."}), 404

    # Materials summary
    cursor.execute("SELECT id, filename, status, page_count, created_at FROM materials WHERE project_id = ?", (project_id,))
    materials = [dict(r) for r in cursor.fetchall()]

    # Concept mastery & growth
    mastery_data = get_project_mastery_and_growth(project_id, user_id)

    # Active recommendations
    recommendations = get_project_recommendations(project_id, user_id)

    # Recent activity events
    cursor.execute("""
        SELECT event_type, event_data_json, created_at 
        FROM learning_events 
        WHERE project_id = ? AND user_id = ? 
        ORDER BY created_at DESC LIMIT 5
    """, (project_id, user_id))
    recent_activity = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "project": dict(project),
        "materials": materials,
        "mastery": mastery_data,
        "recommendations": recommendations,
        "recent_activity": recent_activity
    })

# -------------------------------------------------------------
# Learning Materials & Knowledge Extraction (Asynchronous)
# -------------------------------------------------------------
@app.route('/api/projects/<int:project_id>/materials/upload', methods=['POST'])
def upload_project_material(project_id):
    user_id, err = require_auth()
    if err: return err

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Project not found."}), 404

    filename = secure_filename(file.filename)
    material_id = str(uuid.uuid4())
    stored_name = f"{material_id}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    file.save(filepath)

    file_size = os.path.getsize(filepath)
    file_ext = os.path.splitext(filename)[1].lower()

    # Create initial material record with status 'queued'
    cursor.execute("""
        INSERT INTO materials (id, project_id, user_id, filename, file_path, file_type, file_size, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
    """, (material_id, project_id, user_id, filename, filepath, file_ext, file_size))
    conn.commit()
    conn.close()

    # Enqueue for asynchronous background processing
    queue_material_for_processing(material_id)

    log_event(user_id, "material_uploaded", project_id=project_id, event_data={"material_id": material_id, "filename": filename})

    return jsonify({
        "success": True,
        "material_id": material_id,
        "filename": filename,
        "status": "queued",
        "message": "Material uploaded successfully and queued for background processing."
    })

@app.route('/api/projects/<int:project_id>/materials', methods=['GET'])
def get_project_materials(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filename, file_type, file_size, status, error_message, page_count, created_at, updated_at
        FROM materials
        WHERE project_id = ? AND user_id = ?
        ORDER BY created_at DESC
    """, (project_id, user_id))
    materials = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "materials": materials})

@app.route('/api/projects/<int:project_id>/materials/<material_id>/status', methods=['GET'])
def get_material_status(project_id, material_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filename, status, error_message, page_count, updated_at
        FROM materials
        WHERE id = ? AND project_id = ? AND user_id = ?
    """, (material_id, project_id, user_id))
    mat = cursor.fetchone()
    conn.close()

    if not mat:
        return jsonify({"error": "Material not found."}), 404

    return jsonify({"success": True, "material": dict(mat)})

@app.route('/api/projects/<int:project_id>/materials/<material_id>/retry', methods=['POST'])
def retry_material_processing(project_id, material_id):
    user_id, err = require_auth()
    if err: return err

    queue_material_for_processing(material_id)
    return jsonify({"success": True, "message": "Material re-queued for processing."})

@app.route('/api/projects/<int:project_id>/concepts', methods=['GET'])
def get_project_concepts(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.description, cm.mastery_score, cm.trend
        FROM concepts c
        LEFT JOIN concept_mastery cm ON c.id = cm.concept_id AND cm.user_id = ?
        WHERE c.project_id = ?
        ORDER BY cm.mastery_score ASC
    """, (user_id, project_id))
    concepts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "concepts": concepts})

# -------------------------------------------------------------
# AI Tutor with Citations & Unsupported Question Handling
# -------------------------------------------------------------
@app.route('/api/projects/<int:project_id>/tutor/chat', methods=['POST'])
def tutor_chat(project_id):
    user_id, err = require_auth()
    if err: return err

    data = request.get_json() or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        result = ask_tutor(project_id, user_id, message)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"error": f"Tutor Error: {str(e)}"}), 500

@app.route('/api/projects/<int:project_id>/tutor/history', methods=['GET', 'DELETE'])
def tutor_history(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'DELETE':
        cursor.execute("DELETE FROM tutor_messages WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    cursor.execute("""
        SELECT id, role, content, citations_json, evidence_sufficient, created_at
        FROM tutor_messages
        WHERE project_id = ? AND user_id = ?
        ORDER BY id ASC
    """, (project_id, user_id))
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for r in rows:
        messages.append({
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "citations": json.loads(r["citations_json"]) if r["citations_json"] else [],
            "evidence_sufficient": bool(r["evidence_sufficient"]),
            "created_at": r["created_at"]
        })

    return jsonify({"success": True, "messages": messages})

# -------------------------------------------------------------
# Adaptive Quiz & Assessment (MCQ + Open-Ended)
# -------------------------------------------------------------
@app.route('/api/projects/<int:project_id>/quiz/generate', methods=['POST'])
def generate_quiz_endpoint(project_id):
    user_id, err = require_auth()
    if err: return err

    data = request.get_json() or {}
    num_questions = int(data.get("num_questions", 4))

    try:
        quiz = generate_adaptive_quiz(project_id, user_id, num_questions=num_questions)
        log_event(user_id, "quiz_generated", project_id=project_id, event_data={"quiz_id": quiz["quiz_id"], "difficulty": quiz["difficulty"]})
        return jsonify({"success": True, "quiz": quiz})
    except Exception as e:
        return jsonify({"error": f"Failed to generate quiz: {str(e)}"}), 500

@app.route('/api/projects/<int:project_id>/quiz/evaluate', methods=['POST'])
def evaluate_quiz_endpoint(project_id):
    user_id, err = require_auth()
    if err: return err

    data = request.get_json() or {}
    quiz_id = data.get("quiz_id")
    answers = data.get("answers", []) # list of {"question_id": int, "user_answer": str}

    if not quiz_id or not answers:
        return jsonify({"error": "Quiz ID and answers are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create quiz attempt
    cursor.execute("""
        INSERT INTO quiz_attempts (quiz_id, project_id, user_id, total_questions)
        VALUES (?, ?, ?, ?)
    """, (quiz_id, project_id, user_id, len(answers)))
    attempt_id = cursor.lastrowid

    evaluated_answers = []
    total_score_sum = 0
    correct_count = 0

    for ans in answers:
        q_id = ans.get("question_id")
        user_answer = ans.get("user_answer", "").strip()

        cursor.execute("SELECT * FROM quiz_questions WHERE id = ?", (q_id,))
        q_row = cursor.fetchone()
        if not q_row:
            continue

        q_type = q_row["question_type"]
        score = 0
        is_correct = False
        ai_feedback = ""
        key_covered = []
        missing_concepts = []

        if q_type == "mcq":
            correct_ans = q_row["correct_answer"].strip()
            # Normalize comparison
            if user_answer.lower().startswith(correct_ans.lower()[:2]) or user_answer.strip().lower() == correct_ans.lower():
                is_correct = True
                score = 100
                ai_feedback = f"Correct! {q_row['rubric']}"
            else:
                is_correct = False
                score = 0
                ai_feedback = f"Incorrect. The correct answer is: {correct_ans}. {q_row['rubric']}"
        else:
            # Open-Ended AI Evaluation
            eval_res = evaluate_open_ended_answer(
                question_text=q_row["question_text"],
                rubric=q_row["rubric"],
                expected_answer=q_row["correct_answer"],
                user_answer=user_answer,
                user_id=user_id,
                project_id=project_id
            )
            score = eval_res.get("score", 0)
            is_correct = eval_res.get("is_correct", score >= 65)
            ai_feedback = eval_res.get("feedback", "")
            key_covered = eval_res.get("key_concepts_covered", [])
            missing_concepts = eval_res.get("missing_concepts", [])

        if is_correct:
            correct_count += 1
        total_score_sum += score

        cursor.execute("""
            INSERT INTO quiz_answers (attempt_id, question_id, user_answer, is_correct, score, ai_feedback, key_concepts_covered, missing_concepts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (attempt_id, q_id, user_answer, 1 if is_correct else 0, score, ai_feedback, json.dumps(key_covered), json.dumps(missing_concepts)))

        evaluated_answers.append({
            "question_id": q_id,
            "question_text": q_row["question_text"],
            "question_type": q_type,
            "user_answer": user_answer,
            "is_correct": is_correct,
            "score": score,
            "feedback": ai_feedback,
            "key_concepts_covered": key_covered,
            "missing_concepts": missing_concepts
        })

    avg_score = int(round(total_score_sum / float(len(answers)))) if answers else 0
    summary_feedback = f"You answered {correct_count} of {len(answers)} questions correctly with an overall assessment score of {avg_score}%."

    cursor.execute("""
        UPDATE quiz_attempts 
        SET correct_answers = ?, total_score = ?, feedback_summary = ?
        WHERE id = ?
    """, (correct_count, avg_score, summary_feedback, attempt_id))
    conn.commit()
    conn.close()

    # Trigger intelligent post-quiz workflow asynchronously / sequentially
    trigger_post_quiz_workflow(attempt_id, quiz_id, project_id, user_id, evaluated_answers)

    return jsonify({
        "success": True,
        "attempt_id": attempt_id,
        "total_score": avg_score,
        "correct_answers": correct_count,
        "total_questions": len(answers),
        "feedback_summary": summary_feedback,
        "answers": evaluated_answers
    })

@app.route('/api/projects/<int:project_id>/quiz/history', methods=['GET'])
def get_quiz_history(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT qa.id, qa.total_questions, qa.correct_answers, qa.total_score, qa.feedback_summary, qa.attempted_at, q.title as quiz_title
        FROM quiz_attempts qa
        JOIN quizzes q ON qa.quiz_id = q.id
        WHERE qa.project_id = ? AND qa.user_id = ?
        ORDER BY qa.attempted_at DESC LIMIT 10
    """, (project_id, user_id))
    attempts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "attempts": attempts})

# -------------------------------------------------------------
# Concept Mastery, Growth & Recommendations
# -------------------------------------------------------------
@app.route('/api/projects/<int:project_id>/mastery', methods=['GET'])
def get_mastery(project_id):
    user_id, err = require_auth()
    if err: return err

    data = get_project_mastery_and_growth(project_id, user_id)
    return jsonify({"success": True, **data})

@app.route('/api/projects/<int:project_id>/growth', methods=['GET'])
def get_growth(project_id):
    user_id, err = require_auth()
    if err: return err

    data = get_project_mastery_and_growth(project_id, user_id)
    return jsonify({"success": True, **data})

@app.route('/api/projects/<int:project_id>/recommendations', methods=['GET'])
def get_recommendations_endpoint(project_id):
    user_id, err = require_auth()
    if err: return err

    recs = get_project_recommendations(project_id, user_id)
    return jsonify({"success": True, "recommendations": recs})

@app.route('/api/projects/<int:project_id>/recommendations/<int:rec_id>/complete', methods=['POST'])
def complete_recommendation(project_id, rec_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE recommendations SET is_completed = 1 WHERE id = ? AND project_id = ? AND user_id = ?", (rec_id, project_id, user_id))
    conn.commit()
    conn.close()

    log_event(user_id, "recommendation_completed", project_id=project_id, event_data={"recommendation_id": rec_id})
    return jsonify({"success": True})

# -------------------------------------------------------------
# Analytics & Events
# -------------------------------------------------------------
@app.route('/api/projects/<int:project_id>/analytics', methods=['GET'])
def get_project_analytics(project_id):
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    # Event stream
    cursor.execute("""
        SELECT event_type, event_data_json, created_at
        FROM learning_events
        WHERE project_id = ? AND user_id = ?
        ORDER BY created_at DESC LIMIT 30
    """, (project_id, user_id))
    events = [dict(r) for r in cursor.fetchall()]

    # Quiz score trends
    cursor.execute("""
        SELECT total_score, attempted_at FROM quiz_attempts
        WHERE project_id = ? AND user_id = ?
        ORDER BY attempted_at ASC LIMIT 15
    """, (project_id, user_id))
    quiz_trends = [dict(r) for r in cursor.fetchall()]

    # AI usage breakdown for this project
    cursor.execute("""
        SELECT feature, COUNT(id) as call_count, SUM(total_tokens) as tokens, AVG(latency_ms) as avg_latency
        FROM ai_usage_logs
        WHERE project_id = ? AND user_id = ?
        GROUP BY feature
    """, (project_id, user_id))
    ai_stats = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "events": events,
        "quiz_trends": quiz_trends,
        "ai_stats": ai_stats
    })

@app.route('/api/analytics/global', methods=['GET'])
def get_global_analytics():
    user_id, err = require_auth()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(DISTINCT s.id) as spaces_count,
               COUNT(DISTINCT p.id) as projects_count,
               COUNT(DISTINCT m.id) as materials_count,
               COUNT(DISTINCT qa.id) as quiz_attempts_count
        FROM users u
        LEFT JOIN spaces s ON s.user_id = u.id
        LEFT JOIN projects p ON p.user_id = u.id
        LEFT JOIN materials m ON m.user_id = u.id
        LEFT JOIN quiz_attempts qa ON qa.user_id = u.id
        WHERE u.id = ?
    """, (user_id,))
    kpis = dict(cursor.fetchone())

    conn.close()
    return jsonify({"success": True, "global_stats": kpis})

# -------------------------------------------------------------
# Admin Dashboard & AI Observability
# -------------------------------------------------------------
@app.route('/api/admin/overview', methods=['GET'])
def admin_overview():
    user_id, err = require_admin()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as user_count FROM users")
    user_count = cursor.fetchone()["user_count"]

    cursor.execute("SELECT COUNT(*) as space_count FROM spaces")
    space_count = cursor.fetchone()["space_count"]

    cursor.execute("SELECT COUNT(*) as project_count FROM projects")
    project_count = cursor.fetchone()["project_count"]

    cursor.execute("SELECT COUNT(*) as material_count FROM materials")
    material_count = cursor.fetchone()["material_count"]

    cursor.execute("""
        SELECT COUNT(*) as call_count,
               SUM(total_tokens) as total_tokens,
               SUM(estimated_cost_usd) as total_cost,
               AVG(latency_ms) as avg_latency
        FROM ai_usage_logs
    """)
    ai_kpi = cursor.fetchone()

    conn.close()

    return jsonify({
        "success": True,
        "users": user_count,
        "spaces": space_count,
        "projects": project_count,
        "materials": material_count,
        "ai_calls": ai_kpi["call_count"] or 0,
        "total_tokens": ai_kpi["total_tokens"] or 0,
        "estimated_cost_usd": round(ai_kpi["total_cost"] or 0.0, 4),
        "average_latency_ms": int(round(ai_kpi["avg_latency"] or 0))
    })

@app.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    user_id, err = require_admin()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.role, u.created_at,
               COUNT(DISTINCT p.id) as project_count,
               COUNT(DISTINCT qa.id) as quiz_count,
               COUNT(DISTINCT l.id) as ai_calls_count
        FROM users u
        LEFT JOIN projects p ON p.user_id = u.id
        LEFT JOIN quiz_attempts qa ON qa.user_id = u.id
        LEFT JOIN ai_usage_logs l ON l.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "users": users})

@app.route('/api/admin/users/<int:target_user_id>/journey', methods=['GET'])
def admin_user_journey(target_user_id):
    user_id, err = require_admin()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username, role, created_at FROM users WHERE id = ?", (target_user_id,))
    target_user = cursor.fetchone()
    if not target_user:
        conn.close()
        return jsonify({"error": "User not found."}), 404

    # Projects
    cursor.execute("SELECT id, name, learning_goal, progress, created_at FROM projects WHERE user_id = ?", (target_user_id,))
    projects = [dict(r) for r in cursor.fetchall()]

    # Quizzes
    cursor.execute("""
        SELECT qa.id, qa.total_score, qa.attempted_at, q.title 
        FROM quiz_attempts qa 
        JOIN quizzes q ON qa.quiz_id = q.id 
        WHERE qa.user_id = ? ORDER BY qa.attempted_at DESC LIMIT 10
    """, (target_user_id,))
    quizzes = [dict(r) for r in cursor.fetchall()]

    # Recent AI Interactions
    cursor.execute("""
        SELECT feature, model, latency_ms, total_tokens, estimated_cost_usd, status, created_at
        FROM ai_usage_logs
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 15
    """, (target_user_id,))
    ai_interactions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "user": dict(target_user),
        "projects": projects,
        "quizzes": quizzes,
        "ai_interactions": ai_interactions
    })

@app.route('/api/admin/activity', methods=['GET'])
def admin_activity():
    user_id, err = require_admin()
    if err: return err

    user_filter = request.args.get('user_id')
    event_filter = request.args.get('event_type')
    limit = int(request.args.get('limit', 50))

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT le.id, le.user_id, u.username, le.project_id, p.name as project_name, le.event_type, le.event_data_json, le.created_at
        FROM learning_events le
        JOIN users u ON le.user_id = u.id
        LEFT JOIN projects p ON le.project_id = p.id
        WHERE 1=1
    """
    params = []
    if user_filter:
        query += " AND le.user_id = ?"
        params.append(user_filter)
    if event_filter:
        query += " AND le.event_type = ?"
        params.append(event_filter)

    query += " ORDER BY le.created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, tuple(params))
    events = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "activity": events})

@app.route('/api/admin/ai-observability', methods=['GET'])
def admin_ai_observability():
    user_id, err = require_admin()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()

    # Breakdown by feature
    cursor.execute("""
        SELECT feature, COUNT(*) as count, AVG(latency_ms) as avg_latency, SUM(total_tokens) as total_tokens, SUM(estimated_cost_usd) as cost
        FROM ai_usage_logs
        GROUP BY feature
    """)
    by_feature = [dict(r) for r in cursor.fetchall()]

    # Breakdown by model
    cursor.execute("""
        SELECT model, COUNT(*) as count, AVG(latency_ms) as avg_latency, SUM(total_tokens) as total_tokens, SUM(estimated_cost_usd) as cost
        FROM ai_usage_logs
        GROUP BY model
    """)
    by_model = [dict(r) for r in cursor.fetchall()]

    # Recent error logs
    cursor.execute("""
        SELECT id, user_id, feature, model, latency_ms, error_message, created_at
        FROM ai_usage_logs
        WHERE status = 'failed'
        ORDER BY created_at DESC LIMIT 10
    """)
    failures = [dict(r) for r in cursor.fetchall()]

    # Recent requests
    cursor.execute("""
        SELECT id, user_id, feature, model, latency_ms, total_tokens, estimated_cost_usd, status, created_at
        FROM ai_usage_logs
        ORDER BY created_at DESC LIMIT 25
    """)
    recent_logs = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "by_feature": by_feature,
        "by_model": by_model,
        "failures": failures,
        "recent_logs": recent_logs
    })

@app.route('/api/admin/jobs', methods=['GET'])
def admin_jobs():
    user_id, err = require_admin()
    if err: return err

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, job_type, status, payload_json, retries, error_message, created_at, updated_at
        FROM background_jobs
        ORDER BY updated_at DESC LIMIT 30
    """)
    jobs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "jobs": jobs})

@app.route('/api/admin/evaluations', methods=['GET'])
def admin_evaluations_list():
    user_id, err = require_admin()
    if err: return err

    evals = get_latest_evaluations(limit=30)
    return jsonify({"success": True, "evaluations": evals})

@app.route('/api/admin/evaluations/run', methods=['POST'])
def admin_run_evaluations():
    user_id, err = require_admin()
    if err: return err

    summary = run_evaluation_suite(user_id=user_id)
    return jsonify({"success": True, "summary": summary})

@app.route('/api/admin/system-health', methods=['GET'])
def admin_system_health():
    user_id, err = require_admin()
    if err: return err

    providers = get_configured_providers()
    
    # DB status
    db_healthy = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        db_healthy = True
        conn.close()
    except Exception:
        db_healthy = False

    return jsonify({
        "success": True,
        "database_connected": db_healthy,
        "background_worker_active": True,
        "llm_providers": providers,
        "uptime_status": "operational",
        "system_time": datetime.now().isoformat()
    })

# -------------------------------------------------------------
# Configuration & API Key Settings
# -------------------------------------------------------------
@app.route('/api/check-key', methods=['GET'])
def check_key():
    providers = get_configured_providers()
    configured = providers["groq"] or providers["gemini"]
    active = "groq" if providers["groq"] else ("gemini" if providers["gemini"] else "none")
    return jsonify({
        "configured": configured,
        "provider": active,
        "details": providers
    })

@app.route('/api/save-key', methods=['POST'])
def save_key():
    data = request.json or {}
    api_key = data.get("api_key", "").strip()
    provider = data.get("provider", "groq").strip().lower()

    if not api_key:
        return jsonify({"success": False, "error": "API key cannot be empty."}), 400

    key_name = "GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"
    os.environ[key_name] = api_key

    # Save to .env
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        lines = []
        key_found = False
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith(f"{key_name}="):
                        lines.append(f"{key_name}={api_key}\n")
                        key_found = True
                    else:
                        lines.append(line)
        if not key_found:
            lines.append(f"{key_name}={api_key}\n")

        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return jsonify({"success": True, "message": f"{provider.upper()} API key saved successfully to .env!"})
    except Exception as e:
        return jsonify({"success": True, "message": f"{provider.upper()} key set in memory: {str(e)}"})

# -------------------------------------------------------------
# Career & Study Readiness Labs (Resume Analyzer, Planner, Tools)
# -------------------------------------------------------------
def extract_pdf_text_pdfplumber(path):
    import pdfplumber
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.lower()
    except Exception as e:
        print(f"pdfplumber extraction error: {e}")
        return ""

def extract_skills_from_text(text):
    found_skills = []
    text_lower = text.lower()
    for skill in skills_list:
        skill_escaped = re.escape(skill)
        if "+" in skill or "#" in skill or "." in skill:
            pattern = rf"\b{skill_escaped}"
        else:
            pattern = rf"\b{skill_escaped}\b"
        if re.search(pattern, text_lower):
            found_skills.append(skill)
    return sorted(list(set(found_skills)))

@app.route('/api/analyze-resume', methods=['POST'])
def analyze_resume():
    user_id = session.get('user_id')
    if 'resume' not in request.files:
        return jsonify({"error": "No resume file uploaded"}), 400

    file = request.files['resume']
    jd = request.form.get('job_description', '').strip()

    if file.filename == '':
        return jsonify({"error": "No resume file selected"}), 400
    if not jd:
        return jsonify({"error": "Job description is required"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_resume_{uuid.uuid4()}_{filename}")
    file.save(filepath)

    resume_text = ""
    if filename.lower().endswith(".pdf"):
        resume_text = extract_pdf_text_pypdf(filepath)
        if not resume_text or not resume_text.strip():
            resume_text = extract_pdf_text_pdfplumber(filepath)
    elif filename.lower().endswith(".docx"):
        resume_text = extract_docx_text(filepath)
    else:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                resume_text = f.read()
        except Exception:
            pass

    try:
        os.remove(filepath)
    except Exception:
        pass

    if not resume_text or not resume_text.strip():
        return jsonify({"error": "Failed to extract readable text from resume. Ensure it is not scanned or empty."}), 400

    resume_skills = extract_skills_from_text(resume_text)
    jd_skills = extract_skills_from_text(jd)
    matched_skills = list(set(resume_skills).intersection(set(jd_skills)))
    missing_skills = list(set(jd_skills) - set(resume_skills))

    # Calculate ATS similarity score
    ats_score = 0.0
    similarity = 0.0
    try:
        cv = CountVectorizer()
        matrix = cv.fit_transform([resume_text, jd])
        similarity = cosine_similarity(matrix)[0][1]
    except Exception:
        pass

    if jd_skills:
        skill_match_ratio = len(matched_skills) / len(jd_skills)
        ats_score = round((0.7 * skill_match_ratio + 0.3 * similarity) * 100, 2)
    else:
        ats_score = round(similarity * 100, 2)

    if matched_skills and ats_score < 10.0:
        ats_score = min(35.0, 10.0 * len(matched_skills))

    # Generate personalized learning roadmap via AI
    suggestions = ""
    try:
        prompt = f"""
        Analyze student resume skills vs target job requirements:
        Resume Skills: {', '.join(resume_skills) if resume_skills else 'None detected'}
        Target Job Skills: {', '.join(jd_skills) if jd_skills else 'None detected'}
        Missing Skills: {', '.join(missing_skills) if missing_skills else 'None identified'}
        Current Match Score: {ats_score}%
        
        Provide structured Markdown feedback:
        1. **Executive Compatibility Summary**: 2-3 sentences.
        2. **Critical Gaps & Learning Roadmap**: Group missing skills into logical study areas.
        3. **Specific Recommendations**: Free courses, textbooks, project ideas to bridge the gap.
        4. **Resume Improvement Tips**: Action verbs and formatting advice.
        """
        suggestions = call_ai(prompt, system_instruction="You are an expert ATS Career Coach and Academic Advisor.", feature="resume_gap_analysis", user_id=user_id)
    except Exception as e:
        suggestions = f"### Learning Roadmap\n*Configured LLM error: {str(e)}*"

    if user_id:
        log_event(user_id, "resume_analyzed", event_data={"ats_score": ats_score, "missing_skills_count": len(missing_skills)})

    return jsonify({
        "success": True,
        "ats_score": ats_score,
        "resume_skills": resume_skills,
        "job_description_skills": jd_skills,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "suggestions": suggestions
    })

@app.route('/api/create-project-from-gap', methods=['POST'])
def create_project_from_gap():
    """Bridges the Resume Analyzer into the core AI Study Companion loop!"""
    user_id, err = require_auth()
    if err: return err

    data = request.get_json() or {}
    missing_skills = data.get("missing_skills", [])
    target_role = data.get("target_role", "Target Role").strip()

    if not missing_skills:
        return jsonify({"error": "No missing skills provided to bridge."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find or create a "Career & Skill Readiness" space
    cursor.execute("SELECT id FROM spaces WHERE user_id = ? AND name = 'Career & Skill Readiness'", (user_id,))
    sp_row = cursor.fetchone()
    if sp_row:
        space_id = sp_row["id"]
    else:
        cursor.execute("""
            INSERT INTO spaces (user_id, name, description, icon, color)
            VALUES (?, 'Career & Skill Readiness', 'Dedicated space for bridging industry skill gaps and interview prep', 'briefcase', '#10b981')
        """, (user_id,))
        space_id = cursor.lastrowid

    # Create project targeting missing skills
    proj_name = f"Master: {', '.join(missing_skills[:3])}" + (f" (+{len(missing_skills)-3} more)" if len(missing_skills) > 3 else "")
    learning_goal = f"Bridge skill gap for {target_role}: master {', '.join(missing_skills)}"
    
    cursor.execute("""
        INSERT INTO projects (space_id, user_id, name, description, learning_goal)
        VALUES (?, ?, ?, 'Auto-generated from ATS Resume Gap Analysis', ?)
    """, (space_id, user_id, proj_name, learning_goal))
    proj_id = cursor.lastrowid

    # Initialize missing skills as concepts requiring attention!
    for skill in missing_skills[:8]:
        cursor.execute("""
            INSERT INTO concepts (project_id, name, description)
            VALUES (?, ?, ?)
        """, (proj_id, skill.capitalize(), f"Identified as missing skill requirement for {target_role}."))
        c_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend)
            VALUES (?, ?, ?, 20, 'requiring_attention')
        """, (proj_id, user_id, c_id))

    # Initialize learner context
    cursor.execute("""
        INSERT INTO learner_context (project_id, user_id, strengths_json, weaknesses_json, repeated_mistakes_json)
        VALUES (?, ?, '[]', ?, '[]')
    """, (proj_id, user_id, json.dumps(missing_skills)))

    conn.commit()
    conn.close()

    # Generate immediate targeted recommendations
    generate_project_recommendations(proj_id, user_id)
    log_event(user_id, "project_created_from_gap", space_id=space_id, project_id=proj_id, event_data={"skills": missing_skills})

    return jsonify({
        "success": True,
        "project_id": proj_id,
        "space_id": space_id,
        "message": f"Successfully created project '{proj_name}' with {len(missing_skills)} target concepts!"
    })

@app.route('/api/study-assistant/plan', methods=['POST'])
def generate_study_plan():
    user_id = session.get('user_id')
    data = request.json or {}
    target_topic = data.get("target_topic", "").strip() or data.get("target_role", "").strip()
    duration_weeks = int(data.get("duration_weeks", 4))
    hours_per_week = int(data.get("hours_per_week", 10))
    skill_level = data.get("skill_level", "Beginner").strip()
    current_skills = data.get("current_skills", "").strip()

    if not target_topic:
        return jsonify({"error": "Target topic or goal is required."}), 400

    prompt = f"""
    Create a structured, multi-week study plan:
    - Target: {target_topic}
    - Duration: {duration_weeks} Weeks
    - Hours/Week: {hours_per_week}
    - Current Level: {skill_level}
    - Known Skills: {current_skills or 'None'}

    Format in clean Markdown:
    1. **Overview & Milestones**
    2. **Weekly Curriculum Breakdown** (Core concepts, daily focus, mini coding/practical tasks)
    3. **Key Capstone Projects & Knowledge Checks**
    """
    try:
        response_text = call_ai(prompt, system_instruction="You are an expert university curriculum advisor.", feature="study_plan_generation", user_id=user_id)
        return jsonify({"success": True, "plan": response_text})
    except Exception as e:
        return jsonify({"error": f"Failed to generate study plan: {str(e)}"}), 500

@app.route('/api/summarize-youtube', methods=['POST'])
def summarize_youtube():
    user_id = session.get('user_id')
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "YouTube URL is required."}), 400

    # Extract Video ID
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    video_id = match.group(1) if match else None
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL format."}), 400

    transcript_text = ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        transcript = transcript_list.find_transcript(['en'])
        data_items = transcript.fetch()
        transcript_text = " ".join([item.text for item in data_items])
    except Exception as e:
        return jsonify({"error": f"Could not extract transcript: {str(e)}. Ensure the video has English captions."}), 400

    prompt = (
        "You are an expert study companion. Summarize the following educational YouTube video transcript. "
        "Provide a concise summary, followed by structured bullet points of core technical concepts, equations, and takeaways:\n\n"
        f"Transcript:\n{transcript_text[:12000]}"
    )
    try:
        summary = call_ai(prompt, system_instruction="You are an expert academic tutor summarizing lecture videos.", feature="youtube_summary", user_id=user_id)
        return jsonify({"success": True, "summary": summary, "video_id": video_id})
    except Exception as e:
        return jsonify({"error": f"Summarization failed: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def general_chat():
    user_id = session.get('user_id')
    data = request.json or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Message is required."}), 400

    system_instruction = (
        "You are an intelligent, encouraging academic tutor and STEM problem solver. "
        "Explain complex technical topics simply, provide clear equations and code snippets when helpful, "
        "and guide the student to master concepts thoroughly."
    )
    try:
        response_text = call_ai(message, system_instruction=system_instruction, history=history, feature="general_chat", user_id=user_id)
        return jsonify({"success": True, "response": response_text})
    except Exception as e:
        app.logger.warning(f"AI chat call encountered error: {e}")
        fallback_msg = (
            f"**LearnMate Academic Assistant**:\n\n"
            f"I encountered an issue connecting to the AI model provider: `{str(e)}`.\n\n"
            f"**To enable live AI inference:**\n"
            f"1. Open **Settings & LLM** in the left sidebar menu.\n"
            f"2. Enter your free **Groq API Key** (e.g. `gsk_...`) or **Google Gemini API Key**.\n"
            f"3. Click **Save Settings**.\n\n"
            f"*You can also navigate to **Learning Spaces** to create courses and upload study documents!*"
        )
        return jsonify({"success": True, "response": fallback_msg})

# -------------------------------------------------------------
# Application Entry Point
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)

