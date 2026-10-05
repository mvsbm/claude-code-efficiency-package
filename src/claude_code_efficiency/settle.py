#!/usr/bin/env python3
"""Allow native asynchronous trace writes to finish before headless CLI exit."""
import json
import os
from pathlib import Path
import time


def settle():
    raw=os.environ.get('OTEL_LOG_RAW_API_BODIES','')
    trace=os.environ.get('EFFICIENCY_TRACE_DIR') or (raw[5:] if raw.startswith('file:') else None)
    if os.environ.get('EFFICIENCY_ACCOUNTING')!='1' or not trace:return
    root=Path(trace);state=Path(os.environ['EFFICIENCY_STATE']).resolve()
    if root.is_symlink() or not root.resolve().is_relative_to(state):return
    start=time.monotonic();complete=False
    while time.monotonic()-start<1.5:
        try:
            rows=[json.loads(line) for line in (root/'index.jsonl').read_text().splitlines()]
            paired={Path(row['request_file']).name for row in rows}
            requests={p.name for p in root.glob('*.request.json')}
            for row in rows:
                response=root/row['response_file'];json.loads(response.read_text())
            complete=bool(requests) and paired==requests
            if complete:break
        except (OSError,ValueError,KeyError):pass
        time.sleep(.02)
    (root/'settlement.json').write_text(json.dumps({'seconds':time.monotonic()-start,'all_attempts_paired':complete,'maximum_seconds':1.5}))

if __name__=='__main__':
    try:settle()
    except Exception:pass # Never block or fabricate success; accounting detects gaps.
    print('{}')
