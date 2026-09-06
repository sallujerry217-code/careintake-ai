from datetime import date, datetime, timezone
from enum import Enum
import re
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, field_validator

STATES = set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI'.split())

def phone(value):
    if not isinstance(value, str) or re.search(r'[^0-9+().\s-]', value):
        raise ValueError('Provide a complete 10-digit U.S. phone number.')
    digits = re.sub(r'\D', '', value)
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    if not re.fullmatch(r'[2-9][0-9]{2}[2-9][0-9]{6}', digits):
        raise ValueError('Provide a valid 10-digit U.S. phone number, including area code.')
    return digits

def dob(value):
    if isinstance(value, str) and re.fullmatch(r'\d{2}/\d{2}/\d{4}', value):
        try:
            value = datetime.strptime(value, '%m/%d/%Y').date()
        except ValueError:
            raise ValueError('Provide a valid date in MM/DD/YYYY or YYYY-MM-DD format.')
    if not isinstance(value, (str, date)):
        raise ValueError('Provide a date in MM/DD/YYYY or YYYY-MM-DD format.')
    return value

Phone = Annotated[str, BeforeValidator(phone)]
DOB = Annotated[date, BeforeValidator(dob)]
class Sex(str, Enum):
    male = 'Male'
    female = 'Female'
    other = 'Other'
    decline = 'Decline to Answer'

class PatientInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    date_of_birth: DOB
    sex: Sex
    phone_number: Phone
    email: str | None = Field(default=None, max_length=254)
    address_line_1: str = Field(min_length=1, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str
    zip_code: str
    insurance_provider: str | None = Field(default=None, max_length=150)
    insurance_member_id: str | None = Field(default=None, max_length=100, pattern=r'^[A-Za-z0-9]+$')
    preferred_language: str = Field(default='English', min_length=1, max_length=60)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: Phone | None = None

    @field_validator('first_name', 'last_name')
    @classmethod
    def names(cls, v):
        if not any(c.isalpha() for c in v) or not all(c.isalpha() or c in "'-’" for c in v):
            raise ValueError('Use letters, apostrophes or hyphens only.')
        return v.replace('’', "'")

    @field_validator('date_of_birth')
    @classmethod
    def past_dob(cls, v):
        if v > datetime.now(timezone.utc).date():
            raise ValueError('Date of birth cannot be in the future.')
        return v

    @field_validator('state')
    @classmethod
    def state_code(cls, v):
        if v.upper() not in STATES:
            raise ValueError('Use a valid two-letter U.S. state abbreviation, such as NJ.')
        return v.upper()

    @field_validator('zip_code')
    @classmethod
    def zip_format(cls, v):
        if not re.fullmatch(r'[0-9]{5}(-[0-9]{4})?', v):
            raise ValueError('Use a five-digit ZIP code or ZIP+4.')
        return v

    @field_validator('email')
    @classmethod
    def email_format(cls, v):
        if v is not None:
            from email_validator import validate_email, EmailNotValidError
            try:
                return validate_email(v, check_deliverability=False).normalized
            except EmailNotValidError as e:
                raise ValueError(str(e))
        return v

    @field_validator('*', mode='before')
    @classmethod
    def clean(cls, v):
        if isinstance(v, str):
            if any(ord(c) < 32 for c in v):
                raise ValueError('Control characters are not allowed.')
            return v.strip()
        return v

class PatientOut(PatientInput):
    model_config = ConfigDict(from_attributes=True)
    patient_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @field_validator('created_at', 'updated_at', 'deleted_at')
    @classmethod
    def utc(cls, v):
        return v.replace(tzinfo=timezone.utc) if v and v.tzinfo is None else v


class AppointmentInput(BaseModel):
    """Bonus: appointment scheduling schema."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    patient_id: str
    appointment_date: date
    appointment_time: str = Field(min_length=1, max_length=20)
    appointment_type: str = Field(default='New Patient Visit', max_length=100)
    provider_name: str = Field(default='Dr. Sarah Chen', max_length=150)
    location: str = Field(default='CareIntake Health Center, 7 Clyde Road, Somerset NJ 08873', max_length=200)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator('appointment_date')
    @classmethod
    def future_date(cls, v):
        if v < datetime.now(timezone.utc).date():
            raise ValueError('Appointment date must be today or in the future.')
        return v

