from sqlalchemy import create_engine

from app.config import get_required_setting


DATABASE_URL = get_required_setting("DATABASE_URL")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)