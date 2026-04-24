# SREBench GRPO Training Guide

This guide walks you through training an LLM agent on SREBench using GRPO with Unsloth.

## Prerequisites

- Python 3.9+
- ~8GB RAM (for Llama-3.2-1B)
- GPU recommended (NVIDIA A100, H100, or similar for optimal speed)
- CPU-only training takes ~5-10x longer but still works

## Installation

### 1. Clone and Install Dependencies

```bash
git clone https://github.com/MrDunky14/SREBench.git
cd SREBench

# Install all required packages
pip install -r requirements.txt
```

Key packages installed:
- `trl>=0.9.0` — GRPO trainer implementation
- `unsloth>=2024.04` — Efficient model quantization & LoRA
- `transformers>=4.40.0` — Model loading and tokenization
- `torch>=2.0.0` — Deep learning framework
- `gymnasium>=0.28.0` — Environment interface

### 2. Verify Installation

```bash
cd sre-bench
python train_grpo.py --help
```

Expected output:
```
usage: train_grpo.py [-h] [--steps STEPS] [--model MODEL] ...
Train an SRE agent on SREBench using GRPO with Unsloth.
```

## Quick Start (2-minute demo)

### Run a minimal training example:

```bash
cd sre-bench
python train_grpo.py \
  --steps 10 \
  --model "unsloth/Llama-3.2-1B-Instruct" \
  --batch-size 1 \
  --epochs 1 \
  --output ./minimal_demo
```

**Expected runtime**: ~2-3 minutes (CPU) / ~30 seconds (GPU)

**Expected output**:
```
======================================================================
🚀 SREBench GRPO Training Pipeline
======================================================================

🔧 Loading model: unsloth/Llama-3.2-1B-Instruct
⚡ Applying Unsloth optimizations...
✅ Model loaded and optimized

📊 Collecting 10 training samples...
  📌 Curriculum: easy_restart (3 samples)
    ✓ Sample 1/3 | Avg Reward (last 5): 0.450
    ✓ Sample 2/3 | Avg Reward (last 5): 0.520
    ✓ Sample 3/3 | Avg Reward (last 5): 0.480

🚀 Starting GRPO Training...
   Training in progress...

💾 Saving model...
   ✓ Saved LoRA adapters to ./minimal_demo/trained_model/adapter
   ✓ Saved tokenizer to ./minimal_demo/trained_model
   ✓ Saved metrics to ./minimal_demo/training_metrics.json

📈 Generating reward curves...
   ✓ Saved reward curve to ./minimal_demo/reward_curves.png
   ✓ Saved summary to ./minimal_demo/training_summary.txt

======================================================================
✅ Training Complete!
======================================================================

📁 Output directory: ./minimal_demo
📊 Model saved to: ./minimal_demo/trained_model
📈 Reward curves: ./minimal_demo/reward_curves.png
📋 Metrics: ./minimal_demo/training_metrics.json
```

### Inspect results:

```bash
# View training metrics
cat minimal_demo/training_metrics.json | python -m json.tool

# View training summary
cat minimal_demo/training_summary.txt

# Display reward curves
# (Open minimal_demo/reward_curves.png in your image viewer)
```

---

## Full Training (Production Quality)

For best results, use more steps and computational resources:

### CPU Training (12-24 hours)

```bash
python train_grpo.py \
  --steps 500 \
  --model "unsloth/Llama-3.2-1B-Instruct" \
  --batch-size 1 \
  --epochs 2 \
  --lr 5e-5 \
  --output ./checkpoints_cpu
```

### GPU Training (30 minutes - 2 hours)

```bash
CUDA_VISIBLE_DEVICES=0 python train_grpo.py \
  --steps 500 \
  --model "unsloth/Llama-3.2-1B-Instruct" \
  --batch-size 4 \
  --epochs 2 \
  --lr 5e-5 \
  --output ./checkpoints_gpu
```

### HF Compute Credits (Advanced)

For optimal performance during the hackathon, use Hugging Face compute credits:

