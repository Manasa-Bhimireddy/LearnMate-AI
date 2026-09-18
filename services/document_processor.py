import os
import time
import threading
import queue
import json
import uuid
from models import get_db_connection
from services.ai_service import call_ai, clean_json_response

# Queue for background processing tasks
JOB_QUEUE = queue.Queue()
WORKER_THREAD = None

def extract_pdf_pages(filepath):
    """
    Extracts text page by page from PDF using pdfplumber or pypdf.
    Returns a list of dicts: [{"page": 1, "text": "..."}]
    """
    pages_data = []
    
    # Try pdfplumber first for highest fidelity
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages_data.append({"page": idx + 1, "text": text.strip()})
    except Exception as e:
        print(f"pdfplumber page extraction warning: {e}")

    # Fallback to pypdf if empty
    if not pages_data:
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages_data.append({"page": idx + 1, "text": text.strip()})
        except Exception as e:
            print(f"pypdf extraction error: {e}")

    return pages_data

def extract_text_from_file(filepath, filename):
    """
    Extracts pages or chunks from various file types.
    Always returns a list of {"page": int, "text": str}.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == ".pdf":
        return extract_pdf_pages(filepath)
    elif ext in [".txt", ".md"]:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return [{"page": 1, "text": content.strip()}]
        except Exception as e:
            print(f"Text file read error: {e}")
            return []
    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(filepath)
            full_text = []
            for para in doc.paragraphs:
                if para.text.strip():
                    full_text.append(para.text.strip())
            return [{"page": 1, "text": "\n\n".join(full_text)}]
        except Exception as e:
            print(f"Docx file read error: {e}")
            return []
    else:
        return []

def split_into_chunks(text, max_chunk_size=700, overlap=100):
    """Simple sliding window text chunking preserving sentence boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_len = len(para)
        if current_len + para_len > max_chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # keep the last paragraph for overlap if it's small enough
            if len(current_chunk[-1]) < overlap:
                current_chunk = [current_chunk[-1], para]
                current_len = len(current_chunk[0]) + para_len
            else:
                current_chunk = [para]
                current_len = para_len
        else:
            current_chunk.append(para)
            current_len += para_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks or [text[:max_chunk_size]]

def extract_concepts_from_text(sample_text, project_id, user_id):
    """
    Uses AI to analyze project document text and extract 4 to 8 core concepts with descriptions.
    """
    prompt = f"""
    Analyze the following educational material excerpt and extract 4 to 7 key learning concepts or technical topics covered.
    Return ONLY a valid JSON object in this exact format:
    {{
      "concepts": [
        {{
          "name": "Concept Name",
          "description": "Clear 1-2 sentence definition/summary of the concept based on the text"
        }}
      ]
    }}

    Text excerpt:
    {sample_text[:6000]}
    """
    try:
        response_text = call_ai(
            prompt=prompt,
            system_instruction="You are an expert curriculum designer and educator. Identify key learning concepts accurately from study materials.",
            feature="concept_extraction",
            user_id=user_id,
            project_id=project_id,
            response_format="json"
        )
        parsed = clean_json_response(response_text)
        return parsed.get("concepts", [])
    except Exception as e:
        print(f"Error in AI concept extraction: {e}")
        # Rule-based fallback if AI is unavailable or fails
        lines = [line.strip() for line in sample_text.split("\n") if line.strip()]
        fallback_concepts = []
        for line in lines[:5]:
            if len(line) < 40 and not line.endswith("."):
                fallback_concepts.append({"name": line, "description": f"Core topic derived from {line}"})
        if not fallback_concepts:
            fallback_concepts = [
                {"name": "Core Fundamentals", "description": "Foundational definitions and key mechanisms introduced in the material."},
                {"name": "Key Architecture & Workflow", "description": "System architecture and step-by-step procedures outlined in the content."}
            ]
        return fallback_concepts

