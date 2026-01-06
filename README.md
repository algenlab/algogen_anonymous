# Algogen Project Overview

## Quick Start

```bash
conda create -n algogen python=3.10
cd Algogen
conda activate algogen
python -m pip install -r requirements.txt
conda install -c conda-forge -y cairo pango pkg-config ffmpeg
conda install -c conda-forge -y glib
export SILICONFLOW_API_KEY="sk-yourtoken"
python run_pipeline.py
```

Notes:
- Recommended: Python 3.10, Manim 0.18.1.
- You need a SiliconFlow (硅基流动) API key and set `SILICONFLOW_API_KEY` in your environment.
- Manim may require system-level dependencies (e.g., `ffmpeg`, `cairo`, `pango`, and a LaTeX distribution if you render formulas).

Verification:

```bash
python -c "import jsonschema; import cairo; import manimpango; print('ok')"
```

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
