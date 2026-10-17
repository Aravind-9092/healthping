from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Treatment(Base):
    """A doctor marked this specific reading as treated."""
    __tablename__ = "treatments"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True)
    reading_id = Column(Integer, index=True)
    treated_at = Column(DateTime(timezone=True), server_default=func.now())