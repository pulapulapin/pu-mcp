"""Synthetic MCP host profiles. Protocol evidence only; never claims real-host acceptance."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from novel_version import VERSION


PROFILES = ('stdio-basic', 'tools-only', 'bounded-response', 'cached-tools')
ENTRY = Path(__file__).resolve().with_name('knowledge_entry.py')
REQUIRED = {
    'workspace_guide', 'workspace_list_projects', 'task_resume',
    'task_preview_snapshot', 'task_save_snapshot', 'task_read_snapshot',
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
    return payload['result']


def _write_fixture(root: Path, modules=('core', 'fs')) -> Path:
    alpha = root / 'alpha'; beta = root / 'beta'
    projects = root / 'longform-projects'
    alpha.mkdir(); beta.mkdir(); projects.mkdir()
    (alpha / 'note.md').write_text('# Synthetic\nTraceable project note.\n', encoding='utf-8')
    (beta / 'note.md').write_text('# Synthetic\nIsolated second project.\n', encoding='utf-8')
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
    args = parser.parse_args()
    if not 2000 <= args.response_budget <= 1_000_000:
        parser.error('--response-budget must be between 2000 and 1000000 bytes')
    selected = list(PROFILES) if args.profile == 'all' else [args.profile]
    report = asyncio.run(run_profiles(selected, args.response_budget))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['state'] == 'PASS' else 4


if __name__ == '__main__':
    raise SystemExit(main())
