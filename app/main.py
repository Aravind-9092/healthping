from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes import whatsapp, dashboard
from app.database import engine
from app.models import user, reading
from app.models import user, reading, treatment
import os

user.Base.metadata.create_all(bind=engine)
reading.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HealthPing",
    description="Your daily health companion on WhatsApp",
    version="1.0.0"
)

os.makedirs("reports", exist_ok=True)
app.mount("/reports", StaticFiles(directory="reports"), name="reports")
app.include_router(whatsapp.router)
app.include_router(dashboard.router)

@app.get("/")
def root():
    return {"message": "HealthPing is running!"}