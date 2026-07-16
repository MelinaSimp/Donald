"""The cheap planning loop.

The agent plans with a Sonnet-class model (the Anthropic SDK), and delegates the
expensive composition to Claude Code via the ``generate_mockup`` tool. The
Anthropic SDK is imported lazily so the package imports without it.

``dispatch_tool_call`` — the routing from a tool_use block to the right execute
branch — is a pure function with no SDK dependency, so the wiring is unit tested
without a network or an API key.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config, prompts, tools


@dataclass
class ToolEvent:
    name: str
    input: dict
    output: dict | str


def dispatch_tool_call(
    name: str,
    tool_input: dict,
    slug: str,
    *,
    settings: config.Settings | None = None,
    on_event=None,
) -> dict:
    """Route a single tool_use to its execute branch. Returns a JSON-able dict.

    Errors are returned as ``{"ok": False, "error": ...}`` (not raised) so the
    agent loop can hand them back to the model to recover from.
    """
    try:
        if name == "generate_image":
            return tools.execute_generate_image(
                slug,
                tool_input["feature_slug"],
                tool_input["name"],
                tool_input["prompt"],
                quality=tool_input.get("quality", "standard"),
                aspect_ratio=tool_input.get("aspect_ratio", "16:9"),
            )
        if name == "generate_mockup":
            res = tools.execute_generate_mockup(
                slug,
                tool_input["feature_slug"],
                tool_input["screen_name"],
                tool_input["description"],
                visual_direction=tool_input.get("visual_direction", ""),
                quality=tool_input.get("quality", "standard"),
                reference_images=tool_input.get("reference_images"),
                components_hint=tool_input.get("components_hint"),
                settings=settings,
                on_event=on_event,
            )
            return {
                "ok": res.ok,
                "view_url": res.view_url,
                "page_path": res.page_path,
                "first_dispatch": res.first_dispatch,
                "error": res.error,
            }
        return {"ok": False, "error": f"unknown tool '{name}'"}
    except Exception as exc:  # noqa: BLE001 - feed the error back to the model
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@dataclass
class DispatchResult:
    final_text: str = ""
    tool_events: list[ToolEvent] = field(default_factory=list)
    stop_reason: str = ""


def run_design_task(
    slug: str,
    task: str,
    *,
    settings: config.Settings | None = None,
    max_iterations: int = 12,
    on_event=None,
    _client=None,  # injectable for tests
) -> DispatchResult:
    """Run the planning loop for one design task.

    Requires the Anthropic SDK and ANTHROPIC_API_KEY unless ``_client`` is
    injected. Returns the model's final text plus the tools it invoked.
    """
    settings = settings or config.Settings.from_env()
    client = _client if _client is not None else _make_client()

    system = prompts.system_prompt()
    messages = [{"role": "user", "content": f"Project slug: {slug}\n\nTask: {task}"}]
    result = DispatchResult()

    for _ in range(max_iterations):
        resp = client.messages.create(
            model=settings.planning_model,
            max_tokens=4096,
            system=system,
            tools=tools.ALL_TOOLS,
            messages=messages,
        )
        result.stop_reason = getattr(resp, "stop_reason", "") or ""
        content = list(getattr(resp, "content", []) or [])
        messages.append({"role": "assistant", "content": content})

        tool_results = []
        for block in content:
            btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if btype == "text":
                result.final_text = getattr(block, "text", "") or (block.get("text", "") if isinstance(block, dict) else "")
            elif btype == "tool_use":
                bname = getattr(block, "name", None) or block.get("name")
                binput = getattr(block, "input", None) or block.get("input", {})
                buid = getattr(block, "id", None) or block.get("id")
                out = dispatch_tool_call(bname, binput, slug, settings=settings, on_event=on_event)
                result.tool_events.append(ToolEvent(bname, binput, out))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": buid,
                    "content": _json(out),
                })

        if not tool_results:
            break  # model is done (no more tool calls)
        messages.append({"role": "user", "content": tool_results})

    return result


def _json(obj) -> str:
    import json
    return json.dumps(obj)


def _make_client():
    key = config.anthropic_api_key()
    if not key:
        raise config.MissingDependency(
            message="ANTHROPIC_API_KEY is not set; cannot run the planning loop."
        )
    try:
        import anthropic  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise config.MissingDependency(
            message="anthropic is not installed. `pip install anthropic`."
        ) from exc
    return anthropic.Anthropic(api_key=key)
