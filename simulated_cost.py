"""Correctness-constrained Sonnet 5.5 hypothetical cost objective; not billing."""
from decimal import Decimal
import hashlib,json
from pathlib import Path
CARD=Path(__file__).with_name('sonnet55-simulation.json')

def price(usage,assume_no_cache_writes=False):
 raw=CARD.read_bytes();card=json.loads(raw);issues=[];assumptions=[];terms={}
 reported_creation=usage.get('cache_creation_input_tokens')
 if reported_creation not in (None,0) and (usage.get('cache_creation_5m_input_tokens') is None or usage.get('cache_creation_1h_input_tokens') is None):issues.append('Reported cache creation lacks priced TTL split; cannot assume zero writes')
 for key,rate in card['rates'].items():
  value=usage.get(key)
  if value is None and key.startswith('cache_creation_') and assume_no_cache_writes:
   value=0;assumptions.append(key+' explicitly assumed zero (not measured)')
  if type(value) is not int or value<0:issues.append('Missing/invalid category: '+key);continue
  terms[key]=Decimal(value)*Decimal(rate)/Decimal(card['pricing_unit_tokens'])
 total=sum(terms.values(),Decimal(0))
 return {'model':card['model'],'kind':card['kind'],'known_modeled_usd':str(total),'modeled_usd':str(total) if not issues else None,'categories_usd':{k:str(v) for k,v in terms.items()},'complete_under_assumptions':not issues,'assumptions':assumptions,'issues':issues,'pricing_sha256':hashlib.sha256(raw).hexdigest(),'actual_billed_usd':None,'local_tokenizer_and_cache_mapping_not_calibrated':True}

def objective(attempts,assume_no_cache_writes=False,min_success_rate=1.0):
 """Attempt shape: usage, accounting_complete, correctly_completed, timely.

 All attempts (including failures) belong in numerator. No cheap failure winners.
 Correct completion must come from independent grading AND task contract fidelity.
 """
 if isinstance(min_success_rate,bool) or not isinstance(min_success_rate,(int,float)) or not 0<=min_success_rate<=1:raise ValueError('Invalid preregistered success-rate floor')
 total=Decimal(0);successes=0;records=[];issues=[]
 for i,attempt in enumerate(attempts):
  record=price(attempt.get('usage',{}),assume_no_cache_writes);records.append(record);total+=Decimal(record['known_modeled_usd'])
  if attempt.get('accounting_complete') is not True:issues.append(f'attempt {i}: incomplete usage; unknown in-flight spend')
  if not record['complete_under_assumptions']:issues.append(f'attempt {i}: unpriced categories')
  if attempt.get('correctly_completed') is True and attempt.get('timely') is True:successes+=1
 if not successes:issues.append('No correct timely completions; cost per correct task undefined')
 success_rate=successes/len(attempts) if attempts else 0
 if success_rate<min_success_rate:issues.append('Correctness floor not met; cannot win by failing cheaply')
 value=total/Decimal(successes) if successes and not issues else None
 return {'objective':'simulated_sonnet_5_5_usd_per_correct_timely_task','minimize':True,'eligible':value is not None,'optuna_value':float(value) if value is not None else None,'simulated_usd_per_correct_task':str(value) if value is not None else None,'known_total_modeled_usd':str(total),'successful_tasks':successes,'success_rate':success_rate,'required_success_rate':min_success_rate,'attempts':records,'issues':issues,'actual_billed_usd':None}
