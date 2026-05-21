from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.reading import Reading
from datetime import datetime, timedelta
import jinja2

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
env = jinja2.Environment(loader=jinja2.FileSystemLoader("app/templates"))

@router.get("/", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.onboarding_step == "complete").all()
    
    today = datetime.utcnow().date()
    
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

        if last_reading:
            last_date = last_reading.created_at.date()
            days_ago = (today - last_date).days

            if days_ago == 0:
                logged_today += 1

            if days_ago >= 3:
                missing_count += 1
                status = "Missing"
                status_class = "warning"
            else:
                active_count += 1
                status = "Active"
                status_class = "success"

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

            if is_danger:
                danger_count += 1
                if days_ago >= 3:
                    missing_count -= 1
                active_count = max(0, active_count - 1)
                status = "Danger"
                status_class = "danger"
                danger_patients.append({
                    "name": user.name or user.phone,
                    "alert_msg": alert_msg,
                    "last_reading": last_reading.created_at.strftime("%I:%M %p")
                })

            last_sugar = f"{last_reading.sugar} mg/dL" if last_reading.sugar else "-"
            last_bp = f"{last_reading.bp_systolic}/{last_reading.bp_diastolic}" if last_reading.bp_systolic else "-"
            last_reading_str = last_reading.created_at.strftime("%d %b, %I:%M %p")
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
            "is_bp_high": is_bp_high
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