#!/usr/bin/env python3
"""
AI Fixer Agent — Generic log-driven bug fixer.

Reads a crash log, extracts the traceback to find the failing file/line,
sends log + source to an LLM, gets back the full corrected file,
validates syntax, and applies the patch.

No hardcoded bug knowledge. No hardcoded file names. No hardcoded insert points.
"""

import ast
import os
import re
import sys

import regolo
from dotenv import load_dotenv

# Load .env file at startup
load_dotenv()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_file(filepath):
    """Read and return file contents."""
    with open(filepath, "r") as f:
        return f.read()


def validate_syntax(code):
    """Validate Python syntax. Returns (is_valid, error_message)."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def strip_markdown_fences(text):
    """Remove ```python ... ``` wrappers the LLM might add."""
    text = text.strip()
    if text.startswith("```python"):
        text = text[len("```python"):]
    elif text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def parse_traceback(log_text):
    """
    Extract structured information from a Python traceback in the log.

    Returns a dict with:
      - error_type: e.g. 'KeyError'
      - error_message: e.g. "'credit_card'"
      - frames: list of {file, line_no, function, code_text}
      - source_files: set of file paths mentioned in the traceback
    """
    info = {
        "error_type": None,
        "error_message": None,
        "frames": [],
        "source_files": set(),
    }

    # Find the last traceback block (most recent crash)
    tb_blocks = list(re.finditer(r"Traceback \(most recent call last\):", log_text))
    if not tb_blocks:
        return info

    last_tb = tb_blocks[-1]
    tb_text = log_text[last_tb.start():]

    # Parse frames: 'File "path", line N, in func'
    frame_pattern = re.compile(
        r'File "(?P<file>[^"]+)",\s*line\s*(?P<line>\d+),\s*in\s+(?P<func>\S+)'
    )
    # Code line follows the frame line
    lines = tb_text.split("\n")
    i = 0
    while i < len(lines):
        m = frame_pattern.search(lines[i])
        if m:
            code_text = lines[i + 1].strip() if i + 1 < len(lines) else ""
            frame = {
                "file": m.group("file"),
                "line_no": int(m.group("line")),
                "function": m.group("func"),
                "code_text": code_text,
            }
            info["frames"].append(frame)
            # Track only files that exist locally (skip stdlib paths)
            if os.path.exists(m.group("file")):
                info["source_files"].add(m.group("file"))
        i += 1

    # Parse the error line (last line of traceback): 'KeyError: foo'
    error_pattern = re.compile(r"^(\w+Error|\w+Exception):\s*(.*)", re.MULTILINE)
    error_matches = error_pattern.findall(tb_text)
    if error_matches:
        info["error_type"] = error_matches[-1][0]
        info["error_message"] = error_matches[-1][1]

    return info


def find_local_source_files(traceback_info):
    """
    From the traceback, resolve which source files we can actually read.
    Falls back to common source directories if traceback paths are absolute.
    """
    candidates = set()

    # Direct matches from traceback
    for fpath in traceback_info["source_files"]:
        if os.path.isfile(fpath):
            candidates.add(fpath)

    # If paths are absolute (e.g. /home/user/project/src/file.py),
    # try to resolve them relative to CWD
    for frame in traceback_info["frames"]:
        fpath = frame["file"]
        if os.path.isfile(fpath):
            candidates.add(fpath)
        # Try relative resolution
        basename = os.path.basename(fpath)
        for root_dir in ["src", "lib", "."]:
            candidate = os.path.join(root_dir, basename)
            if os.path.isfile(candidate):
                candidates.add(candidate)

    return sorted(candidates)


# ---------------------------------------------------------------------------
# Main agent logic
# ---------------------------------------------------------------------------

def find_log_file():
    """Auto-discover crash logs in common locations."""
    candidates = [
        os.environ.get("LOG_FILE", ""),
        "logs/crash.log",
        "logs/error.log",
        "crash.log",
        "error.log",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path

    # Last resort: find any .log file under logs/
    if os.path.isdir("logs"):
        for f in os.listdir("logs"):
            if f.endswith(".log"):
                return os.path.join("logs", f)

    return None


def fix_bug():
    """Analyze crash log, contact LLM, apply patch — fully generic."""

    print("🔍 [Agent] Analyzing system failure...")

    # --- API key check ---
    api_key = os.environ.get("REGOLO_API_KEY")
    if not api_key:
        print("❌ Error: REGOLO_API_KEY environment variable not set.")
        print("   Run: export REGOLO_API_KEY=your_key")
        return False

    regolo.default_key = api_key
    regolo.default_chat_model = os.environ.get("REGOLO_MODEL", "qwen3-coder-next")

    # --- 1. Find and read the crash log ---
    log_path = find_log_file()
    if not log_path:
        print("❌ Error: No crash log found. Run the buggy app first to generate one.")
        return False

    print(f"📄 [Agent] Reading crash log from {log_path}...")
    log_content = read_file(log_path)
    print(f"   ✅ Loaded ({len(log_content)} chars)")

    # --- 2. Parse the traceback to discover what crashed ---
    print("🔎 [Agent] Parsing traceback to identify failing code...")
    tb_info = parse_traceback(log_content)

    if not tb_info["frames"]:
        print("❌ Error: No Python traceback found in the log.")
        print("   The log may be empty or from a non-Python application.")
        return False

    print(f"   ✅ Error type: {tb_info['error_type']}: {tb_info['error_message']}")
    for frame in tb_info["frames"]:
        print(f"   → {frame['file']}:{frame['line_no']} in {frame['function']}()")

    # --- 3. Find the source file(s) ---
    source_files = find_local_source_files(tb_info)
    if not source_files:
        print("❌ Error: Could not locate the source files mentioned in the traceback.")
        print("   Searched for:")
        for frame in tb_info["frames"]:
            print(f"   - {frame['file']}")
        return False

    # Read all relevant source files
    sources = {}
    for src_path in source_files:
        print(f"📝 [Agent] Reading source: {src_path}...")
        sources[src_path] = read_file(src_path)
        print(f"   ✅ Loaded ({len(sources[src_path])} chars)")

    # --- 4. Build the prompt — NO hints about the bug ---
    source_section = "\n\n".join(
        f"# FILE: {path}\n{content}" for path, content in sources.items()
    )

    frame_details = "\n".join(
        f"  - {f['file']} line {f['line_no']} in {f['function']}(): {f['code_text']}"
        for f in tb_info["frames"]
    )

    prompt = f"""You are an expert Python DevOps Engineer.
