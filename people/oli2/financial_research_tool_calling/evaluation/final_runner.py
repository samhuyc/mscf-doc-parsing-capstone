"""Fixed-version integrated evaluation. Freeze + offline first; paid execution requires two flags."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

from demo import REPO_ROOT, CHUNKING_DIR
from api_demo import MODEL, TOOL_DEFINITIONS
from financial_agent import (ROOT, CAPS, IntegratedUnderstanding, IntegratedFakeClient,
                             integrated_turn)
from evaluation.live_runner import load_suite, evaluate, write_report, file_hash, PRICING
from evaluation.live_fixtures import client_for

OUT = ROOT / 'artifacts' / 'evaluation' / 'final_integration_v2'
MANIFEST = OUT / 'frozen_version.json'


def git(*args):
    return subprocess.check_output(['git',*args],cwd=REPO_ROOT,text=True,encoding='utf-8').strip()


def source_hashes():
    paths = [*ROOT.glob('*.py'), *ROOT.glob('*.txt'), *ROOT.glob('*.md'),
             * (ROOT/'evaluation').glob('*.py'), *(ROOT/'evaluation').glob('*.json'),
             *(ROOT/'evaluation').glob('*.sha256'), *(ROOT/'evaluation').glob('*.md')]
    return {p.relative_to(ROOT).as_posix():file_hash(p) for p in sorted(paths)}


def version_record():
    suite, dataset, digest = load_suite()
    return dict(schema_version='1', commit=git('rev-parse','HEAD'), model=MODEL, caps=CAPS,
        dataset_version=dataset.get('dataset_id',dataset.get('schema_version')),
        dataset_sha256=suite['dataset_sha256'], suite_id=suite['suite_id'], suite_sha256=digest,
        source_hashes=source_hashes(), retrieval_inputs=dataset['pinned_inputs'],
        retrieval_code={p.relative_to(REPO_ROOT).as_posix():file_hash(p)
                        for p in sorted(CHUNKING_DIR.glob('*.py'))},
        tools={'search_report':file_hash(ROOT/'demo.py'),'calculate':file_hash(ROOT/'demo.py'),
               'validation':file_hash(ROOT/'api_demo.py'), 'definitions':TOOL_DEFINITIONS},
        runtime={'python':sys.version.split()[0], **{name:version(name) for name in
                 ('openai','pydantic','tiktoken','markdown-it-py')}},
        model_settings={'reasoning':'low','service_tier':'default','store':False,'max_retries':0,'timeout_seconds':30},
        pricing=PRICING)


def freeze(path=MANIFEST):
    if git('branch','--show-current') == 'main' or git('status','--porcelain','--untracked-files=all'):
        raise ValueError('冻结需要独立分支上的干净本地 Commit；先保留并提交代码。')
    record = version_record()
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    # No overwrite: a previous fixed-version record must remain auditable.
    with path.open('x',encoding='utf-8') as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2)
    return record


def verify_frozen(path=MANIFEST):
    if git('status','--porcelain','--untracked-files=all'):
        raise ValueError('代码工作区有变化，禁止按旧冻结版本调用付费 API。')
    saved = json.loads(Path(path).read_text(encoding='utf-8'))
    if saved != version_record():
        raise ValueError('Commit、代码、工具、运行环境或 Dataset 与冻结记录不符。')
    return saved


def integrated_fixture(case_id, turn):
    # Explicit hand-written API fixtures independent of Golden Labels.
    parsed = client_for(case_id,turn).parsed
    parsed = {**parsed,'request_scope':'ambiguous' if parsed['needs_clarification'] else 'single_company',
              'candidate_companies':[parsed['company']] if parsed['company'] else []}
    if case_id == 'L05':
        parsed.update(request_scope='multiple_companies', intent='unsupported', company=None,
            candidate_companies=['CVS','UNH'], needs_clarification=False, clarification_question=None,
            metric='consolidated_total_revenue',period={'year':2025,'quarter':2})
    return IntegratedFakeClient(parsed)


def run_evaluation(directory, *, live_client=None, frozen=None):
    directory=Path(directory)
    suite,dataset,digest=load_suite()
    def run(session,question,client,**kwargs):
        # Same integrated path as the CLI. Cases have isolated storage; turns share it.
        return integrated_turn(session,question,client,
            storage_directory=directory/'state'/session.session_id,**kwargs)
    report=evaluate(suite,dataset,digest,live_client=live_client,fake_factory=integrated_fixture,
        turn_runner=run,understanding_model=IntegratedUnderstanding)
    report['fixed_version'] = frozen or version_record()
    report['scope'] += (' Final Integration v2: same CLI execution path. L05 explicit multi-company request '
        'is unsupported_capability, not ambiguity. Original clarify label is preserved; report the mismatch, do not inflate the score.')
    report['limitations'].append('L05 冻结标签为 clarify；新范围分类为 unsupported。原评分照常计差异，人工范围审查单列，不改 Golden Label。')
    report['integration_audit'] = [dict(case_id=t['case_id'],turn=t['turn'],category=t['observed']['category'],
        expected_scope_behavior='unsupported' if t['case_id']=='L05' else None,
        candidates=t['observed']['pending_companies']) for t in report['turns']]
    write_report(report,directory)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--confirm-paid-api',action='store_true')
    args=parser.parse_args(argv)
    if args.freeze:
        if args.live: raise ValueError('冻结与付费执行必须分开。')
        print(json.dumps(freeze(),ensure_ascii=False,indent=2)); return 0
    if args.live and not args.confirm_paid_api:
        print('未确认付费，未读取密钥或调用 API。'); return 1
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=OUT/(('live_' if args.live else 'offline_')+stamp)
    for name in ('openai','httpx','httpx2','httpcore'):
        logging.getLogger(name).disabled=True
    if args.live:
        frozen=verify_frozen()  # Before credential access/client construction.
        from openai import OpenAI
        with OpenAI(api_key=os.environ['OPENAI_API_KEY'],base_url='https://api.openai.com/v1',
                    max_retries=0,timeout=30.0) as client:
            report=run_evaluation(directory,live_client=client,frozen=frozen)
    else:
        frozen=verify_frozen() if MANIFEST.exists() else None
        report=run_evaluation(directory,frozen=frozen)
    print(directory/'report.html')
    print(json.dumps({'type':report['evaluation_type'],'requests':report['requests'],
        'usage':report['usage'],'cost':report['cost'],'stopped':report['stopped_early']},ensure_ascii=False))
    return 1 if report['stopped_early'] else 0


if __name__=='__main__':
    try: code=main()
    except Exception:
        print('配置或执行失败，安全停止；异常详情隐藏，未自动重试。'); code=1
    raise SystemExit(code)
