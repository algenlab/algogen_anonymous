# Algogen Project Overview

## Quick Start

### 0. Install Python dependencies

Algogen ships a `requirements.txt` under `Algogen/` that mirrors the core `algogen_env` setup (centered around Manim).

```bash
cd Algogen
python -m pip install -r requirements.txt
```

Notes:
- Recommended: Python 3.10, Manim 0.18.1.
- Manim may require system-level dependencies (e.g., `ffmpeg`, `cairo`, `pango`, and a LaTeX distribution if you render formulas).

### 1. Run the full pipeline (batch all txt under `example/`)

Assuming you start from the project root (which contains the `Algogen/` directory):

```bash
cd Algogen
python run_pipeline.py
```

### 2. Run only selected txt files

```bash
cd Algogen
python run_pipeline.py --only array_leetcode_204_seed_01 sorting_leetcode_179_seed_02
```


### 3. Evaluate an arbitrary video with AES

```bash
cd Algogen
python eval/aes_eval_video.py bubble_sort \
  --video-path /path/to/your_video.mp4 \
  --knowledge-point "Custom Algorithm Visualization"
```

---

## Example Output Layout

Using `Algogen/example/array_leetcode_204_seed_01.txt` as an example, after running the pipeline you should get:

```text
Algogen/
  outputs/
    CASE/
      array_leetcode_204_seed_01/
        tracker.py
        trace.json
        trace_rsl.json
        trace_render_config.json
        llm_video.mp4
        aes_result.json
```