Your job is to fix a bug in the provided source code based on a crash log.

## RULES:
1. Read the ERROR LOG below.
2. Identify the root cause from the traceback.
3. Fix the source code — make it handle the error gracefully (check, log warning, return early).
4. Do NOT change the overall logic, only add proper error handling.
5. Return ONLY the complete corrected Python source file(s).
6. Preserve ALL existing imports, structure, and comments.
7. If multiple files are provided, return each file prefixed with '# FILE: <path>' on its own line.

## ERROR LOG:
{log_content}

## TRACEBACK SUMMARY:
Error: {tb_info['error_type']}: {tb_info['error_message']}
Frames:
{frame_details}

## SOURCE CODE:
{source_section}
"""

    # --- 5. Call LLM with retry ---
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        print(f"🧠 [Agent] Contacting LLM (attempt {attempt + 1}/{max_retries})...")

        _, content = regolo.static_chat_completions(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful code assistant. "
                        "Output only valid Python code. No explanations. No markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )

        fixed_code = strip_markdown_fences(content)
        print(f"   ✅ Received response ({len(fixed_code)} chars)")

        # Validate syntax
        print("🔍 [Agent] Validating syntax...")
        is_valid, syntax_err = validate_syntax(fixed_code)
        if not is_valid:
            last_error = f"Syntax error: {syntax_err}"
            print(f"   ❌ Validation failed: {syntax_err}")
            print("   Retrying with stricter prompt...")
            prompt += "\n\nIMPORTANT: Return ONLY valid Python code. No markdown fences. No explanations."
            continue

        print("   ✅ Syntax valid")

        # --- 6. Apply patch ---
        # If response contains multiple files (marked with '# FILE:'), split them
        file_blocks = re.split(r"(?=^# FILE: )", fixed_code, flags=re.MULTILINE)

        if len(file_blocks) > 1:
            # Multi-file response
            for block in file_blocks:
                block = block.strip()
                if not block:
                    continue
                first_line = block.split("\n")[0]
                file_match = re.match(r"^# FILE:\s*(.+)$", first_line)
                if file_match:
                    target = file_match.group(1).strip()
                    code_body = "\n".join(block.split("\n")[1:]).strip()
                    _apply_patch(target, code_body)
        else:
            # Single file — patch the main source file from traceback
            target = source_files[0]
            _apply_patch(target, fixed_code)

        print("✅ [Agent] All patches applied successfully!")
        return True

    # All retries exhausted
    print(f"❌ [Agent] Failed after {max_retries} attempts. Last error: {last_error}")
    return False


def _apply_patch(target_path, new_code):
    """Backup original and write the patched file."""
    backup_path = target_path + ".bak"

    print(f"💾 [Agent] Backing up {target_path} → {backup_path}")
    if not os.path.exists(backup_path):
        os.rename(target_path, backup_path)

    print(f"✍️  [Agent] Writing patched code to {target_path}...")
    with open(target_path, "w") as f:
        f.write(new_code)

    print(f"   ✅ Patch applied to {target_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    success = fix_bug()
    sys.exit(0 if success else 1)
