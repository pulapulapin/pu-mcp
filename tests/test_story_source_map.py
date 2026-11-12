import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from story_source_map import build


class SourceMapTests(unittest.TestCase):
    def doc(self, text, **extras):
        return dict(id='chapters', path='draft.md', fingerprint='a'*64,
                    authority='working_manuscript', text=text, **extras)

    def test_chapter_boundaries_and_source_identity(self):
        text = '# 第一章｜起点\n🙂正文\n## 场景\n正文\n# 第二章｜后续\n结尾'
        result = build([self.doc(text)])
        self.assertEqual(result['observed_chapter_headings'], 2)
        self.assertEqual(result['items'][0]['end_char'], text.index('# 第二章'))
        self.assertEqual(result['items'][0]['fingerprint'], 'a'*64)
        self.assertFalse(result['items'][0]['canon'])
        self.assertIsNone(result['characters']['count'])
        self.assertEqual(result['story_contract']['state'], 'not_mapped')

    def test_code_blocks_and_narrative_mentions_are_not_chapters(self):
        text = '正文提到第一章\n```md\n# 第九章｜代码样例\n```\n# 第一章真正标题\n'
        self.assertEqual(build([self.doc(text)])['observed_chapter_headings'], 1)

    def test_excerpt_positions_and_unverified_ending_are_explicit(self):
        excerpt = dict(start_char=100, start_line=10, starts_at_line_boundary=True)
        result = build([self.doc('# 第二章｜半章\n内容', excerpt=excerpt)])
        row = result['items'][0]
        self.assertEqual(row['start_char'], 100)
        self.assertEqual(row['start_line'], 10)
        self.assertEqual(row['end_boundary'], 'excerpt_end')
        excerpt['starts_at_line_boundary'] = False
        self.assertEqual(build([self.doc('# 第二章｜半章\n内容', excerpt=excerpt)])['items'], [])

    def test_non_manuscripts_omitted_content_and_truncation(self):
        doc = self.doc('# 第一章｜研究候选\n# 第二章｜研究候选')
        doc['authority'] = 'mixed_status_document'
        r = build([doc], limit=1)
        self.assertEqual(r['observed_chapter_headings'], 0)
        self.assertTrue(r['items_truncated'])
        self.assertEqual(r['items'][0]['approval_state'], 'not_inferred')
        self.assertFalse(build([self.doc('# 第一章')], limit=1)['items_truncated'])
        doc['content_omitted'] = True
        self.assertEqual(build([doc])['sources'], [])

    def fact(self, **changes):
        return dict(id='gender', source_id='chapters', expected_fingerprint='a'*64,
                    kind='character', entity_id='protagonist', field='gender',
                    value='男性', quote='男性。', **changes)

    def test_fact_candidates_verify_evidence_but_never_adopt_value(self):
        doc = self.doc('男性。\n方向仍为STRONG。')
        proposal = self.fact(status_quote='方向仍为STRONG。')
        m = build([doc], fact_proposals=[proposal])
        candidate = m['fact_candidates'][0]
        self.assertEqual(candidate['evidence_state'], 'anchored')
        self.assertEqual(candidate['status_evidence']['status'], 'anchored')
        self.assertEqual(candidate['approval_state'], 'not_inferred')
        self.assertFalse(candidate['semantic_verified'])
        self.assertFalse(candidate['canon'])
        self.assertEqual(m['characters']['candidate_entity_count'], 1)
        self.assertIsNone(m['characters']['approved_count'])

    def test_missing_wrong_and_duplicate_evidence_are_not_mapped(self):
        doc = self.doc('男性。\n男性。')
        for proposal, state in [(self.fact(), 'ambiguous_quote'),
                ({**self.fact(), 'quote': '女性。'}, 'quote_not_found'),
                ({**self.fact(), 'expected_fingerprint': 'b'*64}, 'fingerprint_mismatch')]:
            m = build([doc], fact_proposals=[proposal])
            self.assertEqual(m['fact_candidates'][0]['evidence_state'], state)
            self.assertEqual(m['characters']['state'], 'not_mapped')
        for proposals in ([], [self.fact(), self.fact()], [{**self.fact(), 'source_id': 'foreign'}]):
            with self.assertRaises(ValueError):
                build([doc], fact_proposals=proposals)

    def test_excerpt_fact_offsets_remain_relative_to_full_source(self):
        doc = self.doc('男性。\nSTRONG', excerpt=dict(start_char=100, start_line=10))
        fact = self.fact(start_char=100, status_quote='STRONG')
        candidate = build([doc], fact_proposals=[fact])['fact_candidates'][0]
        self.assertEqual(candidate['evidence']['start_char'], 100)
        self.assertEqual(candidate['evidence']['start_line'], 10)
        self.assertEqual(candidate['status_evidence']['start_char'], 104)
        self.assertEqual(candidate['status_evidence']['start_line'], 11)
        fact['start_char'] = 0
        self.assertEqual(build([doc], fact_proposals=[fact])['fact_candidates'][0]['evidence_state'], 'outside_delivered_range')

    def test_different_values_for_same_field_are_not_silently_merged(self):
        proposals = [self.fact(), {**self.fact(), 'id': 'other-value', 'value': '不同候选解释'}]
        r = build([self.doc('男性。')], fact_proposals=proposals)
        self.assertEqual(len(r['fact_candidates']), 2)
        self.assertEqual(r['field_conflicts'][0]['state'], 'review_required')
        self.assertFalse(r['semantic_verified'])
