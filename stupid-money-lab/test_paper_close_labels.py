import copy
import unittest
import genius_copy as g

FIELDS = {'closureVerification', 'closureVerificationBeforePaperCloseLabel', 'paperClosureLabelVersion'}
def accounting(ledger):
    result = copy.deepcopy(ledger)
    for row in result['history'] + list(result['positions'].values()):
        for key in FIELDS:
            row.pop(key, None)
    return result

class PaperCloseLabels(unittest.TestCase):
    def setUp(self):
        self.row = dict(id=15803, quantity=0, basis=0, realized=-0.7435054191149589,
                        entryFees=0, marginRequired=0, closedAt='2026-11-11T15:34:09Z',
                        closureVerification='Unverified: no matched source exit; paper exposure remains open',
                        sourceCardClosureWarning={'reason': 'gone'},
                        legs=[dict(action='OPENED', quantity=.0027),
                              dict(action='CLOSED', status='paper fill', eventId=17052, quantity=.0027)])
        self.ledger = dict(cash=4980.43376828499, history=[copy.deepcopy(self.row)],
                           positions={'key': self.row}, decisions=[{'eventId':17052}])
    def test_website_close_retains_old_text_and_accounting(self):
        before = accounting(self.ledger)
        g.refresh_paper_close_labels(self.ledger)
        self.assertIn('matched website full-close alert', self.row['closureVerification'])
        self.assertIn('venue execution unverified', self.row['closureVerification'])
        self.assertIn('remains open', self.row['closureVerificationBeforePaperCloseLabel'])
        self.assertEqual(accounting(self.ledger), before)
    def test_idempotent(self):
        g.refresh_paper_close_labels(self.ledger)
        once = copy.deepcopy(self.ledger)
        g.refresh_paper_close_labels(self.ledger)
        self.assertEqual(self.ledger, once)
    def test_open_warning_untouched(self):
        self.row.pop('closedAt'); self.row['quantity'] = .0027
        self.ledger['history'] = [self.row]
        before = copy.deepcopy(self.ledger)
        g.refresh_paper_close_labels(self.ledger)
        self.assertEqual(self.ledger, before)
    def test_history_only_closed_record_after_key_reuse(self):
        self.ledger['positions'] = {'key': dict(id=17053, quantity=.0027)}
        g.refresh_paper_close_labels(self.ledger)
        self.assertIn('PAPER CLOSED', self.ledger['history'][0]['closureVerification'])
        self.assertNotIn('paperClosureLabelVersion', self.ledger['positions']['key'])
    def test_reconciled_close_still_modeled(self):
        self.row['legs'][-1].update(origin='venue_reconciliation', status='late-discovery paper fill')
        g.refresh_paper_close_labels(self.ledger)
        self.assertIn('corroborated source-history close', self.row['closureVerification'])
        self.assertIn('copier execution modeled', self.row['closureVerification'])
    def test_inconsistent_remaining_quantity_requires_review(self):
        self.row['quantity'] = .0027
        g.refresh_paper_close_labels(self.ledger)
        self.assertIn('requires review', self.row['closureVerification'])
        self.assertEqual(self.row['quantity'], .0027)

if __name__ == '__main__':
    unittest.main()
