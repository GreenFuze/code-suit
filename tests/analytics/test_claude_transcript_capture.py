from __future__ import annotations

import json

from suitcode.analytics.claude_transcript_capture import ClaudeTranscriptCaptureBuilder


def test_builder_ignores_whitespace_only_text_blocks(tmp_path) -> None:
    artifact = tmp_path / "claude.jsonl"
    payload = {
        "sessionId": "session-1",
        "cwd": str(tmp_path),
        "timestamp": "2026-03-23T10:00:00Z",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "\n\n"},
                {"type": "text", "text": "real text"},
            ],
        },
    }
    artifact.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    capture = ClaudeTranscriptCaptureBuilder().build(artifact)

    assert len(capture.segments) == 1
    assert capture.segments[0].content_text == "real text"
