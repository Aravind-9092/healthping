from groq import Groq
import os
import re
import json
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Set GROQ_MODEL in Railway Variables to switch models without a code change.
# Check the exact model ID in the Groq console's model list.
MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

FALLBACK_REPLY = "Thanks for your message! I'm a bit busy right now, please try again in a minute 🙏"


def clean(text: str) -> str:
    """Remove <think>...</think> blocks (and any unclosed <think> tail) from model output."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    return text.strip()


def ask_llm(prompt: str, max_tokens: int) -> str | None:
    """Single place for every Groq call. Returns None on any failure (rate limit, network, etc.)."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt + "\n\n/no_think"}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return clean(response.choices[0].message.content)
    except Exception as e:
        print("Groq error:", e)
        return None


def detect_language(message: str) -> str:
    """Zero-token script check. No LLM call, so it can never hit a rate limit."""
    for ch in message:
        if "\u0900" <= ch <= "\u097F":
            return "hindi"
        if "\u0C00" <= ch <= "\u0C7F":
            return "telugu"
        if "\u0B80" <= ch <= "\u0BFF":
            return "tamil"
    return "english"


def extract_health_data(message: str) -> dict:
    prompt = f"""
    Extract health readings from this message. Return ONLY a JSON object with these fields:
    - sugar (blood sugar in mg/dL, null if not mentioned)
    - bp_systolic (upper BP number, null if not mentioned)
    - bp_diastolic (lower BP number, null if not mentioned)
    - weight (in kg, null if not mentioned)
    - notes (any other health info mentioned)
    Message: "{message}"
    Return only valid JSON, nothing else. Example:
    {{"sugar": 180, "bp_systolic": 120, "bp_diastolic": 80, "weight": null, "notes": "feeling tired"}}
    """
    empty = {"sugar": None, "bp_systolic": None, "bp_diastolic": None, "weight": None, "notes": message}

    text = ask_llm(prompt, max_tokens=250)
    if not text:
        return empty
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        # grab the first {...} block in case the model adds extra words
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
        data = json.loads(text)
        for key in ["sugar", "bp_systolic", "bp_diastolic", "weight", "notes"]:
            data.setdefault(key, None)
        return data
    except Exception as e:
        print("JSON parse error:", e)
        return empty


def generate_health_response(data: dict, user_name: str, condition: str = None, language: str = "english") -> str:
    language_instruction = {
        "english": "Respond in English.",
        "hindi": "Respond in Hindi language using Devanagari script.",
        "telugu": "Respond in Telugu language using Telugu script.",
        "tamil": "Respond in Tamil language using Tamil script.",
    }.get(language, "Respond in English.")

    prompt = f"""
    You are HealthPing, a friendly AI health coach on WhatsApp.
    Patient name: {user_name or "friend"}
    Known condition: {condition or "not specified"}
    Today's readings:
    - Blood Sugar: {data.get("sugar")} mg/dL
    - Blood Pressure: {data.get("bp_systolic")}/{data.get("bp_diastolic")} mmHg
    - Weight: {data.get("weight")} kg
    - Notes: {data.get("notes")}
    {language_instruction}
    IMPORTANT RULES:
    - If notes contain "no sugar" or "don't have sugar/diabetes" it means the person is saying they don't have diabetes — acknowledge it positively, don't ask for sugar readings
    - If all readings are None and notes is just a casual message, reply conversationally and ask them to share today's readings
    - Never say "we're missing data" — just naturally ask for the readings
    - Only comment on readings that are actually provided (not None)
    - Be warm, short (3-4 lines), and friendly
    Give a personalized response:
    1. Acknowledge what they said
    2. Comment only on readings that exist
    3. Give one simple tip relevant to their condition
    """
    reply = ask_llm(prompt, max_tokens=350)
    return reply or FALLBACK_REPLY


def check_danger_levels(data: dict) -> str | None:
    """Rule-based, no LLM. Always works even if Groq is down."""
    sugar = data.get("sugar")
    systolic = data.get("bp_systolic")
    diastolic = data.get("bp_diastolic")
    alerts = []

    if sugar is not None:
        if sugar >= 300:
            alerts.append("🚨 URGENT: Your blood sugar is critically high ({} mg/dL). Please contact your doctor immediately or go to the nearest hospital.".format(sugar))
        elif sugar >= 250:
            alerts.append("⚠️ WARNING: Your blood sugar is very high ({} mg/dL). Avoid sweets, drink water, and contact your doctor today.".format(sugar))
        elif sugar <= 70:
            alerts.append("🚨 URGENT: Your blood sugar is dangerously low ({} mg/dL). Eat something sweet immediately — a glucose tablet, juice, or sugar. Don't wait.".format(sugar))

    if systolic is not None and diastolic is not None:
        if systolic >= 180 or diastolic >= 120:
            alerts.append("🚨 URGENT: Your blood pressure is critically high ({}/{}). This is a hypertensive crisis. Go to the hospital immediately.".format(systolic, diastolic))
        elif systolic >= 160 or diastolic >= 100:
            alerts.append("⚠️ WARNING: Your blood pressure is very high ({}/{}). Rest immediately, avoid salt, and call your doctor today.".format(systolic, diastolic))
        elif systolic <= 90 or diastolic <= 60:
            alerts.append("⚠️ WARNING: Your blood pressure is low ({}/{}). Drink water, lie down, and avoid standing up quickly.".format(systolic, diastolic))

    if alerts:
        return "\n\n".join(alerts)
    return None


def generate_weekly_summary(readings: list, user_name: str, condition: str, language: str = "english") -> str:
    language_instruction = {
        "english": "Write the entire summary in English.",
        "hindi": "Write the entire summary in Hindi using Devanagari script.",
        "telugu": "Write the entire summary in Telugu using Telugu script.",
        "tamil": "Write the entire summary in Tamil using Tamil script.",
    }.get(language, "Write the entire summary in English.")

    if not readings:
        return f"Hi {user_name}! No readings found for this week. Start logging daily and I'll give you a full weekly report next Sunday! 💪"

    readings_text = ""
    for r in readings:
        date = r.created_at.strftime("%A %d %b")
        line = f"{date}: "
        parts = []
        if r.sugar:
            parts.append(f"Sugar {r.sugar} mg/dL")
        if r.bp_systolic:
            parts.append(f"BP {r.bp_systolic}/{r.bp_diastolic}")
        if r.weight:
            parts.append(f"Weight {r.weight}kg")
        line += ", ".join(parts) if parts else "no readings"
        readings_text += line + "\n"

    prompt = f"""
    You are HealthPing, a friendly AI health coach on WhatsApp.
    Patient: {user_name}
    Condition: {condition or "not specified"}
    This week's readings:
    {readings_text}
    {language_instruction}
    Generate a warm weekly summary report in bullet points format:
    • Week Summary (1 line)
    • Best reading of the week
    • Concerning reading if any
    • One specific tip for next week
    • Encouragement to keep logging
    Keep it under 10 lines. Use emojis. Be warm, clear and easy to understand.
    """
    reply = ask_llm(prompt, max_tokens=450)
    return reply or f"Hi {user_name}! Your weekly report is ready in the PDF. Keep logging daily! 💪"