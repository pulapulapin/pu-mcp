"""Safe, explicit onboarding helpers. Initialization writes config only; doctor is read-only."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path


PROJECT_ID = re.compile(r'^[a-z0-9_-]{1,80}$')


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
        raise ValueError(name + '必须是1–200字符的非空文本')
    return value.strip()


def init_workspace_config(config_path: Path, workspace_path: Path, project_id: str,
                          label: str, domain: str, enable_fs: bool = False) -> dict:
    """Create one explicit-project config without creating a database or touching content."""
    config = config_path.expanduser().resolve()
    workspace = workspace_path.expanduser().resolve()
    if config.exists() or config.is_symlink():
        raise ValueError('配置文件已存在，拒绝覆盖: ' + str(config))
    if not PROJECT_ID.fullmatch(project_id or ''):
        raise ValueError('project-id只能使用小写字母、数字、短横线和下划线，最多80字符')
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError('workspace必须是已存在且非符号链接的目录: ' + str(workspace))
    label = _text(label, 'label')
    domain = _text(domain, 'domain')
    if not isinstance(enable_fs, bool):
        raise ValueError('enable-fs必须是布尔值')
    config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    project = {'path': str(workspace), 'label': label, 'domain': domain}
    modules = ['core']
    if enable_fs:
        project['fs_read'] = {'enabled': True, 'readonly': True}
        modules.append('fs')
    body = {
        'data_dir': str((config.parent / 'data').resolve()),
        'workspaces': {project_id: project},
        'research_roots': [str(workspace)],
        'modules': modules,
        'capture': {'enabled': False},
    }
    raw = (json.dumps(body, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    try:
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError('配置文件已存在，拒绝覆盖: ' + str(config)) from exc
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            config.unlink()
        except OSError:
            pass
        raise
    return {
        'state': 'CREATED', 'config': str(config), 'project': project_id,
        'workspace': str(workspace), 'data_dir': body['data_dir'], 'modules': modules,
        'workspace_interface': 'task',
        'database_created': False, 'workspace_content_changed': False,
        'next_step': '运行同一命令并改用--doctor；通过后再由MCP宿主启动服务。',
    }


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _check(checks: list, item_id: str, status: str, detail: str,
           *, blocking: bool = False, path: Path | None = None) -> None:
    item = {'id': item_id, 'status': status, 'blocking': blocking, 'detail': detail}
    if path is not None:
        item['path'] = str(path)
    checks.append(item)


def doctor(config_path: Path, settings: dict, modules: tuple[str, ...]) -> dict:
    """Read-only readiness report; never creates directories, databases, or records."""
    config = config_path.expanduser().resolve()
    checks = []
    _check(checks, 'config', 'passed' if config.is_file() and not config.is_symlink() else 'failed',
           '配置文件可读' if config.is_file() and not config.is_symlink() else '配置文件不存在、不是普通文件或是符号链接',
           blocking=not (config.is_file() and not config.is_symlink()), path=config)

    data = Path(settings['data_dir'])
    if data.exists():
        ok = data.is_dir() and not data.is_symlink() and os.access(data, os.R_OK | os.W_OK | os.X_OK)
        detail = '数据目录存在且当前用户可读写' if ok else '数据目录不是安全可读写目录'
    else:
        parent = _nearest_existing(data.parent)
        ok = parent.is_dir() and not parent.is_symlink() and os.access(parent, os.W_OK)
        detail = '数据目录尚未创建；其现有父目录可写，首次启动可初始化' if ok else '数据目录不存在且无法在父目录创建'
    _check(checks, 'data_dir', 'passed' if ok else 'failed', detail, blocking=not ok, path=data)

    projects = {}
    projects.update(settings.get('research_projects', {}))
    projects.update({key: {'path': value} for key, value in settings.get('projects', {}).items()})
    has_projects = bool(projects)
    _check(checks, 'projects', 'passed' if has_projects else 'failed',
           f'显式登记{len(projects)}个项目' if has_projects else '没有显式登记项目',
           blocking=not has_projects)
    for key, value in sorted(projects.items()):
        root = Path(value['path'])
        exists = root.is_dir() and not root.is_symlink()
        _check(checks, 'workspace:' + key, 'passed' if exists else 'failed',
               '项目目录存在且不是符号链接' if exists else '项目目录不存在、不是目录或是符号链接',
               blocking=not exists, path=root)

    database = data / 'workspace.sqlite3'
    if not database.exists():
        _check(checks, 'database', 'pending', '数据库尚未创建；doctor不会创建数据库', path=database)
    elif not database.is_file() or database.is_symlink():
        _check(checks, 'database', 'failed', '数据库路径不是安全普通文件', blocking=True, path=database)
    else:
        try:
            connection = sqlite3.connect('file:' + database.as_posix() + '?mode=ro', uri=True)
            try:
                integrity = connection.execute('PRAGMA quick_check').fetchone()[0]
            finally:
                connection.close()
            valid = integrity == 'ok'
            _check(checks, 'database', 'passed' if valid else 'failed',
                   'SQLite quick_check=ok' if valid else 'SQLite quick_check=' + str(integrity),
                   blocking=not valid, path=database)
        except sqlite3.Error as exc:
            _check(checks, 'database', 'failed', '无法只读检查SQLite: ' + str(exc),
                   blocking=True, path=database)

    ready = not any(item['blocking'] and item['status'] == 'failed' for item in checks)
    failed = [item['id'] for item in checks if item['blocking'] and item['status'] == 'failed']
    return {
        'state': 'READY' if ready else 'BLOCKED', 'ready': ready,
        'config': str(config), 'modules': list(modules), 'checks': checks,
        'blocking_checks': failed,
        'next_steps': ['启动MCP并调用workspace_guide、workspace_list_projects完成宿主验收'] if ready else
                      ['修复blocking_checks后重新运行--doctor'],
        'notice': 'doctor仅检查本机配置与存储前提；不创建数据库、不扫描项目内容，也不证明宿主已经加载MCP。',
    }
