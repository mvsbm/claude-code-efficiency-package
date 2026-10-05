#!/usr/bin/env python3
"""Install the runtime package without changing Claude settings or credentials."""
import argparse
import json
import os
import shlex
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--data-home', type=Path,
        default=Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))),
    )
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    args = parser.parse_args()

    source = Path(__file__).resolve().parents[1]
    dest = args.data_home.expanduser().resolve() / 'claude-code-efficiency-package'
    bin_dir = args.bin_dir.expanduser().resolve()
    package_source = source / 'src' / 'claude_code_efficiency'

    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    bin_dir.mkdir(parents=True, exist_ok=True)
    installed_package = dest / 'claude_code_efficiency'
    installed_package.mkdir(parents=True, exist_ok=True)
    for path in package_source.glob('*.py'):
        shutil.copy2(path, installed_package / path.name)
    for name in ('LICENSE', 'NVIDIA-LICENSE.txt', 'README.md'):
        shutil.copy2(source / name, dest / name)
    shutil.copy2(source / 'config' / 'schema.json', dest / 'config.schema.json')

    hooks = json.loads((source / 'templates' / 'hooks.json').read_text())

    def module_command(module):
        return shlex.join(['python3', '-m', 'claude_code_efficiency.' + module])
    for entries in hooks['hooks'].values():
        for entry in entries:
            for hook in entry['hooks']:
                hook['command'] = module_command('hooks')
    hooks['statusLine']['command'] = module_command('statusline')
    hooks['hooks']['Stop'] = [{'hooks': [
        {'type': 'command', 'command': module_command('settle'), 'timeout': 3},
        {'type': 'command', 'command': module_command('completion_guard'), 'timeout': 20},
    ]}]
    (dest / 'hooks.json').write_text(json.dumps(hooks, indent=2) + '\n')

    operations_command = module_command('operations')
    handles = (source / 'templates' / 'handles.txt').read_text()
    (dest / 'handles.txt').write_text(handles.replace('@OPERATIONS_COMMAND@', operations_command))
    instructions = (source / 'templates' / 'instructions.txt').read_text()
    (dest / 'instructions.txt').write_text(instructions.replace('@OPERATIONS_COMMAND@', operations_command))

    launcher_text = (source / 'scripts' / 'launcher.sh').read_text()
    launcher_text = launcher_text.replace(
        'ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/claude-code-efficiency-package"',
        'ROOT=' + shlex.quote(str(dest)),
    )
    launcher = bin_dir / 'claude-code-efficiency'
    launcher.write_text(launcher_text)
    launcher.chmod(0o755)

    managed = {
        'LICENSE', 'NVIDIA-LICENSE.txt', 'README.md', 'config.schema.json',
        'handles.txt', 'hooks.json', 'instructions.txt', '.installed-files.json',
    }
    managed.update(
        'claude_code_efficiency/' + path.name
        for path in package_source.glob('*.py')
    )
    # The installed tree belongs to this installer; prune retired/unknown files.
    for path in sorted((p for p in dest.rglob('*') if p.is_file()), key=lambda p: len(p.parts), reverse=True):
        if path.relative_to(dest).as_posix() not in managed:
            path.unlink()
    for path in sorted((p for p in dest.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    (dest / '.installed-files.json').write_text(json.dumps(sorted(managed), indent=2) + '\n')

    print('Installed Claude Code Efficiency Package:', dest)
    print('Launch:', launcher)
    print('Uninstall by removing those two paths. Private state is retained separately.')


if __name__ == '__main__':
    main()
