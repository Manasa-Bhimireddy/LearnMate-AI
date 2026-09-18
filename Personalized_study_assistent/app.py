import os
import json
import re
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)

def get_llm_client():
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        return "groq", groq_key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return "gemini", gemini_key
    return None, None

def call_llm(prompt, system_instruction=None, json_mode=False):
    provider, key = get_llm_client()
    if not provider:
        raise ValueError("No API key configured.")
        
    if provider == "groq":
        try:
            client = Groq(api_key=key)
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            response_format = {"type": "json_object"} if json_mode else None
            completion = client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                response_format=response_format,
                temperature=0.2 if json_mode else 0.7
            )
            return completion.choices[0].message.content
        except Exception as e:
            try:
                completion = client.chat.completions.create(
                    messages=messages,
                    model="llama3-8b-8192",
                    response_format=response_format,
                    temperature=0.2 if json_mode else 0.7
                )
                return completion.choices[0].message.content
            except Exception as e2:
                raise RuntimeError(f"Groq error: {str(e2)}")
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            full_prompt = f"System Instruction: {system_instruction}\n\n{prompt}" if system_instruction else prompt
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini error: {str(e)}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/plan", methods=["POST"])
def plan():
    data = request.json or {}
    topic = data.get("topic", "").strip()
    duration = data.get("duration", "4")
    hours = data.get("hours", "10")
    level = data.get("level", "Beginner")
    
    if not topic:
        return jsonify({"error": "Topic/Target is required"}), 400
        
    prompt = f"""
    Create a personalized week-by-week study plan for the topic: "{topic}".
    Duration: {duration} Weeks.
    Commitment: {hours} Hours/Week.
    Level: {level}.
    
    Provide your plan in clean Markdown format with:
    1. **Overview**: Key learning goals.
    2. **Weekly Breakdown**: Major concepts to cover and hands-on exercises for each week.
    3. **Success Criteria**: How to verify progress.
    """
    
    try:
        res = call_llm(prompt, system_instruction="You are an expert academic tutor.")
        return jsonify({"plan": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/quiz", methods=["POST"])
def quiz():
    data = request.json or {}
    topic = data.get("topic", "").strip()
    
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
        
    prompt = f"""
    Create 5 multiple-choice questions (MCQs) and 5 flashcards for: "{topic}".
    
    Return the response ONLY as a valid JSON object. Do not include markdown codeblocks (like ```json), leading space, or trailing text.
    Ensure it conforms exactly to this structure:
    {{
        "mcqs": [
            {{
                "question": "Question text here?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "answer_idx": 0,
                "explanation": "Brief explanation of why this option is correct."
            }}
        ],
        "flashcards": [
            {{
                "front": "Front of the flashcard (Question/Concept)?",
                "back": "Back of the flashcard (Answer/Explanation)."
            }}
        ]
    }}
    Make them challenging and educational.
    """
    
    try:
        res = call_llm(prompt, system_instruction="You are an academic test designer.", json_mode=True)
        res = res.strip()
        if res.startswith("```"):
            res = re.sub(r"^```(?:json)?\n", "", res)
            res = re.sub(r"\n```$", "", res)
        quiz_data = json.loads(res)
        return jsonify(quiz_data)
    except Exception as e:
        print(f"Error parsing quiz JSON: {e}")
        return jsonify({"error": f"Failed to generate structured quiz: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5003)
