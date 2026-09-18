import os
import time
import json
import re
from dotenv import load_dotenv
from models import get_db_connection

load_dotenv()

# Pricing estimates per 1,000 tokens (approximate blended input/output)
COST_PER_1K_TOKENS = {
    "qwen/qwen3.8-27b": 0.0003,
    "openai/gpt-oss-120b": 0.0006,
    "openai/gpt-oss-20b": 0.0001,
    "groq/compound-mini": 0.0001,
    "gemini-1.5-flash": 0.00015,
    "default": 0.0002
}

def get_configured_providers():
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    return {
        "groq": bool(groq_key),
        "gemini": bool(gemini_key)
    }

def get_primary_provider():
    providers = get_configured_providers()
    if providers["groq"]:
        return "groq"
    if providers["gemini"]:
        return "gemini"
    return None

def log_ai_usage(user_id, project_id, feature, model, latency_ms, prompt_tokens, completion_tokens, status="success", error_message=None):
    """Records AI token consumption, latency, and cost for observability."""
    total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    rate = COST_PER_1K_TOKENS.get(model, COST_PER_1K_TOKENS["default"])
    estimated_cost = round((total_tokens / 1000.0) * rate, 6)

    for attempt in range(5):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_usage_logs 
                (user_id, project_id, feature, model, latency_ms, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, project_id, feature, model, latency_ms, prompt_tokens, completion_tokens, total_tokens, estimated_cost, status, error_message))
            conn.commit()
            conn.close()
            return
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 4:
                time.sleep(0.05 * (attempt + 1))
                continue
            break

def estimate_tokens(text):
    if not text:
        return 0
    # Rough rule of thumb: ~4 characters per token
    return max(1, len(text) // 4)

def call_ai(prompt, system_instruction=None, history=None, feature="general", user_id=None, project_id=None, response_format=None):
    """
    Unified AI Call function with:
    - Provider abstraction (Groq -> Gemini fallback)
    - Observability (records latency, token usage, cost, and errors)
    - Error handling & recovery
    """
    start_time = time.time()
    provider = get_primary_provider()
    
    if not provider:
        err_msg = "No LLM API Key configured. Please add GROQ_API_KEY or GEMINI_API_KEY in .env or Settings."
        log_ai_usage(user_id, project_id, feature, "none", 0, 0, 0, status="failed", error_message=err_msg)
        raise ValueError(err_msg)

    chosen_model = "qwen/qwen3.8-27b" if provider == "groq" else "gemini-1.5-flash"
    prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction or "")

    # Handle Groq
    if provider == "groq":
        from groq import Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        client = Groq(api_key=groq_key)

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        if history:
            for h in history:
                role = "user" if h.get("role") in ["user", "student"] else "assistant"
                messages.append({"role": role, "content": h.get("content") or h.get("text", "")})
        messages.append({"role": "user", "content": prompt})

        # Try active Groq production models
        groq_candidates = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound-mini"]
        last_error = None

        for model_candidate in groq_candidates:
            try:
                kwargs = {
                    "messages": messages,
                    "model": model_candidate,
                    "temperature": 0.3 if response_format == "json" else 0.7,
                }
                if response_format == "json":
                    kwargs["response_format"] = {"type": "json_object"}

                completion = client.chat.completions.create(**kwargs)
                output_text = completion.choices[0].message.content
                
                # Usage extraction
                usage = getattr(completion, "usage", None)
                p_tokens = getattr(usage, "prompt_tokens", prompt_tokens) if usage else prompt_tokens
                c_tokens = getattr(usage, "completion_tokens", estimate_tokens(output_text)) if usage else estimate_tokens(output_text)
                
                latency_ms = int((time.time() - start_time) * 1000)
                log_ai_usage(user_id, project_id, feature, model_candidate, latency_ms, p_tokens, c_tokens, status="success")
                return output_text
            except Exception as ex:
                last_error = ex
                continue

        # If all Groq models failed, check if Gemini is configured as fallback
        if get_configured_providers()["gemini"]:
            provider = "gemini"
        else:
            latency_ms = int((time.time() - start_time) * 1000)
            log_ai_usage(user_id, project_id, feature, groq_candidates[0], latency_ms, prompt_tokens, 0, status="failed", error_message=str(last_error))
            raise RuntimeError(f"Groq API Error: {str(last_error)}")

    # Handle Gemini
    if provider == "gemini":
        try:
            import google.generativeai as genai
            gemini_key = os.environ.get("GEMINI_API_KEY")
            genai.configure(api_key=gemini_key)
            model_name = "gemini-1.5-flash"
            model = genai.GenerativeModel(model_name)

            full_prompt = f"System Instruction: {system_instruction}\n\n{prompt}" if system_instruction else prompt
            generation_config = {}
            if response_format == "json":
                generation_config["response_mime_type"] = "application/json"

            response = model.generate_content(full_prompt, generation_config=generation_config if generation_config else None)
            output_text = response.text
            
            completion_tokens = estimate_tokens(output_text)
            latency_ms = int((time.time() - start_time) * 1000)
            log_ai_usage(user_id, project_id, feature, model_name, latency_ms, prompt_tokens, completion_tokens, status="success")
            return output_text
        except Exception as ex:
            latency_ms = int((time.time() - start_time) * 1000)
            log_ai_usage(user_id, project_id, feature, "gemini-1.5-flash", latency_ms, prompt_tokens, 0, status="failed", error_message=str(ex))
            raise RuntimeError(f"Gemini API Error: {str(ex)}")

def clean_json_response(raw_text):
    """
    Robust JSON parser that strips markdown fences (```json ... ```) 
    and handles partial outputs.
    """
    if not raw_text:
        return {}
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        # Match outermost JSON object or array
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return {"raw": raw_text}
