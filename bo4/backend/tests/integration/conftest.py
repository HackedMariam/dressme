"""Connexion PostgreSQL optionnelle et en lecture seule pour les tests d'intégration.

Les tests sont ignorés si POSTGRES_PASSWORD n'est pas défini. La lecture seule
est imposée côté serveur (default_transaction_read_only) et côté client.
"""

import os

import psycopg
import pytest


@pytest.fixture(scope="session")
def db_conn():
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_PASSWORD non défini : tests d'intégration ignorés")

    try:
        conn = psycopg.connect(
            host=os.getenv("DRESSME_DB_HOST", "localhost"),
            port=int(os.getenv("DRESSME_DB_PORT", "5432")),
            dbname=os.getenv("DRESSME_DB_NAME", "dressme_db"),
            user=os.getenv("DRESSME_DB_USER", "postgres"),
            password=password,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        )
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL indisponible : {type(error).__name__}")

    conn.read_only = True
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture(scope="session")
def user_with_items(db_conn):
    """Un utilisateur quelconque possédant au moins un vêtement disponible."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM wardrobe_items WHERE available = TRUE "
            "GROUP BY user_id ORDER BY user_id LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("Aucun utilisateur avec des vêtements disponibles")
    return row[0]
