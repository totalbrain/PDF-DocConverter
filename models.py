import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

Base = declarative_base()

class ConversionJob(Base):
    __tablename__ = "conversion_jobs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(500), nullable=False)
    total_pages = Column(Integer, nullable=False)
    completed_pages = Column(Integer, default=0)
    failed_pages = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    output_path = Column(String(500), nullable=True)
    output_paths_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    custom_prompt = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

def get_engine():
    if not DATABASE_URL:
        return None
    return create_engine(DATABASE_URL)

def get_session():
    engine = get_engine()
    if not engine:
        return None
    Session = sessionmaker(bind=engine)
    return Session()

def init_db():
    engine = get_engine()
    if engine:
        Base.metadata.create_all(engine)

def create_job(filename: str, total_pages: int, custom_prompt: str = None) -> int:
    session = get_session()
    if not session:
        return None
    job = ConversionJob(
        filename=filename,
        total_pages=total_pages,
        status="processing",
        custom_prompt=custom_prompt
    )
    session.add(job)
    session.commit()
    job_id = job.id
    session.close()
    return job_id

def update_job_progress(job_id: int, completed_pages: int, failed_pages: int = 0):
    session = get_session()
    if not session:
        return
    job = session.query(ConversionJob).filter_by(id=job_id).first()
    if job:
        job.completed_pages = completed_pages
        job.failed_pages = failed_pages
        session.commit()
    session.close()

def complete_job(job_id: int, output_path: str, processing_time: float, failed_count: int = 0, all_output_paths: list = None):
    session = get_session()
    if not session:
        return
    job = session.query(ConversionJob).filter_by(id=job_id).first()
    if job:
        job.status = "completed"
        job.output_path = output_path
        if all_output_paths:
            import json
            job.output_paths_json = json.dumps(all_output_paths)
        job.completed_at = datetime.utcnow()
        job.processing_time_seconds = processing_time
        job.failed_pages = failed_count
        session.commit()
    session.close()

def fail_job(job_id: int, error_message: str):
    session = get_session()
    if not session:
        return
    job = session.query(ConversionJob).filter_by(id=job_id).first()
    if job:
        job.status = "failed"
        job.error_message = error_message
        job.completed_at = datetime.utcnow()
        session.commit()
    session.close()

def cancel_job(job_id: int, completed_pages: int):
    session = get_session()
    if not session:
        return
    job = session.query(ConversionJob).filter_by(id=job_id).first()
    if job:
        job.status = "cancelled"
        job.completed_pages = completed_pages
        job.completed_at = datetime.utcnow()
        session.commit()
    session.close()

def get_all_jobs():
    session = get_session()
    if not session:
        return []
    jobs = session.query(ConversionJob).order_by(ConversionJob.created_at.desc()).all()
    result = []
    for job in jobs:
        output_paths = []
        if job.output_paths_json:
            import json
            try:
                output_paths = json.loads(job.output_paths_json)
            except:
                pass
        result.append({
            'id': job.id,
            'filename': job.filename,
            'total_pages': job.total_pages,
            'completed_pages': job.completed_pages,
            'failed_pages': job.failed_pages,
            'status': job.status,
            'output_path': job.output_path,
            'output_paths': output_paths,
            'created_at': job.created_at,
            'completed_at': job.completed_at,
            'processing_time_seconds': job.processing_time_seconds,
            'custom_prompt': job.custom_prompt,
            'error_message': job.error_message
        })
    session.close()
    return result

def delete_job(job_id: int):
    session = get_session()
    if not session:
        return
    job = session.query(ConversionJob).filter_by(id=job_id).first()
    if job:
        session.delete(job)
        session.commit()
    session.close()
