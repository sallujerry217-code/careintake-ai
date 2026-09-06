"""Vapi custom-tool adapter. Tool results and writes share one DB transaction."""
import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from pydantic import ValidationError
from .config import settings
from .models import VoiceDraft, ToolReceipt, CallRecord, now
from .schemas import PatientInput, phone
from .services import DomainError, by_phone, get_patient, create_patient, update_patient, output


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def sign(payload):
    data = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()).decode()
    signature = hmac.new(settings().signing_secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return data + '.' + signature


def decode(token):
    try:
        data, signature = token.rsplit('.', 1)
        expected = hmac.new(settings().signing_secret.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(data))
        if payload['expires'] < time.time():
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise DomainError(422, 'INVALID_CONFIRMATION', 'Preparation expired or invalid. Prepare and read back the details again.')


def call_record(db, call_id):
    call = db.scalar(select(CallRecord).where(CallRecord.provider_call_id == call_id))
    if not call:
        call = CallRecord(provider_call_id=call_id)
        db.add(call)
        db.flush()
    return call


def execute(db, name, args, call_id):
    if name == 'find_patient_by_phone':
        number = phone(args.get('phone_number'))
        p = by_phone(db, number)
        if not p:
            return {'found': False}
        # Require caller-supplied name and DOB before revealing demographics.
        if not args.get('last_name') or not args.get('date_of_birth'):
            return {'found': True, 'verification_required': True, 'message': 'Ask caller for their last name and date of birth to verify the record.'}
        from .schemas import dob
        birthday = dob(args['date_of_birth'])
        if str(p.date_of_birth) != str(birthday) or p.last_name.casefold() != args['last_name'].strip().casefold():
            return {'found': True, 'verified': False, 'message': 'Details did not match. Do not disclose or update the record.'}
        # Bind a verification grant to this call and patient via signed token.
        return {'found': True, 'verified': True, 'patient': output(p), 'verification_token': sign({'patient_id': p.patient_id, 'call_id': call_id, 'expires': time.time()+900})}
    if name == 'prepare_patient':
        data = PatientInput.model_validate(args.get('patient', {}))
        patient_id = args.get('patient_id')
        if patient_id:
            grant = decode(args.get('verification_token', ''))
            if grant.get('patient_id') != patient_id or grant.get('call_id') != call_id:
                raise DomainError(403, 'VERIFICATION_REQUIRED', 'Verify the returning patient before an update.')
            get_patient(db, patient_id)
        else:
            if by_phone(db, data.phone_number):
                raise DomainError(409, 'DUPLICATE_PHONE', 'An active record already exists. Verify the caller and offer to update it.')
        payload = {'patient': data.model_dump(mode='json'), 'patient_id': patient_id, 'call_id': call_id, 'expires': time.time()+900}
        token = sign(payload)
        draft = db.get(VoiceDraft, call_id)
        if not draft:
            draft = VoiceDraft(call_id=call_id)
            db.add(draft)
        draft.digest, draft.expires_at, draft.result = digest(token), now()+timedelta(minutes=15), None
        db.flush()
        return {'prepared': True, 'saved': False, 'confirmation_token': token, 'read_back': payload['patient'], 'instruction': 'Read back ALL provided fields, including optional fields, then ask Is all of that correct? Wait for explicit approval before saving. For any correction, prepare again.'}
    if name == 'reset_registration':
        draft = db.get(VoiceDraft, call_id)
        if draft:
            db.delete(draft)
        return {'reset': True, 'saved': False}
    if name in ('create_patient', 'update_patient'):
        token = args.get('confirmation_token', '')
        payload = decode(token)
        if payload.get('call_id') != call_id:
            raise DomainError(403, 'INVALID_CONFIRMATION', 'Confirmation belongs to another call.')
        draft = db.scalar(select(VoiceDraft).where(VoiceDraft.call_id == call_id).with_for_update())
        if not draft or not hmac.compare_digest(draft.digest, digest(token)):
            raise DomainError(422, 'STALE_CONFIRMATION', 'Details changed or were reset. Prepare and confirm again.')
        confirmation = args.get('confirmation_text', '').strip()
        if args.get('confirmed') is not True or not confirmation or re.search(r'\b(no|not|except|wrong|actually|but|change|incorrect)\b', confirmation, re.I):
            raise DomainError(422, 'CONFIRMATION_REQUIRED', 'Wait for explicit caller approval of the full read-back before saving.')
        if not re.search(r'\b(yes|correct|right|confirm|confirmed|accurate|save|si|sí)\b', confirmation, re.I):
            raise DomainError(422, 'CONFIRMATION_REQUIRED', 'Ask the caller to explicitly confirm the details.')
        if draft.result:
            return draft.result
        patient_id = payload.get('patient_id')
        if (name == 'update_patient') != bool(patient_id):
            raise DomainError(422, 'WRONG_TOOL', 'Use update_patient for an existing record and create_patient for a new record.')
        data = PatientInput.model_validate(payload['patient'])
        p = update_patient(db, patient_id, data.model_dump()) if patient_id else create_patient(db, data)
        call = call_record(db, call_id)
        call.patient_id = p.patient_id
        call.status = 'registered'
        call.caller_phone = p.phone_number
        result = {'saved': True, 'patient_id': p.patient_id, 'first_name': p.first_name}
        draft.result = result
        if settings().audit_payloads:
            import logging
            logging.getLogger('careintake').info('voice.confirmed_payload', extra={'payload': data.model_dump(mode='json')})
        return result
    if name == 'schedule_appointment':
        # Bonus: mock appointment scheduling after successful registration
        patient_id = args.get('patient_id')
        if not patient_id:
            raise DomainError(422, 'VALIDATION_ERROR', 'Patient ID is required to schedule an appointment.')
        from .models import Appointment
        get_patient(db, patient_id)
        preferred_date = args.get('preferred_date', '')
        preferred_time = args.get('preferred_time', '10:00 AM')
        if not preferred_date:
            from datetime import timedelta as td
            import datetime as dt
            next_business = now().date() + td(days=1)
            while next_business.weekday() >= 5:
                next_business += td(days=1)
            preferred_date = next_business.isoformat()
        # Normalize time
        time_str = preferred_time.strip()
        if time_str.lower() in ('morning', 'am'):
            time_str = '10:00 AM'
        elif time_str.lower() in ('afternoon', 'pm'):
            time_str = '2:00 PM'
        appointment = Appointment(
            patient_id=patient_id,
            appointment_date=preferred_date,
            appointment_time=time_str,
            appointment_type=args.get('appointment_type', 'New Patient Visit'),
            provider_name='Dr. Sarah Chen',
            location='CareIntake Health Center, 7 Clyde Road, Somerset NJ 08873',
            notes=args.get('notes'),
        )
        db.add(appointment)
        db.flush()
        return {
            'scheduled': True,
            'appointment_id': appointment.appointment_id,
            'date': str(appointment.appointment_date),
            'time': appointment.appointment_time,
            'type': appointment.appointment_type,
            'provider': appointment.provider_name,
            'location': appointment.location,
        }
    raise DomainError(400, 'UNKNOWN_TOOL', 'Unknown tool requested.')


def validation_details(exc):
    return [{'field': '.'.join(map(str, e['loc'])), 'message': e['msg']} for e in exc.errors()]


def handle_tools(db, message):
    call_id = str((message.get('call') or {}).get('id') or '')
    if not call_id or len(call_id) > 150:
        raise DomainError(422, 'CALL_ID_REQUIRED', 'A valid Vapi call ID is required.')
    calls = message.get('toolCallList') or []
    if not calls or len(calls) > 10:
        raise DomainError(422, 'INVALID_TOOL_CALLS', 'Provide between 1 and 10 tool calls.')
    results = []
    for tool in calls:
        tool_id = str(tool.get('id') or '')
        if not tool_id or len(tool_id) > 150:
            raise DomainError(422, 'TOOL_ID_REQUIRED', 'A tool call ID is required.')
        key = call_id + ':' + tool_id
        receipt = db.get(ToolReceipt, key)
        if receipt:
            result = receipt.result
        else:
            fn = tool.get('function') or tool
            try:
                args = fn.get('arguments', {})
                if isinstance(args, str):
                    args = json.loads(args)
                if not isinstance(args, dict):
                    raise ValueError('Tool arguments must be an object.')
                result = execute(db, fn.get('name'), args, call_id)
                db.add(ToolReceipt(key=key, result=result))
                db.commit()
            except (DomainError, ValidationError, ValueError, TypeError) as exc:
                db.rollback()
                if isinstance(exc, DomainError):
                    error = {'code': exc.code, 'message': exc.message, 'details': exc.details}
                elif isinstance(exc, ValidationError):
                    error = {'code': 'VALIDATION_ERROR', 'message': 'Please correct the indicated fields.', 'details': validation_details(exc)}
                else:
                    error = {'code': 'VALIDATION_ERROR', 'message': str(exc)}
                result = {'saved': False, 'error': error}
            except Exception:
                db.rollback()
                # A concurrent retry may have committed the receipt while this request waited.
                receipt = db.get(ToolReceipt, key)
                result = receipt.result if receipt else {'saved': False, 'error': {'code': 'SAVE_FAILED', 'message': 'A temporary system issue prevented confirmation of the save. Please try again.'}}
                import logging
                logging.getLogger('careintake').error('voice.operation_failed')
        results.append({'toolCallId': tool_id, 'result': json.dumps(result)})
    return {'results': results}


def end_report(db, message):
    raw = message.get('call') or {}
    call_id = str(raw.get('id') or '')
    if not call_id or len(call_id) > 150:
        raise DomainError(422, 'CALL_ID_REQUIRED', 'A valid Vapi call ID is required.')
    call = call_record(db, call_id)
    for key, target in [('startedAt', 'started_at'), ('endedAt', 'ended_at')]:
        value = message.get(key) or raw.get(key)
        if value:
            setattr(call, target, datetime.fromisoformat(value.replace('Z', '+00:00')))
    call.ended_at = call.ended_at or now()
    call.status = 'registered' if call.patient_id else 'ended-without-registration'
    call.summary = str((message.get('analysis') or {}).get('summary') or message.get('endedReason') or 'Call ended.')[:5000]
    if settings().store_transcripts:
        call.transcript = str(message.get('transcript') or '')[:100000]
    db.commit()
    return {'data': {'received': True}, 'error': None}
