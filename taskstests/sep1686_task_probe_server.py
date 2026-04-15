from __future__ import annotations

import json
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


JSONRPC_VERSION = "2.0"
DEFAULT_PROTOCOL_VERSION = "2025-03-26"
DEFAULT_TTL_MS = 60_000
DEFAULT_POLL_INTERVAL_MS = 1_000
TASK_RELATED_META_KEY = "io.modelcontextprotocol/related-task"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _stderr_log(message: str) -> None:
    sys.stderr.write(f"[tasks-probe] {message}\n")
    sys.stderr.flush()


@dataclass
class TaskRecord:
    task_id: str
    tool_name: str
    arguments: dict[str, Any]
    ttl_ms: int
    poll_interval_ms: int
    status: str = "working"
    status_message: str | None = "Queued"
    created_at: str = field(default_factory=_utc_now_iso)
    last_updated_at: str = field(default_factory=_utc_now_iso)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cv: threading.Condition = field(default_factory=threading.Condition)

    def task_view(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "taskId": self.task_id,
            "status": self.status,
            "createdAt": self.created_at,
            "lastUpdatedAt": self.last_updated_at,
            "ttl": self.ttl_ms,
            "pollInterval": self.poll_interval_ms,
        }
        if self.status_message:
            payload["statusMessage"] = self.status_message
        return payload

    def mark(self, *, status: str, status_message: str | None = None) -> None:
        with self.cv:
            self.status = status
            self.status_message = status_message
            self.last_updated_at = _utc_now_iso()
            self.cv.notify_all()

    def wait_terminal(self) -> None:
        with self.cv:
            while self.status not in {"completed", "failed", "cancelled"}:
                self.cv.wait(timeout=0.25)


