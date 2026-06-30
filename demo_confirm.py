"""Demo + verification for Tier 4 (confirmation gates).

  python demo_confirm.py   # no API key needed

Proves the gate lives in the router, not the tool:
  * a confirmation-gated tool, called with the fail-safe default, returns a
    confirmation_required payload and does NOT perform the action;
  * after explicit approval, the execute-confirmed path runs it exactly once;
  * an ungated tool runs without ever prompting.
"""

from __future__ import annotations

import json

from orchestrator import (
    Agent,
    AgentManifest,
    AllowAll,
    CallbackApprover,
    Tool,
    build_default_registry,
)

# A destructive, irreversible action — marked requires_confirmation. The tool
# itself contains NO gate logic; it just records that it ran.
SENT: list[dict] = []


def _send_email(inp):
    SENT.append(inp)
    return "email sent"


def _registry_with_email():
    reg = build_default_registry()
    reg.register(
        Tool(
            name="send_email",
            description="Send an email. Irreversible.",
            input_schema={
                "type": "object",
                "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "body"],
            },
            handler=_send_email,
            requires_confirmation=True,
        )
    )
    return reg


def main() -> None:
    payload = {"to": "vp@example.com", "body": "shipping now"}

    # 1. Default approver is DenyAll (fail-safe). The action must NOT happen.
    SENT.clear()
    blocked = Agent(
        AgentManifest(name="mailer", system_prompt="x", allowed_tools=["send_email", "calculator"]),
        _registry_with_email(),
    )
    res = blocked._execute_tool_call("send_email", payload, "tu_1")
    body = json.loads(res["content"])
    assert body.get("confirmation_required") and body["status"] == "not_executed", body
    assert SENT == [], SENT
    print(f"PASS: gated tool returned confirmation_required and did NOT run -> {body['reason']}")

    # 2. Explicit approval -> the execute-confirmed path runs it exactly once.
    SENT.clear()
    approved = Agent(
        AgentManifest(name="mailer", system_prompt="x", allowed_tools=["send_email", "calculator"]),
        _registry_with_email(),
        approver=AllowAll(),
    )
    res = approved._execute_tool_call("send_email", payload, "tu_2")
    assert not res["is_error"] and res["content"] == "email sent", res
    assert SENT == [payload], SENT
    print("PASS: after approval, the action executed exactly once.")

    # 3. The standalone execute-confirmed path (approve out-of-band, then run).
    SENT.clear()
    assert approved.execute_confirmed("send_email", payload) == "email sent"
    assert SENT == [payload], SENT
    print("PASS: execute_confirmed() ran the gated action exactly once.")

    # 4. An ungated tool is never prompted — DenyAll doesn't touch it.
    SENT.clear()
    res = blocked._execute_tool_call("calculator", {"expression": "2+2"}, "tu_3")
    assert res["content"] == "4" and not res["is_error"], res
    print("PASS: ungated tool ran normally (gate only applies to flagged tools).")

    # 5. The gate is in the ROUTER: a CallbackApprover that inspects the request
    #    can deny based on inputs — the tool stays oblivious.
    SENT.clear()
    picky = Agent(
        AgentManifest(name="mailer", system_prompt="x", allowed_tools=["send_email", "calculator"]),
        _registry_with_email(),
        approver=CallbackApprover(lambda req: "vp@" not in req.tool_input["to"]),
    )
    res = picky._execute_tool_call("send_email", payload, "tu_4")
    assert json.loads(res["content"]).get("confirmation_required"), res
    assert SENT == [], SENT
    print("PASS: policy approver denied based on inputs; tool stayed oblivious.")

    print("\nTier 4: nothing irreversible ran without an explicit human yes.")


if __name__ == "__main__":
    main()
