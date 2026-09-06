export type Patient = {patient_id:string; first_name:string; last_name:string; date_of_birth:string; sex:string; phone_number:string; email:string|null; address_line_1:string; address_line_2:string|null; city:string; state:string; zip_code:string; insurance_provider:string|null; insurance_member_id:string|null; preferred_language:string; emergency_contact_name:string|null; emergency_contact_phone:string|null; created_at:string; updated_at:string}
export type Call = {call_id:string; provider_call_id:string; patient_id:string|null; caller_phone:string|null; started_at:string; ended_at:string|null; status:string; summary:string|null; transcript?:string|null}
export type Stats = {total_patients:number;registered_today:number;total_calls:number;registered_calls:number;registration_rate:number|null}
export type Config = {auth_required:boolean; phone_number:string; assistant_configured:boolean; environment:string}
export type Envelope<T> = {data:T;error:null;meta?:{total:number;limit:number;offset:number}}
const env = (import.meta as unknown as {env:Record<string,string|boolean>}).env
export const API_BASE = String(env.VITE_API_BASE_URL || (env.DEV ? '/api' : ''))
export class ApiError extends Error {constructor(message:string,public status:number, public details?:{field:string;message:string}[]){super(message)}}
export async function api<T>(path:string,key='',options:RequestInit={}):Promise<Envelope<T>> {
 const response=await fetch(API_BASE+path,{...options,headers:{'Content-Type':'application/json',...(key?{Authorization:`Bearer ${key}`}:{ }),...options.headers}})
 const json=await response.json().catch(()=>null)
 if(!response.ok)throw new ApiError(json?.error?.message || `Request failed (${response.status}).`,response.status,Array.isArray(json?.error?.details)?json.error.details:undefined)
 if(!json || !('data' in json))throw new ApiError('The server returned an unexpected response.',502)
 return json
}
export const formatPhone=(value:string|null)=>value?.replace(/^(\d{3})(\d{3})(\d{4})$/,'($1) $2-$3') || 'Not provided'
export const shortDate=(value:string)=>new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(value))
export const initials=(p:Patient)=>p.first_name[0]+p.last_name[0]
