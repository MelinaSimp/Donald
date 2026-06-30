"""Tier 6 ship test: a composed page is audited against the REQUIRED visual
elements (install != use). A rich page passes; an empty one fails with reasons.

We can't run a live Claude Code build deterministically, so the ship test drives
the audit (the same gate wired into generate_mockup) against a representative
"good" page and a "generic SaaS" page, and asserts the enforcement language is
present in the prompts."""

from __future__ import annotations

from prism import audit, bootstrap, prompts, tools
from prism import claude_code_runner as ccr


GOOD_PAGE = '''"use client";
import { Particles } from "@/components/ui/particles";
import { GridPattern } from "@/components/ui/grid-pattern";
import { BorderBeam } from "@/components/ui/border-beam";
import { NumberTicker } from "@/components/ui/number-ticker";
import { motion } from "framer-motion";

function VoiceWaveform() {
  // inline product surface: an oscillating voice waveform with a blinking caret
  return <div className="animate-pulse">waveform transcript with typing caret</div>;
}

export default function Hero() {
  return (
    <main>
      <GridPattern className="opacity-50" />
      <Particles className="opacity-40 animate-in" />
      <h1 className="font-display text-[120px]">Listen</h1>
      <span className="font-mono uppercase text-sm">LISTENING · 287ms</span>
      <span className="font-mono uppercase text-sm">LATENCY</span>
      <span className="font-mono uppercase text-sm">v2.1.0</span>
      <VoiceWaveform />
      <NumberTicker value={287} />
      <button className="hover:border relative">
        Start <BorderBeam />
      </button>
      <a className="hover:opacity-80">docs</a>
      <a className="group-hover:text-foreground">api</a>
    </main>
  );
}
'''

GENERIC_SAAS_PAGE = '''export default function Hero() {
  return (
    <main className="flex flex-col items-center justify-center">
      <h1 className="text-4xl font-bold">Welcome to our SaaS</h1>
      <p className="text-gray-400">The best platform for teams.</p>
      <button className="bg-blue-600 px-4 py-2 rounded">Get started</button>
    </main>
  );
}
'''


def test_audit_passes_rich_page():
    report = audit.audit_page_tsx(GOOD_PAGE)
    assert report.passed, report.failures
    assert report.has_ambient_background
    assert report.has_product_surface
    assert report.has_continuous_motion
    assert report.mono_uppercase_count >= 3
    assert report.hover_count >= 3
    assert report.has_beam_or_hover_emphasis


def test_audit_fails_generic_saas_page_with_reasons():
    report = audit.audit_page_tsx(GENERIC_SAAS_PAGE)
    assert not report.passed
    joined = " ".join(report.failures)
    assert "ambient background" in joined
    assert "product surface" in joined
    assert "continuous motion" in joined
    assert "marginalia" in joined


def test_generate_mockup_attaches_audit(project):
    slug, root = project
    bootstrap.bootstrap_project(slug)

    def fake_spawn(prompt, cwd, model, max_turns, allowed_tools, on_event=None):
        page = root / ".prism/preview/app/voice/hero/page.tsx"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(GOOD_PAGE)
        out = root / ".prism/preview/out/voice/hero/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<html></html>")
        return ccr.ClaudeCodeResult(ok=True, returncode=0)

    res = tools.execute_generate_mockup(
        slug, "voice", "hero", "Design the hero.", _spawn=fake_spawn,
    )
    assert res.ok
    assert res.audit_passed is True
    assert res.audit_warnings == []


def test_brief_wins_language_is_explicit():
    sp = prompts.system_prompt()
    assert "the brief wins" in sp
    assert "Never silently override" in sp or "never silently" in sp.lower()
