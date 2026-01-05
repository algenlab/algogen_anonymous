#!/usr/bin/env python3
import os, sys, json, argparse, subprocess, shutil, multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CODE2VIDEO_DIR = str(Path(PROJECT_ROOT) / "exp" / "code2video")
if CODE2VIDEO_DIR not in sys.path:
    sys.path.insert(0, CODE2VIDEO_DIR)

from renderer.rsl_style_controller.config_generator import (
    load_schema as load_render_schema,
    validate_config,
)
from renderer.rsl_style_controller.manim_renderer_enhanced import (
    render_svl_with_config,
)
from renderer.rsl_style_controller.rsl_generator import llm_generate_rsl
from renderer.rsl_style_controller.rsl_interpreter import rsl_to_render_config
from eval_single_video_silicon import evaluate_aes as evaluate_aes_full


def eval_aes(video_path: str, trace_path: str = None) -> float:
    try:
        knowledge_point = "Algorithm Visualization"
        if trace_path and os.path.exists(trace_path):
            with open(trace_path, "r", encoding="utf-8") as f:
                trace = json.load(f)
            alg = trace.get("algorithm", {})
            name = alg.get("name", "Algorithm Visualization")
            knowledge_point = name
        
        result = evaluate_aes_full(video_path, knowledge_point)
        
        if result and "scores" in result and "overall" in result["scores"]:
            return float(result["scores"]["overall"])
        else:
            return -1.0
    except Exception as e:
        print(f"⚠️  AES evaluation failed: {e}", file=sys.stderr)
        return -1.0


def _fill_algorithm_info(cfg: dict, trace_path: str) -> dict:
    with open(trace_path, "r", encoding="utf-8") as f:
        trace = json.load(f)

    alg = trace.get("algorithm", {})
    init = trace.get("initial_frame", {})
    ds = init.get("data_state", {})
    data_type = ds.get("type", "array")
    name = alg.get("name", "Unknown")

    if data_type == "graph":
        family = "graph_search"
    elif data_type == "table":
        family = "dp"
    elif data_type == "tree":
        family = "tree"
    elif data_type == "hashtable":
        family = "data_structure"
    elif data_type == "array":
        family = "sorting" if "sort" in name.lower() else "array"
    else:
        family = "data_structure"

    cfg["algorithm_info"] = {
        "name": name,
        "family": family,
        "data_type": (
            data_type
            if data_type in ["array", "graph", "tree", "table", "hashtable"]
            else "array"
        ),
    }
    return cfg


def _get_video_paths(trace_path: str):

    trace_path = os.path.abspath(trace_path)
    trace_dir = os.path.dirname(trace_path)
    video_dir = os.path.join(trace_dir, "videos_llm")
    os.makedirs(video_dir, exist_ok=True)

    stem = Path(trace_path).stem
    if stem.endswith("_trace"):
        base_name = stem[:-6]
    else:
        base_name = stem

    video_path = os.path.join(video_dir, base_name + ".mp4")
    tuned_video_path = os.path.join(video_dir, base_name + "_tuned.mp4")
    return video_path, tuned_video_path


def pipeline_once(trace_path: str, force_regen: bool = False) -> str:
    trace_path = os.path.abspath(trace_path)
    rsl_path = trace_path.replace(".json", "_rsl.json")
    cfg_path = trace_path.replace(".json", "_render_config.json")
    video_path, _ = _get_video_paths(trace_path)


    if not os.path.exists(rsl_path) or force_regen:
        llm_generate_rsl(
            trace_path,
            rsl_path,
            os.path.join(os.path.dirname(__file__), "rsl_schema.json"),
        )


    with open(rsl_path, "r", encoding="utf-8") as f:
        rsl = json.load(f)
    cfg = rsl_to_render_config(rsl)

    cfg = _fill_algorithm_info(cfg, trace_path)

    schema = load_render_schema()
    ok, err = validate_config(cfg, schema)
    if not ok:
        raise RuntimeError(f"render_config validation failed: {err}")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    render_svl_with_config(
        trace_path,
        cfg_path,
        video_path,
        quality="high_quality",
        clean_cache=True,
    )
    return video_path


