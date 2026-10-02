import unittest
from simulated_cost import price,objective
class CostTests(unittest.TestCase):
 def usage(self,n=0):return {k:n for k in ['input_tokens','cache_read_input_tokens','cache_creation_5m_input_tokens','cache_creation_1h_input_tokens','output_tokens']}
 def test_exact_categories_and_rates(self):
  r=price(self.usage(1000000));self.assertEqual(r['modeled_usd'],'18.70');self.assertIsNone(r['actual_billed_usd'])
 def test_output_is_five_times_fresh_and_fifty_times_read(self):
  costs=[]
  for k in ['output_tokens','input_tokens','cache_read_input_tokens']:
   u=self.usage();u[k]=1000000;costs.append(float(price(u)['modeled_usd']))
  self.assertEqual(costs,[10,2,.2])
 def test_missing_categories_not_silent_zero(self):
  r=price({'input_tokens':100,'cache_read_input_tokens':100,'output_tokens':100});self.assertIsNone(r['modeled_usd']);self.assertFalse(r['complete_under_assumptions'])
 def test_explicit_local_assumption_labeled(self):
  r=price({'input_tokens':1000000,'cache_read_input_tokens':1000000,'output_tokens':1000000},True);self.assertEqual(r['modeled_usd'],'12.20');self.assertEqual(len(r['assumptions']),2)
 def test_failures_cost_count(self):
  attempts=[{'usage':self.usage(1000000),'accounting_complete':True,'correctly_completed':True,'timely':True},{'usage':self.usage(1000000),'accounting_complete':True,'correctly_completed':False,'timely':True}]
  r=objective(attempts,min_success_rate=.5);self.assertEqual(r['simulated_usd_per_correct_task'],'37.40');self.assertFalse(objective(attempts)['eligible'])
 def test_zero_successes_ineligible(self):
  self.assertFalse(objective([{'usage':self.usage(),'accounting_complete':True,'correctly_completed':False,'timely':True}])['eligible'])
 def test_incomplete_cannot_win_even_with_correct_attempt(self):
  self.assertIsNone(objective([{'usage':self.usage(1),'accounting_complete':False,'correctly_completed':True,'timely':True}])['optuna_value'])
 def test_bad_counts_rejected_as_unpriced(self):
  for v in [-1,True,1.5,None]:
   u=self.usage();u['output_tokens']=v;self.assertIsNone(price(u)['modeled_usd'])
if __name__=='__main__':unittest.main()
