import os
import sys
from pathlib import Path
os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ADMIN_API_KEY'] = 'test-admin'
os.environ['VAPI_SECRET'] = 'test-webhook'
os.environ['SIGNING_SECRET'] = 'test-secret-at-least-thirty-two-characters'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db import Base, get_db

@pytest.fixture
def client(tmp_path):
    engine = create_engine('sqlite:///'+str(tmp_path/'test.db'), connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    def test_db():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer test-admin'
        client.factory = factory
        yield client
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def patient():
    return {'first_name':'Morgan','last_name':"O'Connor",'date_of_birth':'1998-02-08','sex':'Female','phone_number':'+1 (732) 555-0184','address_line_1':'27 Oak Street','city':'Somerset','state':'nj','zip_code':'08873'}
