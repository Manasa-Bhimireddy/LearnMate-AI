import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Enable WAL mode and foreign keys for high-concurrency background jobs
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'")
    except sqlite3.OperationalError:
        pass


    # Spaces Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT 'book-open',
            color TEXT DEFAULT '#06b6d4',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Projects Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            space_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            learning_goal TEXT,
            status TEXT DEFAULT 'active',
            progress INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Materials Table (Async processing states: queued -> processing -> ready | failed)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            status TEXT DEFAULT 'queued',
            error_message TEXT,
            page_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Material Chunks Table (for grounded retrieval with page references)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id TEXT NOT NULL,
            project_id INTEGER NOT NULL,
            page_number INTEGER DEFAULT 1,
            chunk_index INTEGER DEFAULT 0,
            content TEXT NOT NULL,
            embedding_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)

    # Extracted Concepts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            extracted_from_material_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)

    # Concept Mastery Table (Score 0-100, trend: improving | stable | requiring_attention)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_mastery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            concept_id INTEGER NOT NULL,
            mastery_score INTEGER DEFAULT 20,
            trend TEXT DEFAULT 'stable',
            history_json TEXT DEFAULT '[]',
            last_assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (concept_id) REFERENCES concepts(id) ON DELETE CASCADE,
            UNIQUE(project_id, user_id, concept_id)
        )
    """)

    # Quizzes Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            quiz_type TEXT DEFAULT 'adaptive',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Quiz Questions Table (MCQ or Open-ended)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            concept_id INTEGER,
            concept_name TEXT,
            question_type TEXT DEFAULT 'mcq',
            question_text TEXT NOT NULL,
            options_json TEXT,
            correct_answer TEXT,
            rubric TEXT,
            difficulty TEXT DEFAULT 'medium',
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        )
    """)

    # Quiz Attempts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            total_questions INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            feedback_summary TEXT,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Quiz Answers Table (Records each answer, AI grading feedback, missing concepts)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            user_answer TEXT,
            is_correct INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            ai_feedback TEXT,
            key_concepts_covered TEXT,
            missing_concepts TEXT,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES quiz_questions(id) ON DELETE CASCADE
        )
    """)

    # Tutor Messages Table (Conversations with Citations and Evidence check)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations_json TEXT DEFAULT '[]',
            evidence_sufficient INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Persistent Learner Context Table (Strengths, Weaknesses, Repeated Mistakes, Preferences)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learner_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            strengths_json TEXT DEFAULT '[]',
            weaknesses_json TEXT DEFAULT '[]',
            repeated_mistakes_json TEXT DEFAULT '[]',
            preferences_json TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(project_id, user_id)
        )
    """)

    # Recommendations Table ("What should I do next?")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            action_type TEXT DEFAULT 'quiz',
            action_target TEXT,
            reason TEXT,
            is_completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Learning Events Table (Event-driven learning)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            space_id INTEGER,
            project_id INTEGER,
            event_type TEXT NOT NULL,
            event_data_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # AI Usage & Observability Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            project_id INTEGER,
            feature TEXT NOT NULL,
            model TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0.0,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Background Jobs Queue Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS background_jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT DEFAULT 'queued',
            payload_json TEXT NOT NULL,
            retries INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # AI Evaluation Suite Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT NOT NULL,
            category TEXT NOT NULL,
            input_prompt TEXT NOT NULL,
            expected_behavior TEXT NOT NULL,
            actual_output TEXT NOT NULL,
            score INTEGER DEFAULT 100,
            passed INTEGER DEFAULT 1,
            latency_ms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create default admin user if not exists
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        from werkzeug.security import generate_password_hash
        admin_hash = generate_password_hash("admin123")
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')",
            (admin_hash,)
        )

    # Create default demo student if not exists
    cursor.execute("SELECT id FROM users WHERE username = 'student'")
    if not cursor.fetchone():
        from werkzeug.security import generate_password_hash
        student_hash = generate_password_hash("student123")
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES ('student', ?, 'student')",
            (student_hash,)
        )
        student_id = cursor.lastrowid
        
        # Starter Space
        cursor.execute("""
            INSERT INTO spaces (user_id, name, description, icon, color)
            VALUES (?, 'Computer Science & AI', 'Foundational systems, algorithms, and deep learning models', 'cpu', '#06b6d4')
        """, (student_id,))
        demo_space_id = cursor.lastrowid

        # Starter Project
        cursor.execute("""
            INSERT INTO projects (space_id, user_id, name, description, learning_goal, progress)
            VALUES (?, ?, 'Virtual Memory & Paging', 'Operating systems memory management and address translation', 'Understand page tables, TLB, and page replacement algorithms', 65)
        """, (demo_space_id, student_id))
        demo_proj_id = cursor.lastrowid

        # Starter Concepts
        cursor.execute("INSERT INTO concepts (project_id, name, description) VALUES (?, 'Page Tables & TLB', 'Hierarchical mapping of virtual addresses to physical frames with cache translation.')", (demo_proj_id,))
        c1 = cursor.lastrowid
        cursor.execute("INSERT INTO concepts (project_id, name, description) VALUES (?, 'Page Fault Handling', 'Interrupt mechanism that retrieves missing pages from secondary swap storage.')", (demo_proj_id,))
        c2 = cursor.lastrowid
        cursor.execute("INSERT INTO concepts (project_id, name, description) VALUES (?, 'LRU Replacement Algorithm', 'Page eviction strategy replacing the least recently accessed page.')", (demo_proj_id,))
        c3 = cursor.lastrowid

        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, ?, ?, 82, 'improving')", (demo_proj_id, student_id, c1))
        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, ?, ?, 60, 'stable')", (demo_proj_id, student_id, c2))
        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, ?, ?, 38, 'requiring_attention')", (demo_proj_id, student_id, c3))

        # Starter Learner Context
        cursor.execute("""
            INSERT INTO learner_context (project_id, user_id, strengths_json, weaknesses_json, repeated_mistakes_json)
            VALUES (?, ?, '["Page Tables & TLB"]', '["LRU Replacement Algorithm"]', '["Confused FIFO with optimal Belady anomaly"]')
        """, (demo_proj_id, student_id))

        # Starter Recommendation
        cursor.execute("""
            INSERT INTO recommendations (project_id, user_id, title, description, action_type, action_target, reason)
            VALUES (?, ?, 'Reinforce LRU Page Replacement', 'Review LRU vs FIFO replacement algorithms and take an adaptive 3-question quiz.', 'quiz', 'LRU Replacement Algorithm', 'Targeting low mastery in LRU')
        """, (demo_proj_id, student_id))

    conn.commit()
    conn.close()
    print("LearnMate AI Database schema initialized successfully.")

if __name__ == "__main__":
    init_db()
