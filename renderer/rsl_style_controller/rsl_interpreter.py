#!/usr/bin/env python3
import json, argparse
from pathlib import Path
from typing import Dict, Any

def rsl_to_render_config(rsl: Dict[str, Any]) -> Dict[str, Any]:
    theme = rsl.get("theme", {})
    timeline = rsl.get("timeline", {})
    layout = rsl.get("layout", {}).get("main", {})
    anns = rsl.get("annotations", [])

    render_config = {
        "algorithm_info": { "name": "N/A", "family": "N/A", "data_type": "N/A" },
        "layout_strategy": {
            "main_view": {
                "type": layout.get("type", "force_directed"),
                "params": layout.get("params", {})
            },
            "auxiliary_views": { "position": "left", "max_width": 0.30, "vertical_spacing": 0.20 },
            "pseudocode": { "position": "top-left", "font_size": 14, "max_lines": 24 }
        },
        "style_overrides": {
            "color_scheme": {
                "background": theme.get("background", "#1A1A1A"),
                "text": theme.get("text", "#FFFFFF"),
                "primary": theme.get("primary", "#3498DB"),
                "secondary": theme.get("secondary", "#95A5A6"),
                "accent": theme.get("accent", "#E74C3C")
            },
            "element_styles": {},
            "animation_timing": {
                "transition": float(timeline.get("transition", 0.5)),
                "pause": float(timeline.get("pause", 0.3)),
                "node_highlight": 0.3,
                "edge_update": 0.4,
                "cell_update": 0.3,
                "array_swap": 0.5
            }
        },
        "visual_enhancements": {
            "custom_annotations": []
        }
    }

    for a in anns:
        render_config["visual_enhancements"]["custom_annotations"].append(a)

    return render_config

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("rsl", help="RSL json")
    ap.add_argument("--out", help="Output render_config path")
    args = ap.parse_args()
    rsl = json.load(open(args.rsl,"r",encoding="utf-8"))
    cfg = rsl_to_render_config(rsl)
    out = args.out or args.rsl.replace("_rsl.json", "_render_config.json")
    json.dump(cfg, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✓ Render config generated: {out}")



