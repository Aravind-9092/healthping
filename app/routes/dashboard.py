from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.reading import Reading
from app.models.treatment import Treatment
from datetime import datetime, timedelta
import jinja2
from urllib.parse import unquote

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
env = jinja2.Environment(loader=jinja2.FileSystemLoader("app/templates"))

# Timestamps are stored in UTC; show them in Indian Standard Time
IST = timedelta(hours=5, minutes=30)


@router.get("/", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.onboarding_step == "complete").all()

    today = (datetime.utcnow() + IST).date()

    danger_count = 0
    missing_count = 0
    logged_today = 0
    active_count = 0
    no_data_count = 0
    patients = []
    danger_patients = []

    for user in users:
        last_reading = db.query(Reading).filter(
            Reading.phone == user.phone
        ).order_by(Reading.created_at.desc()).first()

        reading_id = None
        treated = False

        if last_reading:
            reading_id = last_reading.id
            local_time = last_reading.created_at + IST
            days_ago = (today - local_time.date()).days

            if days_ago == 0:
                logged_today += 1

            is_danger = False
            alert_msg = ""
            is_sugar_high = False
            is_sugar_normal = False
            is_bp_high = False

            if last_reading.sugar:
                if last_reading.sugar >= 250:
                    is_danger = True
                    is_sugar_high = True
                    alert_msg = f"Blood sugar critically high at {last_reading.sugar} mg/dL"
                elif last_reading.sugar <= 70:
                    is_danger = True
                    is_sugar_high = True
                    alert_msg = f"Blood sugar dangerously low at {last_reading.sugar} mg/dL"
                elif last_reading.sugar <= 140:
                    is_sugar_normal = True

            if last_reading.bp_systolic and last_reading.bp_systolic >= 160:
                is_danger = True
                is_bp_high = True
                alert_msg = f"BP critically high at {last_reading.bp_systolic}/{last_reading.bp_diastolic}"

            # If a doctor already marked THIS reading as treated, it no longer counts as danger.
            # A new dangerous reading has a new id, so it will raise the alert again.
            if is_danger:
                treated = db.query(Treatment).filter(
                    Treatment.reading_id == last_reading.id
                ).first() is not None
                if treated:
                    is_danger = False
                    is_sugar_high = False
                    is_bp_high = False

            if is_danger:
                danger_count += 1
                status = "Danger"
                status_class = "danger"
                danger_patients.append({
                    "name": user.name or user.phone,
                    "alert_msg": alert_msg,
                    "last_reading": local_time.strftime("%I:%M %p"),
                    "phone": user.phone,
                    "reading_id": last_reading.id
                })
            elif days_ago >= 3:
                missing_count += 1
                status = "Missing"
                status_class = "warning"
            else:
                active_count += 1
                status = "Active"
                status_class = "success"

            last_sugar = f"{last_reading.sugar} mg/dL" if last_reading.sugar else "-"
            last_bp = f"{last_reading.bp_systolic}/{last_reading.bp_diastolic}" if last_reading.bp_systolic else "-"
            last_reading_str = local_time.strftime("%d %b, %I:%M %p")
        else:
            no_data_count += 1
            status = "No Data"
            status_class = "normal"
            last_sugar = "-"
            last_bp = "-"
            last_reading_str = "Never"
            is_sugar_high = False
            is_sugar_normal = False
            is_bp_high = False

        patients.append({
            "name": user.name,
            "phone": user.phone,
            "condition": user.condition,
            "last_sugar": last_sugar,
            "last_bp": last_bp,
            "last_reading": last_reading_str,
            "status": status,
            "status_class": status_class,
            "is_sugar_high": is_sugar_high,
            "is_sugar_normal": is_sugar_normal,
            "is_bp_high": is_bp_high,
            "reading_id": reading_id,
            "treated": treated
        })

    template = env.get_template("dashboard.html")
    html = template.render(
        patients=patients,
        danger_patients=danger_patients,
        total_patients=len(users),
        logged_today=logged_today,
        danger_count=danger_count,
        missing_count=missing_count,
        active_count=active_count,
        no_data_count=no_data_count
    )
    return HTMLResponse(content=html)


@router.post("/treated/{reading_id}")
def mark_treated(reading_id: int, db: Session = Depends(get_db)):
    """Doctor clicks 'Mark as Treated' on a danger alert."""
    reading = db.query(Reading).filter(Reading.id == reading_id).first()
    if reading:
        already = db.query(Treatment).filter(Treatment.reading_id == reading_id).first()
        if not already:
            db.add(Treatment(phone=reading.phone, reading_id=reading_id))
            db.commit()
    return RedirectResponse(url="/dashboard/", status_code=303)


@router.get("/patient/{phone}", response_class=HTMLResponse)
def patient_history(phone: str, db: Session = Depends(get_db)):
    phone = unquote(phone)
    patient = db.query(User).filter(User.phone == phone).first()
    readings = db.query(Reading).filter(
        Reading.phone == phone
    ).order_by(Reading.created_at.desc()).all()

    template = env.get_template("patient.html")
    html = template.render(
        patient=patient,
        readings=readings
    )
    return HTMLResponse(content=html)