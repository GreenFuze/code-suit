from __future__ import annotations

import asyncio


async def _get_prompt(app, name: str):
    return await app.get_prompt(name)


async def _list_prompts(app):
    return await app.list_prompts()


def test_app_registers_expected_prompts(app) -> None:
    prompt_names = {prompt.name for prompt in asyncio.run(_list_prompts(app))}

    assert "understand_repository_with_suitcode" in prompt_names
    assert "refactor_using_suitcode_tools" in prompt_names
    assert "apply_quality_fix_with_suitcode" in prompt_names


def test_prompt_guides_tool_first_usage(app) -> None:
    prompt = asyncio.run(_get_prompt(app, "understand_repository_with_suitcode"))
    prompt_text = str(prompt.messages)

    assert "open_workspace" in prompt_text
    assert "repository_summary" in prompt_text
    assert "analyze_change" in prompt_text
    assert "broad list/find exploration" in prompt_text
