"""Atomic SQLite rebuild of acquisition uniqueness, retaining every source byte/ID."""
import re
from sqlalchemy import inspect, text
from sqlmodel import Session
from .assessment_models import AssessmentOccasion, AssessmentAttempt, AssessmentSourceLink, AssessmentOccasionClassification


def _rebuild(connection, table, old_key):
    schema = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"), {'name': table}).scalar_one()
    columns = {c['name'] for c in inspect(connection).get_columns(table)}
    indexes = connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=:name AND sql IS NOT NULL"), {'name': table}).all()
    unique_constraints = inspect(connection).get_unique_constraints(table)
    needs_rebuild = any(x['column_names'] == [old_key] for x in unique_constraints)
    if needs_rebuild:
        temporary = table + '_assessment_rebuild'
        modified = re.sub(r'CREATE TABLE\s+(?:"' + table + r'"|' + table + r')', f'CREATE TABLE "{temporary}"', schema, count=1, flags=re.I)
        # Original schemas use either table constraints or inline SQLite UNIQUE.
        modified = re.sub(r',\s*(?:CONSTRAINT\s+\w+\s+)?UNIQUE\s*\(\s*"?' + old_key + r'"?\s*\)', '', modified, flags=re.I)
        modified = re.sub(r'("?' + old_key + r'"?\s+[^,()]*?)\s+UNIQUE\b', r'\1', modified, flags=re.I)
        connection.execute(text(modified))
        names = ', '.join(f'"{name}"' for name in columns)
        connection.execute(text(f'INSERT INTO "{temporary}" ({names}) SELECT {names} FROM "{table}"'))
        connection.execute(text(f'DROP TABLE "{table}"'))
        connection.execute(text(f'ALTER TABLE "{temporary}" RENAME TO "{table}"'))
        for _, sql in indexes:
            if not (re.search(r'CREATE UNIQUE INDEX', sql, re.I) and re.search(r'\(\s*"?' + old_key + r'"?\s*\)', sql)):
                connection.execute(text(sql))
    else:
        for name, sql in indexes:
            if re.search(r'CREATE UNIQUE INDEX', sql, re.I) and re.search(r'\(\s*"?' + old_key + r'"?\s*\)', sql):
                connection.execute(text(f'DROP INDEX "{name}"'))
    if 'attempt_id' not in columns:
        connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN attempt_id VARCHAR REFERENCES assessment_attempt(id)'))
    connection.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_attempt_id ON "{table}" (attempt_id)'))


def migrate_assessments(engine):
    from .assessment_adapters import sync_sources
    from .purpose_models import PurposeProvenance, PurposeClassification
    with engine.connect() as connection:
        # sqlite3 legacy transaction control otherwise autocommits DDL before DML.
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            tables = set(inspect(connection).get_table_names())
            for model in (PurposeProvenance, PurposeClassification, AssessmentOccasion, AssessmentAttempt, AssessmentSourceLink, AssessmentOccasionClassification):
                model.__table__.create(connection, checkfirst=True)
            for table, key in [('pvt_assessment', 'visit_id'), ('screenresult', 'participant_id'), ('practiceresult', '__none__')]:
                if table in tables:
                    _rebuild(connection, table, key)
            with Session(bind=connection) as db:
                sync_sources(db)
                db.flush()
            violations = connection.exec_driver_sql('PRAGMA foreign_key_check').all()
            if violations:
                raise RuntimeError(f'assessment migration foreign key violations: {violations}')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
