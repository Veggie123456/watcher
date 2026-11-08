import copy
import unittest
import funding_estimator as f

H='2026-11-08T15:00:00Z'
class AssociationTests(unittest.TestCase):
    def p(self):
        return {'id':1,'symbol':'BTC','sourceVenue':'hyperliquid','direction':'long',
                'legs':[{'action':'OPENED','status':'paper fill','quantity':2,'filledAt':'2026-11-08T14:00:00Z'}]}
    def receipt(self):
        return {'status':'read','requestStartedAtUTC':'2026-11-08T14:59:38Z',
                'responseReceivedAtUTC':'2026-11-08T14:59:39Z','monotonicDurationMs':200,
                'responseSha256':'test','contexts':{'BTC':{'status':'valid','oraclePx':'100'}}}
    def rate(self, offset=25):
        return {'coin':'BTC','time':int(f.millis(H))+offset,'fundingRate':'.001'}
    def test_endpoints_raw_timestamps_and_no_mutation(self):
        p=self.p();rates=[self.rate()];before=copy.deepcopy((p,rates));r=f.estimate_associated_hour(p,rates,[self.receipt()],H)
        self.assertEqual(r['modeledUSDC'],-.2);self.assertEqual(r['associationOffsetMs'],25)
        self.assertEqual((p,rates),before);self.assertFalse(r['exactFunding']);self.assertFalse(r['accountingChanged'])
        for offset in [0,999]:self.assertEqual(f.estimate_associated_hour(p,[self.rate(offset)],[self.receipt()],H)['status'],'modeled')
        for offset in [-1,1000]:self.assertEqual(f.estimate_associated_hour(p,[self.rate(offset)],[self.receipt()],H)['status'],'missing')
        self.assertEqual(f.estimate(p,rates,[self.receipt()],H)['status'],'missing')
    def test_duplicates_effective_time_and_missing_inputs(self):
        p=self.p();r=self.rate();receipt=self.receipt()
        self.assertEqual(f.estimate_associated_hour(p,[r,r],[receipt],H)['status'],'missing')
        for h in ['2026-11-08T14:00:00Z','2026-11-08T15:00:01Z']:
            self.assertEqual(f.estimate_associated_hour(p,[r],[receipt],h)['status'],'missing')
        self.assertEqual(f.estimate_associated_hour(p,[r],[],H)['status'],'missing')
        r['time']=float(r['time']);self.assertEqual(f.estimate_associated_hour(p,[r],[receipt],H)['status'],'missing')
    def test_ambiguous_legs_negative_quantity_and_rate_sign(self):
        for t in ['2026-11-08T14:59:59Z','2026-11-08T15:00:01Z']:
            p=self.p();p['legs'][0]['filledAt']=t
            self.assertEqual(f.estimate_associated_hour(p,[self.rate()],[self.receipt()],H)['status'],'missing')
        p=self.p();p['legs'][0]['action']='REDUCED'
        self.assertEqual(f.estimate_associated_hour(p,[self.rate()],[self.receipt()],H)['status'],'missing')
        p=self.p();p['direction']='short';r=self.rate();r['fundingRate']='-.001'
        self.assertEqual(f.estimate_associated_hour(p,[r],[self.receipt()],H)['modeledUSDC'],-.2)