def process_material_job(material_id):
    """
    Worker function to process a single material item asynchronously.
    Updates status: queued -> processing -> ready | failed.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch material info
    cursor.execute("SELECT * FROM materials WHERE id = ?", (material_id,))
    material = cursor.fetchone()
    if not material:
        conn.close()
        return

    user_id = material["user_id"]
    project_id = material["project_id"]
    filepath = material["file_path"]
    filename = material["filename"]

    # 2. Update status to 'processing'
    cursor.execute("UPDATE materials SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (material_id,))
    cursor.execute("""
        INSERT INTO learning_events (user_id, project_id, event_type, event_data_json)
        VALUES (?, ?, 'material_processing_started', ?)
    """, (user_id, project_id, json.dumps({"material_id": material_id, "filename": filename})))
    conn.commit()

    try:
        # 3. Extract text page by page
        pages = extract_text_from_file(filepath, filename)
        if not pages:
            raise ValueError(f"Could not extract any readable text from '{filename}'. Check if file is scanned or empty.")

        page_count = len(pages)
        full_text_corpus = []

        # 4. Chunk each page and store in material_chunks with page_number
        cursor.execute("DELETE FROM material_chunks WHERE material_id = ?", (material_id,))
        
        chunk_idx = 0
        for p in pages:
            page_num = p["page"]
            page_text = p["text"]
            full_text_corpus.append(page_text)
            page_chunks = split_into_chunks(page_text)
            
            for chunk in page_chunks:
                cursor.execute("""
                    INSERT INTO material_chunks (material_id, project_id, page_number, chunk_index, content)
                    VALUES (?, ?, ?, ?, ?)
                """, (material_id, project_id, page_num, chunk_idx, chunk))
                chunk_idx += 1

        # 5. Extract Concepts and definitions
        combined_text = "\n\n".join(full_text_corpus)
        extracted_concepts = extract_concepts_from_text(combined_text, project_id, user_id)

        # Store concepts and initialize concept mastery
        for concept in extracted_concepts:
            c_name = concept.get("name", "").strip()
            c_desc = concept.get("description", "").strip()
            if not c_name:
                continue

            # Check if concept already exists for this project
            cursor.execute("SELECT id FROM concepts WHERE project_id = ? AND LOWER(name) = LOWER(?)", (project_id, c_name))
            existing_c = cursor.fetchone()
            if existing_c:
                concept_id = existing_c["id"]
            else:
                cursor.execute("""
                    INSERT INTO concepts (project_id, name, description, extracted_from_material_id)
                    VALUES (?, ?, ?, ?)
                """, (project_id, c_name, c_desc, material_id))
                concept_id = cursor.lastrowid

            # Initialize mastery record if not exists
            cursor.execute("""
                INSERT OR IGNORE INTO concept_mastery (project_id, user_id, concept_id, mastery_score, trend, history_json)
                VALUES (?, ?, ?, 35, 'stable', ?)
            """, (project_id, user_id, concept_id, json.dumps([{"score": 35, "timestamp": time.strftime("%Y-%m-%d %H:%M")}])))

        # 6. Mark Material as Ready
        cursor.execute("""
            UPDATE materials 
            SET status = 'ready', page_count = ?, error_message = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (page_count, material_id))

        # 7. Log completion event
        cursor.execute("""
            INSERT INTO learning_events (user_id, project_id, event_type, event_data_json)
            VALUES (?, ?, 'material_processed_ready', ?)
        """, (user_id, project_id, json.dumps({
            "material_id": material_id,
            "filename": filename,
            "pages": page_count,
            "chunks": chunk_idx,
            "concepts_extracted": len(extracted_concepts)
        })))

        # 8. Mark background job completed
        cursor.execute("""
            UPDATE background_jobs 
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (f"job_mat_{material_id}",))

        conn.commit()
        print(f"Material {filename} ({material_id}) processed successfully: {page_count} pages, {chunk_idx} chunks, {len(extracted_concepts)} concepts.")

    except Exception as ex:
        err_str = str(ex)
        print(f"Error processing material {material_id}: {err_str}")
        cursor.execute("""
            UPDATE materials 
            SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (err_str, material_id))
        cursor.execute("""
            UPDATE background_jobs 
            SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (err_str, f"job_mat_{material_id}"))
        conn.commit()
    finally:
        conn.close()

def _worker_loop():
    """Background worker daemon thread to process queued jobs."""
    while True:
        try:
            job_info = JOB_QUEUE.get()
            if job_info is None:
                break
            material_id = job_info.get("material_id")
            if material_id:
                process_material_job(material_id)
            JOB_QUEUE.task_done()
        except Exception as e:
            print(f"Job queue worker exception: {e}")
            time.sleep(1)

def start_background_processor():
    """Starts the background worker thread if not already running."""
    global WORKER_THREAD
    if WORKER_THREAD is None or not WORKER_THREAD.is_alive():
        WORKER_THREAD = threading.Thread(target=_worker_loop, daemon=True)
        WORKER_THREAD.start()
        print("Background document processor worker thread started.")

def queue_material_for_processing(material_id):
    """Enqueues a material ID for async background processing."""
    start_background_processor()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    job_id = f"job_mat_{material_id}"
    cursor.execute("""
        INSERT OR REPLACE INTO background_jobs (id, job_type, status, payload_json)
        VALUES (?, 'document_processing', 'queued', ?)
    """, (job_id, json.dumps({"material_id": material_id})))
    conn.commit()
    conn.close()

    JOB_QUEUE.put({"material_id": material_id})
