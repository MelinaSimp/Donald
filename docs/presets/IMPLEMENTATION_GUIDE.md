# Donald Presets — Implementation Guide

This document is for **developers** building the preset orchestration runtime.

---

## Architecture

Presets are **data-driven orchestrations** executed by the existing Donald orchestrator (Tier 1). No new agent spawning; presets use the router to compose existing agents/skills.

```
┌─────────────────────────────────────────────────────┐
│ Donald Core (Orchestrator + Scheduler)              │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │ Preset Runtime                              │   │
│  │  - Load YAML preset config                  │   │
│  │  - Expand into execution graph (DAG)        │   │
│  │  - Invoke stages in sequence or parallel    │   │
│  │  - Log cost/latency/outcome to audit log    │   │
│  └────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ Orchestrator Router ─────────────────────┐    │
│  │  - stage 1: email-triage                   │    │
│  │    → call skill Gmail/read_inbox           │    │
│  │    → call skill Gmail/summarize_threads    │    │
│  │  - stage 2: calendar-scan                  │    │
│  │    → call skill Google_Calendar/list_...   │    │
│  └────────────────────────────────────────────┘    │
│                                                     │
│  ┌─ Scheduler (cron-like) ───────────────────┐    │
│  │  - morning_ops: every weekday 07:00        │    │
│  │  - trading_monitor: every 300s market hrs  │    │
│  │  - deep_research: on-demand or weekly      │    │
│  └────────────────────────────────────────────┘    │
│                                                     │
└─────────────────────────────────────────────────────┘
                    │
        ┌───────────┴────────────────┐
        ▼                            ▼
   MCP Servers              Memory Layer
   (Gmail, Drive, etc.)     (Postgres + recall)
```

---

## Data Model

### Preset Config (YAML)

Lives in `configs/presets/<preset_id>.yaml`. Top-level structure:

```yaml
preset_id: morning-ops
name: "Morning Operations"
description: "..."
version: "1.0"

# Execution control
scheduler:
  enabled: bool
  frequency: daily | weekly | cron_expr
  at_time: "HH:MM"
  ...

execution_modes: [...]  # (optional; documents how to invoke)

# The orchestration: stages run in sequence
stages:
  - id: stage_id
    name: "Stage Name"
    description: "..."
    cost_estimate_usd: 0.05
    latency_p99_seconds: 30
    model: claude-opus-4-8
    requires_approval: bool
    skills:
      - Gmail/read_inbox
      - Gmail/summarize_threads
    output: description of what this stage produces
    fallback_model: claude-haiku-4-5  # (optional)
    only_if: condition  # (optional; skip stage if false)

  - id: next_stage
    ...

# Output specification
output:
  format: structured | markdown | ...
  channels:
    - type: text | voice | document
      target: stdout | twilio_sms | google_drive
      ...

# Guardrails & limits
guardrails:
  read_only: bool
  cost_daily_limit_usd: number
  quiet_hours: {start, end}
  ...

# Integration requirements
integrations_required: [...]
integrations_optional: [...]

# Metrics to track
metrics: [...]

# Example usage
example_output: |
  ...
```

### Preset Registry

A registry maps preset IDs to configs:

```python
# presets/registry.py
class PresetRegistry:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._presets = {}
        self.load_all()
    
    def load_all(self):
        """Load all .yaml files from config_dir."""
        for path in self.config_dir.glob("*.yaml"):
            preset = load_preset_yaml(path)
            self._presets[preset["preset_id"]] = preset
    
    def get(self, preset_id: str) -> dict:
        return self._presets.get(preset_id)
    
    def list(self) -> list[str]:
        return list(self._presets.keys())
```

---

## Runtime Execution

### 1. Preset Loader

Convert YAML into an execution graph (DAG):

