#!/usr/bin/env python3
import json
from typing import Tuple, List, Dict, Any

ALLOWED_OPS = {
    "updateStyle","updateValues","moveElements","shiftElements","updateBoundary","removeBoundary",
    "updateNodeStyle","updateNodeProperties","updateEdgeStyle","updateEdgeProperties",
    "addNode","removeNode","addEdge","removeEdge",
    "updateTableCell","highlightTableCell","showDependency",
    "appendToList","popFromList","clearList",
    "addChild","removeChild","reparent","swapNodes","highlightPath",
    "insertIntoBucket","updateInBucket","removeFromBucket","showHash","highlightCollision","highlightBucket",
    "addAuxView","removeAuxView","showComment"
}

def semantic_check_rsl(rsl: Dict[str, Any]) -> Tuple[bool, str]:
    issues: List[str] = []

    for i, rule in enumerate(rsl.get("rules", [])):
        when = rule.get("when", {})
        op = when.get("op")
        if op and op not in ALLOWED_OPS:
            issues.append(f"rules[{i}].when.op '{op}' not allowed")

        do = rule.get("do", {})
        anim = do.get("animation", {})
        if "run_time" in anim:
            try:
                rt = float(anim["run_time"])
                if not (0.1 <= rt <= 2.0):
                    issues.append(f"rules[{i}].do.animation.run_time out of range")
            except Exception:
                issues.append(f"rules[{i}].do.animation.run_time not a number")

        style = do.get("style", {})
        if "scale" in style:
            try:
                sc = float(style["scale"])
                if not (0.5 <= sc <= 2.0):
                    issues.append(f"rules[{i}].do.style.scale out of range")
            except Exception:
                issues.append(f"rules[{i}].do.style.scale not a number")

    tl = rsl.get("timeline", {})
    if "max_fps_for_changes" in tl:
        try:
            fps = int(tl["max_fps_for_changes"])
            if not (1 <= fps <= 30):
                issues.append("timeline.max_fps_for_changes out of range")
        except Exception:
            issues.append("timeline.max_fps_for_changes not an integer")

    return (len(issues) == 0, "; ".join(issues))



