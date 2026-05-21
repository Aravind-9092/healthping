from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    phone = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=True)
    condition = Column(String, nullable=True)
    medicines = Column(String, nullable=True)
    language = Column(String, default="english")
    onboarding_step = Column(String, default="ask_name")
    created_at = Column(DateTime(timezone=True), server_default=func.now())