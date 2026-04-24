import json
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

nb_path = r"c:\Users\User\Desktop\SREBench-main\SREBench\output\notebook1400d6771e.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

html_content = ""
for cell in nb.get("cells", []):
    for out in cell.get("outputs", []):
        if "data" in out and "text/html" in out["data"]:
            html_content += "".join(out["data"]["text/html"])

# Extract rows from HTML table using regex
rows = re.findall(r'<tr>(.*?)</tr>', html_content, re.DOTALL)
steps = []
rewards = []

for row in rows:
    cols = re.findall(r'<td>(.*?)</td>', row)
    if len(cols) > 2:
        try:
            step = int(cols[0])
            reward = float(cols[2])
            steps.append(step)
            rewards.append(reward)
        except:
            pass

print(f"Extracted steps: {steps}")
print(f"Extracted rewards: {rewards}")

if steps and rewards:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(steps, rewards, color="#6bcb77", linewidth=2, marker="o", markersize=3)
    ax.set_xlabel("Training Step")
    ax.set_ylabel("Reward")
    ax.set_title("SREBench GRPO Training Reward Curve")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(r"c:\Users\User\Desktop\SREBench-main\SREBench\output\training_curves.png", dpi=150, bbox_inches="tight")
    plt.savefig(r"c:\Users\User\Desktop\SREBench-main\SREBench\training_curves.png", dpi=150, bbox_inches="tight")
    print("Fixed training_curves.png successfully generated.")