```python
# presets/loader.py
from pydantic import BaseModel

class StageConfig(BaseModel):
    id: str
    name: str
    description: str
    cost_estimate_usd: float
    latency_p99_seconds: float
    model: str
    requires_approval: bool = False
    skills: list[str]
    output: str
    fallback_model: Optional[str] = None
    only_if: Optional[str] = None
    parallelism: Optional[int] = None  # for fan-out stages

class PresetConfig(BaseModel):
    preset_id: str
    name: str
    description: str
    version: str
    stages: list[StageConfig]
    scheduler: Optional[dict]
    output: dict
    guardrails: dict
    integrations_required: list[str]
    integrations_optional: list[str]
    metrics: list[str]

def load_preset_yaml(path: Path) -> PresetConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return PresetConfig(**data)

def expand_to_execution_graph(preset: PresetConfig) -> ExecutionGraph:
    """Convert stages list into a DAG of orchestrator calls."""
    dag = ExecutionGraph()
    for stage in preset.stages:
        node = StageNode(
            id=stage.id,
            skills=stage.skills,
            model=stage.model,
            requires_approval=stage.requires_approval,
            fallback_model=stage.fallback_model,
            parallelism=stage.parallelism,
        )
        dag.add_node(node)
        if dag.nodes:  # add edge from prior stage
            dag.add_edge(dag.nodes[-2].id, node.id)
    return dag
```

### 2. Preset Executor

Run a preset end-to-end:

```python
# presets/executor.py
class PresetExecutor:
    def __init__(
        self,
        orchestrator: Orchestrator,
        registry: PresetRegistry,
        scheduler: Scheduler,
        audit_log: AuditLog,
    ):
        self.orchestrator = orchestrator
        self.registry = registry
        self.scheduler = scheduler
        self.audit_log = audit_log
    
    def run_preset(
        self,
        preset_id: str,
        inputs: dict = None,
        dry_run: bool = False,
    ) -> PresetResult:
        """Execute a preset and return structured result."""
        preset = self.registry.get(preset_id)
        if not preset:
            raise ValueError(f"Preset not found: {preset_id}")
        
        # Check integrations
        self._verify_integrations(preset)
        
        # Expand to DAG and execute
        dag = expand_to_execution_graph(preset)
        result = PresetResult(preset_id=preset_id, stages={})
        
        start_time = time.time()
        start_tokens = self.orchestrator.llm_client.usage().output_tokens
        
        for stage in dag.nodes:
            stage_result = self._execute_stage(
                stage, preset, inputs, dry_run
            )
            
            if stage_result.error and not stage_result.fallback_applied:
                # Hard failure
                result.error = stage_result.error
                self.audit_log.log_preset_failure(preset_id, stage.id, stage_result.error)
                break
            
            result.stages[stage.id] = stage_result
            inputs = stage_result.output  # feed output to next stage
        
        end_time = time.time()
        end_tokens = self.orchestrator.llm_client.usage().output_tokens
        
        # Log metrics
        result.duration_seconds = end_time - start_time
        result.cost_usd = self._estimate_cost(end_tokens - start_tokens)
        result.dry_run = dry_run
        
        self.audit_log.log_preset_run(result)
        
        return result
    
    def _execute_stage(
        self,
        stage: StageNode,
        preset: PresetConfig,
        inputs: dict,
        dry_run: bool,
    ) -> StageResult:
        """Execute a single stage (one or more skill calls)."""
        skills_to_call = [
            self._build_skill_call(skill, inputs)
            for skill in stage.skills
        ]
        
        try:
            if stage.parallelism and stage.parallelism > 1:
                # Parallel execution (fan-out)
                results = asyncio.run(
                    self._execute_parallel(skills_to_call, stage.parallelism)
                )
            else:
                # Sequential execution
                results = [
                    self.orchestrator.call_skill(call, dry_run=dry_run)
                    for call in skills_to_call
                ]
            
            # Merge results
            merged = self._merge_skill_results(results)
            
            return StageResult(
                stage_id=stage.id,
                status="success",
                output=merged,
                cost_usd=sum(r.cost_usd for r in results),
                duration_seconds=sum(r.duration_seconds for r in results),
            )
        except Exception as e:
            # Try fallback model
            if stage.fallback_model:
                return self._execute_stage_with_fallback(
                    stage, preset, inputs, dry_run, e
                )
            return StageResult(
                stage_id=stage.id,
                status="failed",
                error=str(e),
            )
    
    def _verify_integrations(self, preset: PresetConfig):
        """Ensure all required integrations are connected."""
        for required in preset.integrations_required:
            if not self.orchestrator.is_integration_ready(required):
                raise ValueError(
                    f"Integration not connected: {required}. "
                    f"Run: donald mcp connect {required.lower()}"
                )
    
    def _estimate_cost(self, tokens: int) -> float:
        """Estimate cost from token usage."""
        # Use pricing tiers from Claude
        return tokens * 0.0001  # rough estimate; tune per model
```

