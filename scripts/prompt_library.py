"""Version-pinned task guidance over existing knowledge records, never executable code."""
from typing import Annotated, Literal

from pydantic import Field

from knowledge_models import ID, SHA, Model
from novel_evidence import encode
from novel_store import digest, identifier

Text = Annotated[str, Field(max_length=10000)]
RequiredText = Annotated[str, Field(min_length=1, max_length=10000)]
Identifier = Annotated[str, Field(pattern=ID)]
Fingerprint = Annotated[str, Field(pattern=SHA)]
Lifecycle = Literal['draft', 'active', 'archived']


class PromptReference(Model):
    dataset_id: Identifier
    record_id: Identifier
    revision: int = Field(ge=1)
    fingerprint: Fingerprint


class PromptTemplate(Model):
    prompt_id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=200)]
    role: RequiredText
    objective: RequiredText
    instructions: RequiredText
    avoid: Text = ''
    output_preferences: Text = ''
    discussion_preferences: Text = ''
    context_policy: Text = ''
    lifecycle: Lifecycle
    version_label: Annotated[str, Field(min_length=1, max_length=80)]
    source: RequiredText
    change_note: RequiredText


class PromptCustomization(Model):
    prompt_id: Identifier
    base_dataset_id: Identifier
    base_record_id: Identifier
    base_revision: int = Field(ge=1)
    base_fingerprint: Fingerprint
    instructions_add: Text = ''
    avoid_add: Text = ''
    output_preferences_override: Text = ''
    discussion_preferences_add: Text = ''
    context_policy_add: Text = ''
    lifecycle: Lifecycle
    source: RequiredText
    change_note: RequiredText

    def base_ref(self):
        return PromptReference(dataset_id=self.base_dataset_id, record_id=self.base_record_id,
                               revision=self.base_revision, fingerprint=self.base_fingerprint)


def _values(body, record_type, model, prompt_id):
    if body['record_type'] != record_type:
        raise ValueError('引用不是所需的 Prompt 记录类型')
    result = model.model_validate(body['values'])
    if result.prompt_id != prompt_id:
        raise ValueError('prompt_id 须与记录 ID 一致')
    return result


def _load_base(k, db, project, prompt_id, ref, require_active=True):
    meta = k._access(db, project, ref.dataset_id)['body']
    if meta['scope'] != 'global' or meta['purpose'] != 'model':
        raise ValueError('Prompt 基础须为 global/model 模板，不支持私有或递归继承')
    if ref.record_id != prompt_id:
        raise ValueError('基础记录 ID 须与 prompt_id 一致')
    row = k._row(db, 'record', ref.dataset_id, ref.record_id, ref.revision)
    if row['fingerprint'] != ref.fingerprint:
        raise ValueError('Prompt 基础版本指纹不符')
    latest = k._row(db, 'record', ref.dataset_id, ref.record_id)
    if row['body']['status'] == 'withdrawn' or latest['body']['status'] == 'withdrawn':
        raise ValueError('Prompt 基础已撤回，不能继续应用')
    values = _values(row['body'], 'prompt_template', PromptTemplate, prompt_id)
    if require_active and values.lifecycle != 'active':
        raise ValueError('只有 active 的准确模板版本可应用')
    return row, latest, values


def validate_prompt_record(k, db, project, meta, object_id, body):
    """Shared by record preview/save and import; ordinary record types are unaffected."""
    record_type = body['record_type']
    if record_type not in ('prompt_template', 'prompt_customization'):
        return
    scope = 'global' if record_type == 'prompt_template' else 'project'
    if meta['scope'] != scope or meta['purpose'] != 'model':
        raise ValueError('Prompt 模板须 global/model；项目定制须 project/model')
    if record_type == 'prompt_template':
        _values(body, record_type, PromptTemplate, object_id)
    else:
        values = _values(body, record_type, PromptCustomization, object_id)
        # Withdrawal must remain possible after a reference has become unavailable.
        if body['status'] != 'withdrawn':
            _load_base(k, db, project, object_id, values.base_ref(), values.lifecycle == 'active')


RESOLVER_VERSION = '1'
APPLICATION_CONTRACT = {
    'authority': 'task_guidance_data',
    'read_only': True,
    'host_system_prompt_modified': False,
    'grants_tool_authorization': False,
    'changes_canon_or_owner_decisions': False,
    'semantic_conflicts': 'not_automatically_verified',
    'context_loading': 'none; context_policy is guidance, not permission',
    'protected_constraints': '系统约束、工具授权、已批准 Canon 和 Owner 决策优先；冲突须明确报告，不静默覆盖。',
}


def _manifest(k, db, row):
    schema = k._row(db, 'schema', row['dataset_id'], row['body']['record_type'],
                    row['body']['schema_revision'])
    return {'dataset_id': row['dataset_id'], 'record_id': row['object_id'],
            'revision': row['revision'], 'fingerprint': row['fingerprint'],
            'dataset_revision': row['commit_revision'],
            'schema_revision': schema['revision'], 'schema_fingerprint': schema['fingerprint'],
            'source': row['body']['values']['source'],
            'change_note': row['body']['values']['change_note'],
            'version_label': row['body']['values'].get('version_label', ''),
            'provenance': row['provenance']}


