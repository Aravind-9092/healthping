from groq import Groq
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.1-8b-instant"

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

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"sugar": None, "bp_systolic": None, "bp_diastolic": None, "weight": None, "notes": message}

def generate_health_response(data: dict, user_name: str, condition: str = None) -> str:
    prompt = f"""
    You are HealthPing, a friendly AI health coach on WhatsApp.

    Patient name: {user_name or "friend"}
    Known condition: {condition or "not specified"}
    Today's readings:
    - Blood Sugar: {data.get("sugar")} mg/dL
    - Blood Pressure: {data.get("bp_systolic")}/{data.get("bp_diastolic")} mmHg
    - Weight: {data.get("weight")} kg
    - Notes: {data.get("notes")}

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

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

def check_danger_levels(data: dict) -> str | None:
    sugar = data.get("sugar")
    systolic = data.get("bp_systolic")
    diastolic = data.get("bp_diastolic")

    alerts = []

    # Sugar checks
    if sugar is not None:
        if sugar >= 300:
            alerts.append("🚨 URGENT: Your blood sugar is critically high ({} mg/dL). Please contact your doctor immediately or go to the nearest hospital.".format(sugar))
        elif sugar >= 250:
            alerts.append("⚠️ WARNING: Your blood sugar is very high ({} mg/dL). Avoid sweets, drink water, and contact your doctor today.".format(sugar))
        elif sugar <= 70:
            alerts.append("🚨 URGENT: Your blood sugar is dangerously low ({} mg/dL). Eat something sweet immediately — a glucose tablet, juice, or sugar. Don't wait.".format(sugar))

    # BP checks
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

def generate_weekly_summary(readings: list, user_name: str, condition: str) -> str:
    if not readings:
        return f"Hi {user_name}! No readings found for this week. Start logging daily and I'll give you a full weekly report next Sunday! 💪"

    readings_text = ""
    for r in readings:
        date = r.created_at.strftime("%A %d %b")
        line = f"{date}: "
        parts = []
        if r.sugar: parts.append(f"Sugar {r.sugar} mg/dL")
        if r.bp_systolic: parts.append(f"BP {r.bp_systolic}/{r.bp_diastolic}")
        if r.weight: parts.append(f"Weight {r.weight}kg")
        line += ", ".join(parts) if parts else "no readings"
        readings_text += line + "\n"

    prompt = f"""
    You are HealthPing, a friendly AI health coach on WhatsApp.

    Patient: {user_name}
    Condition: {condition or "not specified"}

    This week's readings:
    {readings_text}

    Generate a warm weekly summary report with:
    1. A greeting and week summary (1 line)
    2. Best reading of the week (1 line)
    3. Concerning reading if any (1 line)
    4. One specific tip for next week based on their pattern
    5. Encouragement to keep logging

    Keep it under 10 lines. Use emojis. Be warm and personal.
    """

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()