### 3. Scheduling Integration

Wire presets into the scheduler:

```python
# presets/scheduler.py
class PresetScheduler:
    """Integrates preset execution with the main scheduler."""
    
    def __init__(self, executor: PresetExecutor, scheduler: Scheduler):
        self.executor = executor
        self.scheduler = scheduler
        self.preset_jobs = {}
    
    def register_preset(self, preset_id: str, preset: PresetConfig):
        """Register a preset for scheduling."""
        if not preset.get("scheduler", {}).get("enabled"):
            return
        
        sched_config = preset["scheduler"]
        frequency = sched_config.get("frequency")
        
        if frequency == "daily":
            at_time = sched_config.get("at_time")
            job = self.scheduler.every().day.at(at_time).do(
                self.executor.run_preset,
                preset_id=preset_id,
            )
        elif frequency == "weekly":
            day = sched_config.get("at_day", "monday")
            at_time = sched_config.get("at_time")
            job = self.scheduler.every().weeks.at(day, at_time).do(
                self.executor.run_preset,
                preset_id=preset_id,
            )
        elif frequency == "market_hours":
            # Custom: every N seconds during market hours
            interval = sched_config.get("interval_seconds", 300)
            job = self.scheduler.every(interval).seconds.do(
                self._run_if_market_hours,
                preset_id=preset_id,
            )
        else:
            # Cron expression
            job = self.scheduler.every().do(
                self.executor.run_preset,
                preset_id=preset_id,
            )
        
        self.preset_jobs[preset_id] = job
    
    def unregister_preset(self, preset_id: str):
        if preset_id in self.preset_jobs:
            self.scheduler.cancel_job(self.preset_jobs[preset_id])
            del self.preset_jobs[preset_id]
    
    def _run_if_market_hours(self, preset_id: str):
        """Helper: only run during market hours."""
        if is_market_hours():
            self.executor.run_preset(preset_id)
```

### 4. CLI Integration

Expose presets via `donald` CLI:

```python
# cli.py (add these commands)
@click.group()
def presets():
    """Manage and run presets."""
    pass

@presets.command()
def list():
    """List available presets."""
    registry = PresetRegistry(Path("configs/presets"))
    for preset_id in registry.list():
        preset = registry.get(preset_id)
        click.echo(f"✓ {preset['name']}")
        click.echo(f"  {preset['description'][:60]}...")

@presets.command()
@click.argument("preset_id")
@click.option("--dry-run", is_flag=True)
@click.option("--inputs", type=str, help="JSON dict of inputs")
def run(preset_id, dry_run, inputs):
    """Run a preset."""
    executor = get_preset_executor()
    inputs = json.loads(inputs or "{}")
    result = executor.run_preset(preset_id, inputs, dry_run)
    
    # Display result
    click.echo(f"✓ {preset_id} completed")
    click.echo(f"  Duration: {result.duration_seconds:.1f}s")
    click.echo(f"  Cost: ${result.cost_usd:.2f}")
    for stage_id, stage_result in result.stages.items():
        click.echo(f"  {stage_id}: {stage_result.status}")

@presets.command()
@click.argument("preset_id")
@click.option("--stage", type=str, help="Run only this stage")
@click.option("--dry-run", is_flag=True)
def test(preset_id, stage, dry_run):
    """Test a preset or stage."""
    # Similar to run, but with more verbose output
    pass

@presets.command()
@click.argument("preset_id")
def enable(preset_id):
    """Enable and schedule a preset."""
    registry = PresetRegistry(Path("configs/presets"))
    preset = registry.get(preset_id)
    scheduler = get_preset_scheduler()
    scheduler.register_preset(preset_id, preset)
    click.echo(f"✓ {preset_id} scheduled")

@presets.command()
@click.argument("preset_id")
def disable(preset_id):
    """Disable scheduling for a preset."""
    scheduler = get_preset_scheduler()
    scheduler.unregister_preset(preset_id)
    click.echo(f"✗ {preset_id} unscheduled")

@presets.command()
@click.argument("preset_id")
@click.option("--period", type=str, default="week")
def metrics(preset_id, period):
    """Show metrics for a preset."""
    audit_log = get_audit_log()
    metrics = audit_log.get_preset_metrics(preset_id, period)
    
    click.echo(f"Metrics for {preset_id} ({period}):")
    click.echo(f"  Runs: {metrics['count']}")
    click.echo(f"  Avg duration: {metrics['avg_duration_s']:.1f}s")
    click.echo(f"  Avg cost: ${metrics['avg_cost_usd']:.2f}")
    click.echo(f"  Total cost: ${metrics['total_cost_usd']:.2f}")
    if metrics.get('avg_quality_score'):
        click.echo(f"  Avg quality: {metrics['avg_quality_score']:.2f}/10")
```

