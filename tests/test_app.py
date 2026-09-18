import os
import unittest
import json
import sqlite3
from app import app
from models import init_db, get_db_connection
from services.mastery_service import update_concept_mastery_from_assessment, get_project_mastery_and_growth
from services.retrieval_service import retrieve_project_context
from services.assessment_service import select_target_concepts_and_difficulty

class AIStudyCompanionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        init_db()

    def setUp(self):
        self.client = app.test_client()

    def test_01_user_registration_and_login(self):
        """Test user registration, login, and default space/project setup."""
        username = f"testuser_{os.urandom(4).hex()}"
        res = self.client.post('/api/register', json={
            "username": username,
            "password": "password123",
            "role": "student"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["username"], username)

        # Verify session
        session_res = self.client.get('/api/session')
        session_data = session_res.get_json()
        self.assertTrue(session_data["logged_in"])
        self.assertEqual(session_data["user"]["username"], username)

    def test_02_space_and_project_creation_and_isolation(self):
        """Test spaces and projects creation and strict user isolation."""
        user1 = f"user1_{os.urandom(4).hex()}"
        user2 = f"user2_{os.urandom(4).hex()}"

        # Register user 1
        self.client.post('/api/register', json={"username": user1, "password": "password123"})
        res1 = self.client.post('/api/spaces', json={
            "name": "User 1 Space",
            "description": "Private space 1"
        })
        space1_id = res1.get_json()["space"]["id"]

        # Create project in space 1
        proj_res = self.client.post(f'/api/spaces/{space1_id}/projects', json={
            "name": "Isolated Project 1",
            "learning_goal": "Master OS Paging"
        })
        proj1_id = proj_res.get_json()["project"]["id"]

        # Register and log in user 2
        self.client.post('/api/logout')
        self.client.post('/api/register', json={"username": user2, "password": "password123"})

        # User 2 should NOT see user 1's spaces
        spaces_res = self.client.get('/api/spaces')
        spaces_user2 = spaces_res.get_json()["spaces"]
        self.assertFalse(any(s["id"] == space1_id for s in spaces_user2))

        # User 2 attempting to access user 1's project should receive 404
        p_res = self.client.get(f'/api/projects/{proj1_id}')
        self.assertEqual(p_res.status_code, 404)

    def test_03_mastery_calculation_and_growth_trend(self):
        """Test concept mastery update, trajectory tracking, and growth trend categorization."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("INSERT INTO spaces (user_id, name) VALUES (1, 'Test Space')")
        s_id = cursor.lastrowid
        cursor.execute("INSERT INTO projects (space_id, user_id, name) VALUES (?, 1, 'Mastery Test Project')", (s_id,))
        p_id = cursor.lastrowid
        cursor.execute("INSERT INTO concepts (project_id, name) VALUES (?, 'Demand Paging')", (p_id,))
        c_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Update mastery: low score (20%) -> should mark as requiring_attention
        update_concept_mastery_from_assessment(p_id, 1, c_id, "Demand Paging", 20, False)
        growth_data = get_project_mastery_and_growth(p_id, 1)
        
        concept = next(c for c in growth_data["concepts"] if c["concept_id"] == c_id)
        self.assertLessEqual(concept["mastery_score"], 40)
        self.assertEqual(concept["trend"], "requiring_attention")

        # Update mastery with high score (100%) -> should trend towards improving
        update_concept_mastery_from_assessment(p_id, 1, c_id, "Demand Paging", 100, True)
        update_concept_mastery_from_assessment(p_id, 1, c_id, "Demand Paging", 100, True)
        growth_data2 = get_project_mastery_and_growth(p_id, 1)
        concept2 = next(c for c in growth_data2["concepts"] if c["concept_id"] == c_id)
        self.assertGreater(concept2["mastery_score"], 50)
        self.assertEqual(concept2["trend"], "improving")

    def test_04_retrieval_and_unsupported_evidence_check(self):
        """Test project-isolated retrieval and evidence thresholding."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("INSERT INTO spaces (user_id, name) VALUES (1, 'OS Space')")
        s_id = cursor.lastrowid
        cursor.execute("INSERT INTO projects (space_id, user_id, name) VALUES (?, 1, 'Virtual Memory Project')", (s_id,))
        p_id = cursor.lastrowid
        
        mat_id = f"test_mat_{os.urandom(6).hex()}"
        cursor.execute("""
            INSERT INTO materials (id, project_id, user_id, filename, file_path, file_type, status, page_count)
            VALUES (?, ?, 1, 'Virtual_Memory_Notes.pdf', '/tmp/test.pdf', '.pdf', 'ready', 2)
        """, (mat_id, p_id))

        cursor.execute("""
            INSERT INTO material_chunks (material_id, project_id, page_number, chunk_index, content)
            VALUES (?, ?, 1, 0, 'Virtual memory uses demand paging and page tables to map virtual pages to physical memory frames.')
        """, (mat_id, p_id))
        conn.commit()
        conn.close()

        # Query 1: Supported query -> Should find evidence with citations
        res_supported = retrieve_project_context(p_id, "virtual memory demand paging frames")
        self.assertTrue(res_supported["has_sufficient_evidence"])
        self.assertGreaterEqual(len(res_supported["evidence_chunks"]), 1)
        self.assertEqual(res_supported["evidence_chunks"][0]["page_number"], 1)

        # Query 2: Unsupported query -> Should declare insufficient evidence
        res_unsupported = retrieve_project_context(p_id, "How to bake a chocolate strawberry shortcake dessert?")
        self.assertFalse(res_unsupported["has_sufficient_evidence"])

    def test_05_adaptive_concept_targeting(self):
        """Test adaptive quiz question selection prioritizing weak concepts."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO spaces (user_id, name) VALUES (1, 'Algo Space')")
        s_id = cursor.lastrowid
        cursor.execute("INSERT INTO projects (space_id, user_id, name) VALUES (?, 1, 'Algo Project')", (s_id,))
        p_id = cursor.lastrowid

        cursor.execute("INSERT INTO concepts (project_id, name) VALUES (?, 'Strong Concept')", (p_id,))
        c1 = cursor.lastrowid
        cursor.execute("INSERT INTO concepts (project_id, name) VALUES (?, 'Weak Concept')", (p_id,))
        c2 = cursor.lastrowid

        # c1 has high mastery (90%), c2 has low mastery (20%)
        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, 1, ?, 90, 'improving')", (p_id, c1))
        cursor.execute("INSERT INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend) VALUES (?, 1, ?, 20, 'requiring_attention')", (p_id, c2))
        conn.commit()
        conn.close()

        selected, difficulty = select_target_concepts_and_difficulty(p_id, 1, num_questions=1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["name"], "Weak Concept")

    def test_06_admin_observability_and_evaluations(self):
        """Test admin dashboard endpoints and observability logging."""
        login_res = self.client.post('/api/login', json={"username": "admin", "password": "admin123"})
        self.assertEqual(login_res.status_code, 200)

        overview_res = self.client.get('/api/admin/overview')
        self.assertEqual(overview_res.status_code, 200)
        overview_data = overview_res.get_json()
        self.assertIn("ai_calls", overview_data)
        self.assertIn("estimated_cost_usd", overview_data)

        health_res = self.client.get('/api/admin/system-health')
        self.assertEqual(health_res.status_code, 200)
        health_data = health_res.get_json()
        self.assertTrue(health_data["database_connected"])

if __name__ == '__main__':
    unittest.main()