```bash
# Launch on HF Spaces GPU
huggingface-cli repo create sre-bench-training --type space

# Upload training script and run as scheduled task
git clone https://huggingface.co/spaces/YOUR_USER/sre-bench-training
cd sre-bench-training
pip install -r requirements.txt
python train_grpo.py --steps 1000 --model "unsloth/Llama-3.2-8B-Instruct" --output ./production_model
```

---

## Command-Line Options

```
usage: train_grpo.py [-h] [--steps STEPS] [--model MODEL] [--output OUTPUT]
                     [--lr LR] [--batch-size BATCH_SIZE] [--epochs EPOCHS]

optional arguments:
  -h, --help            show this help message and exit
  --steps STEPS         Number of training steps (default: 100)
  --model MODEL         Model name or path (default: unsloth/Llama-3.2-1B-Instruct)
  --output OUTPUT       Output directory for checkpoints (default: ./checkpoints)
  --lr LR              Learning rate (default: 5e-05)
  --batch-size BATCH_SIZE
                        Training batch size (default: 1)
  --epochs EPOCHS       Number of training epochs (default: 1)
```

### Common Configurations

**Minimal Demo** (verify setup works)
```bash
python train_grpo.py --steps 10 --model "unsloth/Llama-3.2-1B-Instruct"
```

**Development** (fast iteration)
```bash
python train_grpo.py --steps 100 --batch-size 2 --lr 1e-4
```

**Production** (best results)
```bash
python train_grpo.py --steps 500 --batch-size 4 --epochs 2 --lr 5e-5
```

**Fine-tuning from checkpoint** 
```bash
python train_grpo.py \
  --steps 200 \
  --model ./checkpoints/trained_model \
  --output ./checkpoints_v2
```

---

## Output Structure

After training, you'll get:

```
checkpoints/
├── grpo_checkpoint/              # TRL checkpoints
│   ├── checkpoint-100/
│   ├── checkpoint-200/
│   └── ...
├── trained_model/
│   ├── adapter/                  # LoRA weights
│   ├── config.json
│   ├── tokenizer.json
│   ├── tokenizer.model
│   └── tokenizer_config.json
├── training_metrics.json         # Statistics
├── training_summary.txt          # Human-readable summary
├── reward_curves.png             # Visualization
└── tensorboard/                  # TensorBoard logs (if available)
```

### Key Output Files

#### `training_metrics.json`
Contains:
- Model name and hyperparameters
- Average/max/min reward across all episodes
- Per-task statistics (easy/medium/hard)
- Timestamp of training

Example:
```json
{
  "timestamp": "2026-04-23T14:32:00.123456",
  "model_name": "unsloth/Llama-3.2-1B-Instruct",
  "num_train_steps": 100,
  "learning_rate": 5e-05,
  "avg_training_reward": 0.3847,
  "max_training_reward": 0.8234,
  "min_training_reward": 0.0012,
  "task_rewards": {
    "easy_restart": {
      "mean": 0.6234,
      "max": 0.8901,
      "samples": 33
    },
    "medium_cascade": {
      "mean": 0.3821,
      "max": 0.7123,
      "samples": 33
    },
    "hard_intermittent": {
      "mean": 0.1456,
      "max": 0.5234,
      "samples": 34
    }
  }
}
```

#### `reward_curves.png`
Two-panel chart showing:
1. **Top**: Overall training reward across all episodes
2. **Bottom**: Per-task reward curves

Visual indicators:
- Smooth upward trend indicates successful learning
- Flat line could indicate:
  - Model is memorizing instead of generalizing
  - Tasks are too easy or too hard
  - Learning rate is too low/high
  - Need more curriculum

#### `training_summary.txt`
Human-readable statistics and decisions made during training.

---

## Troubleshooting

### ❌ "ModuleNotFoundError: No module named 'torch'"

**Solution**: Install PyTorch correctly for your system.

