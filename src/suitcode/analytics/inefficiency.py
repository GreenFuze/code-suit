from __future__ import annotations

from collections import Counter, defaultdict

from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus, InefficiencyFinding


class InefficiencyDetector:
    def __init__(self, tool_catalog: tuple[str, ...], excluded_tools: tuple[str, ...] = ()) -> None:
        self._tool_catalog = tool_catalog
        self._excluded_tools = set(excluded_tools)
        self._high_value_tools = {
            "analyze_change",
            "describe_components",
            "describe_files",
            "describe_symbol_context",
            "describe_test_target",
            "describe_runner",
            "run_test_targets",
            "run_runner",
            "build_target",
            "build_project",
        }
        self._broad_tools = {
            "list_components",
            "list_files",
            "find_symbols",
            "list_symbols_in_file",
            "list_tests",
        }

    def detect(self, events: tuple[AnalyticsEvent, ...]) -> tuple[InefficiencyFinding, ...]:
        filtered = tuple(event for event in events if event.tool_name not in self._excluded_tools)
        grouped_by_session: dict[str, list[AnalyticsEvent]] = defaultdict(list)
        for event in filtered:
            grouped_by_session[event.session_id].append(event)

        findings: list[InefficiencyFinding] = []
        for session_id in sorted(grouped_by_session):
            session_events = tuple(grouped_by_session[session_id])
            findings.extend(self._duplicate_call_findings(session_events, session_id=session_id))
            findings.extend(self._pagination_thrash_findings(session_events, session_id=session_id))
            findings.extend(self._workspace_churn_findings(session_events, session_id=session_id))
            broad_finding = self._broad_exploration_finding(session_events, session_id=session_id)
            if broad_finding is not None:
                findings.append(broad_finding)
            findings.extend(self._unused_tool_findings(session_events, session_id=session_id))
        return tuple(findings)

    def _duplicate_call_findings(
        self,
        events: tuple[AnalyticsEvent, ...],
        *,
        session_id: str,
    ) -> list[InefficiencyFinding]:
        grouped: dict[tuple[str, str], list[AnalyticsEvent]] = defaultdict(list)
        for event in events:
            if event.status != AnalyticsStatus.SUCCESS:
                continue
            grouped[(event.tool_name, event.arguments_fingerprint_sha256)].append(event)

        findings: list[InefficiencyFinding] = []
        for (tool_name, _), group in grouped.items():
            if len(group) < 3:
                continue
            sample_ids = tuple(item.event_id for item in group[:5])
            findings.append(
                InefficiencyFinding(
                    kind="duplicate_call",
                    tool_name=tool_name,
                    session_id=session_id,
                    count=len(group),
                    description=f"`{tool_name}` was called repeatedly with identical arguments.",
                    sample_event_ids=sample_ids,
                )
            )
        return findings

    def _pagination_thrash_findings(
        self,
        events: tuple[AnalyticsEvent, ...],
        *,
        session_id: str,
    ) -> list[InefficiencyFinding]:
        grouped: dict[tuple[str, str], list[AnalyticsEvent]] = defaultdict(list)
        for event in events:
            if event.status != AnalyticsStatus.SUCCESS:
                continue
            args = event.arguments_redacted
            limit = args.get("limit")
            offset = args.get("offset")
            if not isinstance(limit, int) or not isinstance(offset, int):
                continue
            if limit > 50:
                continue
            workspace_id = str(args.get("workspace_id") or "")
            repository_id = str(args.get("repository_id") or "")
            grouped[(event.tool_name, f"{workspace_id}:{repository_id}")].append(event)

        findings: list[InefficiencyFinding] = []
        for (tool_name, _), calls in grouped.items():
            if len(calls) < 4:
                continue
            offsets = [int(item.arguments_redacted["offset"]) for item in calls]  # type: ignore[index]
            if offsets != sorted(offsets):
                continue
            sample_ids = tuple(item.event_id for item in calls[:5])
            findings.append(
                InefficiencyFinding(
                    kind="pagination_thrash",
                    tool_name=tool_name,
                    session_id=session_id,
                    count=len(calls),
                    description=f"`{tool_name}` shows repeated small-page pagination progression.",
                    sample_event_ids=sample_ids,
                )
            )
        return findings

    def _workspace_churn_findings(
        self,
        events: tuple[AnalyticsEvent, ...],
        *,
        session_id: str,
    ) -> list[InefficiencyFinding]:
        opens_by_path: dict[str, list[AnalyticsEvent]] = defaultdict(list)
        for event in events:
            if event.status != AnalyticsStatus.SUCCESS or event.tool_name != "open_workspace":
                continue
            repository_path = event.arguments_redacted.get("repository_path")
            if isinstance(repository_path, str) and repository_path.strip():
                key = repository_path.strip()
            elif event.repository_root:
                key = event.repository_root
            else:
                key = "<unknown>"
            opens_by_path[key].append(event)

        findings: list[InefficiencyFinding] = []
        for repository_path, group in sorted(opens_by_path.items(), key=lambda item: item[0]):
            if len(group) < 3:
                continue
            findings.append(
                InefficiencyFinding(
                    kind="workspace_churn",
                    tool_name="open_workspace",
                    session_id=session_id,
                    count=len(group),
                    description=(
                        f"`open_workspace` was called repeatedly for `{repository_path}` in the same session."
                    ),
                    sample_event_ids=tuple(item.event_id for item in group[:5]),
                )
            )
        return findings

    def _broad_exploration_finding(
        self,
        events: tuple[AnalyticsEvent, ...],
        *,
        session_id: str,
    ) -> InefficiencyFinding | None:
        if len(events) < 20:
            return None
        tool_counts = Counter(item.tool_name for item in events)
        broad_count = sum(tool_counts.get(tool, 0) for tool in self._broad_tools)
        exact_count = sum(tool_counts.get(tool, 0) for tool in self._high_value_tools)
        if broad_count < 12 or exact_count > 0:
            return None
        sample_event_ids = tuple(item.event_id for item in events[:5])
        return InefficiencyFinding(
            kind="broad_exploration",
            tool_name=None,
            session_id=session_id,
            count=broad_count,
            description="Session uses broad exploratory tools heavily without high-value deterministic tools.",
            sample_event_ids=sample_event_ids,
        )

    def _unused_tool_findings(
        self,
        events: tuple[AnalyticsEvent, ...],
        *,
        session_id: str,
    ) -> list[InefficiencyFinding]:
        if len(events) < 10:
            return []
        called = {event.tool_name for event in events}
        findings: list[InefficiencyFinding] = []
        for tool_name in sorted(self._high_value_tools):
            if tool_name not in self._tool_catalog or tool_name in self._excluded_tools:
                continue
            if tool_name in called:
                continue
            findings.append(
                InefficiencyFinding(
                    kind="unused_tool",
                    tool_name=tool_name,
                    session_id=session_id,
                    count=0,
                    description=f"High-value deterministic tool `{tool_name}` is unused.",
                    sample_event_ids=tuple(),
                )
            )
        return findings
