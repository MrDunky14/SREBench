"""LangGraph multi-agent incident response team for SREBench."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, TypedDict

import requests
try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - runtime dependency check
    END = None
    StateGraph = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - runtime dependency check
    OpenAI = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
    from rich.rule import Rule
    console = Console()
except ImportError:  # pragma: no cover - runtime dependency check
    Console = None
    Panel = None
    Progress = None
    SpinnerColumn = None
    TextColumn = None
    BarColumn = None
    Rule = None
    console = None


@dataclass
class LLMAdapter:
    """Generic adapter for OpenAI-compatible and Ollama endpoints."""

    provider: Literal["openai", "ollama"] = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "dummy"
    temperature: float = 0.2
    max_tokens: int = 256
    timeout_seconds: int = 45

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text from whichever backend is configured."""
        if self.provider == "ollama":
            return self._generate_ollama(system_prompt, user_prompt)
        return self._generate_openai_compatible(system_prompt, user_prompt)

    def _generate_openai_compatible(self, system_prompt: str, user_prompt: str) -> str:
        if OpenAI is None:
            raise RuntimeError("openai dependency is missing. Install with `pip install openai`.")
        client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout_seconds)
        response = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _generate_ollama(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        response = requests.post(
            f"{self.base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return body.get("message", {}).get("content", "")


class SREState(TypedDict):
    observation: Dict[str, Any]
    scratchpad: List[str]
    diagnosis: str
    remediation_done: bool
    chosen_service: str
    remediation_command: str
    remediation_target: str
    iteration: int


def _extract_json_object(raw: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _call_step(env_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(f"{env_url.rstrip('/')}/step", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def _call_reset(env_url: str, task_id: str) -> Dict[str, Any]:
    response = requests.post(f"{env_url.rstrip('/')}/reset", json={"task_id": task_id}, timeout=30)
    response.raise_for_status()
    return response.json()


def build_workflow(adapter: LLMAdapter, env_url: str, max_investigation_rounds: int = 3):
    """Build and compile the LangGraph workflow."""
    if StateGraph is None or END is None:
        raise RuntimeError("langgraph dependency is missing. Install with `pip install langgraph`.")
    if console is None or Progress is None:
        raise RuntimeError("rich dependency is missing. Install with `pip install rich`.")

    def investigator_node(state: SREState) -> SREState:
        degraded = [svc for svc in state["observation"]["system_dashboard"] if svc["status"] != "healthy"]
        checked = [line for line in state["scratchpad"] if line.startswith("Logs for ")]
        sys_prompt = (
            "You are the SRE Investigator. Choose ONE service to inspect with check_logs. "
            "Prefer degraded services first. Avoid services already investigated. "
            'Return only JSON: {"target":"service-name","reason":"short reason"}'
        )
        user_prompt = (
            f"Dashboard: {json.dumps(state['observation']['system_dashboard'])}\n"
            f"Degraded: {[svc['name'] for svc in degraded]}\n"
            f"Already Investigated: {checked}"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("🕵️ Investigator selecting service"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("investigator", total=100)
            response = adapter.generate(sys_prompt, user_prompt)
            progress.update(task, advance=100)

        choice = _extract_json_object(response)
        target = choice.get("target")
        if not target:
            target = degraded[0]["name"] if degraded else "database-primary"
        state["chosen_service"] = target

        step_payload = {
            "action_type": "investigate",
            "command": "check_logs",
            "target": target,
            "params": {"severity": "ERROR", "last_n": 20},
        }
        result = _call_step(env_url, step_payload)
        state["observation"] = result["observation"]
        state["scratchpad"].append(f"Logs for {target}: {result['observation']['last_action_result']}")
        state["iteration"] += 1
        console.print(f"🕵️ [bold cyan]Investigator[/bold cyan] checked [bold]{target}[/bold]")
        return state

    def diagnoser_node(state: SREState) -> SREState:
        sys_prompt = (
            "You are the SRE Diagnoser. Read investigation logs and infer root cause. "
            "If uncertain, return empty diagnosis. "
            'Return only JSON: {"diagnosis":"fault_type or comma-separated fault types","confidence":"low|medium|high"}'
        )
        user_prompt = f"Scratchpad logs: {json.dumps(state['scratchpad'])}"
        response = adapter.generate(sys_prompt, user_prompt)
        parsed = _extract_json_object(response)
        diagnosis = parsed.get("diagnosis", "").strip()
        state["diagnosis"] = diagnosis
        if diagnosis:
            console.print(f"🧠 [bold magenta]Diagnoser[/bold magenta] hypothesis: [bold]{diagnosis}[/bold]")
            submit_payload = {
                "action_type": "diagnose",
                "command": "submit_diagnosis",
                "target": state.get("chosen_service") or "database-primary",
                "params": {"root_cause": diagnosis},
            }
            result = _call_step(env_url, submit_payload)
            state["observation"] = result["observation"]
        else:
            console.print("🧠 [bold magenta]Diagnoser[/bold magenta] needs more evidence")
        return state

    def operator_node(state: SREState) -> SREState:
        sys_prompt = (
            "You are the SRE Operator. Choose the safest remediation command and target service. "
            "Available commands: restart, scale_up, increase_pool, flush_cache, rollback, failover. "
            'Return only JSON: {"command":"...", "target":"...", "params":{}}'
        )
        user_prompt = (
            f"Diagnosis: {state.get('diagnosis', '')}\n"
            f"Dashboard: {json.dumps(state['observation']['system_dashboard'])}\n"
            f"Recent logs: {json.dumps(state['scratchpad'][-2:])}"
        )
        response = adapter.generate(sys_prompt, user_prompt)
        parsed = _extract_json_object(response)

        command = parsed.get("command", "restart")
        target = parsed.get("target") or state.get("chosen_service") or "database-primary"
        params = parsed.get("params", {})
        if not isinstance(params, dict):
            params = {}

        state["remediation_command"] = command
        state["remediation_target"] = target

        with Progress(
            SpinnerColumn(),
            TextColumn("🛠️ Operator executing remediation"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("operator", total=100)
            result = _call_step(
                env_url,
                {
                    "action_type": "remediate",
                    "command": command,
                    "target": target,
                    "params": params,
                },
            )
            progress.update(task, advance=100)

        state["observation"] = result["observation"]
        state["remediation_done"] = True
        console.print(f"🛠️ [bold green]Operator[/bold green] ran [bold]{command}[/bold] on [bold]{target}[/bold]")
        return state

    def should_remediate(state: SREState) -> str:
        if state.get("diagnosis"):
            return "operator"
        if state["iteration"] >= max_investigation_rounds:
            return "operator"
        return "investigator"

    workflow = StateGraph(SREState)
    workflow.add_node("investigator", investigator_node)
    workflow.add_node("diagnoser", diagnoser_node)
    workflow.add_node("operator", operator_node)
    workflow.set_entry_point("investigator")
    workflow.add_edge("investigator", "diagnoser")
    workflow.add_conditional_edges(
        "diagnoser",
        should_remediate,
        {"investigator": "investigator", "operator": "operator"},
    )
    workflow.add_edge("operator", END)
    return workflow.compile()


def run_episode(
    task_id: str,
    adapter: LLMAdapter,
    env_url: str = "http://localhost:8000",
    max_investigation_rounds: int = 3,
) -> Dict[str, Any]:
    """Run one full multi-agent episode and return final state."""
    if console is None or Rule is None or Panel is None:
        raise RuntimeError("rich dependency is missing. Install with `pip install rich`.")
    console.print(Rule(f"[bold red]SRE Multi-Agent Run[/bold red] task={task_id}"))
    initial_observation = _call_reset(env_url, task_id)
    app = build_workflow(adapter, env_url, max_investigation_rounds=max_investigation_rounds)
    initial_state: SREState = {
        "observation": initial_observation,
        "scratchpad": [],
        "diagnosis": "",
        "remediation_done": False,
        "chosen_service": "",
        "remediation_command": "",
        "remediation_target": "",
        "iteration": 0,
    }

    final_state = initial_state
    for step_output in app.stream(initial_state):
        if not step_output:
            continue
        node_name = list(step_output.keys())[0]
        final_state = step_output[node_name]

    grader_resp = requests.get(
        f"{env_url.rstrip('/')}/grader",
        params={"agent_name": "langgraph_multi_agent"},
        timeout=30,
    )
    grader_resp.raise_for_status()
    grade_data = grader_resp.json()
    console.print(
        Panel.fit(
            (
                f"Diagnosis: [bold]{final_state.get('diagnosis') or 'N/A'}[/bold]\n"
                f"Remediation: [bold]{final_state.get('remediation_command')}[/bold] "
                f"on [bold]{final_state.get('remediation_target')}[/bold]\n"
                f"Score: [bold green]{grade_data.get('score')}[/bold green] | "
                f"Resolved: [bold]{grade_data.get('incident_resolved')}[/bold] | "
                f"Steps: [bold]{grade_data.get('steps')}[/bold]"
            ),
            title="Run Summary",
            border_style="green",
        )
    )
    return final_state


def export_agent_graph(
    adapter: LLMAdapter | None = None,
    env_url: str = "http://localhost:8000",
    png_path: str = "agent_architecture.png",
    mermaid_md_path: str = "agent_architecture.md",
    max_investigation_rounds: int = 3,
) -> str:
    """Export the LangGraph architecture as PNG, falling back to Mermaid markdown."""
    if StateGraph is None or END is None:
        raise RuntimeError("langgraph dependency is missing. Install with `pip install langgraph`.")

    adapter = adapter or LLMAdapter()
    app = build_workflow(
        adapter=adapter,
        env_url=env_url,
        max_investigation_rounds=max_investigation_rounds,
    )
    graph = app.get_graph()

    try:
        png_bytes = graph.draw_mermaid_png()
        with open(png_path, "wb") as png_file:
            png_file.write(png_bytes)
        if console is not None:
            console.print(f"[bold green]Exported graph PNG:[/bold green] {png_path}")
        return png_path
    except Exception as exc:
        mermaid_graph = graph.draw_mermaid()
        with open(mermaid_md_path, "w", encoding="utf-8") as md_file:
            md_file.write("# Agent Architecture\n\n")
            md_file.write("```mermaid\n")
            md_file.write(mermaid_graph.strip())
            md_file.write("\n```\n")
            md_file.write("\n")
            md_file.write(
                f"_PNG export failed (`{type(exc).__name__}`); "
                "use Mermaid-compatible tooling to render this graph._\n"
            )
        if console is not None:
            console.print(
                f"[bold yellow]PNG export unavailable; wrote Mermaid markdown:[/bold yellow] {mermaid_md_path}"
            )
        return mermaid_md_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SREBench LangGraph multi-agent team")
    parser.add_argument("--task", default="medium_cascade", help="Task id from SREBench")
    parser.add_argument("--env-url", default=os.getenv("SREBENCH_ENV_URL", "http://localhost:8000"))
    parser.add_argument("--provider", choices=["openai", "ollama"], default=os.getenv("LLM_PROVIDER", "openai"))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:8000/v1"))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", "dummy"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "gpt-4o-mini"))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--max-investigation-rounds", type=int, default=3)
    parser.add_argument(
        "--export-graph",
        action="store_true",
        help="Export Investigator-Diagnoser-Operator graph to PNG (or Mermaid markdown fallback).",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    resolved_base_url = args.base_url
    if args.provider == "ollama" and args.base_url == "http://localhost:8000/v1":
        # Prefer standard Ollama endpoint when user selects ollama provider.
        resolved_base_url = "http://localhost:11434"
    adapter = LLMAdapter(
        provider=args.provider,
        model=args.model,
        base_url=resolved_base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    if args.export_graph:
        export_agent_graph(
            adapter=adapter,
            env_url=args.env_url,
            max_investigation_rounds=args.max_investigation_rounds,
        )
        return
    run_episode(
        task_id=args.task,
        adapter=adapter,
        env_url=args.env_url,
        max_investigation_rounds=args.max_investigation_rounds,
    )


if __name__ == "__main__":
    main()
