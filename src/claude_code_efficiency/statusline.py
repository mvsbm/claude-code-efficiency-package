#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import sys
try:
    event=json.load(sys.stdin);session=event.get('session_id','');root=Path(os.environ.get('EFFICIENCY_STATE',str(Path.home()/'.local/state/claude-efficiency')))
    p=root/'live'/(hashlib.sha256(session.encode()).hexdigest()+'.fusion.json')
    calls=len(json.loads(p.read_text()).get('calls',{})) if p.exists() else 0
    q=root/'ledger'/(hashlib.sha256(session.encode()).hexdigest()+'.json')
    hints=json.loads(q.read_text()).get('duplicate_read_hints',0) if q.exists() else 0
    print(f'Action Fusion · {calls} validation invocation(s) · {hints} unchanged-read hint(s)')
    print('Observation Pack · not enabled on this native connection · no savings claim')
except Exception:print('Efficiency metrics unavailable')