def pipeline_with_one_tune(trace_path: str, enable_tune: bool = True) -> str:
    vid0 = pipeline_once(trace_path, force_regen=True)
    score0 = eval_aes(vid0, trace_path) if enable_tune else -1.0

    if not enable_tune or score0 < 0:
        if enable_tune and score0 < 0:
            print(f"Initial AES evaluation failed, skip tuning and return original video")
        return vid0

    rsl_path = trace_path.replace(".json", "_rsl.json")
    with open(rsl_path, "r", encoding="utf-8") as f:
        rsl = json.load(f)

    tl = rsl.setdefault("timeline", {})
    tl["transition"] = min(2.0, float(tl.get("transition", 0.5)) + 0.1)
    tl["pause"] = min(1.0, float(tl.get("pause", 0.3)) + 0.05)

    layout = rsl.setdefault("layout", {}).setdefault("main", {})
    params = layout.setdefault("params", {})
    if layout.get("type", "") in ("force_directed", "hierarchical", "circular"):
        params["node_spacing"] = min(10.0, float(params.get("node_spacing", 3.5)) + 0.3)

    tuned_rsl_path = trace_path.replace(".json", "_rsl_tuned.json")
    with open(tuned_rsl_path, "w", encoding="utf-8") as f:
        json.dump(rsl, f, ensure_ascii=False, indent=2)

    cfg = rsl_to_render_config(rsl)
    cfg = _fill_algorithm_info(cfg, trace_path)

    schema = load_render_schema()
    ok, err = validate_config(cfg, schema)
    if not ok:
        return vid0

    cfg_path = trace_path.replace(".json", "_render_config_tuned.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    _, vid1 = _get_video_paths(trace_path)

    render_svl_with_config(
        trace_path,
        cfg_path,
        vid1,
        quality="high_quality",
        clean_cache=True,
    )

    score1 = eval_aes(vid1, trace_path)
    if score1 >= score0:
        print(f"✅ AES score improved after tuning: {score0:.1f} → {score1:.1f}, using tuned version")
        return vid1
    else:
        print(f"⚠️  AES score did not improve after tuning: {score0:.1f} → {score1:.1f}, using original version")
        return vid0


def init_worker(temp_base_dir):
    """Initialize worker process with its own Manim media/cache directory."""
    if temp_base_dir is None:
        return
    
    pid = multiprocessing.current_process().pid
    worker_temp_dir = os.path.join(temp_base_dir, f"worker_{pid}")
    os.makedirs(worker_temp_dir, exist_ok=True)
    
    os.environ['MANIM_MEDIA_DIR'] = worker_temp_dir
    
    try:
        from manim import config
        config.media_dir = worker_temp_dir
        config.log_to_file = False
    except ImportError:
        pass


def _process_single_trace_for_pool(args):
    """Wrapper for process pool: render one trace in an isolated process."""
    trace_path, enable_tune = args
    try:
        out_video = pipeline_with_one_tune(trace_path, enable_tune=enable_tune)
        return {
            "trace": trace_path,
            "video": out_video,
            "ok": True,
            "error": "",
        }
    except Exception as e:
        return {
            "trace": trace_path,
            "video": "",
            "ok": False,
            "error": str(e),
        }


def _collect_trace_files_in_dir(dir_path: str):
    """Collect all tracker__*_trace.json files in a directory (non-recursive)."""
    dir_path = os.path.abspath(dir_path)
    files = []
    for name in os.listdir(dir_path):
        full = os.path.join(dir_path, name)
        if not os.path.isfile(full):
            continue
        if name.startswith("tracker__") and name.endswith("_trace.json"):
            files.append(full)
    files.sort()
    return files


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="SVL → Manim rendering pipeline (single file or batch, videos under videos_llm)"
    )
    ap.add_argument(
        "trace",
        nargs="?",
        help="Single SVL trace.json (optional; if omitted, use --batch-dir)",
    )
    ap.add_argument(
        "--batch-dir",
        help="Batch directory (process tracker__*_trace.json in this directory, non-recursive)",
    )
    ap.add_argument(
        "--tune-once",
        action="store_true",
        help="Enable a single round of self-tuning (off by default)",
    )
    ap.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Number of worker processes (default 8)",
    )
    args = ap.parse_args()

    if args.batch_dir is None and args.trace is None:
        ap.error("You must specify either a single trace (positional) or --batch-dir")

    if args.batch_dir is None and args.trace is not None:
        out = pipeline_with_one_tune(args.trace, enable_tune=args.tune_once)
        print(f"✓ Final video: {out}")
        sys.exit(0)

    trace_files = _collect_trace_files_in_dir(args.batch_dir)
    if not trace_files:
        print(f"⚠️  No tracker__*_trace.json found in directory: {args.batch_dir}")
        sys.exit(1)

    print(f"🧾 Found {len(trace_files)} trace.json to process")
    for p in trace_files:
        print("  -", p)

    max_workers = max(1, int(args.max_workers))
    print(f"\n🚀 Starting concurrent rendering, workers: {max_workers}\n")

    if trace_files:
        first_trace_dir = os.path.dirname(trace_files[0])
        temp_base_dir = os.path.join(first_trace_dir, ".temp_workers_llm")
        os.makedirs(temp_base_dir, exist_ok=True)
    else:
        temp_base_dir = None

    results = []
    completed = 0
    total = len(trace_files)
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=init_worker,
        initargs=(temp_base_dir,) if temp_base_dir else (None,)
    ) as ex:
        future_to_trace = {
            ex.submit(_process_single_trace_for_pool, (p, args.tune_once)): p
            for p in trace_files
        }
        for fut in as_completed(future_to_trace):
            res = fut.result()
            results.append(res)
            completed += 1
            if res["ok"]:
                trace_name = os.path.basename(res['trace'])
                print(f"[{completed}/{total}] ✅ {trace_name}")
            else:
                trace_name = os.path.basename(res['trace'])
                print(f"[{completed}/{total}] ❌ {trace_name}: {res['error'][:80]}")

    if temp_base_dir and os.path.exists(temp_base_dir):
        try:
            shutil.rmtree(temp_base_dir)
        except Exception as e:
            print(f"⚠️  Failed to clean temporary directory: {e}")

    ok_cnt = sum(1 for r in results if r["ok"])
    fail_cnt = len(results) - ok_cnt
    print("\n================ Batch rendering finished ================")
    print(f"Succeeded: {ok_cnt}")
    print(f"Failed: {fail_cnt}")
    if fail_cnt:
        print("Failed items:")
        for r in results:
            if not r["ok"]:
                print(f"  - {r['trace']}: {r['error']}")
