import json
import re
import requests
import argparse
import os
import time
from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# --- CONFIGURATION & CLI ---
parser = argparse.ArgumentParser(description="SREBench Multi-Agent Evaluator (Bulletproof Edition)")
parser.add_argument("--api_url", type=str, default="https://openrouter.ai/api/v1/chat/completions", help="LLM API URL")
parser.add_argument("--model", type=str, default="minimax/minimax-01", help="Model ID (e.g., minimax/minimax-01 or anthropic/claude-3.5-sonnet)")
parser.add_argument("--api_key", type=str, required=True, help="Your API Key")
args = parser.parse_args()

# The URL of your live Hugging Face Space
BASE_URL = "https://creatorneuron-sre-bench.hf.space"

# --- CORE LLM BRAIN (With Auto-Retry) ---
def ask_universal_llm(system_prompt: str, user_prompt: str, max_retries=3) -> str:
    headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": args.model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.1,
        "max_tokens": 512
    }
    
    for attempt in range(max_retries):
        try:
            raw_response = requests.post(args.api_url, headers=headers, json=payload, timeout=30)
            response = raw_response.json()
            if "choices" in response and len(response["choices"]) > 0:
                return response["choices"][0]["message"]["content"]
            print(f"   [API WARNING] Attempt {attempt+1}: {response.get('error', 'Unknown Error')}")
            time.sleep(2)
        except Exception as e:
            print(f"   [API ERROR] Attempt {attempt+1}: {e}")
            time.sleep(2)
    return "{}"

# --- LANGGRAPH STATE ---
class SREState(TypedDict):
    observation: dict
    scratchpad: List[str]
    checked_targets: List[str]
    diagnosis: str
    target_service: str
    system_recovered: bool

# --- NODES ---
def investigator_node(state: SREState):
    print("\n🕵️ [INVESTIGATOR]: Analyzing dashboard...")
    if not state.get("checked_targets"): state["checked_targets"] = []
    
    sys_prompt = (
        "You are a Senior SRE Investigator. Look at the degraded services. "
        "Pick ONE service to check logs. CRITICAL: Do NOT pick a service in the 'Already Checked' list. "
        "Output ONLY valid JSON: {\"target\": \"service-name\"}"
    )
    user_prompt = f"Dashboard: {json.dumps(state['observation']['system_dashboard'])}\nAlready Checked: {state['checked_targets']}"
    
    response = ask_universal_llm(sys_prompt, user_prompt)
    target = "api-gateway"
    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match: target = json.loads(match.group(0)).get("target", target)
    except: pass

    # Starvation Override: If LLM hallucinates or runs out of targets
    if target in state["checked_targets"]:
        available = [s["name"] for s in state['observation']['system_dashboard'] if s["name"] not in state["checked_targets"]]
        if not available:
            print("   -> 🔄 All services scanned! Resetting target list...")
            state["checked_targets"] = []
            target = state['observation']['system_dashboard'][0]["name"]
        else: target = available[0]

    print(f"   -> Checking logs for {target}...")
    r = requests.post(f"{BASE_URL}/step", json={"action_type": "investigate", "command": "check_logs", "target": target, "params": {"last_n": 30}}).json()
    
    state["checked_targets"].append(target)
    state["scratchpad"].append(f"Source: {target} | Logs: {r['observation']['last_action_result']}")
    state["observation"] = r["observation"]
    return state

def diagnoser_node(state: SREState):
    print("🧠 [DIAGNOSER]: Reviewing evidence...")
    sys_prompt = (
        "You are an SRE Diagnoser. Read the log history. "
        "RULES: \n"
        "1. 'No logs found' = Healthy service. Output empty strings.\n"
        "2. UPSTREAM RULE: If a frontend service (api-gateway, user-service) logs a backend error (PostgreSQL, Redis, WAL, Pool Exhausted), the 'target' MUST be the backend database (database-primary, database-replica, or cache-redis).\n"
        "3. Ignore 'Transient' or 'self-resolved' logs.\n"
        "Output ONLY JSON: {\"diagnosis\": \"Description\", \"target\": \"service-name\"}. Empty strings if no fault found."
    )
    response = ask_universal_llm(sys_prompt, f"Log History: {state['scratchpad']}")
    
    diagnosis, target = "", ""
    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            diagnosis, target = data.get("diagnosis", ""), data.get("target", "")
    except: pass

    if diagnosis:
        print(f"   -> Root cause identified: {diagnosis} on {target}")
        state["diagnosis"], state["target_service"] = diagnosis, target
    else:
        print("   -> [DEBUG]: Not enough evidence yet.")
    return state

def operator_node(state: SREState):
    diagnosis = state.get("diagnosis", "Unknown")
    target_service = state.get("target_service", "api-gateway")
    print(f"\n🛠️ [OPERATOR]: Mapping fix for -> {target_service}")
    
    sys_prompt = (
        "Map diagnosis to OpenEnv command: restart, scale_up, increase_pool, flush_cache, rollback, failover.\n"
        "MAP: Disk full -> scale_up | GC/OOM/Leak -> restart | Pool exhausted -> increase_pool | Fragmentation -> flush_cache.\n"
        "Output ONLY JSON: {\"command\": \"name\"}"
    )
    response = ask_universal_llm(sys_prompt, f"Diagnosis: {diagnosis}")
    
    command = "restart"
    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match: command = json.loads(match.group(0)).get("command", command)
    except: pass

    print(f"   -> Sending HTTP POST: {command} on {target_service}...")
    r = requests.post(f"{BASE_URL}/step", json={"action_type": "remediate", "command": command, "target": target_service, "params": {}}).json()
    
    state["observation"] = r.get("observation", state["observation"])
    if r.get("done"):
        print("   -> 🏆 Live System Recovered! SLA Saved.")
        state["system_recovered"] = True
    else:
        print("   -> ⚠️ Fix applied, system still degraded. Flushing memory for next fault...")
        state["system_recovered"] = False
        state["diagnosis"], state["target_service"], state["scratchpad"] = "", "", []
    return state

# --- ROUTING LOGIC ---
def should_remediate(state: SREState):
    if state.get("diagnosis"): return "operator"
    if len(state.get("scratchpad", [])) >= 6: return "operator" # Safety guess
    return "investigator"

def should_continue(state: SREState):
    return "end" if state.get("system_recovered") else "investigator"

# --- WORKFLOW SETUP ---
workflow = StateGraph(SREState)
workflow.add_node("investigator", investigator_node)
workflow.add_node("diagnoser", diagnoser_node)
workflow.add_node("operator", operator_node)

workflow.set_entry_point("investigator")
workflow.add_edge("investigator", "diagnoser")
workflow.add_conditional_edges("diagnoser", should_remediate, {"operator": "operator", "investigator": "investigator"})
workflow.add_conditional_edges("operator", should_continue, {"end": END, "investigator": "investigator"})

app = workflow.compile()

# --- MAIN LOOP ---
if __name__ == "__main__":
    print("🌪️ SREBench Procedural Stress Test Starting...")
    for i in range(1, 4):
        print(f"\n{'='*50}\n🚨 INCIDENT #{i}: (task_id: random)\n{'='*50}")
        initial_obs = requests.post(f"{BASE_URL}/reset", json={"task_id": "random"}).json()
        initial_state = {"observation": initial_obs, "scratchpad": [], "checked_targets": [], 
                         "diagnosis": "", "target_service": "", "system_recovered": False}
        
        for output in app.stream(initial_state, config={"recursion_limit": 50}): pass
        print("\n⏳ Resetting for next run...")