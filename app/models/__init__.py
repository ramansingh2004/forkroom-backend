"""SQLAlchemy models.

Import every model in ``import_all_models`` so Alembic can discover it.
"""


def import_all_models() -> None:
    """Import model modules before Alembic reads Base.metadata."""
