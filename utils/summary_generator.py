import os
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

def generate_summary(text):
    if not text:
        return "No text provided to summarize."
        
    prompt = f"""
    Please generate a concise, high-level summary of the following document.
    Focus on main concepts, core arguments, and important takeaways.
    Use bullet points where appropriate.
    
    **Document Text Excerpt (first 6000 characters)**:
    ---
    {text[:6000]}
    ---
    """
    
    provider, key = get_llm_client()
    if not provider:
        return "Please save your API key in settings to unlock summaries."

    if provider == "groq":
        try:
            client = Groq(api_key=key)
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a professional academic summarizer."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.3
            )
            return completion.choices[0].message.content
        except Exception as e:
            try:
                client = Groq(api_key=key)
                completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a professional academic summarizer."},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama3-8b-8192",
                    temperature=0.3
                )
                return completion.choices[0].message.content
            except Exception as e2:
                return f"Groq Error: {str(e2)}"
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(f"System Instruction: You are a professional academic summarizer.\n\n{prompt}")
            return response.text
        except Exception as e:
            return f"Gemini Error: {str(e)}"
