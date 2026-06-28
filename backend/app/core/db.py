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
        default_owner_id = connection.execute(
            text("SELECT id FROM user WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1")
        ).scalar()

        def add_owner_column(table_name: str) -> None:
            rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            columns = {row[1] for row in rows}
            if rows and "owner_user_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN owner_user_id INTEGER"))
            if rows and default_owner_id is not None:
                connection.execute(
                    text(f"UPDATE {table_name} SET owner_user_id = :owner_id WHERE owner_user_id IS NULL"),
                    {"owner_id": default_owner_id},
                )

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
                    quality_score FLOAT DEFAULT 0,
                    quality_summary VARCHAR DEFAULT '',
                    model_enhanced BOOLEAN DEFAULT 0,
                    error_message VARCHAR,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        analysis_rows = connection.execute(text("PRAGMA table_info(referencevideoanalysis)")).fetchall()
        analysis_columns = {row[1] for row in analysis_rows}
        analysis_migrations = {
            "quality_score": "ALTER TABLE referencevideoanalysis ADD COLUMN quality_score FLOAT DEFAULT 0",
            "quality_summary": "ALTER TABLE referencevideoanalysis ADD COLUMN quality_summary VARCHAR DEFAULT ''",
            "model_enhanced": "ALTER TABLE referencevideoanalysis ADD COLUMN model_enhanced BOOLEAN DEFAULT 0",
        }
        for column, statement in analysis_migrations.items():
            if analysis_rows and column not in analysis_columns:
                connection.execute(text(statement))

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

        for table_name in (
            "material",
            "trendingsearch",
            "trendingvideo",
            "transcriptiontask",
            "referencevideoanalysis",
            "topic",
            "script",
            "digitalhuman",
            "videotask",
            "platformaccount",
            "publishrecord",
        ):
            add_owner_column(table_name)

        human_rows = connection.execute(text("PRAGMA table_info(digitalhuman)")).fetchall()
        human_columns = {row[1] for row in human_rows}
        human_migrations = {
            "source_video_material_id": "ALTER TABLE digitalhuman ADD COLUMN source_video_material_id INTEGER",
            "volcengine_auth_status": "ALTER TABLE digitalhuman ADD COLUMN volcengine_auth_status VARCHAR DEFAULT 'not_started'",
            "volcengine_auth_url": "ALTER TABLE digitalhuman ADD COLUMN volcengine_auth_url VARCHAR",
            "volcengine_byted_token": "ALTER TABLE digitalhuman ADD COLUMN volcengine_byted_token VARCHAR",
            "volcengine_auth_result_code": "ALTER TABLE digitalhuman ADD COLUMN volcengine_auth_result_code VARCHAR",
            "volcengine_asset_group_id": "ALTER TABLE digitalhuman ADD COLUMN volcengine_asset_group_id VARCHAR",
            "volcengine_asset_group_uri": "ALTER TABLE digitalhuman ADD COLUMN volcengine_asset_group_uri VARCHAR",
            "volcengine_asset_uri": "ALTER TABLE digitalhuman ADD COLUMN volcengine_asset_uri VARCHAR",
            "volcengine_asset_status": "ALTER TABLE digitalhuman ADD COLUMN volcengine_asset_status VARCHAR",
            "volcengine_auth_payload": "ALTER TABLE digitalhuman ADD COLUMN volcengine_auth_payload VARCHAR DEFAULT ''",
        }
        for column, statement in human_migrations.items():
            if human_rows and column not in human_columns:
                connection.execute(text(statement))

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
            "subtitle_enabled": "ALTER TABLE videotask ADD COLUMN subtitle_enabled BOOLEAN DEFAULT 1",
            "subtitle_style": "ALTER TABLE videotask ADD COLUMN subtitle_style VARCHAR DEFAULT 'auto'",
            "subtitle_status": "ALTER TABLE videotask ADD COLUMN subtitle_status VARCHAR DEFAULT 'pending'",
            "subtitle_srt_path": "ALTER TABLE videotask ADD COLUMN subtitle_srt_path VARCHAR",
            "subtitle_ass_path": "ALTER TABLE videotask ADD COLUMN subtitle_ass_path VARCHAR",
            "captioned_output_path": "ALTER TABLE videotask ADD COLUMN captioned_output_path VARCHAR",
        }
        for column, statement in video_task_migrations.items():
            if video_task_rows and column not in video_task_columns:
                connection.execute(text(statement))

        trending_search_rows = connection.execute(text("PRAGMA table_info(trendingsearch)")).fetchall()
        trending_search_columns = {row[1] for row in trending_search_rows}
        trending_search_migrations = {
            "limit": 'ALTER TABLE trendingsearch ADD COLUMN "limit" INTEGER DEFAULT 20',
            "min_like_count": "ALTER TABLE trendingsearch ADD COLUMN min_like_count INTEGER DEFAULT 0",
            "min_comment_count": "ALTER TABLE trendingsearch ADD COLUMN min_comment_count INTEGER DEFAULT 0",
            "sort_by": "ALTER TABLE trendingsearch ADD COLUMN sort_by VARCHAR DEFAULT 'engagement'",
        }
        for column, statement in trending_search_migrations.items():
            if trending_search_rows and column not in trending_search_columns:
                connection.execute(text(statement))

        video_segment_rows = connection.execute(text("PRAGMA table_info(videosegment)")).fetchall()
        video_segment_columns = {row[1] for row in video_segment_rows}
        video_segment_migrations = {
            "material_id": "ALTER TABLE videosegment ADD COLUMN material_id INTEGER",
            "material_match_notes": "ALTER TABLE videosegment ADD COLUMN material_match_notes VARCHAR DEFAULT ''",
        }
        for column, statement in video_segment_migrations.items():
            if video_segment_rows and column not in video_segment_columns:
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
