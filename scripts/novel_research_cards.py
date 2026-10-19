"""Research cards entered by Chat, with declared provenance and no Canon authority."""
from datetime import date
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator

CARD_COLLECTION='research-cards'
PREFIX='<!-- novel-research-card-v1 '
SUFFIX=' -->'
EDITION_LABELS={'dnd35':'D&D 3.5','srd51':'SRD 5.1','srd52':'SRD 5.2',
                'bg3':'BG3','dos2':'DOS2','mixed':'混合版本','unknown':'未标定','pathfinder1e':'Pathfinder 1e','dnd5e_game':'D&D 5e游戏改编','independent':'独立体系'}
Question=Annotated[str,Field(min_length=1,max_length=500)]

class ResearchCard(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    card_id: str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    title: str=Field(min_length=1,max_length=200)
    source_locator: str=Field(min_length=1,max_length=2000,description='URL或书名/文件路径及章节页码；仅记录出处，不自动访问。')
    rule_edition: Literal['dnd35','srd51','srd52','bg3','dos2','mixed','unknown','pathfinder1e','dnd5e_game','independent']='unknown'
    source_kind: Literal['primary','mirror','secondary','community','reference_novel','user_note']='secondary'
    retrieved_on: date
    summary: str=Field(min_length=1,max_length=6000,description='Chat整理的摘要，不能冒充原文或已确认设定。')
    applicability: str=Field(min_length=1,max_length=2000)
    open_questions: list[Question]=Field(default_factory=list,max_length=20)
    excerpt: str=Field(default='',max_length=1500,description='可选短摘录；需满足资料使用权限，不能录入整本参考小说。')

    @field_validator('source_locator')
    @classmethod
    def locator_has_no_url_credentials(cls,value):
        if value.lower().startswith(('http://','https://')):
            url=urlsplit(value)
            if not url.netloc or url.username or url.password:
                raise ValueError('出处URL必须有效且不能带账号密码')
        return value

def prepare_card(card):
    data=ResearchCard.model_validate(card).model_dump(mode='json')
    metadata={k:data[k] for k in ('card_id','title','source_locator','rule_edition','source_kind','retrieved_on')}
    header=PREFIX+json.dumps(metadata,ensure_ascii=False,sort_keys=True,separators=(',',':'))+SUFFIX
    questions='\n'.join('- '+q for q in data['open_questions']) or '- 无；不代表所有问题已解决。'
    body='\n'.join([header,'# '+data['title'],'','> 研究卡片，由Chat录入；出处和规则版本为声明，未独立核验，不是Canon。',
        '', '## 摘要',data['summary'],'','## 出处',data['source_locator'],
        '规则版本声明：'+EDITION_LABELS[data['rule_edition']],
        '来源类型声明：'+data['source_kind'],'资料读取日期声明：'+data['retrieved_on'],
        '', '## 适用范围与限制',data['applicability'],'','## 待核问题',questions,
        '', '## 短摘录',data['excerpt'] or '未保存原文摘录。',''])
    return data,body

def card_metadata(body):
    line=body.split('\n',1)[0]
    if not line.startswith(PREFIX) or not line.endswith(SUFFIX):
        return None
    try:
        data=json.loads(line[len(PREFIX):-len(SUFFIX)])
    except (ValueError,TypeError):
        return None
    if not isinstance(data,dict) or data.get('rule_edition') not in EDITION_LABELS:
        return None
    return {**data,'verification_status':'unverified','canon':False}

def card_edition_label(edition):
    return '研究卡版本声明：'+EDITION_LABELS[edition]+'（未独立核验）'

def card_reference(reference,metadata):
    edition=metadata['rule_edition']
    # The author's classification of a card is separate from verified source text.
    if edition=='unknown':
        reference={'edition_refs':[],'edition_scope':'unknown','edition_evidence':[],
                   'edition_notice':reference['edition_notice']}
    elif edition=='mixed':
        reference['edition_scope']='mixed'
    else:
        if edition not in reference['edition_refs']:
            reference['edition_refs'].append(edition)
        reference['edition_scope']='mixed' if len(reference['edition_refs'])>1 else edition
    reference['edition_evidence'].append({'edition':edition,'basis':'research_card_declaration','marker':edition})
    reference['edition_notice']='研究卡片的版本为Chat录入声明，不是原始规则真实性或Canon确认。'
    return reference

