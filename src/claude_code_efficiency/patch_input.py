"""Strict, count-free exact-context patch input. No fuzzy matching or auto-repair."""
from pathlib import Path


def parse_patch(text):
    lines=text.splitlines(keepends=True)
    if not lines or lines[0].rstrip('\r\n')!='*** Begin Patch':raise ValueError('Expected *** Begin Patch')
    if lines[-1].rstrip('\r\n')!='*** End Patch':raise ValueError('Expected *** End Patch; no trailing data')
    actions=[];i=1
    while i<len(lines)-1:
        marker=lines[i].rstrip('\r\n');i+=1
        if marker.startswith('*** Add File: '):
            path=marker[len('*** Add File: '):]
            if not path:raise ValueError('Empty path')
            body=[]
            while i<len(lines)-1 and not lines[i].startswith('*** '):
                if not lines[i].startswith('+'):raise ValueError('Add File lines must start with +')
                body.append(lines[i][1:]);i+=1
            actions.append({'path':path,'content':''.join(body),'must_not_exist':True})
        elif marker.startswith('*** Update File: '):
            path=marker[len('*** Update File: '):]
            if not path:raise ValueError('Empty path')
            edits=[]
            while i<len(lines)-1 and not lines[i].startswith('*** '):
                if lines[i].rstrip('\r\n')!='@@':raise ValueError('Expected @@, without line numbers or hints')
                i+=1;old=[];new=[];changed=False
                while i<len(lines)-1 and not lines[i].startswith('*** ') and lines[i].rstrip('\r\n')!='@@':
                    line=lines[i];i+=1
                    if line.startswith(' '):old.append(line[1:]);new.append(line[1:])
                    elif line.startswith('-'):old.append(line[1:]);changed=True
                    elif line.startswith('+'):new.append(line[1:]);changed=True
                    else:raise ValueError('Hunk lines must start with space, - or +')
                if not changed or not old:raise ValueError('Update hunk needs original context and a change')
                edits.append({'oldText':''.join(old),'newText':''.join(new)})
            if not edits:raise ValueError('Update File needs at least one hunk')
            actions.append({'path':path,'edits':edits})
        else:raise ValueError('Only Add File and Update File markers supported')
    if not actions:raise ValueError('Patch has no files')
    return {'files':actions}
