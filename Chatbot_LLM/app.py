import os
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

def call_llm(prompt, history=None):
    provider, key = get_llm_client()
    if not provider:
        return "No API key found. Please configure GROQ_API_KEY or GEMINI_API_KEY in your .env file."
        
    messages = []
    # System prompt
    system_prompt = "You are a helpful, smart AI Academic Tutor. Provide structured, clean answers using markdown."
    
    if provider == "groq":
        try:
            client = Groq(api_key=key)
            messages.append({"role": "system", "content": system_prompt})
            if history:
                for h in history:
                    messages.append({"role": h["role"], "content": h["content"]})
            messages.append({"role": "user", "content": prompt})
            
            completion = client.chat.completions.create(
                messages=messages,
                model="openai/gpt-oss-120b"
            )
            return completion.choices[0].message.content
        except Exception as e:
            try:
                # fallback
                client = Groq(api_key=key)
                completion = client.chat.completions.create(
                    messages=messages,
                    model="openai/gpt-oss-20b"
                )
                return completion.choices[0].message.content
            except Exception as e2:
                return f"Groq Error: {str(e2)}"
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            # Convert history format
            formatted_history = []
            if history:
                for h in history:
                    role = "user" if h["role"] == "user" else "model"
                    formatted_history.append({"role": role, "parts": [h["content"]]})
            chat = model.start_chat(history=formatted_history)
            response = chat.send_message(f"System Instruction: {system_prompt}\n\n{prompt}")
            return response.text
        except Exception as e:
            return f"Gemini Error: {str(e)}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    message = data.get("message", "")
    history = data.get("history", [])
    
    if not message:
        return jsonify({"error": "No message provided"}), 400
        
    response = call_llm(message, history)
    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True, port=5002)
