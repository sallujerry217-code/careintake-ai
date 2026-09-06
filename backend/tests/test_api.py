from datetime import date, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.models import Patient


def create(client, patient):
    r = client.post('/patients', json=patient)
    assert r.status_code == 201, r.text
    return r.json()['data']


def test_health(client):
    r=client.get('/health'); assert r.status_code==200
    assert r.json()['data']['database']=='connected'
    assert r.headers['x-request-id']


def test_create_get_list_filters(client, patient):
    p=create(client,patient)
    assert p['phone_number']=='7325550184' and p['state']=='NJ'
    assert p['preferred_language']=='English' and p['created_at'].endswith('Z')
    assert client.get('/patients/'+p['patient_id']).json()['data']==p
    for params in ({},{'last_name':"o'connor"},{'date_of_birth':'02/08/1998'},{'date_of_birth':'1998-02-08'},{'phone_number':'(732) 555-0184'},{'q':'Morgan'}):
        r=client.get('/patients',params=params);assert r.status_code==200,r.text
        assert r.json()['meta']['total']==1
    assert client.get('/patients',params={'last_name':'Wrong'}).json()['data']==[]
    assert client.get('/patients/search/by-phone',params={'phone_number':'+17325550184'}).json()['data'][0]['patient_id']==p['patient_id']


@pytest.mark.parametrize('field,value',[
 ('phone_number','123'),('phone_number','0000000000'),('phone_number','7325550184 ext 2'),
 ('date_of_birth','2037-01-01'),('date_of_birth','02/30/1998'),('date_of_birth','invalid'),('date_of_birth',0),
 ('state','XX'),('state','New Jersey'),('zip_code','123'),('zip_code','ABCDE'),('sex','Unknown'),
 ('first_name',''),('first_name','Mary3'),('last_name','A'*51),('city',''),('address_line_1',''),
 ('email','not-an-email'),('insurance_member_id','ABC-123'),('emergency_contact_phone','123'),('preferred_language',None),
 ('first_name','A\nB'),('unexpected','field')])
def test_validation(client,patient,field,value):
    r=client.post('/patients',json={**patient,field:value});assert r.status_code==422,r.text
    assert r.json()['data'] is None and r.json()['error']['code']=='VALIDATION_ERROR'
    assert client.get('/patients').json()['meta']['total']==0


@pytest.mark.parametrize('number',['7328735133','732-873-5133','(732) 873-5133','+1 732 873 5133'])
def test_phone_normalization(client,patient,number):
    p=create(client,{**patient,'phone_number':number});assert p['phone_number']=='7328735133'


def test_valid_optionals_and_us_date(client,patient):
    p=create(client,{**patient,'date_of_birth':'02/08/1998','email':'morgan@example.com','zip_code':'08873-1234','insurance_member_id':'ABC123','emergency_contact_phone':'7325550199'})
    assert p['date_of_birth']=='1998-02-08'


def test_update_partial_validation_duplicate(client,patient):
    p=create(client,patient);id=p['patient_id']
    r=client.put('/patients/'+id,json={'last_name':'Davis','email':'morgan@example.com'})
    assert r.status_code==200,r.text
    assert r.json()['data']['first_name']=='Morgan'
    assert r.json()['data']['last_name']=='Davis'
    assert client.put('/patients/'+id,json={'phone_number':'123'}).status_code==422
    assert client.put('/patients/'+id,json={'last_name':None}).status_code==422
    assert client.put('/patients/'+id,json={'patient_id':str(uuid4())}).status_code==422
    assert client.put('/patients/'+id,json={'email':None}).json()['data']['email'] is None
    second=create(client,{**patient,'phone_number':'7325550199'})
    assert client.put('/patients/'+id,json={'phone_number':second['phone_number']}).status_code==409
    assert client.get('/patients/'+id).json()['data']['phone_number']=='7325550184'


def test_soft_delete_persistence(client,patient):
    p=create(client,patient);id=p['patient_id']
    assert client.delete('/patients/'+id).status_code==200
    assert client.get('/patients/'+id).status_code==404
    assert client.get('/patients').json()['data']==[]
    with client.factory() as db:
        row=db.get(Patient,id)
        assert row is not None and row.deleted_at is not None
    # Released active-phone index permits re-registration after archiving.
    assert create(client,patient)['patient_id']!=id


def test_duplicate(client,patient):
    create(client,patient)
    r=client.post('/patients',json={**patient,'phone_number':'732-555-0184'})
    assert r.status_code==409 and r.json()['error']['code']=='DUPLICATE_PHONE'


def test_not_found(client):
    id=str(uuid4())
    for response in [client.get('/patients/'+id),client.put('/patients/'+id,json={}),client.delete('/patients/'+id),client.get('/calls/'+id)]:
        assert response.status_code==404 and response.json()['data'] is None
    assert client.get('/patients/not-a-uuid').status_code==422


def test_filter_errors_and_pagination(client,patient):
    create(client,patient)
    assert client.get('/patients?phone_number=123').status_code==422
    assert client.get('/patients?date_of_birth=nope').status_code==422
    assert client.get('/patients?limit=0').status_code==422
    assert client.get('/patients?limit=101').status_code==422
    assert client.get('/patients?offset=1').json()['data']==[]
    assert client.get('/patients?q=%25').json()['data']==[]


def test_auth(client,patient):
    client.headers.pop('Authorization')
    for path in ['/patients','/stats','/calls']:
        assert client.get(path).status_code==401
    assert client.post('/patients',json=patient).status_code==401
    assert client.get('/health').status_code==200
    assert client.post('/webhooks/vapi',json={}).status_code==401


def test_stats_truthful(client,patient):
    assert client.get('/stats').json()['data']['registration_rate'] is None
    create(client,patient)
    stats=client.get('/stats').json()['data']
    assert stats['total_patients']==1 and stats['registered_today']==1 and stats['total_calls']==0


def test_persist_across_sessions(client,patient):
    p=create(client,patient)
    with client.factory() as db:
        assert db.scalar(select(Patient).where(Patient.patient_id==p['patient_id'])).first_name=='Morgan'
