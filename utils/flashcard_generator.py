import os
import json
import re
from groq import Groq
import google.generativeai as genai

def get_llm_client():
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        return "groq", groq_key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return "gemini", gemini_key
    return None, None

def generate_flashcards(topic):
    prompt = f"""
    Create 5 study flashcards for the topic: "{topic}".
    
    Return the response ONLY as a valid JSON object. Do not include markdown codeblocks (like ```json), leading space, or trailing text.
    Ensure it conforms exactly to this structure:
    {{
        "flashcards": [
            {{
                "front": "Front of the flashcard (Question/Concept)?",
                "back": "Back of the flashcard (Answer/Explanation)."
            }}
        ]
    }}
    Make them informative and clear.
    """
    
    provider, key = get_llm_client()
    if not provider:
        return {"flashcards": [], "error": "No API key configured."}

    if provider == "groq":
        try:
            client = Groq(api_key=key)
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                response_format={"type": "json_object"},
                temperature=0.2
            )
            res_text = completion.choices[0].message.content
        except Exception as e:
            try:
                client = Groq(api_key=key)
                completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama3-8b-8192",
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                res_text = completion.choices[0].message.content
            except Exception as e2:
                return {"flashcards": [], "error": f"Groq error: {str(e2)}"}
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(f"System Instruction: You are an academic test designer. Output JSON ONLY.\n\n{prompt}")
            res_text = response.text
        except Exception as e:
            return {"flashcards": [], "error": f"Gemini error: {str(e)}"}
            
    try:
        res_text = res_text.strip()
        if res_text.startswith("```"):
            res_text = re.sub(r"^```(?:json)?\n", "", res_text)
            res_text = re.sub(r"\n```$", "", res_text)
        return json.loads(res_text)
    except Exception as e:
        print(f"JSON parsing error in flashcards: {e}")
        return {"flashcards": [], "error": "Invalid JSON returned from LLM."}
