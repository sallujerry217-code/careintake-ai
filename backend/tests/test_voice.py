import json
from uuid import uuid4
import pytest
from app import voice


def tool(client,name,args,call='call-test',tool_id=None):
    r=client.post('/webhooks/vapi',headers={'X-Vapi-Secret':'test-webhook'},json={'message':{'type':'tool-calls','call':{'id':call},'toolCallList':[{'id':tool_id or str(uuid4()),'function':{'name':name,'arguments':json.dumps(args)}}]}})
    assert r.status_code==200,r.text
    return json.loads(r.json()['results'][0]['result'])


def prepare(client,patient,call='call-test'):
    r=tool(client,'prepare_patient',{'patient':patient},call)
    assert r['prepared'] is True and r['saved'] is False,r
    assert client.get('/patients').json()['data']==[]
    return r['confirmation_token']


def save(client,token,**kwargs):
    return tool(client,'create_patient',{'confirmation_token':token,'confirmed':True,'confirmation_text':'Yes, all of that is correct.',**kwargs})


def test_preparation_does_not_save(client,patient):
    prepare(client,patient)
    assert client.get('/stats').json()['data']['total_patients']==0


@pytest.mark.parametrize('confirmation',[{'confirmed':False},{'confirmed':'true'},{'confirmation_text':'Everything except my ZIP'},{'confirmation_text':'Yes but my name is wrong'},{'confirmation_text':''},{'confirmation_text':'maybe'}])
def test_confirmation_required(client,patient,confirmation):
    t=prepare(client,patient)
    r=save(client,t,**confirmation)
    assert r['saved'] is False and r['error']['code']=='CONFIRMATION_REQUIRED'
    assert client.get('/patients').json()['data']==[]


def test_confirm_save_and_replay(client,patient):
    t=prepare(client,patient)
    r=save(client,t);assert r['saved'] is True
    assert save(client,t)==r
    assert client.get('/patients').json()['meta']['total']==1
    assert client.get('/calls').json()['data'][0]['patient_id']==r['patient_id']


def test_correction_invalidates_token(client,patient):
    old=prepare(client,patient)
    new=prepare(client,{**patient,'zip_code':'08874'})
    assert save(client,old)['error']['code']=='STALE_CONFIRMATION'
    assert save(client,new)['saved'] is True
    assert client.get('/patients').json()['data'][0]['zip_code']=='08874'


def test_tampered_cross_call_and_expired(client,patient,monkeypatch):
    token=prepare(client,patient)
    assert save(client,token+'x')['saved'] is False
    r=tool(client,'create_patient',{'confirmation_token':token,'confirmed':True,'confirmation_text':'yes'},'another-call')
    assert r['error']['code']=='INVALID_CONFIRMATION'
    monkeypatch.setattr(voice.time,'time',lambda:99999999999)
    assert save(client,token)['saved'] is False


def test_reset(client,patient):
    token=prepare(client,patient)
    assert tool(client,'reset_registration',{})['reset']
    assert save(client,token)['error']['code']=='STALE_CONFIRMATION'


def test_tools_validation_retry(client,patient):
    r=tool(client,'prepare_patient',{'patient':{**patient,'phone_number':'123'}})
    assert r['error']['code']=='VALIDATION_ERROR'
    token=prepare(client,patient)
    args={'confirmation_token':token,'confirmed':True,'confirmation_text':'yes'}
    a=tool(client,'create_patient',args,tool_id='same-tool')
    b=tool(client,'create_patient',args,tool_id='same-tool')
    assert a==b and a['saved']


def test_returning_caller_verification_and_update(client,patient):
    p=client.post('/patients',json=patient).json()['data']
    found=tool(client,'find_patient_by_phone',{'phone_number':patient['phone_number']})
    assert found['verification_required'] and 'patient' not in found
    assert not tool(client,'find_patient_by_phone',{'phone_number':patient['phone_number'],'last_name':'Wrong','date_of_birth':'1998-02-08'})['verified']
    verified=tool(client,'find_patient_by_phone',{'phone_number':patient['phone_number'],'last_name':patient['last_name'],'date_of_birth':'1998-02-08'})
    args={'patient':{**patient,'city':'Edison'},'patient_id':p['patient_id'],'verification_token':verified['verification_token']}
    draft=tool(client,'prepare_patient',args)
    r=tool(client,'update_patient',{'confirmation_token':draft['confirmation_token'],'confirmed':True,'confirmation_text':'Yes, correct'})
    assert r['saved']
    assert client.get('/patients/'+p['patient_id']).json()['data']['city']=='Edison'
    assert client.get('/patients').json()['meta']['total']==1


def test_report_replay_and_no_false_success(client):
    payload={'message':{'type':'end-of-call-report','call':{'id':'ended-call'},'startedAt':'2026-09-06T00:00:00Z','endedAt':'2026-09-06T00:01:00Z','endedReason':'customer-ended-call','transcript':'fictional transcript'}}
    for _ in range(2):
        assert client.post('/webhooks/vapi',headers={'X-Vapi-Secret':'test-webhook'},json=payload).status_code==200
    rows=client.get('/calls').json()['data'];assert len(rows)==1
    assert rows[0]['status']=='ended-without-registration'
    assert client.get('/calls/'+rows[0]['call_id']).json()['data']['transcript'] is None


def test_database_failure_never_claims_success(client,patient,monkeypatch):
    token=prepare(client,patient)
    def fail(*args):raise RuntimeError('simulated database failure')
    monkeypatch.setattr(voice,'create_patient',fail)
    r=save(client,token)
    assert not r['saved'] and r['error']['code']=='SAVE_FAILED'
    assert client.get('/patients').json()['data']==[]
