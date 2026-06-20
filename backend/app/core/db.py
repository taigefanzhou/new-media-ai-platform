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

        account_rows = connection.execute(text("PRAGMA table_info(platformaccount)")).fetchall()
        account_columns = {row[1] for row in account_rows}
        if account_rows and "is_default" not in account_columns:
            connection.execute(text("ALTER TABLE platformaccount ADD COLUMN is_default BOOLEAN DEFAULT 0"))

        human_rows = connection.execute(text("PRAGMA table_info(digitalhuman)")).fetchall()
        human_columns = {row[1] for row in human_rows}
        if human_rows and "source_video_material_id" not in human_columns:
            connection.execute(text("ALTER TABLE digitalhuman ADD COLUMN source_video_material_id INTEGER"))

        video_task_rows = connection.execute(text("PRAGMA table_info(videotask)")).fetchall()
        video_task_columns = {row[1] for row in video_task_rows}
        video_task_migrations = {
            "generation_mode": "ALTER TABLE videotask ADD COLUMN generation_mode VARCHAR DEFAULT 'short'",
            "segment_count": "ALTER TABLE videotask ADD COLUMN segment_count INTEGER DEFAULT 1",
            "completed_segments": "ALTER TABLE videotask ADD COLUMN completed_segments INTEGER DEFAULT 0",
        }
        for column, statement in video_task_migrations.items():
            if video_task_rows and column not in video_task_columns:
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
