"""Public stdio entry point for the neutral PuKnowledge workspace."""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='PuKnowledge traceable context and evidence MCP')
    parser.add_argument('--config', type=Path, help='local JSON configuration')
    parser.add_argument('--check-config', action='store_true')
    parser.add_argument('--doctor', action='store_true', help='read-only readiness checks')
    parser.add_argument('--init-workspace', type=Path, help='create a new config for one existing workspace')
    parser.add_argument('--project-id', default='', help='explicit project id used with --init-workspace')
    parser.add_argument('--label', default='', help='project display label used with --init-workspace')
    parser.add_argument('--domain', default='general', help='project domain used with --init-workspace')
    parser.add_argument('--enable-fs', action='store_true', help='enable bounded read-only files for the initialized workspace')
    parser.add_argument('--modules', default='', help='core is the base; optional extensions: fs,longform')
    args = parser.parse_args()
    if args.init_workspace:
        if not args.config:
            parser.error('--init-workspace requires --config')
        if args.check_config or args.doctor or args.modules:
            parser.error('--init-workspace cannot be combined with --check-config/--doctor/--modules')
        from onboarding import init_workspace_config
        try:
            result = init_workspace_config(args.config, args.init_workspace, args.project_id,
                                           args.label, args.domain, args.enable_fs)
        except (ValueError, OSError) as exc:
            print('Initialization error: ' + str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if any((args.project_id, args.label, args.enable_fs)):
        parser.error('--project-id/--label/--enable-fs are only valid with --init-workspace')
    if args.doctor and (args.check_config or not args.config):
        parser.error('--doctor requires --config and cannot be combined with --check-config')
    if args.config:
        os.environ['PUKNOWLEDGE_CONFIG'] = str(args.config.expanduser().resolve())
    from novel_config import load_settings
    from module_server import AVAILABLE, create_server, parse_modules
    try:
        settings = load_settings(neutral=True)
        modules = parse_modules(args.modules or settings.get('modules') or 'core')
    except (ValueError, OSError) as exc:
        print('Configuration error: ' + str(exc), file=sys.stderr)
        return 2
    if args.check_config:
        def serial(value):
            if isinstance(value, dict): return {k: serial(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)): return [serial(v) for v in value]
            return str(value) if isinstance(value, Path) else value
        print(json.dumps({
            'data_dir': serial(settings['data_dir']),
            'research_roots': serial(settings['research_roots']),
            'capture': serial(settings['capture']),
            'fs_workspaces': serial(settings['fs_workspaces']),
            'workspaces': serial(settings['research_projects']),
            'modules': list(modules),
            'available_modules': list(AVAILABLE),
        }, ensure_ascii=False, indent=2))
        return 0
    if args.doctor:
        from onboarding import doctor
        report = doctor(args.config, settings, modules)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ready'] else 3
    create_server(modules=modules).run(transport='stdio')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
