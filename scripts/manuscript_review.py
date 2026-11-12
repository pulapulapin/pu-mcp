"""Read-only review anchors; validates evidence locations, never literary quality."""
import re

from novel_store import digest


def check(draft, expected_fingerprint='', review_items=None):
    body = draft['body']
    fingerprint = digest(body)
    if expected_fingerprint and (
            not re.fullmatch(r'[a-f0-9]{64}', expected_fingerprint)
            or expected_fingerprint != fingerprint):
        raise ValueError('草稿正文指纹不匹配；须重新读取准确版本')
    result = {**draft, 'body_fingerprint': fingerprint,
              'fingerprint_scheme': 'sha256_utf8_body'}
    if review_items is None:
        return result
    if not expected_fingerprint:
        raise ValueError('核对审稿引用须提供expected_fingerprint')
    checked = anchors(body, review_items)
    result['review_check'] = {
        'source': {'project': draft['project'], 'draft_id': draft['id'],
                   'revision': draft['revision'], 'body_fingerprint': fingerprint},
        'items': checked, 'all_anchored': bool(checked) and all(x['status'] == 'anchored' for x in checked),
        'semantic_verified': False, 'owner_adopted': False, 'saved': False,
        'scope': '仅核对引用与位置；不验证审稿结论、修订质量或作者采纳。'}
    return result


def anchors(body, review_items):
    """Match quotes in one verified decoded source; offsets are Unicode characters."""
    if not isinstance(review_items, list) or len(review_items) > 30:
        raise ValueError('review_items须为最多30项列表')
    checked = []
    for item in review_items:
        if not isinstance(item, dict) or set(item) - {'id', 'quote', 'start_char'}:
            raise ValueError('审稿引用仅允许id、quote、start_char')
        if not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', item['id']):
            raise ValueError('审稿引用须有有效id')
        quote = item.get('quote')
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 3000:
            raise ValueError('quote须为非空原文且不超过3000字符')
        start = item.get('start_char')
        if start is not None and (type(start) is not int or start < 0):
            raise ValueError('start_char须为非负整数，按Unicode字符从0起算')
        if start is not None:
            status = 'anchored' if body[start:start + len(quote)] == quote else 'location_mismatch'
        else:
            start = body.find(quote)
            if start < 0:
                status = 'quote_not_found'
            elif body.find(quote, start + 1) >= 0:
                status = 'ambiguous_quote'
            else:
                status = 'anchored'
        row = {'id': item['id'], 'quote': quote, 'status': status}
        if status == 'anchored':
            row.update(start_char=start, end_char=start + len(quote),
                       start_line=body.count('\n', 0, start) + 1,
                       end_line=body.count('\n', 0, start + len(quote) - 1) + 1)
        checked.append(row)
    if len({x['id'] for x in checked}) != len(checked):
        raise ValueError('审稿引用id不能重复')
    return checked
