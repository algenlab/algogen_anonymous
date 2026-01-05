from openai import OpenAI
import os
import json
import time
import subprocess
import re
import argparse
import tempfile
from pathlib import Path


_siliconflow_api_key = os.environ.get("SILICONFLOW_API_KEY")
if not _siliconflow_api_key:
    raise RuntimeError("Environment variable SILICONFLOW_API_KEY is not set")

client = OpenAI(
    base_url='https://api.siliconflow.cn/v1',
    api_key=_siliconflow_api_key,
)


CURRENT_MODEL = 'deepseek-ai/DeepSeek-V3.2'


def sanitize_model_name(model_name: str) -> str:
    """Convert a model name to a safe folder name (replace '/' with '_')."""

    return model_name.replace('/', '_')


def read_file(path: str) -> str:
    """Read file content as UTF-8 text."""

    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def split_algo_blocks(text: str) -> list:
    """Split the input specification into algorithm blocks.

    Historically this matched Chinese markers, we keep the same regex.
    """

    matches = list(re.finditer(r'(?m)^\s*算法附加片段（', text))
    if not matches:
        cleaned = text.strip()
        return [cleaned] if cleaned else []

    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks

def sanitize_tag(tag: str) -> str:
    tag = re.sub(r'[^A-Za-z0-9_\-]+', '_', tag)
    tag = tag.strip('_')
    return tag if tag else 'task'

def derive_task_tag(base_tag: str, algo_block: str, index: int) -> str:
    """Derive a task tag from the base tag and algo block content."""

    m = re.search(r'目标\s*\(Goal\).*?生成\s*`?\s*([A-Za-z0-9_\-]+)\.py\s*`?', algo_block)
    if m:
        return sanitize_tag(f"{base_tag}__{m.group(1)}")
    return sanitize_tag(f"{base_tag}__part{index + 1:02d}")

def dedupe_tag(tag: str, used: set, index: int) -> str:
    if tag not in used:
        used.add(tag)
        return tag
    alt = sanitize_tag(f"{tag}__dup{index + 1:02d}")
    if alt not in used:
        used.add(alt)
        return alt
    suffix = 1
    while True:
        alt2 = sanitize_tag(f"{tag}__dup{index + 1:02d}_{suffix}")
        if alt2 not in used:
            used.add(alt2)
            return alt2
        suffix += 1

