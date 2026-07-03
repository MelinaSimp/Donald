"""Connector that drives Hermes through its **one-shot CLI**, via ``docker exec``.

Some Hermes deployments don't expose an OpenAI-compatible HTTP API. What they
*do* have is the headless one-shot mode::

    hermes -z "<task>" --yolo

which runs the full agent (all its tools, on the local model) to completion and
prints the final answer to stdout. When Hermes runs inside a Docker container,
we reach it with::

    docker exec <container> /opt/hermes/.venv/bin/hermes -z "<task>" --yolo

This connector shells out to that command, captures stdout, and returns it — so
the Donald gateway (running on the same host, with Docker access) can delegate
to Hermes without needing Hermes' JSON-RPC/WebSocket protocol.

The subprocess runner is injectable so tests never touch a real Docker/Hermes.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Awaitable, Callable, List, Optional

from .base import ConnectorResult

# A runner takes an argv list and returns (returncode, stdout, stderr).
Runner = Callable[[List[str], float], Awaitable["tuple[int, str, str]"]]
# An observer called with each stdout line as Hermes prints it.
OnLine = Callable[[str], None]
# A streaming runner additionally feeds stdout lines to the observer live.
StreamRunner = Callable[[List[str], float, OnLine], Awaitable["tuple[int, str, str]"]]


class HermesCliConnector:
    """Delegate tasks to a Hermes agent by invoking its one-shot CLI."""

    name = "hermes"
    # The orchestrator checks this before passing an ``on_line`` observer.
    supports_streaming = True

    def __init__(
        self,
        container: Optional[str] = None,
        cli_path: str = "/opt/hermes/.venv/bin/hermes",
        extra_args: Optional[List[str]] = None,
        model: Optional[str] = None,
        timeout_s: float = 600.0,
        docker_bin: str = "docker",
        runner: Optional[Runner] = None,
        stream_runner: Optional[StreamRunner] = None,
    ) -> None:
        # container=None means "run the CLI directly on this host" (Hermes not
        # containerised); otherwise we go through `docker exec <container>`.
        self.container = container
        self.cli_path = cli_path
        # --yolo auto-approves tool actions so a one-shot run never blocks on a
        # confirmation prompt (Donald's own confirm_cb is the human gate).
        self.extra_args = list(extra_args) if extra_args is not None else ["--yolo"]
        self.model = model
        self.timeout_s = timeout_s
        self.docker_bin = docker_bin
        self._runner = runner or _subprocess_runner
        # A custom plain runner (tests) without a matching stream runner falls
        # back to replaying its buffered output line-by-line after the fact.
        self._stream_runner = stream_runner or (
            _streaming_subprocess_runner if runner is None else None
        )

    # -- command construction ----------------------------------------------
    def _base_argv(self) -> List[str]:
        """The argv prefix that lands us at the `hermes` executable."""
        if self.container:
            return [self.docker_bin, "exec", self.container, self.cli_path]
        return [self.cli_path]

    def _task_argv(self, prompt: str) -> List[str]:
        argv = self._base_argv() + ["-z", prompt]
        if self.model:
            argv += ["-m", self.model]
        argv += self.extra_args
        return argv

    # -- AgentConnector -----------------------------------------------------
    async def health(self) -> bool:
        """True if the Hermes CLI is reachable (responds to ``--version``)."""
        argv = self._base_argv() + ["--version"]
        try:
            code, _out, _err = await self._runner(argv, 30.0)
            return code == 0
        except Exception:
            return False

    async def execute(
        self,
        task: str,
        *,
        context: Optional[str] = None,
        on_line: Optional[OnLine] = None,
    ) -> ConnectorResult:
        """Run one task through Hermes' one-shot CLI and return its answer.

        ``on_line`` (optional) is called with each stdout line as Hermes
        prints it, so a UI can show live agent activity while the run is
        still going. The final result is unchanged either way.
        """
        task = (task or "").strip()
        if not task:
            return ConnectorResult(
                ok=False, text="", connector=self.name, error="empty task"
            )

        prompt = f"{context.strip()}\n\n{task}" if context else task
        argv = self._task_argv(prompt)

        try:
            if on_line is not None:
                code, out, err = await self._run_streaming(argv, on_line)
            else:
                code, out, err = await self._runner(argv, self.timeout_s)
        except asyncio.TimeoutError:
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error=(
                    f"Hermes timed out after {self.timeout_s:.0f}s "
                    f"(local model may still be loading — try again, or raise "
                    f"HERMES_TIMEOUT_S)"
                ),
            )
        except FileNotFoundError as exc:
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error=f"could not launch Hermes CLI ({self.docker_bin}): {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ConnectorResult(
                ok=False, text="", connector=self.name, error=str(exc)
            )

        if code != 0:
            detail = (err or out or "").strip()[:400] or "no output"
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error=f"Hermes CLI exited {code}: {detail}",
            )

        text = (out or "").strip()
        if not text:
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error="Hermes returned no output",
            )
        return ConnectorResult(ok=True, text=text, connector=self.name)

    async def _run_streaming(self, argv: List[str], on_line: OnLine):
        """Run with live line streaming, falling back to buffered replay."""
        def safe(line: str) -> None:  # a broken observer never kills the run
            _safe_on_line(on_line, line)

        if self._stream_runner is not None:
            return await self._stream_runner(argv, self.timeout_s, safe)
        code, out, err = await self._runner(argv, self.timeout_s)
        for line in (out or "").splitlines():
            if line.strip():
                safe(line)
        return code, out, err

    async def aclose(self) -> None:
        # Nothing persistent to release; each task is its own subprocess.
        return None

    def command_preview(self) -> str:
        """Human-readable view of the command shape (for /health, logs)."""
        return " ".join(shlex.quote(a) for a in self._task_argv("<task>"))


def _safe_on_line(on_line: OnLine, line: str) -> None:
    """A broken observer must never take down the Hermes run itself."""
    try:
        on_line(line)
    except Exception:
        pass


async def _streaming_subprocess_runner(
    argv: List[str], timeout_s: float, on_line: OnLine
):
    """Spawn the process and feed stdout to ``on_line`` line-by-line, live."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_parts: List[str] = []

    async def _drain() -> bytes:
        assert proc.stdout is not None and proc.stderr is not None
        while True:
            line_b = await proc.stdout.readline()
            if not line_b:
                break
            line = line_b.decode("utf-8", "replace")
            out_parts.append(line)
            stripped = line.rstrip("\r\n")
            if stripped.strip():
                on_line(stripped)  # already safety-wrapped by _run_streaming
        err_b = await proc.stderr.read()
        await proc.wait()
        return err_b

    try:
        err_b = await asyncio.wait_for(_drain(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # pragma: no cover - race on exit
            pass
        raise
    return (
        proc.returncode or 0,
        "".join(out_parts),
        err_b.decode("utf-8", "replace"),
    )


async def _subprocess_runner(argv: List[str], timeout_s: float):
    """Default runner: spawn the process, capture output, enforce a timeout."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # pragma: no cover - race on exit
            pass
        raise
    return (
        proc.returncode or 0,
        out_b.decode("utf-8", "replace"),
        err_b.decode("utf-8", "replace"),
    )
