"""Development only: validate Alembic on a temporary database, never downgrade the configured DB.

Run inside the API image with this file mounted at /tmp/validate_migrations.py.
The configured PostgreSQL role must have CREATEDB permission.
"""
import os
import subprocess
import uuid

from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def main() -> None:
    name = "statuswatch_migration_test_" + uuid.uuid4().hex
    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    test_engine = None
    created = False
    try:
        with admin.connect() as connection:
            # Name is generated locally from a UUID, never supplied by a client.
            connection.connection.driver_connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
            )
        created = True
        test_url = url.set(database=name)
        env = {**os.environ, "DATABASE_URL": test_url.render_as_string(hide_password=False)}
        test_engine = create_engine(test_url)

        def alembic(*args: str) -> None:
            subprocess.run(["alembic", *args], env=env, check=True)

        alembic("upgrade", "head")
        with test_engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, email, full_name, password_hash) VALUES (:id, :email, :name, :hash)"),
                               {"id": uuid.uuid4(), "email": "migration@example.com", "name": "Migration", "hash": "test-only"})
        alembic("downgrade", "-1")
        assert "monitors" not in inspect(test_engine).get_table_names()
        with test_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
        alembic("upgrade", "head")
        assert "monitors" in inspect(test_engine).get_table_names()
        alembic("current")
        alembic("check")
        print("PASS: upgrade, downgrade preserves users, re-upgrade, metadata check")
    finally:
        if test_engine is not None:
            test_engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.connection.driver_connection.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(name))
                )
        admin.dispose()


if __name__ == "__main__":
    main()
