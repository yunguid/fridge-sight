from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine('sqlite:///fridge_state.db')
Session = sessionmaker(bind=engine)

class FridgeEvent(Base):
    __tablename__ = 'fridge_events'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String)  # 'door_open', 'door_close', 'item_detected'
    image_path = Column(String, nullable=True)
    light_level = Column(Float, nullable=True)

class FridgeItem(Base):
    __tablename__ = 'fridge_items'
    
    id = Column(Integer, primary_key=True)
    name = Column(String)
    quantity = Column(Integer)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    confidence = Column(Float)
    is_present = Column(Boolean, default=True)

class ItemHistory(Base):
    __tablename__ = 'item_history'
    
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer)
    event_id = Column(Integer)
    action = Column(String)  # 'added', 'removed', 'updated'
    quantity_change = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create all tables
Base.metadata.create_all(engine) 