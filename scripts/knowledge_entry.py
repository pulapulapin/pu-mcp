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
    parser.add_argument('--modules', default='', help='comma-separated: core,fs,longform')
    args = parser.parse_args()
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
    create_server(modules=modules).run(transport='stdio')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