class TaskProbeServer:
    def __init__(self) -> None:
        self._client_capabilities: dict[str, Any] = {}
        self._tasks: dict[str, TaskRecord] = {}
        self._tasks_lock = threading.Lock()
        self._stdout_lock = threading.Lock()
        self._running = True

    def run(self) -> None:
        while self._running:
            message = self._read_message()
            if message is None:
                return
            try:
                self._handle_message(message)
            except Exception:  # noqa: BLE001
                _stderr_log("unhandled exception in message handler")
                _stderr_log(traceback.format_exc())

    def _read_message(self) -> dict[str, Any] | None:
        content_length = None
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("utf-8", errors="replace").strip()
            if ":" not in text:
                continue
            key, value = text.split(":", 1)
            if key.lower().strip() == "content-length":
                content_length = _safe_int(value.strip(), -1)
        if content_length is None or content_length < 0:
            return None
        body = sys.stdin.buffer.read(content_length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def _write_message(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        with self._stdout_lock:
            sys.stdout.buffer.write(header)
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()

    def _write_response(self, request_id: Any, result: dict[str, Any] | list[Any] | str | int | float | None) -> None:
        self._write_message({"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result})

    def _write_error(self, request_id: Any, code: int, message: str, data: Any | None = None) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._write_message({"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error})

    def _notify_task_status(self, task: TaskRecord) -> None:
        self._write_message(
            {
                "jsonrpc": JSONRPC_VERSION,
                "method": "notifications/tasks/status",
                "params": {
                    "task": task.task_view(),
                },
            }
        )

    def _handle_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            self._handle_initialize(request_id, params)
            return
        if method == "notifications/initialized":
            _stderr_log("received notifications/initialized")
            return
        if method == "notifications/cancelled":
            _stderr_log("received notifications/cancelled")
            return
        if method == "tools/list":
            self._write_response(request_id, {"tools": self._tools_list()})
            return
        if method == "tools/call":
            self._handle_tools_call(request_id, params)
            return
        if method == "tasks/get":
            self._handle_tasks_get(request_id, params)
            return
        if method == "tasks/result":
            self._handle_tasks_result(request_id, params)
            return
        if method == "tasks/list":
            self._handle_tasks_list(request_id)
            return
        if method == "tasks/cancel":
            self._handle_tasks_cancel(request_id, params)
            return

        # Unknown methods should still be JSON-RPC compliant.
        if request_id is not None:
            self._write_error(request_id, -32601, f"method not found: {method}")

    def _handle_initialize(self, request_id: Any, params: dict[str, Any]) -> None:
        self._client_capabilities = params.get("capabilities") or {}
        _stderr_log(f"initialize client capabilities: {json.dumps(self._client_capabilities, ensure_ascii=True)}")

        protocol_version = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
        result = {
            "protocolVersion": protocol_version,
            "serverInfo": {
                "name": "sep1686-task-probe",
                "version": "0.1.0",
            },
            "capabilities": {
                "tools": {},
                "tasks": {
                    "list": {},
                    "cancel": {},
                    "requests": {
                        "tools": {
                            "call": {},
                        }
                    },
                },
            },
            "instructions": (
                "Task probe server for SEP-1686 testing. "
                "Use `task_echo_required` with task augmentation to create background tasks."
            ),
        }
        self._write_response(request_id, result)

    def _tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "task_echo_required",
                "description": (
                    "Requires SEP-1686 task-augmented tools/call. "
                    "Returns a task handle and completes asynchronously."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "delay_seconds": {"type": "number"},
                    },
                    "required": ["message"],
                    "additionalProperties": False,
                },
                "execution": {
                    "taskSupport": "required",
                },
            },
            {
                "name": "task_probe_capabilities",
                "description": "Returns initialize-time client capabilities observed by this server.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "execution": {
                    "taskSupport": "forbidden",
                },
            },
        ]

    def _handle_tools_call(self, request_id: Any, params: dict[str, Any]) -> None:
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        task_request = params.get("task")

        _stderr_log(
            "tools/call "
            + json.dumps(
                {
                    "name": tool_name,
                    "has_task_field": task_request is not None,
                    "task_field": task_request,
                },
                ensure_ascii=True,
            )
        )

        if tool_name == "task_probe_capabilities":
            payload = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "server_observed_client_capabilities": self._client_capabilities,
                                "note": "If `capabilities.tasks` is missing, the client is not negotiating SEP-1686 tasks.",
                            },
                            indent=2,
                        ),
                    }
                ],
            }
            self._write_response(request_id, payload)
            return

        if tool_name != "task_echo_required":
            self._write_error(request_id, -32602, f"unknown tool `{tool_name}`")
            return

        if task_request is None:
            self._write_error(
                request_id,
                -32602,
                "task_echo_required needs task augmentation (`params.task`) per SEP-1686.",
            )
            return

        ttl = _safe_int(task_request.get("ttl"), DEFAULT_TTL_MS)
        poll_interval = DEFAULT_POLL_INTERVAL_MS
        task_id = str(uuid.uuid4())

        task = TaskRecord(
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            ttl_ms=max(1_000, ttl),
            poll_interval_ms=poll_interval,
            status_message="Task created and queued",
        )
        with self._tasks_lock:
            self._tasks[task_id] = task

        worker = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
        worker.start()

        self._write_response(request_id, {"task": task.task_view()})

    def _execute_task(self, task: TaskRecord) -> None:
        try:
            delay_seconds = float(task.arguments.get("delay_seconds", 3))
            if delay_seconds < 0:
                delay_seconds = 0
        except (TypeError, ValueError):
            delay_seconds = 3.0

        task.mark(status="working", status_message=f"Sleeping for {delay_seconds:.2f}s")
        self._notify_task_status(task)

        time.sleep(delay_seconds)

        if task.status == "cancelled":
            return

        message = str(task.arguments.get("message", ""))
        task.result = {
            "content": [
                {
                    "type": "text",
                    "text": f"task completed: {message}",
                }
            ]
        }
        task.mark(status="completed", status_message="Completed successfully")
        self._notify_task_status(task)

    def _get_task(self, task_id: Any) -> TaskRecord | None:
        if not isinstance(task_id, str) or not task_id:
            return None
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def _handle_tasks_get(self, request_id: Any, params: dict[str, Any]) -> None:
        task = self._get_task(params.get("taskId"))
        if task is None:
            self._write_error(request_id, -32602, "unknown taskId")
            return
        self._write_response(request_id, {"task": task.task_view()})

    def _handle_tasks_result(self, request_id: Any, params: dict[str, Any]) -> None:
        task = self._get_task(params.get("taskId"))
        if task is None:
            self._write_error(request_id, -32602, "unknown taskId")
            return

        task.wait_terminal()

        if task.status == "cancelled":
            self._write_error(
                request_id,
                -32800,
                "task was cancelled",
                {
                    "_meta": {
                        TASK_RELATED_META_KEY: {"taskId": task.task_id},
                    }
                },
            )
            return
        if task.status == "failed":
            err = task.error or {"code": -32001, "message": "task failed"}
            self._write_error(
                request_id,
                int(err.get("code", -32001)),
                str(err.get("message", "task failed")),
                {
                    "_meta": {
                        TASK_RELATED_META_KEY: {"taskId": task.task_id},
                    }
                },
            )
            return

        result = task.result or {"content": [{"type": "text", "text": "task completed with empty result"}]}
        if isinstance(result, dict):
            meta = result.get("_meta")
            if not isinstance(meta, dict):
                meta = {}
                result["_meta"] = meta
            meta[TASK_RELATED_META_KEY] = {"taskId": task.task_id}
        self._write_response(request_id, result)

    def _handle_tasks_list(self, request_id: Any) -> None:
        with self._tasks_lock:
            tasks = [task.task_view() for task in self._tasks.values()]
        tasks.sort(key=lambda item: item["createdAt"])
        self._write_response(request_id, {"tasks": tasks, "nextCursor": None})

    def _handle_tasks_cancel(self, request_id: Any, params: dict[str, Any]) -> None:
        task = self._get_task(params.get("taskId"))
        if task is None:
            self._write_error(request_id, -32602, "unknown taskId")
            return
        if task.status in {"completed", "failed", "cancelled"}:
            self._write_response(request_id, {"task": task.task_view()})
            return
        task.mark(status="cancelled", status_message="Cancelled by requestor")
        self._notify_task_status(task)
        self._write_response(request_id, {"task": task.task_view()})


def main() -> None:
    server = TaskProbeServer()
    server.run()


if __name__ == "__main__":
    main()
