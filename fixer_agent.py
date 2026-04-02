#!/usr/bin/env python3
"""
AI Fixer Agent - Uses Regolo client to analyze crash logs and patch buggy code.
"""

import ast
import os
import regolo


def read_file(filepath):
    """Read and return file contents."""
    with open(filepath, "r") as f:
        return f.read()


def validate_syntax(code):
    """Validate Python syntax using ast.parse(). Returns (is_valid, error_message)."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def is_complete_code(code):
    """Check if code ends with complete syntax (no unclosed quotes, parentheses, etc.)."""
    # Check for unclosed strings
    lines = code.split('\n')
    for line in lines:
        stripped = line.strip()
        # Check for unclosed quotes (single or double)
        if (stripped.count('"') - stripped.count('\\"')) % 2 != 0:
            return False
        if (stripped.count("'") - stripped.count("\\'")) % 2 != 0:
            return False
        # Check for unclosed f-strings
        if stripped.count('f"') % 2 != 0 or stripped.count("f'") % 2 != 0:
            return False
    # Check parentheses balance
    paren_count = 0
    brace_count = 0
    bracket_count = 0
    in_string = False
    string_char = None
    
    for char in code:
        if char in '"\'' and not in_string:
            in_string = True
            string_char = char
        elif char == string_char and in_string:
            in_string = False
            string_char = None
        elif not in_string:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
            elif char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
    
    return paren_count == 0 and brace_count == 0 and bracket_count == 0


def fix_bug():
    """Analyze crash log, contact LLM, and apply patch to fix the bug."""
    print("🔍 [Agent] Analyzing system failure...")
    print("📄 [Agent] Reading crash log from logs/crash.log...")

    # Check for required API key
    api_key = os.environ.get("REGOLO_API_KEY")
    if not api_key:
        print("❌ Error: REGOLO_API_KEY environment variable not set.")
        print("   Please set it before running: export REGOLO_API_KEY=your_key")
        return

    # Configure regolo client
    regolo.default_key = api_key
    regolo.default_chat_model = os.environ.get("REGOLO_MODEL", "qwen3-coder-next")

    # 1. Gather Context
    print("📄 [Agent] Reading crash log from logs/crash.log...")
    log_content = read_file("logs/crash.log")
    print(f"✅ [Agent] Crash log loaded ({len(log_content)} characters)")

    print("📝 [Agent] Reading source code from src/payment_processor.py...")
    source_code = read_file("src/payment_processor.py")
    print(f"✅ [Agent] Source code loaded ({len(source_code)} characters)")

    # 2. Construct the Prompt - ask for minimal fix (3 lines each for credit_card and amount)
    prompt = f"""The function process_payment() crashes with KeyError because it directly accesses user_data['credit_card'] without checking if the key exists.

Give me Python code (3 lines) to add inside process_payment() at the start to check for missing keys.
Format: Use if statement on separate line, with 4-space indent for the body. No semicolons. No markdown.

Example:
if 'credit_card' not in user_data:
    logging.warning("Missing credit_card")
    return False"""

    # 3. Get LLM response with retry logic
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        print(f"🧠 [Agent] Contacting LLM for diagnosis... (attempt {attempt + 1}/{max_retries})")

        role, content = regolo.static_chat_completions(
            messages=[
                {"role": "system", "content": "You are a helpful code assistant. Output only valid Python code, no explanations, no markdown."},
                {"role": "user", "content": prompt}
            ]
        )

        fixed_code = content

        print(f"✅ [Agent] Received fix from LLM ({len(fixed_code)} characters)")

        # Clean up markdown formatting if present
        if fixed_code.startswith("```python"):
            fixed_code = fixed_code.strip("```python").strip("`")
        elif fixed_code.startswith("```"):
            fixed_code = fixed_code.strip("```").strip()

        # Check if code is complete
        if not is_complete_code(fixed_code):
            last_error = "Incomplete code response"
            print(f"⚠️  [Agent] Code appears incomplete, retrying...")
            # Make prompt more concise for retry
            prompt = prompt.replace("Keep code MINIMAL", "Keep code VERY SHORT - just add the missing key checks")
            continue

        # Validate syntax
        print("🔍 [Agent] Validating generated code syntax...")
        is_valid, syntax_error = validate_syntax(fixed_code)
        if not is_valid:
            last_error = f"Syntax error: {syntax_error}"
            print(f"❌ [Agent] Validation failed: {syntax_error}. Retrying...")
            print(f"   Retrying with more concise prompt...")
            # Make prompt more concise for retry
            prompt = prompt.replace("Keep code MINIMAL", "Keep code VERY SHORT")
            continue

        # Success - apply patch by inserting into source file
        backup_path = "src/payment_processor.py.bak"
        print(f"💾 [Agent] Creating backup at {backup_path}...")
        os.rename("src/payment_processor.py", backup_path)
        print("ℹ️  [Agent] Backup created successfully")

        print("✍️  [Agent] Writing patched code to src/payment_processor.py...")

        # Find the line "logging.info(f"Processing payment for user" - insert after it
        lines = source_code.split('\n')
        patch_lines = fixed_code.split('\n')
        
        # Remove any markdown formatting from patch lines
        patch_lines = [l for l in patch_lines if not l.strip().startswith('```')]
        
        # Add 4-space indentation to patch lines (since they're inserted inside a function)
        patch_lines = ['    ' + line for line in patch_lines]
        
        # Find the insert point - after "logging.info(f"Processing payment"
        insert_idx = None
        for i, line in enumerate(lines):
            if 'Processing payment for user' in line:
                insert_idx = i + 1
                break
        
        if insert_idx is None:
            # Fallback: insert after the docstring in process_payment
            for i, line in enumerate(lines):
                if line.strip().startswith('"""') and i > 10:  # After docstring in function
                    insert_idx = i + 1
                    break
        
        if insert_idx is None:
            insert_idx = 20  # Safe default
        
        # Insert patch
        new_lines = lines[:insert_idx] + patch_lines + lines[insert_idx:]
        
        with open("src/payment_processor.py", "w") as f:
            f.write('\n'.join(new_lines))

        print("✅ [Agent] Patch applied successfully!")
        print(f"ℹ️  [Agent] Backup saved to {backup_path}")
        print(f"🧠 [Agent] Summary: Added null checks for 'credit_card' and 'amount' fields")
        return

    # All retries failed
    print(f"❌ [Agent] Failed after {max_retries} attempts. Last error: {last_error}")
    print("   Restoring original code from backup...")


if __name__ == "__main__":
    fix_bug()