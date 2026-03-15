from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.codex.service import CodexEvaluationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='run_codex_adoption_experiment')
    parser.add_argument('--tasks-file', default='benchmarks/codex/tasks/suitcode_v7_adoption_latency.json')
    parser.add_argument('--timeout-seconds', type=int, default=None)
    parser.add_argument('--model', default=None)
    parser.add_argument('--codex-config-profile', default=None)
    parser.add_argument('--json', action='store_true', dest='as_json')
    parser.add_argument('--no-full-auto', action='store_true')
    parser.add_argument('--sandbox', default='workspace-write')
    parser.add_argument('--bypass-approvals-and-sandbox', action='store_true')
    return parser


def _summary(report) -> dict[str, object]:
    return {
        'report_id': report.report_id,
        'task_total': report.task_total,
        'task_passed': report.task_passed,
        'task_failed': report.task_failed,
        'task_error': report.task_error,
        'avg_duration_ms': report.avg_duration_ms,
        'avg_transcript_tokens': report.avg_transcript_tokens,
        'avg_first_suitcode_tool_index': report.avg_first_suitcode_tool_index,
        'avg_first_high_value_tool_index': report.avg_first_high_value_tool_index,
        'avg_tokens_before_first_suitcode_tool': report.avg_tokens_before_first_suitcode_tool,
        'avg_tokens_before_first_high_value_tool': report.avg_tokens_before_first_high_value_tool,
        'required_tool_success_rate': report.required_tool_success_rate,
        'high_value_tool_early_rate': report.high_value_tool_early_rate,
    }


def _markdown(experiment_id: str, generated_at_utc: str, default_summary: dict[str, object], hinted_summary: dict[str, object], tasks_file: str) -> str:
    return '\n'.join([
        '# Codex Adoption Latency Experiment',
        '',
        f'- experiment id: `{experiment_id}`',
        f'- generated at: `{generated_at_utc}`',
        f'- tasks file: `{tasks_file}`',
        '- arm: `suitcode` in both conditions',
        '- condition difference: `auto_orientation_hint` only',
        '',
        '## Conditions',
        '',
        '| Condition | Report | Passed | Failed | Error | Avg duration ms | Avg transcript tokens | Avg first SuitCode tool index | Avg first high-value tool index | Avg tokens before first high-value tool |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
        f"| default | {default_summary['report_id']} | {default_summary['task_passed']} | {default_summary['task_failed']} | {default_summary['task_error']} | {default_summary['avg_duration_ms']:.1f} | {default_summary['avg_transcript_tokens'] if default_summary['avg_transcript_tokens'] is not None else '-'} | {default_summary['avg_first_suitcode_tool_index'] if default_summary['avg_first_suitcode_tool_index'] is not None else '-'} | {default_summary['avg_first_high_value_tool_index'] if default_summary['avg_first_high_value_tool_index'] is not None else '-'} | {default_summary['avg_tokens_before_first_high_value_tool'] if default_summary['avg_tokens_before_first_high_value_tool'] is not None else '-'} |",
        f"| auto_orientation_hint | {hinted_summary['report_id']} | {hinted_summary['task_passed']} | {hinted_summary['task_failed']} | {hinted_summary['task_error']} | {hinted_summary['avg_duration_ms']:.1f} | {hinted_summary['avg_transcript_tokens'] if hinted_summary['avg_transcript_tokens'] is not None else '-'} | {hinted_summary['avg_first_suitcode_tool_index'] if hinted_summary['avg_first_suitcode_tool_index'] is not None else '-'} | {hinted_summary['avg_first_high_value_tool_index'] if hinted_summary['avg_first_high_value_tool_index'] is not None else '-'} | {hinted_summary['avg_tokens_before_first_high_value_tool'] if hinted_summary['avg_tokens_before_first_high_value_tool'] is not None else '-'} |",
        '',
        '## Interpretation',
        '',
        'This experiment is intended to measure whether a minimal deterministic-orientation hint changes tool adoption timing and visible trajectory cost without changing the task text or output schema.',
        '',
    ])


def main() -> None:
    args = build_parser().parse_args()
    tasks_file = Path(args.tasks_file).expanduser().resolve()
    if not tasks_file.exists():
        raise ValueError(f'Codex adoption tasks file not found: `{tasks_file}`')
    service = CodexEvaluationService(working_directory=PROJECT_ROOT)
    tasks = service.load_tasks(tasks_file)
    if args.timeout_seconds is not None:
        if args.timeout_seconds <= 0:
            raise ValueError('--timeout-seconds must be > 0')
        tasks = tuple(item.model_copy(update={'timeout_seconds': args.timeout_seconds}) for item in tasks)

    common = {
        'model': args.model,
        'profile': args.codex_config_profile,
        'prompt_arm': EvaluationArm.SUITCODE,
        'full_auto': not args.no_full_auto,
        'sandbox': args.sandbox,
        'bypass_approvals_and_sandbox': args.bypass_approvals_and_sandbox,
    }
    default_report = service.run(tasks, auto_orientation_hint=False, **common)
    hinted_report = service.run(tasks, auto_orientation_hint=True, **common)

    generated_at_utc = datetime.now(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    experiment_id = f'codex-adoption-{uuid4().hex}'
    run_dir = PROJECT_ROOT / '.suit' / 'evaluation' / 'codex' / 'adoption' / f"{generated_at_utc.replace(':', '-')}__{experiment_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        'experiment_id': experiment_id,
        'generated_at_utc': generated_at_utc,
        'tasks_file': str(tasks_file.relative_to(PROJECT_ROOT)),
        'default': _summary(default_report),
        'auto_orientation_hint': _summary(hinted_report),
    }
    (run_dir / 'summary.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    (run_dir / 'summary.md').write_text(_markdown(experiment_id, generated_at_utc, payload['default'], payload['auto_orientation_hint'], payload['tasks_file']), encoding='utf-8')

    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f'Generated Codex adoption experiment: {experiment_id}')
        print(f'Default report: {default_report.report_id}')
        print(f'Auto-orientation report: {hinted_report.report_id}')
        print(f'Artifact directory: {run_dir}')


if __name__ == '__main__':
    main()
