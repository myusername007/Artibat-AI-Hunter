from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String(100), nullable=False)
    city = Column(String(100))
    department = Column(String(10))
    project = Column(Text)
    type = Column(String(50))          # direct_lead / weak_signal_a / b / c
    surface = Column(Float)
    budget = Column(Float)
    phone = Column(String(30))
    email = Column(String(150))
    priority = Column(String(10))      # HIGH / MEDIUM / LOW
    url = Column(String(500), unique=True, nullable=False)
    description = Column(Text)

    def __repr__(self):
        return f"<Lead {self.source} | {self.city} | {self.priority}>"