### 5. Audit Logging

Log every preset execution:

```python
# audit.py (enhance existing)
class AuditLog:
    def log_preset_run(self, result: PresetResult):
        """Record a preset execution."""
        self.db.insert(
            "audit.preset_runs",
            {
                "preset_id": result.preset_id,
                "started_at": result.started_at,
                "duration_seconds": result.duration_seconds,
                "cost_usd": result.cost_usd,
                "dry_run": result.dry_run,
                "status": "success" if not result.error else "failed",
                "stages": json.dumps(result.stages),
                "error": result.error,
            }
        )
    
    def get_preset_metrics(self, preset_id: str, period: str) -> dict:
        """Retrieve aggregated metrics for a preset."""
        query = f"""
            SELECT
                COUNT(*) as count,
                AVG(duration_seconds) as avg_duration_s,
                AVG(cost_usd) as avg_cost_usd,
                SUM(cost_usd) as total_cost_usd
            FROM audit.preset_runs
            WHERE preset_id = %s
            AND started_at > NOW() - INTERVAL %s
            AND dry_run = FALSE
        """
        return self.db.fetchone(query, (preset_id, period))
```

---

## Testing Strategy

### Unit Tests (no API keys)

```python
# tests/presets/test_loader.py
def test_load_preset_yaml():
    """Load and validate a preset YAML."""
    config = load_preset_yaml(Path("configs/presets/morning-ops.yaml"))
    assert config.preset_id == "morning-ops"
    assert len(config.stages) > 0
    assert config.stages[0].id == "email-triage"

def test_expand_to_dag():
    """Convert preset to execution DAG."""
    config = load_preset_yaml(Path("configs/presets/morning-ops.yaml"))
    dag = expand_to_execution_graph(config)
    assert len(dag.nodes) == len(config.stages)
    assert dag.is_acyclic()
```

### Integration Tests (with mock LLM)

```python
# tests/presets/test_executor.py
@pytest.mark.integration
def test_run_preset_morning_ops_dry_run(mock_orchestrator):
    """Run morning-ops in dry-run mode (no API calls)."""
    executor = PresetExecutor(mock_orchestrator, ...)
    result = executor.run_preset("morning-ops", dry_run=True)
    
    assert result.status == "success"
    assert result.duration_seconds < 1  # dry-run is fast
    assert result.cost_usd == 0  # no real costs
    assert "email-triage" in result.stages
```

### End-to-End Tests (optional, with real API)

```bash
# Run live (requires API keys)
donald presets test morning-ops --dry-run
donald presets test deep-research --dry-run
donald presets test trading-monitor --dry-run
```

---

## Deployment Checklist

- [ ] **Preset configs** — all three YAML files in `configs/presets/`
- [ ] **PresetRegistry** — load YAML, validate schema
- [ ] **PresetExecutor** — orchestrate stages, handle errors, estimate costs
- [ ] **PresetScheduler** — wire into cron scheduler
- [ ] **CLI commands** — `donald presets list|run|test|enable|disable|metrics`
- [ ] **Audit logging** — log every run with cost, duration, outcome
- [ ] **Integration checks** — verify required MCP servers are connected
- [ ] **Cost estimation** — accurate pricing per model, per stage
- [ ] **Tests** — unit + integration, dry-run mode works
- [ ] **Docs** — README, QUICKSTART, and this guide

---

## Future Enhancements

1. **Preset discovery & versioning** — marketplace of community presets
2. **Adaptive presets** — learn from trace data to optimize (Tier 6 enhancement)
3. **Preset composition** — combine multiple presets into workflows
4. **Real-time optimization** — adjust parallelism, model tier based on load
5. **A/B testing** — run two variants of a preset, measure outcomes
