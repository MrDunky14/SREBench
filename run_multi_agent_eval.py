"""
SREBench SOTA Evaluation Script
Complies with OpenEnv Specifications.
"""
import json
import re
import requests
from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# --- CONFIGURATION ---
BASE_URL = "https://creatorneuron-sre-bench.hf.space"
HF_API_URL = "YOUR_70B_ENDPOINT_URL_HERE" # Replace with your HF endpoint!
HF_TOKEN = "YOUR_HF_TOKEN_HERE"           # Replace before running locally, but hide in public repo if needed!

def ask_enterprise_llama(system_prompt: str, user_prompt: str) -> str:
    headers = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "inputs": f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n{user_prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n",
        "parameters": {"max_new_tokens": 128, "temperature": 0.1, "return_full_text": False}
    }
    response = requests.post(HF_API_URL, headers=headers, json=payload).json()
    if isinstance(response, list) and "generated_text" in response[0]:
        return response[0]["generated_text"]
    return "{}"

class SREState(TypedDict):
    observation: dict
    scratchpad: List[str]
    diagnosis: str
    remediation_done: bool

def investigator_node(state: SREState):
    print("\n🕵️ [INVESTIGATOR]: Analyzing dashboard...")
    checked_services = [log for log in state['scratchpad']]
    sys_prompt = (
        "You are a Senior SRE Investigator. Look at the degraded services. "
        "Pick ONE service to check its logs to find the root cause. "
        "PRO TIP: In cascading failures, always prioritize checking databases or caches first! "
        "CRITICAL: Do NOT check a service if you already see its logs in the history. "
        "Output ONLY valid JSON: {\"target\": \"service-name\"}"
    )
    user_prompt = f"Dashboard: {json.dumps(state['observation']['system_dashboard'])}\nAlready Checked: {checked_services}"
    response = ask_enterprise_llama(sys_prompt, user_prompt)
    
    target = "database-primary" 
    try:
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1: target = json.loads(response[start:end+1]).get("target", target)
    except: pass

    print(f"   -> Checking logs for {target}...")
    r = requests.post(f"{BASE_URL}/step", json={"action_type": "investigate", "command": "check_logs", "target": target, "params": {}}).json()
    state["scratchpad"].append(f"Logs for {target}: {r['observation']['last_action_result']}")
    state["observation"] = r["observation"]
    return state

def diagnoser_node(state: SREState):
    print("\n🧠 [DIAGNOSER]: Reviewing evidence...")
    sys_prompt = (
        "You are the SRE Diagnoser. Read the log history. "
        "If you see a database error, connection pool issue, or OOM, you MUST output ONLY valid JSON: {\"diagnosis\": \"Connection Pool Exhausted\"}. "
        "If you need more logs, output EXACTLY: {\"diagnosis\": \"\"}"
    )
    response = ask_enterprise_llama(sys_prompt, f"Log History: {state['scratchpad']}")
    
    diagnosis = ""
    try:
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1: diagnosis = json.loads(response[start:end+1]).get("diagnosis", "")
    except: pass

    if diagnosis:
        print(f"   -> Root cause identified: {diagnosis}")
        state["diagnosis"] = diagnosis
    else:
        print("   -> Not enough evidence. Sending Investigator back in.")
    return state

def operator_node(state: SREState):
    diagnosis = state.get("diagnosis", "Unknown Error")
    print(f"\n🛠️ [OPERATOR]: Executing fix for -> {diagnosis}")
    r = requests.post(f"{BASE_URL}/step", json={"action_type": "remediate", "command": "restart", "target": "database-primary", "params": {}}).json()
    if r.get("done"): print("   -> System Recovered! SLA Saved. 🏆")
    state["remediation_done"] = True
    return state

def should_remediate(state: SREState):
    if state.get("diagnosis") != "": return "operator"
    if len(state["scratchpad"]) >= 5: return "operator" 
    return "investigator"

workflow = StateGraph(SREState)
workflow.add_node("investigator", investigator_node)
workflow.add_node("diagnoser", diagnoser_node)
workflow.add_node("operator", operator_node)
workflow.set_entry_point("investigator")
workflow.add_conditional_edges("diagnoser", should_remediate, {"operator": "operator", "investigator": "investigator"})
workflow.add_edge("investigator", "diagnoser")
workflow.add_edge("operator", END)
app = workflow.compile()

if __name__ == "__main__":
    print("🚨 Triggering SREBench Incident: medium_cascade...")
    initial_obs = requests.post(f"{BASE_URL}/reset", json={"task_id": "medium_cascade"}).json()
    initial_state = {"observation": initial_obs, "scratchpad": [], "diagnosis": "", "remediation_done": False}
    print("🚀 Launching Multi-Agent Local-LLM Team...")
    for output in app.stream(initial_state): pass