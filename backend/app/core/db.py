from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel import select
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import User, UserRole


settings = get_settings()
engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    apply_sqlite_migrations()
    seed_admin_user()


def apply_sqlite_migrations() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(publishrecord)")).fetchall()
        columns = {row[1] for row in rows}
        migrations = {
            "platform_account_id": "ALTER TABLE publishrecord ADD COLUMN platform_account_id INTEGER",
            "hashtags": "ALTER TABLE publishrecord ADD COLUMN hashtags VARCHAR DEFAULT ''",
            "caption": "ALTER TABLE publishrecord ADD COLUMN caption VARCHAR DEFAULT ''",
            "scheduled_at": "ALTER TABLE publishrecord ADD COLUMN scheduled_at DATETIME",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(text(statement))


def seed_admin_user() -> None:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == settings.admin_username)).first()
        if existing is not None:
            return
        user = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            role=UserRole.admin,
        )
        session.add(user)
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
