import os

import pytest

from app.db import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def clean_database(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
