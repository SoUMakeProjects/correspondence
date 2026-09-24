from alembic import context

from app import models  # noqa: F401
from app.db import Base, UTCDateTime


def render_type(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from app.db import UTCDateTime")
        return "UTCDateTime()"
    return False


connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError(
        "Use the application's migration command with an explicit database connection."
    )
context.configure(connection=connection, target_metadata=Base.metadata, render_item=render_type)
with context.begin_transaction():
    context.run_migrations()
