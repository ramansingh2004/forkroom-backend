"""SQLAlchemy model registration."""


def import_all_models() -> None:
    """Import every model before Alembic reads Base.metadata."""
    from app.models.user import User  # noqa: F401
