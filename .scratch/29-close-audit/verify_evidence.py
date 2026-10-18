"""Lightweight evidence/references gate. Never import or execute captured candidate code."""
from pathlib import Path
import argparse
import hashlib
import json
import re

HOME = Path(__file__).resolve().parent
ROOT = HOME.parent.parent
parser=argparse.ArgumentParser()
parser.add_argument('--check-sources', action='store_true', help='also require original raw sources and verify their recorded bytes')
args=parser.parse_args()


def sha(data):
    return hashlib.sha256(data).hexdigest()


manifest=json.loads((HOME/'manifest.json').read_text())+json.loads((HOME/'manifest-supplement.json').read_text())
for row in manifest:
    data=(HOME/row['target']).read_bytes()
    assert len(data)==row['bytes'] and sha(data)==row['sha256'], row['target']
    if args.check_sources:
        original=Path(row['source']).read_bytes()
        assert sha(original)==row.get('source_sha256',row['sha256']), row['source']
# Safe negative control: the same byte-integrity criterion rejects a bounded in-memory mutation.
probe=(HOME/manifest[0]['target']).read_bytes()
assert sha(probe+b'changed')!=manifest[0]['sha256']
print(f'PASS retained byte hashes: {len(manifest)}; in-memory corruption negative control rejected')

samples=json.loads((HOME/'samples.json').read_text())
assert len(samples)==24
aliases=json.loads((HOME/'sample-map.json').read_text())
assert len(aliases)==24
writes=0
for rec in json.loads((HOME/'reconstruction.json').read_text()):
    d=HOME/'evidence'/rec['id']
    trajectory=[json.loads(x) for x in (d/'trajectory.jsonl').read_text().splitlines()]
    for w in rec['writes']:
        event=trajectory[w['trajectory_line']-1]
        assert event['kind']=='source_write' and event['sha256']==w['sha256']
        payload=d/'payloads'/f'L{w["payload_line"]:03}'/w['path']
        assert sha(payload.read_bytes())==w['sha256'] and w['payload_matches']
        writes+=1
    for final in rec['finals']:
        assert sha((d/'work'/final['path']).read_bytes())==final['sha256']
        grade=d/'grade-repo'/final['path']
        if grade.exists():assert sha(grade.read_bytes())==final['graded_sha256']
assert writes==50
print(f'PASS literal source_write identity: {writes}; final work/graded hashes verified separately')

# Replay only successful pi write/edit text operations IN MEMORY. No captured shell execution.
pi_replays=[]
for sample in samples:
    if sample['arm']!='pi':continue
    d=HOME/'evidence'/sample['id']; row=json.loads((d/'row.json').read_text())
    pristine=HOME/'evidence/specs'/sample['task']/'repo'
    state={str(p.relative_to(pristine)):p.read_text() for p in pristine.rglob('*') if p.is_file() and str(p.relative_to(pristine)) not in row['withheld_grader_paths']}
    events=[json.loads(x) for x in (d/'events-selected.jsonl').read_text().splitlines()]
    results={w['event']['toolCallId']:w['event'] for w in events if w['event']['type']=='tool_execution_end'}
    changes=[]
    for line,w in enumerate(events,1):
        event=w['event']
        if event['type']!='message_end' or event['message']['role']!='assistant':continue
        for call in event['message'].get('content',[]):
            if call.get('type')!='toolCall' or call.get('name') not in ['write','edit']:continue
            result=results[call['id']]
            if result.get('isError'):continue
            a=call['arguments'];path=Path(a['path'])
            if path.is_absolute():path=path.relative_to(Path(sample['source_run'])/'work')
            rel=str(path);assert '..' not in path.parts
            if call['name']=='write':state[rel]=a['content']
            else:
                text=state[rel]
                for edit in a['edits']:
                    assert text.count(edit['oldText'])==1, (sample['id'],line)
                    text=text.replace(edit['oldText'],edit['newText'])
                state[rel]=text
            changes.append(dict(event_line=line,path=rel,sha256=sha(state[rel].encode())))
    finals=[]
    for p in sorted((d/'work').rglob('*.py')):
        rel=str(p.relative_to(d/'work'))
        assert rel in state and state[rel].encode()==p.read_bytes(), (sample['id'],rel)
        original=pristine/rel
        finals.append(dict(path=rel,sha256=sha(p.read_bytes()),same_as_pristine=original.is_file() and original.read_bytes()==p.read_bytes()))
    pi_replays.append(dict(id=sample['id'],changes=changes,finals=finals))
