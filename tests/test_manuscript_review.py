import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from manuscript_review import check
from novel_store import digest


class ReviewAnchorTests(unittest.TestCase):
    def setUp(self):
        self.body = '🙂她说：好。\n他没回答。\n她说：好。'
        self.draft = dict(project='sample', id='chapter', revision=2, body=self.body)
        self.fp = digest(self.body)

    def test_unicode_positions_and_duplicate_quote_need_explicit_location(self):
        rows = check(self.draft, self.fp, [
            dict(id='one', quote='她说：好。'),
            dict(id='two', quote='她说：好。', start_char=1),
            dict(id='three', quote='他没回答。')])['review_check']
        self.assertEqual([x['status'] for x in rows['items']],
                         ['ambiguous_quote', 'anchored', 'anchored'])
        self.assertEqual(rows['items'][1]['start_char'], 1)
        self.assertEqual(rows['items'][2]['start_line'], 2)
        self.assertFalse(rows['all_anchored'])
        self.assertFalse(rows['semantic_verified'])
        self.assertFalse(rows['saved'])

    def test_fabricated_quote_and_wrong_location_are_not_evidence(self):
        rows = check(self.draft, self.fp, [dict(id='a', quote='他点头了。'),
            dict(id='b', quote='他没回答。', start_char=0)])['review_check']['items']
        self.assertEqual([x['status'] for x in rows], ['quote_not_found', 'location_mismatch'])
        self.assertNotIn('start_char', rows[0])

    def test_stale_fingerprint_and_invalid_requests_fail(self):
        for fingerprint, items in [('0'*64, []), ('', []), (self.fp, [dict(id='a', quote=' ')]),
                (self.fp, [dict(id='a', quote='好', start_char=True)]),
                (self.fp, [dict(id='a', quote='好'), dict(id='a', quote='好')])]:
            with self.subTest(items=items), self.assertRaises(ValueError):
                check(self.draft, fingerprint, items)

    def test_ordinary_read_is_compatible_and_does_not_modify_input(self):
        result = check(self.draft)
        self.assertEqual(result['body_fingerprint'], self.fp)
        self.assertNotIn('review_check', result)
        self.assertNotIn('body_fingerprint', self.draft)
        self.assertFalse(check(self.draft, self.fp, [])['review_check']['all_anchored'])
