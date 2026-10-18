"""Render retained trajectories and extract literal code payloads; never execute candidate code."""
from pathlib import Path
import hashlib
import json
import ast

HOME = Path(__file__).resolve().parent
records = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


for sample in json.loads((HOME/'samples.json').read_text()):
    d = HOME/'evidence'/sample['id']
    lines = [f'# {sample["id"]}', f'Measurement revision: `{sample["revision"]}`; actual={sample["actual"]}; claimed={sample["claimed"]}.', f'Raw row: `{sample["source_results"]}:{sample["source_line"]}`; retained `row.json:1`.']
    if (d/'trajectory.jsonl').exists():
        rows = [json.loads(x) for x in (d/'trajectory.jsonl').read_text().splitlines()]
        pending = {}
        writes = []
        for n, r in enumerate(rows, 1):
            kind = r['kind']
            label = f'`trajectory.jsonl:{n}` seq={r.get("seq")}'
            if kind == 'model_call':
                env = r.get('envelope') or {}
                lines.append(f'- {label} **{r["step_type"]}**: {env.get("comment", "")}')
                codefiles = env.get('files', [])
                if env.get('file_path') and 'content' in env:
                    codefiles = [dict(file_path=env['file_path'], content=env['content'])]
                for f in codefiles:
                    if not isinstance(f, dict) or not isinstance(f.get('content'), str):
                        continue
                    rel = Path(f['file_path'])
                    assert not rel.is_absolute() and '..' not in rel.parts
                    target = d/'payloads'/f'L{n:03}'/rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = f['content'].encode()
                    target.write_bytes(data)
                    pending[str(rel)] = (n, data)
                    try:
                        if rel.suffix == '.py':
                            ast.parse(data)
                            parse = 'parse-ok'
                        else:
                            parse = 'not Python; parse not applicable'
                    except SyntaxError as exc:
                        parse = f'SyntaxError line {exc.lineno}: {exc.msg}'
                    lines.append(f'  - Literal payload `{target.relative_to(d)}` sha256={sha(data)}; {parse}.')
                if env.get('blame') or env.get('grade'):
                    lines.append('  - '+json.dumps(env, ensure_ascii=False))
            elif kind == 'source_write':
                p = r['path']
                match = p in pending and sha(pending[p][1]) == r['sha256']
                writes.append(dict(trajectory_line=n,path=p,sha256=r['sha256'],payload_line=pending.get(p,(None,))[0],payload_matches=match))
                lines.append(f'- {label} **source_write** `{p}` sha256={r["sha256"]}; payload-match={match}.')
            elif kind == 'test_run':
                lines.append(f'- {label} **test {r.get("label")}** verdict={r.get("verdict")}; '+json.dumps(r.get('excerpts', []),ensure_ascii=False))
            elif kind == 'harness_event':
                event = r['event']
                data = json.dumps(r.get('data',{}),ensure_ascii=False)
                if event in ['criterion_ledger','failure_report','independent_test_verdict'] and len(data)>1200:
                    data = data[:1200]+' … (full data in trajectory)'
                lines.append(f'- {label} **{event}** {data}')
        finals = []
        for p in sorted((d/'work').rglob('*.py')):
            h = sha(p.read_bytes()); rel=str(p.relative_to(d/'work'))
            matching=[x['trajectory_line'] for x in writes if x['path']==rel and x['sha256']==h]
            grade = d/'grade-repo'/rel
            finals.append(dict(path=rel,sha256=h,matching_write_lines=matching,graded_sha256=sha(grade.read_bytes()) if grade.is_file() else None,work_equals_graded=grade.is_file() and grade.read_bytes()==p.read_bytes()))
        records.append(dict(id=sample['id'],writes=writes,finals=finals))
        lines.append('## Final byte identities')
        lines.extend('- '+json.dumps(x,ensure_ascii=False) for x in finals)
    else:
        for n, raw in enumerate((d/'events-selected.jsonl').read_text().splitlines(),1):
            wrap=json.loads(raw); r=wrap['event']; orig=wrap['source_line']
            label=f'`events-selected.jsonl:{n}` (original events line {orig})'
            if r['type']=='message_end':
                msg=r['message']; role=msg['role']
                if role=='system':
                    continue
                lines.append(f'- {label} **{role}** stopReason={msg.get("stopReason")}; errorMessage={msg.get("errorMessage")}; outputTokens={msg.get("usage", {}).get("output")}')
                content=msg.get('content',[])
                if isinstance(content,str):
                    content=[dict(type='text',text=content)]
                for c in content:
                    if c.get('type')=='toolCall':
                        lines.append('  - tool '+c['name']+' '+json.dumps(c.get('arguments'),ensure_ascii=False))
                    elif c.get('type') in ['text','thinking']:
                        lines.append('  - '+c.get('text',c.get('thinking','')))
            elif r['type']=='tool_execution_end':
                lines.append(f'- {label} **tool result** '+json.dumps(r,ensure_ascii=False))
    (d/'index.md').write_text('\n'.join(lines)+'\n')
(HOME/'reconstruction.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
assert all(w['payload_matches'] for r in records for w in r['writes'])
print(f'{len(records)} trajectories; {sum(len(r["writes"]) for r in records)} source_write payload hashes match; no candidate execution')
