"""Run only against a dedicated TEST_DATABASE_URL. Roll back all fixture writes."""
import os
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from app.db import Base
from app.models import Patient
from app.schemas import PatientInput
from app.services import create_patient, update_patient
url=os.environ['TEST_DATABASE_URL']
engine=create_engine(url)
assert engine.dialect.name=='postgresql'
Base.metadata.create_all(engine)
with engine.connect() as connection:
    transaction=connection.begin()
    with Session(bind=connection) as db:
        patient=PatientInput(first_name='Test',last_name='Fixture',date_of_birth='1998-02-08',sex='Other',phone_number='7325550198',address_line_1='1 Test Street',city='Somerset',state='NJ',zip_code='08873')
        p=create_patient(db,patient)
        update_patient(db,p.patient_id,{'last_name':'Updated'})
        assert db.scalar(select(Patient).where(Patient.patient_id==p.patient_id)).last_name=='Updated'
        db.execute(text('SELECT 1'))
    transaction.rollback()
engine.dispose()
print('PostgreSQL schema, CRUD and transaction rollback: PASS')
