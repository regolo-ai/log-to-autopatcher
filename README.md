# Self-Healing Python Demo

AI Agent that auto-fixes bugs by analyzing crash logs and patching source code.

## Prerequisites

- Python ≥3.9
- [uv](https://github.com/astral-sh/uv) package manager (recommended)
- Regolo API key (from [dashboard.regolo.ai](https://dashboard.regolo.ai))

## Installation

### Using uv (Recommended)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt
```

### Using pip

```bash
pip install -r requirements.txt
```

## Setup

Copy `.env.example` to `.env` and set your API key:

```bash
cp .env.example .env
# Edit .env and set your REGOLO_API_KEY
```

## Demo Steps

### Step 1: Watch the Crash

Run the buggy payment processor:

```bash
python src/payment_processor.py
```

**Expected output**:
```
2026-04-02 15:00:04,130 - INFO - Processing payment for user: demo_user...
2026-04-02 15:00:04,130 - ERROR - Critical Failure: 'credit_card'
KeyError: 'credit_card'
```

The crash log is created at `logs/crash.log`.

### Step 2: AI Fixes the Bug

Run the AI fixer agent:

```bash
python fixer_agent.py
```

**Expected output**:
```
🔍 [Agent] Analyzing system failure...
🧠 [Agent] Contacting LLM for diagnosis...
✅ [Agent] Patch applied successfully!
ℹ️  [Agent] Backup saved to src/payment_processor.py.bak
```

### Step 3: Verify the Fix

Run the payment processor again:

```bash
python src/payment_processor.py
```

**Expected output**:
```
2026-04-02 15:08:50,778 - INFO - Processing payment for user: demo_user...
2026-04-02 15:08:50,778 - WARNING - Missing credit_card
```

No crash! The AI successfully patched the bug.

## How It Works

1. **Crash**: The buggy `payment_processor.py` crashes when processing incomplete data
2. **Log**: Error details written to `logs/crash.log`
3. **Analyze**: `fixer_agent.py` reads the log + source code
4. **Patch**: LLM generates fixed code with validation, backup created, patch applied
5. **Verify**: Re-run to confirm the bug is fixed

## Files

- `src/payment_processor.py` — Buggy application (deliberate KeyError)
- `logs/crash.log` — Generated crash log
- `fixer_agent.py` — AI agent that patches the bug (uses regolo client)
- `requirements.txt` — Dependencies
- `README.md` — This file
