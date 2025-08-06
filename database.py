from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from config import DB_URL

engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True)
    name = Column(String)
    pair_code = Column(String, nullable=True)
    pair_id = Column(Integer, nullable=True)

class Pair(Base):
    __tablename__ = 'pairs'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(String)

class AssignedTask(Base):
    __tablename__ = 'assigned_tasks'
    id = Column(Integer, primary_key=True)
    pair_id = Column(Integer)
    task_id = Column(Integer)
    status = Column(String, default="pending")  # pending, accepted, rejected
    date = Column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)