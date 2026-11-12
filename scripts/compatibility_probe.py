"""Synthetic MCP host profiles. Protocol evidence only; never claims real-host acceptance."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from novel_version import VERSION


PROFILES = ('stdio-basic', 'tools-only', 'bounded-response', 'cached-tools', 'longform-basic')
ENTRY = Path(__file__).resolve().with_name('knowledge_entry.py')
REQUIRED = {
    'workspace_guide', 'workspace_list_projects', 'task_resume',
    'task_preview_snapshot', 'task_save_snapshot', 'task_read_snapshot',
}
LONGFORM_REQUIRED = {
    'workspace_guide', 'workspace_list_projects', 'writing_resume',
    'writing_preview_snapshot', 'writing_save_snapshot', 'writing_list_snapshots',
    'writing_read_snapshot', 'draft_propose', 'draft_preview', 'draft_save', 'draft_get',
}


def _check(checks: list, name: str, passed: bool, detail: str, *, warning: bool = False) -> None:
    checks.append({'id': name, 'status': 'warning' if warning else 'passed' if passed else 'failed',
                   'passed': passed, 'detail': detail})


def _exception_text(exc: BaseException) -> str:
    """Keep nested async failures visible in the machine-readable report."""
    nested = getattr(exc, 'exceptions', None)
    if nested:
        return '; '.join(_exception_text(item) for item in nested)
    return f'{type(exc).__name__}: {exc}'


def _environment(config: Path) -> dict:
    env = os.environ.copy()
    env.pop('PUKNOWLEDGE_CONFIG', None)
    env.pop('NOVEL_WORKBENCH_CONFIG', None)
    env.pop('NOVEL_WORKBENCH_DATA', None)
    env['PUKNOWLEDGE_CONFIG'] = str(config)
    return env


def _parameters(config: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=['-B', str(ENTRY), '--config', str(config)],
        cwd=str(config.parent),
        env=_environment(config),
    )


async def _call(session: ClientSession, name: str, args: dict, sizes: dict) -> dict:
    response = await session.call_tool(name, args)
    if not response.content or not hasattr(response.content[0], 'text'):
        raise RuntimeError(name + '未返回文本结果')
    raw = response.content[0].text
    sizes[name] = max(sizes.get(name, 0), len(raw.encode('utf-8')))
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(name + '未返回有效JSON') from exc
    if response.is_error or not payload.get('ok'):
        raise RuntimeError(name + '失败: ' + str(payload.get('error') or 'unknown'))
    return payload.get('result', payload)


def _write_story(path: Path, project_id: str) -> None:
    path.mkdir(parents=True)
    values = {
        'story-contract': {
            'id': project_id, 'mode': 'novel', 'title': 'Synthetic Longform',
            'genre': 'test', 'logline': 'A synthetic fixture proves traceable recovery.',
            'core_conflict': 'The test must preserve boundaries.', 'theme': 'traceability',
            'narrative_pov': 'third-person limited', 'ending_direction': 'verified recovery',
            'invariants': ['Synthetic candidates never become Canon automatically.'],
        },
        'world': {'rules': [{'id': 'synthetic-rule', 'rule': 'Test data only', 'status': 'confirmed'}]},
        'characters': {'characters': []}, 'timeline': {'events': []}, 'chapters': {'chapters': []},
    }
    for name, value in values.items():
        (path / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def _story_hashes(projects: Path) -> dict[str, str]:
    return {str(path.relative_to(projects)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(projects.rglob('*.json'))}


def _write_fixture(root: Path, modules=('core', 'fs'), *, longform: bool = False) -> Path:
    alpha = root / 'alpha'; beta = root / 'beta'
    projects = root / 'longform-projects'
    alpha.mkdir(); beta.mkdir(); projects.mkdir()
    (alpha / 'note.md').write_text('# Synthetic\nTraceable project note.\n', encoding='utf-8')
    (beta / 'note.md').write_text('# Synthetic\nIsolated second project.\n', encoding='utf-8')
    if longform:
        _write_story(projects / 'story-alpha', 'story-alpha')
        _write_story(projects / 'story-beta', 'story-beta')
    fs = {'enabled': True, 'readonly': True}
    config = root / 'config.json'
    config.write_text(json.dumps({
        'data_dir': str(root / 'data'),
        'projects_dir': str(projects),
        'workspaces': {
            'alpha': {'path': str(alpha), 'label': 'Alpha', 'domain': 'synthetic', 'fs_read': fs},
            'beta': {'path': str(beta), 'label': 'Beta', 'domain': 'synthetic', 'fs_read': fs},
        },
        'research_roots': [str(alpha), str(beta)],
        'modules': list(modules), 'capture': {'enabled': False},
    }, ensure_ascii=False), encoding='utf-8')
    return config


def prepare_host_fixture(output: Path) -> dict:
    """Create a persistent synthetic fixture for real-host acceptance; never overwrite."""
    root = output.expanduser().resolve()
    if root.exists():
        raise ValueError('验收目录已存在；为避免覆盖，请指定一个新的空路径')
    root.mkdir(parents=True)
    config = _write_fixture(root, modules=('core', 'fs', 'longform'), longform=True)
    return {
        'state': 'READY', 'synthetic': True, 'database_created': False,
        'root': str(root), 'config': str(config),
        'projects': ['alpha', 'beta', 'story-alpha', 'story-beta'],
        'mcp': {
            'command': sys.executable,
            'args': ['-B', str(ENTRY), '--config', str(config)],
            'transport': 'stdio',
        },
        'next_step': '将mcp.command和mcp.args登记到待验收宿主，然后按外部用户验收文档操作。',
        'notice': '仅合成项目；首次宿主写入时才创建本次验收数据库，不读取现有PuKnowledge配置。',
    }


async def _longform_workflow(config: Path) -> dict:
    checks = []; sizes = {}
    projects_dir = Path(json.loads(config.read_text(encoding='utf-8'))['projects_dir'])
    before_hashes = _story_hashes(projects_dir)
    snapshot_fingerprint = ''
    draft_id = 'synthetic-chapter'
    try:
        async with stdio_client(_parameters(config)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                info = await session.initialize()
                _check(checks, 'initialize', info.server_info.name == 'pu-knowledge-workbench' and
                       info.server_info.version == VERSION,
                       'server=' + info.server_info.name + ' version=' + info.server_info.version)
                definitions = (await session.list_tools()).tools
                names = {item.name for item in definitions}
                missing = sorted(LONGFORM_REQUIRED - names)
                _check(checks, 'longform_tool_discovery', not missing,
                       'required longform tools present' if not missing else 'missing=' + ','.join(missing))
                guide = await _call(session, 'workspace_guide', {}, sizes)
                _check(checks, 'longform_guide_modules', guide['modules'] == ['core', 'fs', 'longform'],
                       'loaded=' + ','.join(guide['modules']))
                catalog = await _call(session, 'workspace_list_projects', {}, sizes)
                projects = {item['id']: item for item in catalog['projects']}
                valid_projects = (projects.get('story-alpha', {}).get('workspace_interface') == 'writing' and
                                  projects.get('story-beta', {}).get('workspace_interface') == 'writing')
                _check(checks, 'longform_project_discovery', valid_projects,
                       'two synthetic writing projects discovered')
                initial = await _call(session, 'writing_resume', {'project': 'story-alpha'}, sizes)
                _check(checks, 'longform_initial_state', initial['resume_mode'] == 'json_task_inference' and
                       initial['session_backup'] is None,
                       'initial project has inferred task and no saved session')
                snapshot = {
                    'task': 'Develop a synthetic opening scene.',
                    'summary': 'Synthetic longform acceptance; no real project content.',
                    'next_step': 'Restart the MCP process and recover this exact direction.',
                    'candidates': ['Unapproved synthetic scene branch.'],
                    'unresolved': ['Owner has not selected a scene.'],
                    'task_context': {'task_id': 'longform-compatibility', 'stage': 'scene-outline',
                                     'state': 'active', 'direction_revision': 1},
                }
                snapshot_args = {'project': 'story-alpha', 'session_id': 'longform-probe',
                                 'snapshot': snapshot}
                preview = await _call(session, 'writing_preview_snapshot', snapshot_args, sizes)
                saved = await _call(session, 'writing_save_snapshot', {
                    **snapshot_args, 'baseline': preview['baseline'],
                    'preview_fingerprint': preview['preview_fingerprint'],
                    'operation_key': 'longform-snapshot-save',
                }, sizes)
                snapshot_fingerprint = saved['fingerprint']
                non_canon = (preview['saved'] is False and preview['canon'] is False and
                             saved['revision'] == 1 and saved['canon'] is False and
                             saved['approval_verified'] is False)
                _check(checks, 'writing_snapshot_non_canon', non_canon,
                       'preview/save revision=1 remains non-Canon and unapproved')
                listed = await _call(session, 'writing_list_snapshots',
                                     {'project': 'story-alpha', 'session_id': 'longform-probe'}, sizes)
                read = await _call(session, 'writing_read_snapshot', {
                    'project': 'story-alpha', 'session_id': 'longform-probe', 'revision': 1,
                    'expected_fingerprint': snapshot_fingerprint, 'max_chars': 6000,
                }, sizes)
                snapshot_roundtrip = (listed['total'] == 1 and
                                      json.loads(read['text'])['task_context']['task_id'] ==
                                      'longform-compatibility')
                _check(checks, 'writing_snapshot_roundtrip', snapshot_roundtrip,
                       'fixed revision and fingerprint round-trip succeeded')
                proposal = await _call(session, 'draft_propose', {
                    'project': 'story-alpha', 'draft_id': draft_id,
                    'title': 'Synthetic chapter candidate',
                    'body': 'A synthetic paragraph used only for installed-package verification.',
                    'baseline': 0,
                }, sizes)
                reviewed = await _call(session, 'draft_preview', {'proposal_id': proposal['id']}, sizes)
                draft_saved = await _call(session, 'draft_save', {
                    'proposal_id': proposal['id'], 'operation_key': 'longform-draft-save',
                }, sizes)
                draft = await _call(session, 'draft_get', {
                    'project': 'story-alpha', 'draft_id': draft_id, 'revision': 1,
                }, sizes)
                draft_ok = (reviewed['state'] == 'pending' and draft_saved['revision'] == 1 and
                            draft_saved['canon'] is False and draft_saved['published'] is False and
                            draft['body'].startswith('A synthetic paragraph') and
                            draft['canon'] is False and draft['published'] is False)
                _check(checks, 'draft_preview_save', draft_ok,
                       'independent draft revision=1 remains non-Canon and unpublished')
                isolated_snapshot = await session.call_tool('writing_read_snapshot', {
                    'project': 'story-beta', 'session_id': 'longform-probe', 'revision': 1,
                    'expected_fingerprint': snapshot_fingerprint,
                })
                isolated_draft = await session.call_tool('draft_get', {
                    'project': 'story-beta', 'draft_id': draft_id, 'revision': 1,
                })
                denied = []
                for response in (isolated_snapshot, isolated_draft):
                    raw = response.content[0].text if response.content else '{}'
                    try:
                        denied.append(response.is_error or not json.loads(raw).get('ok', False))
                    except json.JSONDecodeError:
                        denied.append(True)
                _check(checks, 'longform_project_isolation', all(denied),
                       'second writing project cannot read snapshot or draft')
        async with stdio_client(_parameters(config)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                recovered = await _call(session, 'writing_resume', {
                    'project': 'story-alpha', 'session_id': 'longform-probe',
                }, sizes)
                recovered_draft = await _call(session, 'draft_get', {
                    'project': 'story-alpha', 'draft_id': draft_id, 'revision': 1,
                }, sizes)
                recovery_ok = (recovered['resume_mode'] == 'session_backup' and
                               recovered['task_id'] == 'longform-compatibility' and
                               recovered['direction_revision'] == 1 and
                               recovered_draft['revision'] == 1)
                _check(checks, 'longform_restart_recovery', recovery_ok,
                       'exact writing direction and draft recovered after process restart')
                untouched = await _call(session, 'writing_resume', {'project': 'story-beta'}, sizes)
                _check(checks, 'longform_restart_isolation',
                       untouched['session_backup'] is None and untouched['task_id'] is None,
                       'second writing project remains without saved session')
        _check(checks, 'project_files_unchanged', before_hashes == _story_hashes(projects_dir),
               'story JSON files were not modified by snapshot or draft storage')
    except Exception as exc:
        _check(checks, 'unexpected_error', False, _exception_text(exc))
    passed = not any(item['status'] == 'failed' for item in checks)
    return {'profile': 'longform-basic', 'state': 'PASS' if passed else 'FAIL', 'checks': checks,
            'max_response_bytes': max(sizes.values(), default=0), 'response_sizes': sizes}


async def _workflow(config: Path, profile: str, response_budget: int) -> dict:
    checks = []; sizes = {}; fingerprint = ''
    try:
        async with stdio_client(_parameters(config)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                info = await session.initialize()
                _check(checks, 'initialize', info.server_info.name == 'pu-knowledge-workbench' and
                       info.server_info.version == VERSION,
                       'server=' + info.server_info.name + ' version=' + info.server_info.version)
                definitions = (await session.list_tools()).tools
                names = {item.name for item in definitions}
                missing = sorted(REQUIRED - names)
                _check(checks, 'tool_discovery', not missing,
                       'required tools present' if not missing else 'missing=' + ','.join(missing))
                schema_ok = all(isinstance(item.input_schema, dict) for item in definitions)
                _check(checks, 'tool_schemas', schema_ok, 'all discovered tools expose object schemas')
                guide = await _call(session, 'workspace_guide', {}, sizes)
                _check(checks, 'guide_modules', set(guide['modules']) == {'core', 'fs'},
                       'loaded=' + ','.join(guide['modules']))
                projects = await _call(session, 'workspace_list_projects', {}, sizes)
                ids = [item['id'] for item in projects['projects']]
                _check(checks, 'project_discovery', ids == ['alpha', 'beta'], 'projects=' + ','.join(ids))
                resumed = await _call(session, 'task_resume', {'project': 'alpha'}, sizes)
                _check(checks, 'initial_state', resumed['resume_mode'] == 'unassigned',
                       'resume_mode=' + resumed['resume_mode'])
                snapshot = {
                    'task': 'Synthetic compatibility task',
                    'summary': 'Protocol-only fixture; no real project content.',
                    'next_step': 'Restart and verify exact recovery.',
                    'task_context': {'task_id': 'compatibility', 'stage': 'probe',
                                     'state': 'active', 'direction_revision': 1},
                }
                preview = await _call(session, 'task_preview_snapshot',
                                      {'project': 'alpha', 'session_id': 'probe', 'snapshot': snapshot}, sizes)
                saved = await _call(session, 'task_save_snapshot', {
                    'project': 'alpha', 'session_id': 'probe', 'snapshot': snapshot,
                    'baseline': preview['baseline'], 'preview_fingerprint': preview['preview_fingerprint'],
                    'operation_key': 'compatibility-probe',
                }, sizes)
                fingerprint = saved['fingerprint']
                _check(checks, 'preview_save', saved['revision'] == 1, 'saved revision=1')
                files = await _call(session, 'fs_list_files', {'project': 'alpha'}, sizes)
                note = next(item for item in files['files'] if item['path'] == 'note.md')
                read = await _call(session, 'fs_read_file', {
                    'project': 'alpha', 'path': 'note.md',
                    'expected_fingerprint': note['fingerprint'], 'max_chars': 1000,
                }, sizes)
                _check(checks, 'bounded_fs_read', 'Traceable project note.' in read['text'],
                       'fingerprint-pinned text read')
                isolated = await session.call_tool('task_read_snapshot', {
                    'project': 'beta', 'session_id': 'probe', 'revision': 1,
                    'expected_fingerprint': fingerprint,
                })
                raw = isolated.content[0].text if isolated.content else '{}'
                sizes['task_read_snapshot'] = max(sizes.get('task_read_snapshot', 0), len(raw.encode('utf-8')))
                denied = isolated.is_error
                if not denied:
                    try: denied = not json.loads(raw).get('ok', False)
                    except json.JSONDecodeError: denied = True
                _check(checks, 'project_isolation', denied, 'cross-project snapshot read rejected')
        async with stdio_client(_parameters(config)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                recovered = await _call(session, 'task_resume', {'project': 'alpha'}, sizes)
                _check(checks, 'restart_recovery', recovered.get('task_id') == 'compatibility' and
                       recovered.get('direction_revision') == 1,
                       'exact task direction recovered after process restart')
                untouched = await _call(session, 'task_resume', {'project': 'beta'}, sizes)
                _check(checks, 'restart_isolation', untouched['resume_mode'] == 'unassigned',
                       'second project remains unassigned')
    except Exception as exc:
        _check(checks, 'unexpected_error', False, _exception_text(exc))
    if profile == 'tools-only':
        _check(checks, 'tools_only', True, 'scenario used MCP tools only; no prompts/resources/apps required')
    if profile == 'bounded-response':
        essential = {key: value for key, value in sizes.items() if key != 'workspace_guide'}
        oversized = {key: value for key, value in essential.items() if value > response_budget}
        _check(checks, 'response_budget', not oversized,
               'essential responses within ' + str(response_budget) + ' bytes' if not oversized else
               'oversized=' + json.dumps(oversized, sort_keys=True))
        if sizes.get('workspace_guide', 0) > response_budget:
            _check(checks, 'guide_budget', True,
                   f'guide is {sizes["workspace_guide"]} bytes; host should keep it outside task evidence', warning=True)
    passed = not any(item['status'] == 'failed' for item in checks)
    return {'profile': profile, 'state': 'PASS' if passed else 'FAIL', 'checks': checks,
            'max_response_bytes': max(sizes.values(), default=0), 'response_sizes': sizes}


async def _cached_tools(config: Path) -> dict:
    checks = []
    try:
        async with stdio_client(_parameters(config)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize(); cached = {x.name for x in (await session.list_tools()).tools}
        raw = json.loads(config.read_text(encoding='utf-8')); raw['modules'] = ['core', 'fs']
        config.write_text(json.dumps(raw), encoding='utf-8')
        async with stdio_client(_parameters(config)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize(); current = {x.name for x in (await session.list_tools()).tools}
        added = sorted(current - cached)
        _check(checks, 'cache_mismatch_detected', 'fs_workspace_status' in added,
               'new tools=' + ','.join(added))
        _check(checks, 'stale_cache_not_accepted', cached != current,
               'client must refresh tools after module changes')
    except Exception as exc:
        _check(checks, 'unexpected_error', False, _exception_text(exc))
    passed = not any(item['status'] == 'failed' for item in checks)
    return {'profile': 'cached-tools', 'state': 'PASS' if passed else 'FAIL', 'checks': checks}


async def run_profiles(profiles: list[str], response_budget: int = 12000) -> dict:
    results = []
    for profile in profiles:
        with tempfile.TemporaryDirectory(prefix='puknowledge-compat-') as temp:
            root = Path(temp)
            if profile == 'cached-tools':
                config = _write_fixture(root, modules=('core',))
                results.append(await _cached_tools(config))
            elif profile == 'longform-basic':
                config = _write_fixture(root, modules=('core', 'fs', 'longform'), longform=True)
                results.append(await _longform_workflow(config))
            else:
                config = _write_fixture(root)
                results.append(await _workflow(config, profile, response_budget))
    passed = all(item['state'] == 'PASS' for item in results)
    return {
        'state': 'PASS' if passed else 'FAIL', 'simulated': True,
        'real_host_verified': False, 'server_version': VERSION, 'profiles': results,
        'limitations': [
            '不模拟宿主隐藏系统指令、模型工具选择、UI授权或账号/OAuth行为',
            'PASS只证明公开MCP协议流程在合成临时项目中成立，不代表Claude Code/Cursor实机通过',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='PuKnowledge synthetic MCP host compatibility probe')
    parser.add_argument('--profile', choices=('all',) + PROFILES, default='all')
    parser.add_argument('--response-budget', type=int, default=12000)
    parser.add_argument('--prepare-host', type=Path,
                        help='create a persistent synthetic fixture for real-host acceptance')
    args = parser.parse_args()
    if args.prepare_host:
        if args.profile != 'all' or args.response_budget != 12000:
            parser.error('--prepare-host cannot be combined with --profile/--response-budget')
        try:
            report = prepare_host_fixture(args.prepare_host)
        except (ValueError, OSError) as exc:
            print(json.dumps({'state': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not 2000 <= args.response_budget <= 1_000_000:
        parser.error('--response-budget must be between 2000 and 1000000 bytes')
    selected = list(PROFILES) if args.profile == 'all' else [args.profile]
    report = asyncio.run(run_profiles(selected, args.response_budget))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['state'] == 'PASS' else 4


if __name__ == '__main__':
    raise SystemExit(main())