def resolve(k, project, prompt_id, customization_dataset_id='', customization_revision=0,
            base_ref=None, proposed_customization=None, turn_instruction=''):
    """Read one pinned base and at most one private customization, without session state."""
    k.w.project(project)
    identifier(prompt_id)
    if type(customization_revision) is not int or customization_revision < 0:
        raise ValueError('项目定制版本须非负整数')
    if not isinstance(turn_instruction, str) or len(turn_instruction) > 10000:
        raise ValueError('本轮要求须为最多10000字符的文本')
    if sum((bool(customization_dataset_id), base_ref is not None,
            proposed_customization is not None)) != 1:
        raise ValueError('须且仅须指定项目定制数据集、固定 base_ref 或 proposed_customization')
    if customization_revision and not customization_dataset_id:
        raise ValueError('项目定制版本须同时指定其数据集')
    with k.store.connection() as db:
        # SQLite SELECTs otherwise need not share a snapshot across concurrent commits.
        db.execute('BEGIN')
        custom = None
        custom_ref = None
        custom_source = 'project_customization'
        warnings = []
        if customization_dataset_id:
            meta = k._access(db, project, customization_dataset_id)['body']
            if meta['scope'] != 'project' or meta['purpose'] != 'model':
                raise ValueError('项目定制须为当前项目私有的 model 数据集')
            row = k._row(db, 'record', customization_dataset_id, prompt_id, customization_revision)
            latest = k._row(db, 'record', customization_dataset_id, prompt_id)
            if row['body']['status'] == 'withdrawn' or latest['body']['status'] == 'withdrawn':
                raise ValueError('项目 Prompt 定制已撤回')
            custom = _values(row['body'], 'prompt_customization', PromptCustomization, prompt_id)
            custom_ref = _manifest(k, db, row)
            if latest['revision'] != row['revision']:
                warnings.append({'code': 'customization_superseded', 'latest_revision': latest['revision']})
        elif proposed_customization is not None:
            if len(encode(proposed_customization).encode()) > 65536:
                raise ValueError('定制草案超过64KiB')
            custom = PromptCustomization.model_validate(proposed_customization)
            if custom.prompt_id != prompt_id:
                raise ValueError('草案 prompt_id 不匹配')
            custom_source = 'proposed_customization'
        if custom is not None:
            if custom.lifecycle != 'active':
                raise ValueError('只有 active 的项目定制版本可应用；预览启用请显式提出 active 草案')
            ref = custom.base_ref()
        else:
            ref = PromptReference.model_validate(base_ref)
        base, latest, template = _load_base(k, db, project, prompt_id, ref)
        base_manifest = _manifest(k, db, base)
        if latest['revision'] != base['revision']:
            warnings.append({'code': 'base_superseded', 'latest_revision': latest['revision']})
        if latest['body']['values'].get('lifecycle') == 'archived':
            warnings.append({'code': 'base_archived', 'pinned_version_retained': True})

        effective = {}
        sources = {}
        base_source_ref = ref.model_dump()
        custom_source_ref = ({key: custom_ref[key] for key in
                              ('dataset_id', 'record_id', 'revision', 'fingerprint')}
                             if custom_ref is not None else None)
        for field in ('name', 'role', 'objective', 'instructions', 'avoid', 'output_preferences',
                      'discussion_preferences', 'context_policy'):
            text = getattr(template, field)
            field_sources = [{'source': 'global_template', 'field': field, 'ref': base_source_ref}]
            if custom is not None:
                extra_field = field + '_add'
                if field == 'output_preferences' and 'output_preferences_override' in custom.model_fields_set:
                    text = custom.output_preferences_override
                    field_sources = [{'source': custom_source, 'field': 'output_preferences_override',
                                      'ref': custom_source_ref}]
                elif extra_field in type(custom).model_fields:
                    extra = getattr(custom, extra_field)
                    if extra:
                        text = text + '\n\n' + extra if text else extra
                        field_sources.append({'source': custom_source, 'field': extra_field, 'ref': custom_source_ref})
            effective[field] = text
            sources[field] = field_sources
        effective['turn_instruction'] = turn_instruction
        sources['turn_instruction'] = [{'source': 'turn_instruction', 'ref': None}] if turn_instruction else []
        fingerprint_input = {
            'resolver_version': RESOLVER_VERSION, 'project': project, 'prompt_id': prompt_id,
            'base_ref': base_manifest, 'customization_ref': custom_ref,
            'proposed_customization': custom.model_dump(exclude_unset=True)
                if proposed_customization is not None else None,
            'effective_config': effective, 'application_contract': APPLICATION_CONTRACT,
        }
        return {'project': project, 'prompt_id': prompt_id, 'resolver_version': RESOLVER_VERSION,
                'effective_config': effective, 'base_ref': base_manifest, 'customization_ref': custom_ref,
                'field_sources': sources, 'effective_fingerprint': digest(encode(fingerprint_input)),
                'warnings': warnings, 'preview_only': proposed_customization is not None,
                'application_contract': dict(APPLICATION_CONTRACT), 'canon': False}