```bash
# CPU only
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### ❌ CUDA Out of Memory

**Solutions** (in order):
1. Reduce `--batch-size` to 1
2. Use smaller model: `--model "unsloth/Llama-3.2-1B-Instruct"` (vs. 8B)
3. Enable gradient checkpointing (automatic in script)
4. Run on CPU (slower but works)

### ❌ Training is very slow (CPU)

This is expected. Single-step training on CPU takes ~30 seconds. Plan for:
- 10 steps: ~5 minutes
- 50 steps: ~20 minutes
- 100 steps: ~40 minutes

**Recommendation:** Use GPU on HF Spaces or through Colab.

### ❌ Reward curves are flat / random

Possible causes:
1. **Curriculum not working**: Check console output for "Curriculum: easy_restart" message
2. **Model not training**: Check loss values (should decrease over time)
3. **Rewards all zero**: Verify environment runs with `pytest sre-bench/gymnasium_env.py`
4. **Learning rate too low**: Try `--lr 1e-4` (10× higher)

### ❌ LoRA weights not saved

Check if `trained_model/adapter/` directory exists. If missing:

```bash
# Manually save model after training
python -c "
from transformers import AutoModel
model.save_pretrained('./manual_save')
"
```

---

## Evaluation & Next Steps

### 1. Generate Baseline Metrics

Before and after quantitative comparison:

```bash
# Run inference with untrained model
python inference.py --model "unsloth/Llama-3.2-1B-Instruct" --env http://localhost:7860

# Run inference with trained model  
python inference.py --model ./checkpoints/trained_model --env http://localhost:7860
```

### 2. Benchmark Against Baselines

```bash
cd sre-bench
python -m pytest test_comprehensive.py -v
```

### 3. Deploy to HF Spaces

```bash
# Push your trained model to Hub
huggingface-cli upload YOUR_USERNAME/sre-bench-trained ./checkpoints/trained_model --repo-type model

# Use in Space
ENV_URL=https://huggingface.co/spaces/YOUR_USERNAME/sre-bench \
MODEL_URL=https://huggingface.co/YOUR_USERNAME/sre-bench-trained \
python inference.py
```

---

## Advanced: Custom Reward Functions

Modify `SREBenchReward.compute_reward()` in `train_grpo.py` to customize:

```python
def compute_reward(self, episode_data: Dict) -> float:
    reward = episode_data.get('cumulative_reward', 0.0)
    terminated = episode_data.get('terminated', False)
    
    # Customize here:
    # - Emphasize diagnosis accuracy
    # - Penalize excessive steps
    # - Reward speed
    # - Multi-task performance
    
    normalized = (reward + 1.0) / 2.0
    if terminated:
        normalized = min(normalized + 0.1, 1.0)
    
    return float(normalized)
```

---

## FAQ

**Q: How long does training take?**  
A: ~30 seconds - 2 hours depending on hardware (GPU much faster than CPU).

**Q: Can I resume training from the last checkpoint?**  
A: Yes, use the checkpoint directory as `--model` argument.

**Q: What's the difference between train_grpo.py and train_agents.py?**  
A: `train_grpo.py` uses TRL/Unsloth (required by hackathon). `train_agents.py` uses SB3 (research baseline).

**Q: Should I use Llama-3.2-1B or 8B?**  
A: Start with 1B (faster), then scale to 8B if you have compute credits.

**Q: How do I know if training is working?**  
A: Check `reward_curves.png` — should show upward trend, not flat line.

**Q: Can I train on multiple GPUs?**  
A: Yes, modify `GRPOConfig` with `multi_gpu=True` (see TRL docs).

---

## Citation

If you use SREBench training in research, please cite:

```bibtex
@misc{srebench2026,
  title={SREBench: OpenEnv-Compliant Benchmark for LLM-Based SRE Incident Response},
  author={Singh, Krishna},
  year={2026},
  url={https://github.com/MrDunky14/SREBench}
}
```

---

**Questions?** Open an issue on [GitHub](https://github.com/MrDunky14/SREBench/issues) or check the [blog post](../BLOG_POST.md).

Happy training! 🚀
