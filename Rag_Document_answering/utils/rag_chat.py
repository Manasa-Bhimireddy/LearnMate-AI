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

def answer_question(docs, question):
    context = "\n\n".join([doc.page_content for doc in docs])
    
    prompt = f"""
    Answer the user's question based strictly on the provided document excerpts.
    
    **Document Context**:
    ---
    {context}
    ---
    
    **User Question**: {question}
    
    **Instructions**:
    - Provide a detailed and accurate answer using only the details from the context.
    - If the context doesn't contain the answer, say "Based on the uploaded document, I cannot find the answer to this question."
    - Highlight key terms in bold. Use markdown for structured lists if appropriate.
    - Do not invent facts or mention information outside of the context.
    """
    
    provider, key = get_llm_client()
    if not provider:
        return "Please configure GROQ_API_KEY or GEMINI_API_KEY in your .env file."

    if provider == "groq":
        try:
            client = Groq(api_key=key)
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a precise academic document tutor using RAG."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.2
            )
            return completion.choices[0].message.content
        except Exception as e:
            try:
                client = Groq(api_key=key)
                completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a precise academic document tutor using RAG."},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama3-8b-8192",
                    temperature=0.2
                )
                return completion.choices[0].message.content
            except Exception as e2:
                return f"Groq Error: {str(e2)}"
    else:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(f"System Instruction: You are a precise academic document tutor using RAG.\n\n{prompt}")
            return response.text
        except Exception as e:
            return f"Gemini Error: {str(e)}"
