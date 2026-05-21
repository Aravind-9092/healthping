from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.reading import Reading
from app.services.ai import extract_health_data, generate_health_response, check_danger_levels, generate_weekly_summary
from app.services.pdf import generate_pdf_report
from twilio.rest import Client as TwilioClient
import os
from dotenv import load_dotenv

load_dotenv()

twilio_client = TwilioClient(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

def twiml_response(message: str) -> PlainTextResponse:
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{message}</Message>
</Response>"""
    return PlainTextResponse(twiml, media_type="text/xml")

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    incoming_msg = form_data.get("Body", "").strip()
    sender = form_data.get("From", "").replace("whatsapp:", "")

    print(f"Message from {sender}: {incoming_msg}")

    user = db.query(User).filter(User.phone == sender).first()

    # NEW USER
    if not user:
        user = User(phone=sender, onboarding_step="ask_name")
        db.add(user)
        db.commit()
        return twiml_response(
            "👋 Welcome to HealthPing!\n\nI'm your personal daily health coach. I'll help you track your sugar, BP, and weight every day and give you personalized insights.\n\nFirst, what's your name?"
        )

    # ONBOARDING STEP 1
    if user.onboarding_step == "ask_name":
        user.name = incoming_msg.strip().title()
        user.onboarding_step = "ask_condition"
        db.commit()
        return twiml_response(
            f"Nice to meet you, {user.name}! 😊\n\nWhat health condition are you managing?\n\nFor example:\n- Diabetes\n- High BP\n- Thyroid\n- Multiple (e.g. Diabetes + BP)"
        )

    # ONBOARDING STEP 2
    if user.onboarding_step == "ask_condition":
        user.condition = incoming_msg.strip()
        user.onboarding_step = "ask_medicines"
        db.commit()
        return twiml_response(
            f"Got it! Managing {user.condition} can be challenging but you're doing great by tracking it. 💪\n\nWhat medicines do you take daily? (or type 'none' if you don't take any)"
        )

    # ONBOARDING STEP 3
    if user.onboarding_step == "ask_medicines":
        user.medicines = incoming_msg.strip()
        user.onboarding_step = "complete"
        db.commit()
        return twiml_response(
            f"Perfect, {user.name}! You're all set! 🎉\n\nEvery day just send me your readings like:\n'sugar 180, BP 130/90, weight 70kg'\n\nI'll track everything and give you daily insights. Let's start — how are your readings today?"
        )

    # REPORT COMMAND
    if incoming_msg.lower() in ["report", "weekly report", "summary"]:
        from datetime import datetime, timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        readings = db.query(Reading).filter(
            Reading.phone == sender,
            Reading.created_at >= week_ago
        ).all()
        summary = generate_weekly_summary(readings, user.name, user.condition)
        pdf_path = generate_pdf_report(user, readings, summary)

        ngrok_url = os.getenv("NGROK_URL")
        pdf_filename = os.path.basename(pdf_path)

        twilio_client.messages.create(
            from_="whatsapp:+14155238886",
            to=f"whatsapp:{sender}",
            media_url=[f"{ngrok_url}/reports/{pdf_filename}"],
            body=f"📋 Here's your weekly health report, {user.name}!"
        )
        return twiml_response("Generating your PDF report... sending it now! 📄")

    # ONBOARDED USER - process health readings
    health_data = extract_health_data(incoming_msg)

    # Only save if actual health data was found
    has_data = any([
        health_data.get("sugar"),
        health_data.get("bp_systolic"),
        health_data.get("bp_diastolic"),
        health_data.get("weight")
    ])

    if has_data:
        reading = Reading(
            phone=sender,
            sugar=health_data.get("sugar"),
            bp_systolic=health_data.get("bp_systolic"),
            bp_diastolic=health_data.get("bp_diastolic"),
            weight=health_data.get("weight"),
            notes=health_data.get("notes")
        )
        db.add(reading)
        db.commit()

    # Check for danger levels first
    danger_alert = check_danger_levels(health_data)
    if danger_alert:
        return twiml_response(danger_alert)

    response_text = generate_health_response(health_data, user.name, user.condition)
    return twiml_response(response_text)
