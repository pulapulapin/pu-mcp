"""Local stdio launcher. Setup is explicit; never download or infer a database."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BOOT = 'from knowledge_entry import main; raise SystemExit(main())'
MODULES = {'core', 'fs', 'longform'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--python')
    parser.add_argument('--config')
    parser.add_argument('--modules', default='core')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    settings = Path.home() / '.config/puknowledge/desktop.json'
    try:
        if args.configure:
            if not args.python or not args.config:
                raise ValueError('--configure requires --python and --config')
            if settings.exists() and not args.replace:
                raise ValueError('Setup already exists; use --replace to change the binding')
            # Do not resolve the Python symlink: that would discard virtualenv identity.
            payload = {'python': os.path.abspath(os.path.expanduser(args.python)),
                       'config': str(Path(args.config).expanduser().resolve()),
                       'modules': args.modules}
        else:
            if args.python or args.config or args.replace or args.modules != 'core':
                raise ValueError('Runtime options must be saved using --configure')
            if not settings.is_file():
                raise ValueError('Run launch.py --configure --python /path/to/venv/python '
                                 '--config /path/to/config.json before enabling this plugin')
            payload = json.loads(settings.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('Desktop setup must be a JSON object; rerun --configure')
        for name in ('python', 'config'):
            if not isinstance(payload.get(name), str) or not Path(payload[name]).is_absolute():
                raise ValueError('Setup must contain absolute python and config paths')
            if not Path(payload[name]).is_file():
                raise ValueError('Configured ' + name + ' file is missing; rerun --configure')
        modules = payload.get('modules')
        if not isinstance(modules, str) or not modules or any(x not in MODULES for x in modules.split(',')):
            raise ValueError('Unknown modules in desktop setup')
        env = os.environ.copy()
        for name in ('NOVEL_WORKBENCH_DATA', 'NOVEL_WORKBENCH_CONFIG', 'PUKNOWLEDGE_CONFIG'):
            env.pop(name, None)
        command = [payload['python'], '-B', '-c', BOOT, '--config', payload['config'],
                   '--modules', modules]
        if args.configure:
            result = subprocess.run(command + ['--check-config'], env=env, capture_output=True,
                                    text=True, timeout=30)
            if result.returncode:
                raise ValueError('Runtime/config validation failed; install this checkout into '
                                 'the selected Python environment and check config separately')
            check = json.loads(result.stdout)
            if check.get('modules') != list(dict.fromkeys(modules.split(','))):
                raise ValueError('Runtime does not support the selected module contract')
            settings.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=settings.parent,
                                             delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            try:
                os.chmod(temporary, 0o600)
                os.replace(temporary, settings)
            finally:
                temporary.unlink(missing_ok=True)
            print('Desktop runtime binding saved. No MCP database was created or moved.')
            return 0
        os.execve(command[0], command, env)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        print('PuKnowledge desktop setup: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
