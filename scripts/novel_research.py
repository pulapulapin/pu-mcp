"""Conservative edition references for indexed excerpts, not rule verification."""
import re

EDITIONS=('all','dnd35','srd51','srd52','bg3','dos2','mixed','unknown','pathfinder1e','dnd5e_game','independent')
PATH_MARKERS={
    'dnd35':('dnd35','srd35'),
    'srd51':('srd51',),
    'srd52':('srd52',),
    'bg3':('bg3',),
    'dos2':('dos2',),
}
TEXT_PATTERNS={
    'dnd35':r'(?:D\s*[&＆]\s*D|DND|SRD)\s*(?:v(?:ersion)?\.?\s*)?3\.5(?![\d.])',
    'srd51':r'SRD\s*(?:v(?:ersion)?\.?\s*)?5\.1(?![\d.])',
    'srd52':r'SRD\s*(?:v(?:ersion)?\.?\s*)?5\.2(?:\.1)?(?![\d.])',
    'bg3':r'\bBG3\b|博德之门\s*3',
    'dos2':r'\bDOS2\b|神界[：:]?\s*原罪\s*2',
}

def edition_references(path, body):
    """Use explicit excerpt mentions or known source filename families only."""
    evidence=[]
    for edition,markers in PATH_MARKERS.items():
        for marker in markers:
            if re.search(r'(?:^|[/_.-])'+re.escape(marker)+r'(?=[/_.-]|$)',path,re.I):
                evidence.append({'edition':edition,'basis':'source_path','marker':marker})
                break
        match=re.search(TEXT_PATTERNS[edition],body,re.I)
        if match:
            evidence.append({'edition':edition,'basis':'excerpt_text','marker':match.group(0)})
    refs=list(dict.fromkeys(item['edition'] for item in evidence))
    return {'edition_refs':refs,'edition_scope':'mixed' if len(refs)>1 else refs[0] if refs else 'unknown',
            'edition_evidence':evidence,
            'edition_notice':'版本引用线索，不验证规则真伪或适用性；混合、否定引用和同人需读取原文。'}

def validate_filters(edition_filter,path_prefix,match_mode):
    if edition_filter not in EDITIONS:
        raise ValueError('edition_filter必须为all/dnd35/srd51/srd52/bg3/dos2/mixed/unknown')
    if match_mode not in ('any','all'):
        raise ValueError('match_mode必须为any或all')
    if (not isinstance(path_prefix,str) or len(path_prefix)>256 or path_prefix.startswith('/')
            or '\\' in path_prefix or '\x00' in path_prefix
            or any(part in ('.','..') for part in path_prefix.split('/'))):
        raise ValueError('path_prefix必须为集合内相对路径前缀，不能包含目录穿越')

def matches_edition(reference,edition_filter):
    if edition_filter=='all':
        return True
    if edition_filter in ('mixed','unknown','pathfinder1e','dnd5e_game','independent'):
        return reference['edition_scope']==edition_filter
    return edition_filter in reference['edition_refs']
