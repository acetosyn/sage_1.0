"""Idempotent additive schema install. No historical rows or tables are altered."""
from sqlalchemy import inspect
from packages.database import db


def install_business_schema():
    tables=[table for table in db.metadata.sorted_tables if table.name.startswith('business_')]
    before=set(inspect(db.engine).get_table_names())
    with db.engine.begin() as connection:
        for table in tables:table.create(connection,checkfirst=True)
    inspector=inspect(db.engine)
    for table in tables:
        actual={col['name'] for col in inspector.get_columns(table.name)}
        missing=set(table.c.keys())-actual
        if missing:raise RuntimeError(f'{table.name} needs a reviewed column migration: {sorted(missing)}')
    return [table.name for table in tables if table.name not in before]
