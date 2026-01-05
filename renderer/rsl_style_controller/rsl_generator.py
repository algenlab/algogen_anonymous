#!/usr/bin/env python3
import os, json, argparse
from pathlib import Path
from typing import Dict, Any
import jsonschema
from openai import OpenAI

from .rsl_semantic_checks import semantic_check_rsl, ALLOWED_OPS

MODEL_TEXT = "deepseek-ai/DeepSeek-V3.1-Terminus"

def load_schema(schema_path: str) -> dict:
    return json.load(open(schema_path, "r", encoding="utf-8"))

def extract_trace_features(trace: dict) -> dict:
    alg = trace.get("algorithm", {})
    init = trace.get("initial_frame", {})
    deltas = trace.get("deltas", [])
    ds = init.get("data_state", {})
    ops = set()
    for d in deltas:
        for opg in d.get("operations", []):
            if isinstance(opg, list):
                for op in opg:
                    if isinstance(op, dict):
                        name = op.get("op")
                        if name:
                            ops.add(name)
    data_type = ds.get("type", "unknown")
    scale = {}
    if data_type == "array":
        struct = ds.get("structure", ds.get("data", []))
        scale["array_length"] = len(struct) if isinstance(struct, list) else 0
    elif data_type == "graph":
        struct = ds.get("structure", {})
        scale["node_count"] = len(struct.get("nodes", []))
        scale["edge_count"] = len(struct.get("edges", []))
    elif data_type == "table":
        data = ds.get("data", [])
        scale["rows"] = len(data) if isinstance(data, list) else 0
        scale["cols"] = len(data[0]) if scale["rows"] and isinstance(data[0], list) else 0
    return {
        "algorithm": {"name": alg.get("name","Unknown"), "family": alg.get("family","Unknown")},
        "data_type": data_type,
        "data_scale": scale,
        "frame_count": len(deltas) + 1,
        "operations_used": sorted(ops),
        "has_pseudocode": bool(init.get("pseudocode"))
    }

def build_prompt(features: Dict[str, Any], rsl_schema: Dict[str, Any]) -> str:
    return (
f"""You are an expert in algorithm visualization rendering. Based on the "SVL rendering requirements" and the RSL schema below, generate an RSL rendering script (JSON, output valid JSON only).

[SVL CONTEXT - READ ONLY, DO NOT MODIFY]
- Algorithm: {features['algorithm']['name']} ({features['algorithm']['family']})
- Data type: {features['data_type']}
- Data scale: {features['data_scale']}
- Frame count: {features['frame_count']}
- Operations used: {', '.join(features['operations_used'])}
- Pseudocode: {'present' if features['has_pseudocode'] else 'absent'}

[RSL DESIGN REQUIREMENTS]
- Goal: improve layout clarity, contrast and pacing; you may add a small number of annotations.
- Only generate RSL (JSON), and all fields must conform to the schema.
- Colors must use #RRGGBB; timings must follow the ranges in the schema.
- You must NOT change the order or semantics of operations in the SVL trace.
- **Important**: rules[].when.op must use ONLY the following allowed operations:
  {', '.join(sorted(ALLOWED_OPS))}
  Do NOT use semantic aliases like 'initialize', 'visit_node', 'relax_edge'; you must use the actual SVL op names.

[RSL Schema]
```json
{json.dumps(rsl_schema, ensure_ascii=False, indent=2)}
```

Now output the complete RSL JSON:
"""
    )


def _extract_first_json_block(text: str) -> str:
    """Extract the first top-level JSON object block from text, or empty string.

    This mirrors the helper used in AES evaluation to make parsing more robust
    against models that wrap JSON in explanations or markdown.
    """
    import re

    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else ""


def _clean_json_string_for_rsl(text: str) -> str:
    import re
    text = re.sub(r'(\n\s*)([A-Za-z_][A-Za-z0-9_]*)":', r'\1"\2":', text)

    return text

def llm_generate_rsl(trace_path: str, out_path: str, schema_path: str) -> Dict[str, Any]:
    trace = json.load(open(trace_path, "r", encoding="utf-8"))
    schema = load_schema(schema_path)
    features = extract_trace_features(trace)

    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("Environment variable SILICONFLOW_API_KEY is not set")

    client = OpenAI(base_url="https://api.siliconflow.cn/v1", api_key=api_key)
    prompt = build_prompt(features, schema)

    # 1) First LLM call to generate RSL
    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        temperature=0.6,
        messages=[
            {"role": "system", "content": "You are a renderer-style script generator that strictly follows the given JSON schema. Output only valid JSON, with no explanations."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=3000,
    )
    content = resp.choices[0].message.content.strip()

    out_path_obj = Path(out_path)
    out_dir = out_path_obj.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save raw content for debugging
    raw_path = out_path_obj.with_suffix(".raw.txt")
    raw_path.write_text(content, encoding="utf-8")

    # Try to extract JSON block and parse (with a light heuristic cleanup)
    json_str = _clean_json_string_for_rsl(_extract_first_json_block(content) or content)
    rsl = None
    parse_error = None

    try:
        rsl = json.loads(json_str)
    except Exception as e:
        parse_error = str(e)

    # 2) If initial parse failed, try a repair call similar to aes_eval_video.py
    if rsl is None:
        repair_prompt = (
            "You are a strict JSON formatter. "
            "Given the following text that should contain a JSON object representing an RSL script, "
            "output ONLY a valid JSON object that matches this JSON schema exactly. "
            "Do not add any explanations, comments, or markdown.\n\n"
            "SCHEMA:\n" + json.dumps(schema) + "\n\n"
            "TEXT:\n" + content
        )

        repair_resp = client.chat.completions.create(
            model=MODEL_TEXT,
            temperature=0,
            messages=[{"role": "user", "content": repair_prompt}],
            max_tokens=3000,
        )
        repaired = repair_resp.choices[0].message.content.strip()
        # Save repaired text for debugging
        repair_path = out_path_obj.with_suffix(".repair.txt")
        repair_path.write_text(repaired, encoding="utf-8")

        repaired_json_str = _clean_json_string_for_rsl(_extract_first_json_block(repaired) or repaired)
        try:
            rsl = json.loads(repaired_json_str)
        except Exception as e:
            raise RuntimeError(f"Failed to parse RSL JSON after repair attempt. Original error: {parse_error}; repair error: {e}")

    # 3) Validate against schema and semantic rules
    jsonschema.validate(rsl, schema)

    ok, msg = semantic_check_rsl(rsl)
    if not ok:
        raise RuntimeError(f"RSL semantic check failed: {msg}")

    # 4) Save final RSL JSON
    json.dump(rsl, open(out_path_obj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return rsl

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", help="Path to SVL trace.json")
    ap.add_argument("--schema", default=str(Path(__file__).with_name("rsl_schema.json")))
    ap.add_argument("--out", help="Output RSL path", default=None)
    args = ap.parse_args()
    out = args.out or args.trace.replace(".json", "_rsl.json")
    rsl = llm_generate_rsl(args.trace, out, args.schema)
    print(f"✓ RSL generated: {out}")
