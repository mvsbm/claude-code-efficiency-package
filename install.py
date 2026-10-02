#!/usr/bin/env python3
"""Explicit local install of runtime files only; never touch Claude settings/auth."""
import argparse,json,os,shlex,shutil
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--data-home',type=Path,default=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share'))))
p.add_argument('--bin-dir',type=Path,default=Path.home()/'.local/bin')
a=p.parse_args()
source=Path(__file__).resolve().parent
dest=a.data_home.expanduser().resolve()/'claude-code-efficiency-package'
bin_dir=a.bin_dir.expanduser().resolve()
dest.mkdir(parents=True,exist_ok=True,mode=0o700);bin_dir.mkdir(parents=True,exist_ok=True)
runtime=('settings.py','operations.py','regions.py','patch_input.py','hooks.py','statusline.py','checks.py','accounting.py','completion_guard.py','settle.py','pricing.json','simulated_cost.py','sonnet55-simulation.json','config.schema.json','NVIDIA-LICENSE.txt','LICENSE','README.md')
for name in runtime:shutil.copy2(source/name,dest/name)
(dest/'handles.txt').write_text((source/'handles.template.txt').read_text().replace('/opt/claude-code-efficiency-package/operations.py',shlex.quote(str(dest/'operations.py'))))
settings=json.loads((source/'hooks.template.json').read_text())
for entries in settings['hooks'].values():
 for entry in entries:
  for hook in entry['hooks']:hook['command']=shlex.join(['python3',str(dest/'hooks.py')])
settings['statusLine']['command']=shlex.join(['python3',str(dest/'statusline.py')])
settings['hooks']['Stop']=[{'hooks':[{'type':'command','command':shlex.join(['python3',str(dest/'settle.py')]),'timeout':3},{'type':'command','command':shlex.join(['python3',str(dest/'completion_guard.py')]),'timeout':20}]}]
(dest/'hooks.json').write_text(json.dumps(settings,indent=2)+'\n')
(dest/'instructions.txt').write_text((source/'instructions.template.txt').read_text().replace('@OPERATIONS_PATH@',shlex.quote(str(dest/'operations.py'))))
launcher=(source/'launcher.sh').read_text().replace('ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/claude-code-efficiency-package"','ROOT='+shlex.quote(str(dest)))
command=bin_dir/'claude-code-efficiency';command.write_text(launcher);command.chmod(0o755)
managed=set(runtime)|{'handles.txt','hooks.json','instructions.txt','.installed-files.json'}
# The installed tree is installer-owned; private session state lives elsewhere.
# Retire stale experiment files rather than leaving them importable forever.
for path in sorted((p for p in dest.rglob('*') if p.is_file()),key=lambda p:len(p.parts),reverse=True):
    if path.relative_to(dest).as_posix() in managed:continue
    path.unlink()
for path in sorted((p for p in dest.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
    try:path.rmdir()
    except OSError:pass
(dest/'.installed-files.json').write_text(json.dumps(sorted(managed),indent=2)+'\n')
print('Installed Claude Code Efficiency Package:',dest)
print('Launch:',command)
print('Uninstall by removing those two paths. Private session state is retained separately.')