def extract_final_code(response: str) -> str:
    """Extract the final version of code (Version 3) from the LLM response.

    Priority:
    1. Look for blocks marked as "Version 3" / "Final submission" in either
       Chinese or English.
    2. Otherwise, take the last Python code block.
    3. As a last resort, take the last fenced code block.
    """

    # Strategy 1: search for explicit "version 3 / final" markers.
    patterns = [
        r'【版本3[：:：].*?】.*?```python\s*(.*?)```',
        r'【最终提交】.*?```python\s*(.*?)```',
        r'Version 3.*?```python\s*(.*?)```',
        r'Final.*?```python\s*(.*?)```'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # Strategy 2: take the last Python code block.
    all_blocks = re.findall(r'```python\s*(.*?)```', response, re.DOTALL)
    if all_blocks:
        return all_blocks[-1].strip()
    
    # Strategy 3: take the last fenced code block (any language).
    all_blocks = re.findall(r'```.*?\s*(.*?)```', response, re.DOTALL)
    if all_blocks:
        return all_blocks[-1].strip()
    
    # If nothing is found, return the raw response.
    return response.strip()

def quick_pre_check(code: str) -> tuple:
    """Quick static checks on the generated code (no execution).

    Returns (ok: bool, message: str).
    """

    # Check 1: required Python / SVL keywords.
    required_keywords = ['import', 'def', 'trace', 'svl_version', 'initial_frame', 'deltas']
    missing = [kw for kw in required_keywords if kw not in code]
    if missing:
        return False, f"Missing required keywords: {', '.join(missing)}"
    
    # Check 2: obvious format errors.
    if 'svl_version": 5.0' in code:  # numeric instead of string
        return False, 'svl_version must be the string "5.0", not the number 5.0'
    
    # Check Infinity (excluding mentions inside comments).
    lines = code.split('\n')
    for line in lines:
        # Strip comments.
        code_part = line.split('#')[0]
        if '"Infinity"' in code_part or ('Infinity' in code_part and 'import' not in code_part):
            return False, 'Do not use Infinity; use None instead'
    
    # Check 3: Chinese variable names (excluding strings and comments).
    lines = code.split('\n')
    for i, line in enumerate(lines, 1):
        # Strip comments.
        code_part = line.split('#')[0]
        
        # Strip strings (including f-strings / r-strings, simplified).
        # Remove triple-quoted strings (simplified handling).
        code_part = re.sub(r'[frbFRB]?""".*?"""', '', code_part)
        code_part = re.sub(r"[frbFRB]?'''.*?'''", '', code_part)
        # Remove single-line strings.
        code_part = re.sub(r'[frbFRB]?"[^"]*"', '', code_part)
        code_part = re.sub(r"[frbFRB]?'[^']*'", '', code_part)
        
        # Now check for Chinese characters followed by optional spaces and '='.
        if re.search(r'[\u4e00-\u9fff]\s*=', code_part):
            return False, f'Chinese identifier detected on line {i}; all variable names must be English.'
    
    return True, ""

def run_and_validate_trace(tracker_py_path: str) -> tuple:
    """Run the generated tracker and validate the produced trace.json.

    Returns (ok: bool, message: str, trace: Optional[dict]).
    """

    tracker_dir = os.path.dirname(tracker_py_path)
    trace_path = os.path.join(tracker_dir, 'trace.json')

    # Remove stale trace.json if it exists.
    if os.path.exists(trace_path):
        os.remove(trace_path)
    
    try:
        # Run tracker.
        result = subprocess.run(
            ['python', tracker_py_path],
            cwd=tracker_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            # Keep full error information; if too long, keep head and tail.
            error_msg = result.stderr if result.stderr else result.stdout
            if len(error_msg) > 2000:
                error_msg = error_msg[:1000] + "\n...(middle truncated)...\n" + error_msg[-1000:]
            return False, f"Execution failed:\n{error_msg}", None

        # Check trace.json existence.
        if not os.path.exists(trace_path):
            return False, "trace.json was not generated", None

        # Load and validate trace.
        with open(trace_path, 'r', encoding='utf-8') as f:
            trace = json.load(f)
        
        # Basic validation.
        if not isinstance(trace, dict):
            return False, "trace.json root is not an object", trace
        
        if trace.get('svl_version') != '5.0':
            return False, f"Invalid svl_version: {trace.get('svl_version')}", trace
        
        if 'initial_frame' not in trace:
            return False, "Missing initial_frame in trace.json", trace
        
        if 'deltas' not in trace:
            return False, "Missing deltas in trace.json", trace
        
        return True, "", trace
        
    except subprocess.TimeoutExpired:
        return False, "Execution timed out (30 seconds)", None
    except json.JSONDecodeError as e:
        return False, f"trace.json JSON decode error: {e}", None
    except Exception as e:
        return False, f"Validation failed: {e}", None


def generate_tracker_v2(
    algo_block: str,
    tag: str,
    unified_prompt: str,
    previous_error: str | None = None,
    retry_count: int = 0,
) -> tuple:
    """Generate tracker code using the unified VTA prompt (single task).

    Args:
        algo_block: The problem description / algorithm specification.
        tag:       A short identifier for logging.
        unified_prompt: The shared VTA specification prompt.
        previous_error: Error message from the previous attempt (for retry).
        retry_count:    Current retry index (0 = first attempt).

    Returns:
        (code: str, success: bool, stats: dict, error_msg: str)
    """

    retry_tag = f"[retry {retry_count}]" if retry_count > 0 else ""
    print(f"[{tag}]{retry_tag} Starting generation (VTA unified flow)...")
    start_time = time.time()
    
    # Build full prompt.
    error_feedback = ""
    if previous_error:
        error_feedback = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Previous generation error] (analyze carefully and avoid repeating it)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{previous_error}

 Fixing guidelines:
1. Carefully read the error message above (including error type, line number, variable names).
2. Cross-check the VTA specification for the relevant data structures and field definitions.
3. Pay special attention to: full trace structure, field names, operation parameter names.
4. Refer to the sections "VTA 5.0 Core Specification" and "Complete Operation List" in the prompt.

"""

    full_prompt = f"""{unified_prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Algorithm requirements]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{algo_block}

{error_feedback}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please follow the three-version workflow to generate the tracker code.
"""
    
    try:
        # LLM call (streaming).
        response = client.chat.completions.create(
            model=CURRENT_MODEL,
            messages=[
                {'role': 'user', 'content': full_prompt}
            ],
            stream=True,
            stream_options={"include_usage": True}
        )
        
        # Collect streaming response.
        content_parts = []
        final_usage = None
        
        for chunk in response:
            if not chunk.choices or len(chunk.choices) == 0:
                if hasattr(chunk, 'usage') and chunk.usage:
                    final_usage = chunk.usage
                continue
            
            delta = chunk.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                content_parts.append(delta.content)
            
            if hasattr(chunk, 'usage') and chunk.usage:
                final_usage = chunk.usage
        
        full_response = "".join(content_parts)
        gen_duration = time.time() - start_time
        
        # Extract final code.
        final_code = extract_final_code(full_response)
        
        # Token statistics.
        stats = {
            'input_tokens': getattr(final_usage, 'prompt_tokens', 0) if final_usage else 0,
            'output_tokens': getattr(final_usage, 'completion_tokens', 0) if final_usage else 0,
            'total_tokens': getattr(final_usage, 'total_tokens', 0) if final_usage else 0,
            'duration': gen_duration,
            'llm_calls': 1
        }
        
        print(f"[{tag}] ✅ Generation finished - {stats['total_tokens']:,} tokens, {gen_duration:.1f}s")

        # Quick static pre-check.
        pre_ok, pre_err = quick_pre_check(final_code)
        if not pre_ok:
            print(f"[{tag}] ⚠️ Pre-check failed: {pre_err}")
            return final_code, False, stats, f"Pre-check error:\n{pre_err}"

        # Run and validate in an isolated temporary directory.
        print(f"[{tag}] 🔍 Running tracker and validating trace.json...")
        with tempfile.TemporaryDirectory(prefix="vta_tracker_run__") as tmp_dir:
            tmp_tracker_path = os.path.join(tmp_dir, 'tracker.py')
            with open(tmp_tracker_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            run_ok, run_err, _ = run_and_validate_trace(tmp_tracker_path)

        if not run_ok:
            print(f"[{tag}] ❌ Validation failed: {run_err}")
            return final_code, False, stats, f"Execution / validation error:\n{run_err}"

        print(f"[{tag}] ✅ Validation passed!")
        return final_code, True, stats, ""

    except Exception as e:
        error_msg = f"[{tag}] Generation failed: {e}"
        print(f"{error_msg}")
        return "", False, {'error': str(e)}, error_msg

def generate_with_retry(
    algo_content: str,
    tag: str,
    unified_prompt: str,
    max_retries: int = 1,
) -> tuple:
    """Generate tracker code with retries.

    Returns (code: str, success: bool, accumulated_stats: dict, retry_count: int).
    """

    code: str | None = None
    success = False
    error_msg: str | None = None

    # Accumulate statistics over multiple attempts.
    accumulated_stats = {
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'duration': 0,
        'llm_calls': 0,
    }

    for retry in range(max_retries + 1):
        code, success, stats, last_error = generate_tracker_v2(
            algo_content,
            tag,
            unified_prompt,
            previous_error=error_msg,
            retry_count=retry,
        )

        # Accumulate stats for this attempt.
        accumulated_stats['input_tokens'] += stats.get('input_tokens', 0)
        accumulated_stats['output_tokens'] += stats.get('output_tokens', 0)
        accumulated_stats['total_tokens'] += stats.get('total_tokens', 0)
        accumulated_stats['duration'] += stats.get('duration', 0)
        accumulated_stats['llm_calls'] += 1

        if success:
            return code, True, accumulated_stats, retry

        # If failed and we still have retries, build feedback for the next round.
        if retry < max_retries:
            error_msg = last_error or "Unknown error"
            print("\n⚠️ Generation failed, will retry...")
            print(f"Error summary:\n{error_msg[:200]}...")

    # All attempts failed.
    return code or "", False, accumulated_stats, max_retries


def main() -> None:
    """Entry point: generate a single tracker.py from one input file."""

    parser = argparse.ArgumentParser(description='VTA tracker generator (single input)')
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Path to a single algorithm description .txt file',
    )
    parser.add_argument(
        '--output',
        type=str,
        default='tracker.py',
        help='Path to the output tracker.py file (default: tracker.py in current directory)',
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=1,
        help='Maximum number of retries when generation/validation fails (default: 1)',
    )

    args = parser.parse_args()

    repo_root = os.path.abspath('.')
    prompt_path = os.path.join(repo_root, 'prompt', 'VTA_specification.txt')
    unified_prompt = read_file(prompt_path)

    algo_text = read_file(args.input)
    blocks = split_algo_blocks(algo_text)
    if not blocks:
        print('❌ Error: input file is empty or contains no algorithm blocks.')
        return

    # For now, use only the first block in the file.
    base_tag = os.path.basename(args.input).replace('.txt', '')
    tag = sanitize_tag(base_tag)

    code, success, stats, retry_count = generate_with_retry(
        blocks[0],
        tag,
        unified_prompt,
        max_retries=args.max_retries,
    )

    if not code:
        print('❌ Error: failed to generate tracker code.')
        return

    # Write final tracker.py.
    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(repo_root, output_path)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)

    print('\n' + '=' * 80)
    if success:
        status_msg = '✅ Generation and validation succeeded'
    else:
        status_msg = '⚠️ Generation finished but validation did not fully succeed; please review tracker.py manually'

    print(status_msg)
    print(f'Output file: {output_path}')
    print(f'Total tokens: {stats.get("total_tokens", 0):,}')
    print(f'Total duration: {stats.get("duration", 0):.1f} seconds')
    print(f'LLM calls: {stats.get("llm_calls", 0)}')
    print('=' * 80)

if __name__ == '__main__':
    main()
