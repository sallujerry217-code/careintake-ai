import logging
from sqlalchemy import select
from .models import Patient, now
from .schemas import PatientInput, PatientOut

log = logging.getLogger('careintake')
class DomainError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details

def output(patient):
    return PatientOut.model_validate(patient).model_dump(mode='json')

def get_patient(db, patient_id):
    p = db.scalar(select(Patient).where(Patient.patient_id == str(patient_id), Patient.deleted_at.is_(None)))
    if p is None:
        raise DomainError(404, 'NOT_FOUND', 'Patient not found.')
    return p

def by_phone(db, phone_number):
    return db.scalar(select(Patient).where(Patient.phone_number == phone_number, Patient.deleted_at.is_(None)))

def create_patient(db, data):
    p = by_phone(db, data.phone_number)
    if p:
        raise DomainError(409, 'DUPLICATE_PHONE', 'An active patient already uses this phone number.', {'patient_id': p.patient_id})
    p = Patient(**data.model_dump())
    db.add(p)
    db.flush()
    log.info('patient.created', extra={'patient_id': p.patient_id})
    return p

def update_patient(db, patient_id, changes):
    p = get_patient(db, patient_id)
    unknown = set(changes) - set(PatientInput.model_fields)
    if unknown:
        raise DomainError(422, 'VALIDATION_ERROR', 'Unknown or read-only fields.', {'fields': sorted(unknown)})
    data = PatientInput.model_validate({**{k: getattr(p, k) for k in PatientInput.model_fields}, **changes})
    other = by_phone(db, data.phone_number)
    if other and other.patient_id != p.patient_id:
        raise DomainError(409, 'DUPLICATE_PHONE', 'An active patient already uses this phone number.')
    for key, value in data.model_dump().items():
        setattr(p, key, value)
    p.updated_at = now()
    db.flush()
    log.info('patient.updated', extra={'patient_id': p.patient_id})
    return p
