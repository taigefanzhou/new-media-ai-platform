from sqlmodel import SQLModel, Session, create_engine
from sqlmodel import select
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import User, UserRole


settings = get_settings()
engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    seed_admin_user()


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
