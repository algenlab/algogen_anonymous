#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

# Project paths
ALGOGEN_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ALGOGEN_ROOT.parent

# Ensure Algogen-local packages and test utilities are importable when running as a script
if str(ALGOGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(ALGOGEN_ROOT))

from renderer.rsl_style_controller.rsl_generator import llm_generate_rsl
from renderer.rsl_style_controller.rsl_interpreter import rsl_to_render_config
from eval.aes_eval_video import evaluate_aes
from renderer.rsl_style_controller.config_generator import (
    load_schema as load_render_schema,
    validate_config,
)
from renderer.rsl_style_controller.manim_renderer_enhanced import (
    render_svl_with_config,
)


def generate_tracker_and_trace(example_txt: Path, case_dir: Path) -> Path:
    """Generate tracker.py via tool_maker_agent and run it to produce trace.json."""

    example_txt = example_txt.resolve()
    case_dir.mkdir(parents=True, exist_ok=True)

    trace_path = case_dir / "trace.json"
    if trace_path.exists():
        print(f"[skip] Existing trace.json found in {case_dir}, skip tracker generation.")
        return trace_path

    tracker_path = case_dir / "tracker.py"

    cmd = [
        sys.executable,
        "toolmaker/tool_maker_agent.py",
        "--input",
        str(example_txt),
        "--output",
        str(tracker_path),
    ]
    print(f"[toolmaker] Generating tracker.py for {example_txt.name} ...")
    subprocess.run(cmd, cwd=str(ALGOGEN_ROOT), check=True)

    print(f"[tracker] Running tracker.py to produce trace.json ...")
    run_cmd = [sys.executable, tracker_path.name]
    subprocess.run(run_cmd, cwd=str(case_dir), check=True)

    if not trace_path.exists():
        raise RuntimeError(f"trace.json was not generated in {case_dir}")

    return trace_path


def render_trace_with_rsl(trace_path: Path, case_dir: Path) -> Path:
    """Run RSL LLM renderer + interpreter + Manim to produce a video inside case_dir."""

    trace_path = trace_path.resolve()
    case_dir.mkdir(parents=True, exist_ok=True)

    video_path = case_dir / "llm_video.mp4"
    if video_path.exists():
        print(f"[skip] Existing llm_video.mp4 found in {case_dir}, skip RSL/Manim rendering.")
        return video_path

    rsl_schema_path = ALGOGEN_ROOT / "renderer" / "rsl_style_controller" / "rsl_schema.json"
    rsl_path = trace_path.with_name(trace_path.stem + "_rsl.json")

    print(f"[RSL] Generating RSL for {trace_path.name} ...")
    llm_generate_rsl(str(trace_path), str(rsl_path), str(rsl_schema_path))

    with rsl_path.open("r", encoding="utf-8") as f:
        rsl = json.load(f)

    cfg = rsl_to_render_config(rsl)

    # ------------------------------------------------------------------
    # Fill algorithm_info from trace.json so it passes render_config_schema
    # validation. The schema expects:
    #   - family ∈ {graph_search, graph_topology, graph_mst, graph_flow,
    #               sorting, dp, data_structure, tree, array}
    #   - data_type ∈ {array, graph, tree, table, hashtable}
    # Our trace.json already has algorithm.family and initial_frame.data_state.type,
    # so we map them into these enums here.
    # ------------------------------------------------------------------
    with trace_path.open("r", encoding="utf-8") as f_trace:
        trace = json.load(f_trace)

    alg = trace.get("algorithm", {})
    init = trace.get("initial_frame", {})
    ds = init.get("data_state", {})

    raw_family = alg.get("family", "unknown")
    ds_type = ds.get("type", "unknown")

    valid_families = {
        "graph_search",
        "graph_topology",
        "graph_mst",
        "graph_flow",
        "sorting",
        "dp",
        "data_structure",
        "tree",
        "array",
    }
    valid_data_types = {"array", "graph", "tree", "table", "hashtable"}

    # Try to keep original family if it is already valid; otherwise, infer
    # from data_type, falling back to data_structure.
    if raw_family in valid_families:
        family = raw_family
    else:
        if ds_type in {"graph"}:
            family = "graph_search"
        elif ds_type in {"tree"}:
            family = "tree"
        elif ds_type in {"array"}:
            family = "array"
        elif ds_type in {"table"}:
            family = "dp"
        else:
            family = "data_structure"

    data_type = ds_type if ds_type in valid_data_types else "array"

    cfg["algorithm_info"] = {
        "name": alg.get("name", case_dir.name),
        "family": family,
        "data_type": data_type,
    }

    schema = load_render_schema()
    ok, err = validate_config(cfg, schema)
    if not ok:
        raise RuntimeError(f"render_config validation failed: {err}")

    cfg_path = trace_path.with_name(trace_path.stem + "_render_config.json")
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"[Manim] Rendering video to {video_path} ...")
    render_svl_with_config(
        str(trace_path),
        str(cfg_path),
        str(video_path),
        quality="high_quality",
        clean_cache=True,
    )

    return video_path


