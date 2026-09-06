"""Generate the importable, credential-free assistant configuration from API schema."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.schemas import PatientInput

def resolve(schema, defs):
    if isinstance(schema, dict):
        if '$ref' in schema:
            return resolve(defs[schema['$ref'].split('/')[-1]], defs)
        return {k:resolve(v,defs) for k,v in schema.items() if k not in ('$defs','title')}
    if isinstance(schema,list):
        return [resolve(v,defs) for v in schema]
    return schema

def tool(name, description, properties, required):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required}},'server':{'url':'https://YOUR_API_BASE_URL/webhooks/vapi','headers':{'X-Vapi-Secret':'REPLACE_WITH_VAPI_SECRET'},'timeoutSeconds':20}}

patient=PatientInput.model_json_schema()
patient=resolve(patient,patient.get('$defs',{}))
string={'type':'string'}
tools=[
 tool('find_patient_by_phone','Look up a returning caller by phone. Provide caller-supplied last_name and date_of_birth to verify before disclosing the record.',{'phone_number':string,'last_name':string,'date_of_birth':{'type':'string','description':'YYYY-MM-DD'}},['phone_number']),
 tool('prepare_patient','Validate the complete latest details before reading them back. DOES NOT SAVE. Call again after every correction. Returning patients require a verification_token.',{'patient':patient,'patient_id':string,'verification_token':string},['patient']),
 tool('create_patient','Save a NEW patient ONLY after full read-back and explicit caller approval in a subsequent turn. Use the latest unchanged preparation token.',{'confirmation_token':string,'confirmed':{'type':'boolean','description':'True ONLY after explicit final caller approval.'},'confirmation_text':{'type':'string','description':'Exact words spoken by caller approving the complete latest read-back.'}},['confirmation_token','confirmed','confirmation_text']),
 tool('update_patient','Update a VERIFIED returning patient ONLY after full read-back and explicit caller approval. Requires an update preparation token.',{'confirmation_token':string,'confirmed':{'type':'boolean'},'confirmation_text':{'type':'string','description':'Exact caller words approving the latest complete read-back.'}},['confirmation_token','confirmed','confirmation_text']),
 tool('reset_registration','Invalidate pending preparation when caller asks to start over. Does not delete saved patients.',{},[]),
 {'type':'endCall'}
]
config={'name':'CareIntake AI — Riley','firstMessage':"Hi, thanks for calling CareIntake. I'm Riley, an AI intake assistant for this demo. Please use fictional details. I'll help you register and read everything back before saving. Could you start with your name and date of birth?",'model':{'provider':'groq','model':'openai/gpt-oss-120b','temperature':0.2,'maxTokens':2500,'messages':[{'role':'system','content':(ROOT/'docs/vapi-system-prompt.md').read_text()}],'tools':tools},'voice':{'provider':'vapi','voiceId':'Elliot','version':'2'},'transcriber':{'provider':'deepgram','model':'nova-3','language':'en'},'server':{'url':'https://YOUR_API_BASE_URL/webhooks/vapi','headers':{'X-Vapi-Secret':'REPLACE_WITH_VAPI_SECRET'},'timeoutSeconds':20},'serverMessages':['tool-calls','end-of-call-report'],'endCallMessage':'Thank you for calling CareIntake. Goodbye.','maxDurationSeconds':900,'startSpeakingPlan':{'waitSeconds':0.4},'artifactPlan':{'recordingEnabled':False}}
(ROOT/'docs/vapi-assistant.json').write_text(json.dumps(config,indent=2)+'\n')
print('Generated docs/vapi-assistant.json (no secrets).')
