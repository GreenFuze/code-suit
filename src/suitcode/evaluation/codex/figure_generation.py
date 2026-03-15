from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from suitcode.analytics.transcript_models import TranscriptTokenBreakdown
from suitcode.evaluation.comparison_models import (
    ComparisonFigure,
    ComparisonFigureSection,
    CodexStandoutReport,
    EvaluationArm,
    SuiteRole,
)
from suitcode.evaluation.models import CodexEvaluationReport, CodexEvaluationTaskResult, EvaluationStatus
from suitcode.evaluation.protocol_models import MetricKind


class CodexComparisonFigureBuilder:
    _SUITCODE_COLOR = '#1f77b4'
    _BASELINE_COLOR = '#ff7f0e'
    _PASS_COLOR = '#4daf4a'
    _FAIL_COLOR = '#d62728'
    _NEUTRAL_COLOR = '#7f7f7f'
    _FAILURE_COLORS = {
        'answer_mismatch': '#d62728',
        'schema_validation_failed': '#9467bd',
        'required_tools_missing': '#8c564b',
        'argument_mismatch': '#e377c2',
        'required_action_not_executed': '#bcbd22',
        'required_action_wrong_target': '#17becf',
        'timeout': '#7f7f7f',
        'cli_error': '#525252',
        'usage_limit': '#6a3d9a',
        'session_artifact_missing': '#9e9e9e',
        'session_correlation_ambiguous': '#bdbdbd',
        'unexpected_exception': '#636363',
    }
    _TOKEN_FIELDS = (
        ('user_message_tokens', 'User messages'),
        ('assistant_message_tokens', 'Assistant messages'),
        ('mcp_tool_call_tokens', 'MCP tool calls'),
        ('mcp_tool_output_tokens', 'MCP tool outputs'),
        ('custom_tool_call_tokens', 'Custom tool calls'),
        ('custom_tool_output_tokens', 'Custom tool outputs'),
        ('reasoning_summary_tokens', 'Reasoning summaries'),
        ('terminal_output_tokens', 'Terminal output'),
    )

    def build(
        self,
        *,
        report: CodexStandoutReport,
        run_dir: Path,
        stable_readonly_suitcode_report: CodexEvaluationReport,
        stable_readonly_baseline_report: CodexEvaluationReport,
        stable_execution_report: CodexEvaluationReport | None,
        stable_execution_baseline_report: CodexEvaluationReport | None = None,
        stress_report: CodexEvaluationReport | None,
        stress_baseline_report: CodexEvaluationReport | None = None,
    ) -> tuple[ComparisonFigure, ...]:
        figures_dir = run_dir / 'figures'
        data_dir = figures_dir / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)
        figures: list[ComparisonFigure] = []
        figures.append(self._build_headline_outcomes(report, figures_dir, data_dir))
        figures.append(self._build_headline_costs(report, figures_dir, data_dir))
        if stable_execution_report is not None:
            figures.append(
                self._build_execution_matrix(
                    stable_execution_report,
                    stable_execution_baseline_report,
                    figures_dir,
                    data_dir,
                )
            )
        figures.append(self._build_task_dumbbell(report, figures_dir, data_dir))
        figures.append(self._build_failure_taxonomy(report, figures_dir, data_dir))
        figures.append(
            self._build_token_composition(
                stable_readonly_suitcode_report=stable_readonly_suitcode_report,
                stable_readonly_baseline_report=stable_readonly_baseline_report,
                figures_dir=figures_dir,
                data_dir=data_dir,
            )
        )
        passive_figure = self._build_passive_adoption(report, figures_dir, data_dir)
        if passive_figure is not None:
            figures.append(passive_figure)
        return tuple(figures)

    def _build_headline_outcomes(self, report: CodexStandoutReport, figures_dir: Path, data_dir: Path) -> ComparisonFigure:
        metrics = (
            ('Task success', self._headline_metric(report, 'task_success_rate')),
            ('Schema success', self._headline_metric(report, 'answer_schema_success_rate')),
        )
        fig, ax = plt.subplots(figsize=(8, 4.8))
        positions = range(len(metrics))
        width = 0.35
        suitcode_values = [metric[1][0] * 100.0 for metric in metrics]
        baseline_values = [metric[1][1] * 100.0 for metric in metrics]
        ax.bar([index - width / 2 for index in positions], suitcode_values, width, color=self._SUITCODE_COLOR, label='SuitCode')
        ax.bar([index + width / 2 for index in positions], baseline_values, width, color=self._BASELINE_COLOR, label='Baseline')
        ax.set_xticks(list(positions), [metric[0] for metric in metrics])
        ax.set_ylabel('Rate (%)')
        ax.set_ylim(0, 100)
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
        ax.set_title('Stable read-only headline outcomes')
        ax.legend()
        ax.grid(axis='y', alpha=0.25)
        for index, value in enumerate(suitcode_values):
            ax.text(index - width / 2, value + 2, f'{value:.0f}%', ha='center', va='bottom', fontsize=9)
        for index, value in enumerate(baseline_values):
            ax.text(index + width / 2, value + 2, f'{value:.0f}%', ha='center', va='bottom', fontsize=9)
        svg_path = figures_dir / '01-headline-outcomes.svg'
        csv_path = data_dir / '01-headline-outcomes.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        self._write_csv(csv_path, ('metric', 'arm', 'value_percent'), [
            ('task_success', 'suitcode', f'{suitcode_values[0]:.2f}'),
            ('task_success', 'baseline', f'{baseline_values[0]:.2f}'),
            ('answer_schema_success', 'suitcode', f'{suitcode_values[1]:.2f}'),
            ('answer_schema_success', 'baseline', f'{baseline_values[1]:.2f}'),
        ])
        return ComparisonFigure(
            figure_id='figure-01-headline-outcomes',
            title='Figure 1. Headline A/B Outcomes',
            section=ComparisonFigureSection.MAIN,
            caption='Stable read-only A/B comparison of task success and answer-schema success under Codex with and without SuitCode.',
            interpretation='SuitCode completed all headline tasks, while baseline answers were schema-valid but did not match deterministic ground truth.',
            svg_relative_path='figures/01-headline-outcomes.svg',
            csv_relative_path='figures/data/01-headline-outcomes.csv',
            source_scope='stable_readonly',
            metric_kinds=(MetricKind.MEASURED,),
            depends_on_sections=('Headline Core A/B', 'Benchmark Protocol'),
        )

    def _build_headline_costs(self, report: CodexStandoutReport, figures_dir: Path, data_dir: Path) -> ComparisonFigure:
        duration = self._headline_metric(report, 'avg_duration_ms')
        tokens = self._headline_metric(report, 'avg_transcript_tokens')
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
        axes[0].bar(['SuitCode', 'Baseline'], [duration[0] / 1000.0, duration[1] / 1000.0], color=[self._SUITCODE_COLOR, self._BASELINE_COLOR])
        axes[0].set_title('Average duration')
        axes[0].set_ylabel('Seconds')
        axes[0].grid(axis='y', alpha=0.25)
        axes[1].bar(['SuitCode', 'Baseline'], [tokens[0], tokens[1]], color=[self._SUITCODE_COLOR, self._BASELINE_COLOR])
        axes[1].set_title('Average transcript-estimated tokens')
        axes[1].set_ylabel('Tokens')
        axes[1].grid(axis='y', alpha=0.25)
        svg_path = figures_dir / '02-headline-costs.svg'
        csv_path = data_dir / '02-headline-costs.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        self._write_csv(csv_path, ('metric', 'arm', 'value'), [
            ('avg_duration_seconds', 'suitcode', f'{duration[0] / 1000.0:.4f}'),
            ('avg_duration_seconds', 'baseline', f'{duration[1] / 1000.0:.4f}'),
            ('avg_transcript_tokens', 'suitcode', f'{tokens[0]:.2f}'),
            ('avg_transcript_tokens', 'baseline', f'{tokens[1]:.2f}'),
        ])
        return ComparisonFigure(
            figure_id='figure-02-headline-costs',
            title='Figure 2. Headline A/B Cost Comparison',
            section=ComparisonFigureSection.MAIN,
            caption='Stable read-only A/B comparison of average runtime and transcript-estimated token cost.',
            interpretation='SuitCode reduced both visible transcript cost and wall-clock time relative to the baseline on the bounded headline suite.',
            svg_relative_path='figures/02-headline-costs.svg',
            csv_relative_path='figures/data/02-headline-costs.csv',
            source_scope='stable_readonly',
            metric_kinds=(MetricKind.MEASURED, MetricKind.ESTIMATED),
            depends_on_sections=('Headline Core A/B', 'Benchmark Protocol'),
        )

    def _build_execution_matrix(
        self,
        report: CodexEvaluationReport,
        baseline_report: CodexEvaluationReport | None,
        figures_dir: Path,
        data_dir: Path,
    ) -> ComparisonFigure:
        rows = []
        labels = []
        csv_rows = []
        reports: tuple[tuple[str, CodexEvaluationReport], ...] = (
            (("Baseline", baseline_report),) if baseline_report is not None else ()
        ) + (("SuitCode", report),)
        for arm_label, arm_report in reports:
            for task in arm_report.tasks:
                labels.append(f"{task.task_id} ({arm_label})")
                values = [
                    1 if task.tool_selection.required_tools_present else 0,
                    1 if task.answer_score.schema_valid else 0,
                    1 if task.action_score.executed else 0,
                    1 if task.action_score.matched_target else 0,
                    1 if task.status == EvaluationStatus.PASSED else 0,
                ]
                rows.append(values)
                csv_rows.append((task.task_id, arm_label.lower(), *map(str, values)))
        fig, ax = plt.subplots(figsize=(8, max(3.5, 1.2 + len(labels) * 0.7)))
        image = ax.imshow(rows, cmap='RdYlGn', vmin=0, vmax=1, aspect='auto')
        ax.set_yticks(range(len(labels)), labels=labels)
        ax.set_xticks(range(5), labels=['Required tools', 'Schema valid', 'Action executed', 'Target matched', 'Passed'], rotation=20, ha='right')
        ax.set_title('Stable execution outcome matrix')
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                ax.text(col_index, row_index, 'yes' if value else 'no', ha='center', va='center', fontsize=8)
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
        svg_path = figures_dir / '03-stable-execution-matrix.svg'
        csv_path = data_dir / '03-stable-execution-matrix.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        self._write_csv(
            csv_path,
            ('task_id', 'arm', 'required_tools', 'schema_valid', 'action_executed', 'target_matched', 'passed'),
            csv_rows,
        )
        return ComparisonFigure(
            figure_id='figure-03-stable-execution-matrix',
            title='Figure 3. Stable Execution Outcome Matrix',
            section=ComparisonFigureSection.MAIN,
            caption='Stable execution A/B task outcomes, showing tool use, schema validity, and deterministic action correctness for both arms when available.',
            interpretation='SuitCode is evaluated against the same bounded execution tasks as baseline rather than treatment-only execution examples.',
            svg_relative_path='figures/03-stable-execution-matrix.svg',
            csv_relative_path='figures/data/03-stable-execution-matrix.csv',
            source_scope='stable_execution',
            metric_kinds=(MetricKind.MEASURED,),
            depends_on_sections=('Stable Execution', 'Failure Taxonomy'),
        )

    def _build_task_dumbbell(self, report: CodexStandoutReport, figures_dir: Path, data_dir: Path) -> ComparisonFigure:
        grouped: dict[str, dict[str, CodexEvaluationTaskResult]] = {}
        for item in report.task_level_summaries:
            if item.suite_role != SuiteRole.STABLE_READONLY:
                continue
            grouped.setdefault(item.task_id, {})[item.arm.value] = item
        rows = []
        for task_id, pair in grouped.items():
            if 'suitcode' not in pair or 'baseline' not in pair:
                raise ValueError(f'stable_readonly task `{task_id}` is missing a paired arm for the task-level dumbbell figure')
            rows.append((task_id, pair['suitcode'], pair['baseline']))
        rows.sort(key=lambda item: item[0])
        fig, axes = plt.subplots(1, 2, figsize=(12, max(4.5, 1.5 + len(rows) * 0.8)), sharey=True)
        y_positions = list(range(len(rows)))
        labels = [item[0] for item in rows]
        for axis, getter, title, xlabel in (
            (axes[0], lambda item: item.duration_ms / 1000.0, 'Per-task duration', 'Seconds'),
            (axes[1], lambda item: float(item.transcript_tokens or 0), 'Per-task transcript-estimated tokens', 'Tokens'),
        ):
            for idx, (_, suitcode_item, baseline_item) in enumerate(rows):
                suitcode_value = getter(suitcode_item)
                baseline_value = getter(baseline_item)
                axis.plot([baseline_value, suitcode_value], [idx, idx], color='#9e9e9e', linewidth=1.5)
                axis.scatter([baseline_value], [idx], color=self._BASELINE_COLOR, s=40, label='Baseline' if idx == 0 else None)
                axis.scatter([suitcode_value], [idx], color=self._SUITCODE_COLOR, s=40, label='SuitCode' if idx == 0 else None)
            axis.set_title(title)
            axis.set_xlabel(xlabel)
            axis.grid(axis='x', alpha=0.25)
        axes[0].set_yticks(y_positions, labels=labels)
        axes[0].invert_yaxis()
        axes[0].legend(loc='lower right')
        svg_path = figures_dir / '04-task-level-dumbbell.svg'
        csv_path = data_dir / '04-task-level-dumbbell.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        csv_rows = [
            (task_id, 'suitcode', f'{suitcode_item.duration_ms / 1000.0:.4f}', str(suitcode_item.transcript_tokens or 0))
            for task_id, suitcode_item, _ in rows
        ]
        csv_rows.extend(
            (task_id, 'baseline', f'{baseline_item.duration_ms / 1000.0:.4f}', str(baseline_item.transcript_tokens or 0))
            for task_id, _, baseline_item in rows
        )
        self._write_csv(csv_path, ('task_id', 'arm', 'duration_seconds', 'transcript_tokens'), csv_rows)
        return ComparisonFigure(
            figure_id='figure-04-task-level-dumbbell',
            title='Figure 4. Task-Level Duration and Token Comparison',
            section=ComparisonFigureSection.SUPPORTING,
            caption='Paired task-level comparison of duration and transcript-estimated token cost for the stable read-only suite.',
            interpretation='The aggregate headline gain is broad across the bounded tasks rather than coming from a single outlier task.',
            svg_relative_path='figures/04-task-level-dumbbell.svg',
            csv_relative_path='figures/data/04-task-level-dumbbell.csv',
            source_scope='stable_readonly',
            metric_kinds=(MetricKind.MEASURED, MetricKind.ESTIMATED),
            depends_on_sections=('Headline Core A/B', 'Task-Level Results'),
        )

    def _build_failure_taxonomy(self, report: CodexStandoutReport, figures_dir: Path, data_dir: Path) -> ComparisonFigure:
        labels = []
        rows = []
        categories = []
        for item in report.suite_failure_explanations:
            labels.append(f'{item.suite_role.value}\n{item.arm.value}')
            for key in item.failure_kind_mix:
                if key not in categories:
                    categories.append(key)
        if not categories:
            categories = ['answer_mismatch']
        csv_rows = []
        fig, ax = plt.subplots(figsize=(10, 5))
        bottoms = [0] * len(report.suite_failure_explanations)
        x_positions = list(range(len(report.suite_failure_explanations)))
        for category in categories:
            values = []
            for index, item in enumerate(report.suite_failure_explanations):
                count = int(item.failure_kind_mix.get(category, 0))
                values.append(count)
                csv_rows.append((item.suite_role.value, item.arm.value, category, str(count)))
            ax.bar(x_positions, values, bottom=bottoms, label=category, color=self._FAILURE_COLORS.get(category, self._NEUTRAL_COLOR))
            bottoms = [current + value for current, value in zip(bottoms, values)]
        ax.set_xticks(x_positions, labels=labels)
        ax.set_ylabel('Task count')
        ax.set_title('Failure taxonomy by suite and arm')
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(axis='y', alpha=0.25)
        svg_path = figures_dir / '05-failure-taxonomy.svg'
        csv_path = data_dir / '05-failure-taxonomy.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        self._write_csv(csv_path, ('suite_role', 'arm', 'failure_kind', 'count'), csv_rows)
        return ComparisonFigure(
            figure_id='figure-05-failure-taxonomy',
            title='Figure 5. Failure Taxonomy by Suite and Arm',
            section=ComparisonFigureSection.SUPPORTING,
            caption='Failure-kind distribution across the included suites and arms.',
            interpretation='The headline baseline failures are substantive answer mismatches rather than harness or infrastructure failures.',
            svg_relative_path='figures/05-failure-taxonomy.svg',
            csv_relative_path='figures/data/05-failure-taxonomy.csv',
            source_scope='suite_failures',
            metric_kinds=(MetricKind.MEASURED,),
            depends_on_sections=('Failure Taxonomy', 'Suite Failure Analysis'),
        )

    def _build_token_composition(self, *, stable_readonly_suitcode_report: CodexEvaluationReport, stable_readonly_baseline_report: CodexEvaluationReport, figures_dir: Path, data_dir: Path) -> ComparisonFigure:
        suitcode_breakdown = self._aggregate_token_breakdowns(stable_readonly_suitcode_report.tasks)
        baseline_breakdown = self._aggregate_token_breakdowns(stable_readonly_baseline_report.tasks)
        fig, ax = plt.subplots(figsize=(10, 5))
        x_positions = [0, 1]
        bottoms = [0, 0]
        csv_rows = []
        for field_name, label in self._TOKEN_FIELDS:
            values = [float(suitcode_breakdown[field_name]), float(baseline_breakdown[field_name])]
            ax.bar(x_positions, values, bottom=bottoms, label=label)
            bottoms = [current + value for current, value in zip(bottoms, values)]
            csv_rows.append((label, 'suitcode', str(values[0])))
            csv_rows.append((label, 'baseline', str(values[1])))
        ax.set_xticks(x_positions, labels=['SuitCode', 'Baseline'])
        ax.set_ylabel('Tokens')
        ax.set_title('Transcript token composition by arm')
        ax.legend(loc='upper right', fontsize=8)
        svg_path = figures_dir / '06-token-composition.svg'
        csv_path = data_dir / '06-token-composition.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        self._write_csv(csv_path, ('segment', 'arm', 'tokens'), csv_rows)
        return ComparisonFigure(
            figure_id='figure-06-token-composition',
            title='Figure 6. Transcript Token Composition by Arm',
            section=ComparisonFigureSection.SUPPORTING,
            caption='Visible transcript token composition for the stable read-only A/B comparison.',
            interpretation='The token-cost difference is not only a smaller total; it also changes where the visible transcript budget is spent.',
            svg_relative_path='figures/06-token-composition.svg',
            csv_relative_path='figures/data/06-token-composition.csv',
            source_scope='stable_readonly',
            metric_kinds=(MetricKind.ESTIMATED,),
            depends_on_sections=('Headline Core A/B', 'Passive Codex Usage'),
        )

    def _build_passive_adoption(self, report: CodexStandoutReport, figures_dir: Path, data_dir: Path) -> ComparisonFigure | None:
        summary = report.passive_usage_summary
        if summary is None:
            return None
        first_tool = summary.get('first_tool_distribution')
        first_high_value = summary.get('first_high_value_tool_distribution')
        if not isinstance(first_tool, dict) or not isinstance(first_high_value, dict) or not first_tool or not first_high_value:
            return None
        first_tool_items = sorted(((str(k), int(v)) for k, v in first_tool.items()), key=lambda item: (-item[1], item[0]))
        high_value_items = sorted(((str(k), int(v)) for k, v in first_high_value.items()), key=lambda item: (-item[1], item[0]))
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
        axes[0].bar([item[0] for item in first_tool_items], [item[1] for item in first_tool_items], color=self._SUITCODE_COLOR)
        axes[0].set_title('First SuitCode tool')
        axes[0].tick_params(axis='x', rotation=30)
        axes[0].set_ylabel('Sessions')
        axes[1].bar([item[0] for item in high_value_items], [item[1] for item in high_value_items], color=self._PASS_COLOR)
        axes[1].set_title('First high-value SuitCode tool')
        axes[1].tick_params(axis='x', rotation=30)
        svg_path = figures_dir / '07-passive-adoption.svg'
        csv_path = data_dir / '07-passive-adoption.csv'
        fig.tight_layout()
        fig.savefig(svg_path, format='svg')
        plt.close(fig)
        csv_rows = [(tool, 'first_tool', str(count)) for tool, count in first_tool_items]
        csv_rows.extend((tool, 'first_high_value_tool', str(count)) for tool, count in high_value_items)
        self._write_csv(csv_path, ('tool', 'distribution_kind', 'sessions'), csv_rows)
        return ComparisonFigure(
            figure_id='figure-07-passive-adoption',
            title='Figure 7. Passive Codex Adoption Distribution',
            section=ComparisonFigureSection.SUPPORTING,
            caption='Distribution of the first SuitCode tool and the first high-value SuitCode tool across passive Codex sessions.',
            interpretation='Passive usage helps show whether Codex typically adopts SuitCode early enough to matter in practice.',
            svg_relative_path='figures/07-passive-adoption.svg',
            csv_relative_path='figures/data/07-passive-adoption.csv',
            source_scope='passive_usage',
            metric_kinds=(MetricKind.DERIVED,),
            depends_on_sections=('Passive Codex Usage',),
        )

    @staticmethod
    def _write_csv(path: Path, headers: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)

    @staticmethod
    def _headline_metric(report: CodexStandoutReport, metric_name: str) -> tuple[float, float]:
        for item in report.headline_deltas:
            if item.metric_name == metric_name:
                if item.suitcode_value is None or item.baseline_value is None:
                    raise ValueError(f'headline metric `{metric_name}` is not available for figure generation')
                return float(item.suitcode_value), float(item.baseline_value)
        raise ValueError(f'headline metric `{metric_name}` is missing from the comparison report')

    def _aggregate_token_breakdowns(self, tasks: tuple[CodexEvaluationTaskResult, ...]) -> dict[str, int]:
        totals = {field_name: 0 for field_name, _ in self._TOKEN_FIELDS}
        for task in tasks:
            breakdown = task.transcript_token_breakdown
            if breakdown is None:
                raise ValueError(f'task `{task.task_id}` is missing transcript_token_breakdown required for token-composition figure generation')
            for field_name, _ in self._TOKEN_FIELDS:
                totals[field_name] += int(getattr(breakdown, field_name))
        return totals
