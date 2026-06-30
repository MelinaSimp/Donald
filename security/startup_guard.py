"""1.5 - Startup guard against dev-mode + public-bind.

Threat T4 (public-surface attack): the classic pre-production foot-shoot is
flipping ``dev_mode=True`` for an afternoon (enabling debug endpoints, verbose
errors, auth bypasses) and forgetting to flip it back before a deploy that
binds to a public interface. ``assert_safe_startup()`` refuses to boot in
exactly that combination.

Call it once, early in your server-startup function::

    from security.startup_guard import assert_safe_startup
    assert_safe_startup(dev_mode=settings.dev_mode, bind_host=settings.host)
"""

from __future__ import annotations

# Hosts considered loopback-only (safe to pair with dev_mode).
_LOCAL_HOSTS = frozenset(
    {
        "127.0.0.1",
        "localhost",
        "::1",
        "::ffff:127.0.0.1",
        "0:0:0:0:0:0:0:1",
    }
)


class StartupSecurityError(RuntimeError):
    """Raised when the process would start in a known-dangerous config."""


def is_local_bind(bind_host: str) -> bool:
    """True if ``bind_host`` only accepts loopback connections."""
    return (bind_host or "").strip().lower() in _LOCAL_HOSTS


def assert_safe_startup(dev_mode: bool, bind_host: str) -> None:
    """Raise ``StartupSecurityError`` if ``dev_mode`` is on AND the bind is public.

    A public bind is anything that is not loopback (``0.0.0.0``, ``::``, a LAN
    IP, a concrete public IP). All other combinations are allowed.
    """
    if dev_mode and not is_local_bind(bind_host):
        raise StartupSecurityError(
            f"Refusing to start with dev_mode=True AND public bind ({bind_host!r}). "
            "Either flip dev_mode=False or rebind to localhost (127.0.0.1). "
            "Debug endpoints would otherwise be reachable from the public surface."
        )