(HOME/'pi-reconstruction.json').write_text(json.dumps(pi_replays,ensure_ascii=False,indent=2)+'\n')
assert len(pi_replays)==12
print(f'PASS pi text-operation replay: {len(pi_replays)} runs; source payloads reconstruct retained work; shell commands not rerun')

outcomes=json.loads((HOME/'outcomes-selected.json').read_text())
assert len(outcomes)==550 and len({(r['arm'],r['task'],r['seed']) for r in outcomes})==550
for task in {r['task'] for r in outcomes}:
    for arm in ['ours','pi']:
        assert sum(r['task']==task and r['arm']==arm for r in outcomes)==25
r3=json.loads((HOME/'r3-observations.json').read_text())
for arm in ['leaf','tree-greedy','tree-tournament']:
    rs=[r for r in r3 if r['arm']==arm];assert len(rs)==70
    if arm!='leaf':
        blocked=[r for r in rs if not r['actual'] and not r['claimed']]
        assert len(blocked)==52 and all(r['unchanged_python'] for r in blocked)
if args.check_sources:
    for path,h in json.loads((HOME/'summary-input-hashes.json').read_text()).items():assert sha(Path(path).read_bytes())==h,path
    for r in r3:assert sha(Path(r['source']).read_bytes())==r['source_sha256'],r['source']
print('PASS bounded outcome shape: 550 unique rows, 25/task/arm; R3 70/arm and 52 unclaimed pristine failures/tree arm')
report_rows=re.findall(r'^\| ([TA]\d{2}) \| (\d+) \| (\d+) \| (\d+) \|$', (HOME/'report.md').read_text(), re.M)
assert len(report_rows)==11
for task,ours_count,pi_count,no_paths in report_rows:
    prefix=task[0]+'-'+task[1:]
    rs=[r for r in outcomes if r['task'].startswith(prefix)]
    assert sum(r['actual'] for r in rs if r['arm']=='ours')==int(ours_count),task
    assert sum(r['actual'] for r in rs if r['arm']=='pi')==int(pi_count),task
    assert sum(not r['actual'] and not r['files_touched'] for r in rs if r['arm']=='pi')==int(no_paths),task
matrix_rows=re.findall(r'^\| ([TA]\d{2}) / (\d+):(\d+) \|', (HOME/'evidence-matrix.md').read_text(), re.M)
assert len(matrix_rows)==11
for task,ours_count,pi_count in matrix_rows:
    prefix=task[0]+'-'+task[1:]
    rs=[r for r in outcomes if r['task'].startswith(prefix)]
    assert sum(r['actual'] for r in rs if r['arm']=='ours')==int(ours_count),task
    assert sum(r['actual'] for r in rs if r['arm']=='pi')==int(pi_count),task
print('PASS report/matrix counts agree with retained selected outcomes')

refcount=0
for filename in ['report.md','evidence-matrix.md']:
    text=(HOME/filename).read_text()
    for alias,path,start,end in re.findall(r'\b([OP][TA]\d{2}(?:good|bad)?|R2A05)/([\w./-]+):(\d+)(?:-(\d+))?',text):
        p=HOME/aliases[alias]/path
        assert p.is_file(),(filename,alias,path)
        count=len(p.read_text().splitlines());end=int(end or start)
        assert 1<=int(start)<=end<=count,(filename,p,start,end,count)
        refcount+=1
print(f'PASS explicit alias file/line references: {refcount}; compressed context references still require human reading')

linkcount=0
for path in [ROOT/'README.md',*(ROOT/'docs'/f for f in ['STATUS.md','LEARNINGS.md','ROADMAP.md']),*(HOME/f for f in ['report.md','evidence-matrix.md','sample-router.md','review-contract.md'])]:
    if not path.exists():raise AssertionError(path)
    for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
        if re.match(r'\w+://',dest) or dest.startswith('#'):continue
        target=(path.parent/dest.split('#',1)[0]).resolve()
        assert target.exists(),(str(path),dest)
        linkcount+=1
print(f'PASS scoped local Markdown destinations: {linkcount}; external URLs/heading anchors not validated')
print('No grader, candidate, model, pytest, or heavy test execution was performed by this command.')
