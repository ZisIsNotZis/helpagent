#!/usr/bin/env bash
# Ticket-29 lightweight proof only; never execute captured code or call models/graders.
set -euo pipefail
cd /home/z/vibe/helpagent
date --iso-8601=seconds
echo '$ python3 -B .scratch/29-close-audit/verify_evidence.py --check-sources'
python3 -B .scratch/29-close-audit/verify_evidence.py --check-sources
echo '$ python3 -B .scratch/29-close-audit/check_docs_semantics.py'
python3 -B .scratch/29-close-audit/check_docs_semantics.py
echo '$ AST parse authored root Python; bash -n run_checks.sh'
python3 -B - <<'PY'
from pathlib import Path
import ast
files=list(Path('.scratch/29-close-audit').glob('*.py'))
for p in files:ast.parse(p.read_text(),filename=str(p))
print('PASS authored scripts AST parse:',len(files))
PY
bash -n .scratch/29-close-audit/run_checks.sh
echo '$ git diff --check -- README.md docs/STATUS.md docs/LEARNINGS.md docs/ROADMAP.md .scratch/29-close-audit'
git diff --check -- README.md docs/STATUS.md docs/LEARNINGS.md docs/ROADMAP.md .scratch/29-close-audit
echo 'PASS tracked scoped diff whitespace'
echo '$ git diff --no-index --check /dev/null <new authored root text> with stdin negative control'
python3 -B - <<'PY'
from pathlib import Path
import subprocess

def check(path, text=None):
    return subprocess.run(['git','diff','--no-index','--check','--','/dev/null',str(path)],input=text,capture_output=True,text=True)
clean=check('/dev/stdin','line\n')
bad=check('/dev/stdin','line \n')
assert clean.returncode in (0,1) and not clean.stdout and not clean.stderr
assert bad.returncode not in (0,1) and 'trailing whitespace' in bad.stdout
files=[p for p in Path('.scratch/29-close-audit').iterdir() if p.is_file() and p.suffix in ['.md','.py','.json','.sh']]
for p in files:
    r=check(p)
    assert r.returncode in (0,1) and not r.stdout and not r.stderr,(str(p),r.stdout,r.stderr,r.returncode)
print('PASS new authored/structured root files whitespace:',len(files),'; stdin whitespace negative control rejected')
print('Raw evidence/payload/patch bytes are preserved, hash-checked, not normalized or executed.')
PY
echo '$ git apply --check --reverse .scratch/29-close-audit/final.diff'
git apply --check --reverse .scratch/29-close-audit/final.diff
echo 'PASS saved document patch reverses cleanly in check-only mode; nothing applied'
echo '$ git diff 45ebb32 HEAD --exit-code -- <named code and corpus paths>'
git diff 45ebb32 HEAD --exit-code -- harness/leaf.py harness/tree_run.py harness/node.py bench/v2_leaf.py bench/v2_tree.py bench/pi_baseline.py bench/corpus bench/anchor
echo 'PASS measurement-source identity'
echo '$ git diff --cached --exit-code'
git diff --cached --exit-code
echo 'PASS no staged files'
echo '$ validate changed-path allowlist and unchanged HEAD'
python3 -B - <<'PY'
import subprocess
baseline='72f25fac838afa5b6ff1b7799225ebfd6e252a1e'
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==baseline
tracked=subprocess.check_output(['git','diff','--name-only'],text=True).splitlines()
assert set(tracked)=={'README.md','docs/STATUS.md','docs/LEARNINGS.md','docs/ROADMAP.md'},tracked
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
assert all(p.startswith('.scratch/29-close-audit/') for p in untracked),untracked
print('PASS four modified current docs; additions only .scratch/29-close-audit/; HEAD unchanged')
PY
echo 'NOT RUN: model calls, candidate execution, original grader, pytest/unit/contract/full CI; docs-only bounded read/AST/hash checks.'
date --iso-8601=seconds
