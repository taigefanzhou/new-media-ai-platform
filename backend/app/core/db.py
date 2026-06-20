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
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS referencevideoanalysis (
                    id INTEGER NOT NULL PRIMARY KEY,
                    material_id INTEGER NOT NULL,
                    provider VARCHAR DEFAULT 'local',
                    status VARCHAR DEFAULT 'queued',
                    language VARCHAR DEFAULT 'zh-CN',
                    duration_seconds FLOAT DEFAULT 0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    fps FLOAT DEFAULT 0,
                    has_audio BOOLEAN DEFAULT 0,
                    scene_count INTEGER DEFAULT 0,
                    avg_shot_seconds FLOAT DEFAULT 0,
                    visual_change_frequency VARCHAR DEFAULT '',
                    contact_sheet_path VARCHAR,
                    dense_contact_sheet_path VARCHAR,
                    timeline_json VARCHAR DEFAULT '',
                    transcript VARCHAR DEFAULT '',
                    script_analysis VARCHAR DEFAULT '',
                    shooting_analysis VARCHAR DEFAULT '',
                    editing_analysis VARCHAR DEFAULT '',
                    reusable_template VARCHAR DEFAULT '',
                    reuse_notes VARCHAR DEFAULT '',
                    error_message VARCHAR,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )

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

        script_rows = connection.execute(text("PRAGMA table_info(script)")).fetchall()
        script_columns = {row[1] for row in script_rows}
        script_migrations = {
            "storyboard_plan": "ALTER TABLE script ADD COLUMN storyboard_plan VARCHAR DEFAULT ''",
            "target_platform": "ALTER TABLE script ADD COLUMN target_platform VARCHAR DEFAULT 'douyin'",
        }
        for column, statement in script_migrations.items():
            if script_rows and column not in script_columns:
                connection.execute(text(statement))

        video_task_rows = connection.execute(text("PRAGMA table_info(videotask)")).fetchall()
        video_task_columns = {row[1] for row in video_task_rows}
        video_task_migrations = {
            "target_platform": "ALTER TABLE videotask ADD COLUMN target_platform VARCHAR DEFAULT 'douyin'",
            "export_profile": "ALTER TABLE videotask ADD COLUMN export_profile VARCHAR DEFAULT 'douyin_vertical'",
            "export_width": "ALTER TABLE videotask ADD COLUMN export_width INTEGER DEFAULT 1080",
            "export_height": "ALTER TABLE videotask ADD COLUMN export_height INTEGER DEFAULT 1920",
            "generation_mode": "ALTER TABLE videotask ADD COLUMN generation_mode VARCHAR DEFAULT 'short'",
            "production_mode": "ALTER TABLE videotask ADD COLUMN production_mode VARCHAR DEFAULT 'talking_head_template'",
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
