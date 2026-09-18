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

def create_study_plan(topic, duration_weeks=4, hours_per_week=10, skill_level="Beginner", current_skills=""):
    prompt = f"""
    Create a highly detailed, personalized, week-by-week study plan for a student.
    
    **Student Profile**:
    - Target Goal/Subject/Role: {topic}
    - Study Duration: {duration_weeks} Weeks
    - Time Commitment: {hours_per_week} Hours/Week
    - Current Level: {skill_level}
    - Already Known Skills: {current_skills if current_skills else "None specified"}
    
    Provide your plan in clean Markdown format with:
    1. **Plan Overview**: A summary of what they will achieve by the end.
    2. **Weekly Breakdown**: For each week (e.g. Week 1, Week 2, etc.):
       - **Core Topics**: Major concepts to cover.
       - **Study Hours Breakdown**: Recommended hours per subtopic.
       - **Hands-on Practice**: Specific coding tasks, mini-projects, or exercises they must do.
       - **Recommended Resources**: Specific books, platforms, or search keywords.
    3. **Milestones & Success Metrics**: How to self-assess or test understanding.
    """
    
    provider, key = get_llm_client()
    if not provider:
        return "Please save your API key in settings to unlock study planning."

    if provider == "groq":
        try:
            client = Groq(api_key=key)
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an Expert AI Academic Advisor."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.5
            )
            return completion.choices[0].message.content
        except Exception as e:
            try:
                client = Groq(api_key=key)
                completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are an Expert AI Academic Advisor."},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama3-8b-8192",
                    temperature=0.5
                )
                return completion.choices[0].message.content
            except Exception as e2:
                return f"Groq Error: {str(e2)}"
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(f"System Instruction: You are an Expert AI Academic Advisor.\n\n{prompt}")
            return response.text
        except Exception as e:
            return f"Gemini Error: {str(e)}"
