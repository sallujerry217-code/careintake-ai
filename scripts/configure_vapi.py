"""Configure the assistant; optional free U.S. number. Secrets come from env only."""
import argparse
import json
import os
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--assistant-id',default=os.getenv('VAPI_ASSISTANT_ID'))
parser.add_argument('--provision-number',action='store_true')
parser.add_argument('--area-code',default='732')
args=parser.parse_args()
key=os.environ['VAPI_API_KEY']
base=os.environ['API_BASE_URL'].rstrip('/')
secret=os.environ['VAPI_SECRET']
if not base.startswith('https://'):
    raise SystemExit('API_BASE_URL must be the public HTTPS backend URL.')
config=json.loads((Path(__file__).resolve().parents[1]/'docs/vapi-assistant.json').read_text())
server={'url':base+'/webhooks/vapi','headers':{'X-Vapi-Secret':secret},'timeoutSeconds':20}
config['server']=server
for t in config['model']['tools']:
    if t['type']=='function': t['server']=server
with httpx.Client(base_url='https://api.vapi.ai',headers={'Authorization':'Bearer '+key,'User-Agent':'CareIntake/1.0'},timeout=30) as client:
    def request(method,path,body=None):
        r=client.request(method,path,json=body)
        if r.is_error:
            raise SystemExit(f'Vapi {method} {path} failed ({r.status_code}); check Vapi dashboard for details. No credentials printed.')
        return r.json()
    if os.getenv('GROQ_API_KEY'):
        existing=request('GET','/credential')
        if not any(c.get('provider')=='groq' for c in existing):
            request('POST','/credential',{'provider':'groq','name':'CareIntake Groq','apiKey':os.environ['GROQ_API_KEY']})
    assistant=request('PATCH','/assistant/'+args.assistant_id,config) if args.assistant_id else request('POST','/assistant',config)
    print('Assistant ID:',assistant['id'])
    numbers=request('GET','/phone-number')
    matching=next((n for n in numbers if n.get('assistantId')==assistant['id']),None)
    if args.provision_number and not matching:
        matching=request('POST','/phone-number',{'provider':'vapi','numberDesiredAreaCode':args.area_code,'name':'CareIntake registration','assistantId':assistant['id']})
    if matching: print('U.S. phone number:',matching.get('number','Provisioning'))
    else: print('No number attached. Use --provision-number or assign a number in Vapi.')
