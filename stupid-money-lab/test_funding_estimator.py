import copy
import unittest
import funding_estimator as f

H='2026-11-08T13:00:00Z'
class FundingTests(unittest.TestCase):
    def p(self, direction='long'):
        return {'id':1,'symbol':'BTC','sourceVenue':'hyperliquid','direction':direction,'legs':[
            {'filledAt':'2026-11-08T12:00:02Z','quantity':2,'action':'OPENED','status':'paper fill'},
            {'filledAt':'2026-11-08T12:30:00Z','quantity':1,'action':'ADDED','status':'paper fill'},
            {'filledAt':'2026-11-08T12:40:00Z','quantity':1,'action':'REDUCED','status':'paper fill'}]}
    def receipts(self):
        return [{'status':'read','requestStartedAtUTC':'2026-11-08T12:59:38Z',
          'responseReceivedAtUTC':'2026-11-08T12:59:39Z','monotonicDurationMs':200,
          'responseSha256':'test','contexts':{'BTC':{'status':'valid','oraclePx':'100'}}}]
    def test_signed_rate_and_changed_leg_quantity_without_mutation(self):
        rates=[{'coin':'BTC','time':f.millis(H),'fundingRate':'.001'}]
        p=self.p();before=copy.deepcopy(p);r=f.estimate(p,rates,self.receipts(),H)
        self.assertEqual(r['modeledUSDC'],-.2);self.assertEqual(r['paperQuantity'],2);self.assertEqual(p,before)
        self.assertEqual(f.estimate(self.p('short'),rates,self.receipts(),H)['modeledUSDC'],.2)
        rates[0]['fundingRate']='-.001';self.assertEqual(f.estimate(p,rates,self.receipts(),H)['modeledUSDC'],.2)
    def test_missing_duplicate_and_predicted_rate_not_substituted(self):
        self.assertEqual(f.estimate(self.p(),[],self.receipts(),H)['status'],'missing')
        rate={'coin':'BTC','time':f.millis(H),'fundingRate':'.001'}
        self.assertEqual(f.estimate(self.p(),[rate,rate],self.receipts(),H)['status'],'missing')
        self.assertEqual(f.estimate(self.p(),[rate],[],H)['status'],'missing')
        shifted=dict(rate,time=rate['time']+25)
        self.assertEqual(f.estimate(self.p(),[shifted],self.receipts(),H)['status'],'missing')
    def test_boundary_and_order_ambiguity(self):
        p=self.p();p['legs'][-1]['filledAt']='2026-11-08T13:00:00Z'
        self.assertRaises(ValueError,f.quantity_at,p,H)
        p=self.p();p['legs'].reverse();self.assertRaises(ValueError,f.quantity_at,p,H)
    def test_zero_funding_is_valid_but_unknown_venue_is_not(self):
        rate={'coin':'BTC','time':f.millis(H),'fundingRate':'0'}
        self.assertEqual(f.estimate(self.p(),[rate],self.receipts(),H)['modeledUSDC'],0)
        p=self.p();p.pop('sourceVenue');self.assertEqual(f.estimate(p,[rate],self.receipts(),H)['status'],'missing')
