import unittest,copy
from portfolio import opening,addition,snapshot,admit,observe,STUDY
from evidence_audit import audit
class BankrollTests(unittest.TestCase):
    def e(self,id=1,side='LONG',action='OPENED'):
        return dict(id=id,coin='BTC',createdAt='1970-01-01T00:01:00+00:00',payload={'wallet':'0x'+str(id%10)*40,'side':side,'action':action,'cohort':'GENIUS','leverage':{'value':10}})
    def b(self,p=100):return dict(time=100000,observedAt='1970-01-01T00:01:40+00:00',levels=[[{'px':str(p-.01),'sz':'1000'}],[{'px':str(p+.01),'sz':'1000'}]])
    def test_cash_cannot_be_used_twice(self):
        ss=[]
        for i in range(1,5):
            s=opening(self.e(i),self.b(),5,20);admit(ss,s,now=100000);ss.append(s)
        self.assertLess(snapshot(ss,100000)['available'],200)
        with self.assertRaises(ValueError):admit(ss,opening(self.e(5),self.b(),5,20),now=100000)
    def test_twenty_slots_need_margin_and_twenty_first_rejected(self):
        ss=[]
        for i in range(20):
            s=opening(self.e(i),self.b(),5,20,'source');admit(ss,s,now=100000);ss.append(s)
        self.assertEqual(snapshot(ss,100000)['openCount'],20)
        with self.assertRaises(ValueError):admit(ss,opening(self.e(21),self.b(),5,20,'source'),now=100000)
    def test_margin_released_once_on_close(self):
        s=opening(self.e(),self.b(),5,20);before=snapshot([s],100000);s['closedAt']='later';after=snapshot([s],100000)
        self.assertAlmostEqual(after['available']-before['available'],s['marginRequired'])
        self.assertEqual(after,snapshot([s],100000))
    def test_milestones_both_sides_after_costs_and_durable(self):
        for side in ['LONG','SHORT']:
            s=opening(self.e(side=side),self.b(),5,20);b=self.b(121 if side=='LONG' else 79);observe(s,b)
            self.assertIn('20',s['milestones']['notional']);h=copy.deepcopy(s['milestones']);observe(s,self.b());self.assertEqual(h,s['milestones']);self.assertTrue(s['checks']['legArithmetic'])
    def test_leverage_return_separate_from_notional(self):
        s=opening(self.e(),self.b(),5,20,'source');observe(s,self.b(101));self.assertLess(s['returnOnNotional'],.05);self.assertIn('5',s['milestones']['margin']);self.assertNotIn('5',s['milestones']['notional'])
    def test_adds_raise_notional_to_cap_not_new_position(self):
        e=self.e();s=opening(e,self.b(),5,20)
        for i in [2,3]:
            a=self.e(i,action='ADDED');a['payload']['wallet']=e['payload']['wallet'];s=addition(s,a,self.b(),5)
        self.assertLessEqual(s['notional'],350);self.assertGreater(s['notional'],349)
        self.assertEqual(len(s['legs']),3)
    def test_stale_existing_quotes_block_allocation(self):
        s=opening(self.e(),self.b(),5,20)
        with self.assertRaises(ValueError):admit([s],opening(self.e(2),self.b(),5,20),now=200000)
    def test_wick_only_is_possible_not_confirmed(self):
        s=opening(self.e(),self.b(),5,20);s['closedAt']='1970-01-01T00:04:40+00:00';r=audit(s,[{'t':120000,'T':179999,'h':'130','l':'100'}],'now')
        self.assertTrue(r['possibleNotionalTouches']['20']);self.assertNotIn('20',s['milestones']['notional'])
if __name__=='__main__':unittest.main()

class SplitSignalTests(BankrollTests):
    def test_add_alert_is_separate_without_falsifying_source_opening(self):
        e=self.e(action='ADDED');s=opening(e,self.b(),5,20,'source',signal_class='add_scalp')
        self.assertEqual(s['action'],'ADDED');self.assertEqual(s['sourceEvent']['payload']['action'],'ADDED');self.assertEqual(s['signalClass'],'add_scalp');self.assertFalse(s['checks']['observedOpening']);self.assertTrue(s['checks']['signalClassMatchesSource']);self.assertTrue(s['leverageMatched']);self.assertEqual(s['leverage'],10)
        account=snapshot([s],100000);self.assertEqual(account['families']['add_scalp']['total'],1);self.assertEqual(account['families']['fresh']['total'],0)
    def test_split_sections_share_the_same_cash_pool(self):
        ss=[]
        for i in range(4):
            e=self.e(i,action='ADDED' if i%2 else 'OPENED');s=opening(e,self.b(),5,20,signal_class='add_scalp' if i%2 else 'fresh');admit(ss,s,now=100000);ss.append(s)
        extra=opening(self.e(9,action='ADDED'),self.b(),5,20,signal_class='add_scalp')
        with self.assertRaises(ValueError):admit(ss,extra,now=100000)
    def test_missing_source_leverage_rejected_in_match_mode(self):
        e=self.e(action='ADDED');e['payload'].pop('leverage')
        with self.assertRaisesRegex(ValueError,'Source leverage'):opening(e,self.b(),5,20,'source',signal_class='add_scalp')
    def test_standalone_add_scalp_cannot_be_scaled_as_original_position(self):
        e=self.e(action='ADDED');s=opening(e,self.b(),5,20,'source',signal_class='add_scalp');e['id']=2
        with self.assertRaises(ValueError):addition(s,e,self.b(),5)