def run_aes_eval(video_path: Path, trace_path: Path, case_dir: Path) -> Path:
    """Run AES evaluation on the generated video and save result JSON in case_dir."""

    with trace_path.open("r", encoding="utf-8") as f:
        trace = json.load(f)

    alg = trace.get("algorithm", {})
    knowledge_point = alg.get("name") or case_dir.name

    print(f"[AES] Evaluating video {video_path.name} for knowledge point: {knowledge_point}")
    result = evaluate_aes(str(video_path), knowledge_point)

    aes_path = case_dir / "aes_result.json"
    with aes_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return aes_path


def collect_example_txt(examples_dir: Path, only: List[str] | None = None) -> List[Path]:
    examples_dir = examples_dir.resolve()
    if not examples_dir.exists():
        raise RuntimeError(f"Examples directory not found: {examples_dir}")

    txt_files = sorted(examples_dir.glob("*.txt"))

    if only:
        name_set = {n for n in only}
        txt_files = [p for p in txt_files if p.name in name_set or p.stem in name_set]

    return txt_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Algogen end-to-end pipeline: from example .txt to tracker.py, "
            "trace.json, LLM-rendered video and AES evaluation, all per-case under outputs/CASE."
        )
    )
    parser.add_argument(
        "--examples-dir",
        type=str,
        default="example",
        help="Directory under Algogen containing example .txt files (default: example)",
    )
    parser.add_argument(
        "--case-root",
        type=str,
        default="outputs/CASE",
        help="Root directory under Algogen for per-case artifacts (default: outputs/CASE)",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="Optional list of specific example txt basenames (with or without .txt) to run.",
    )

    args = parser.parse_args()

    examples_dir = (ALGOGEN_ROOT / args.examples_dir).resolve()
    case_root = (ALGOGEN_ROOT / args.case_root).resolve()
    os.makedirs(case_root, exist_ok=True)

    txt_files = collect_example_txt(examples_dir, args.only)
    if not txt_files:
        print(f"No .txt files found under {examples_dir}")
        sys.exit(1)

    print(f"Algogen pipeline starting...")
    print(f"  Examples dir: {examples_dir}")
    print(f"  Case root:    {case_root}")
    print(f"  Tasks:        {len(txt_files)} example txt files")

    for txt in txt_files:
        case_name = txt.stem
        case_dir = case_root / case_name
        print("\n" + "=" * 80)
        print(f"[CASE] {case_name}")
        print("=" * 80)

        existing_video = case_dir / "llm_video.mp4"
        if existing_video.exists():
            print(f"[skip] Existing llm_video.mp4 found in {case_dir}, skip this case.")
            continue

        try:
            trace_path = generate_tracker_and_trace(txt, case_dir)
            video_path = render_trace_with_rsl(trace_path, case_dir)
            aes_path = run_aes_eval(video_path, trace_path, case_dir)

            print(f"[DONE] {case_name}")
            print(f"  tracker.py : {case_dir / 'tracker.py'}")
            print(f"  trace.json : {trace_path}")
            print(f"  video      : {video_path}")
            print(f"  AES result : {aes_path}")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Subprocess failed for case {case_name}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] Case {case_name} failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
