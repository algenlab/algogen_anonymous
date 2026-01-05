
import json
import os
from pathlib import Path
import copy
import math
import sys
import re
import shutil
from typing import List, Dict, Any, Tuple, Optional

import numpy as np

from manim import *

class SVLManimRenderer(Scene):
    
    def __init__(self, svl_data: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        
        self.svl_data = svl_data
        self._validate_version(svl_data.get("svl_version"))
        
        self.algorithm_info = svl_data["algorithm"]
        self.initial_frame = svl_data["initial_frame"]
        self.styles = self.initial_frame["styles"]
        self.pseudocode = self.initial_frame.get("pseudocode", [])
        self.variables_schema = self.initial_frame.get("variables_schema", [])
        self.data_schema = self.initial_frame.get("data_schema", {})
        
        self.current_data_state = copy.deepcopy(self.initial_frame["data_state"])
        self.current_aux_views = copy.deepcopy(self.initial_frame.get("auxiliary_views", []))
        
        self.skip_smooth_transition = False
        
        if not self.current_data_state.get("type"):
            dp_aux = None
            for v in self.current_aux_views:
                if isinstance(v, dict) and v.get("type") == "table" and v.get("view_id") == "dp_table":
                    dp_aux = v
                    break
            if dp_aux:
                self.current_data_state = {
                    "type": "table",
                    "view_id": dp_aux.get("view_id", "main_table"),
                    "title": dp_aux.get("title"),
                    "data": copy.deepcopy(dp_aux.get("data", [])),
                    "options": copy.deepcopy(dp_aux.get("options", {})),
                }
                self.current_aux_views = [v for v in self.current_aux_views if v is not dp_aux]
        
        alias = self.current_data_state.get("type")
        if alias in ("dp", "dp_table", "dp_edit_distance"):
            self.current_data_state["type"] = "table"
            if "data" not in self.current_data_state:
                struct = self.current_data_state.get("structure")
                if isinstance(struct, list):
                    self.current_data_state["data"] = copy.deepcopy(struct)
        
        if self.current_data_state.get("type") == "table" and not self.current_data_state.get("view_id"):
            self.current_data_state["view_id"] = "dp_table"
        
        self.data_type = self.current_data_state.get("type", "none")
        self.current_variables = {var["name"]: "-" for var in self.variables_schema}
        
        self.temp_elements = []
        self.dependencies = []
        self.current_comments = []
        self.current_comment_text = None
        
        self.mobject_cache = {}
        self.array_mobjects = []
        self.graph_mobjects = {}
        self.table_mobjects = {}
        self.tree_mobjects = {}
        
        try:
            self.elem_spacing = float(os.environ.get("SVL_ARRAY_SPACING_CM", "1.2"))
        except Exception:
            self.elem_spacing = 1.2
        
        try:
            self.graph_gap_x = float(os.environ.get("SVL_GRAPH_GAP_X_CM", "3.5"))
            self.graph_gap_y = float(os.environ.get("SVL_GRAPH_GAP_Y_CM", "3.5"))
        except Exception:
            self.graph_gap_x = 3.5
            self.graph_gap_y = 3.5
        
        self.node_size = 0.5  # radius (diameter=1.0cm), aligned with renderer.py
        self.cell_size = 0.8  # aligned with renderer.py
        
        try:
            self.transition_time = float(os.environ.get("SVL_TRANSITION_TIME", "0.5"))
            self.pause_time = float(os.environ.get("SVL_PAUSE_TIME", "0.3"))
            self.fast_mode = os.environ.get("SVL_FAST_MODE", "0") == "1"
        except Exception:
            self.transition_time = 0.5
            self.pause_time = 0.3
            self.fast_mode = False
    
    def _validate_version(self, version):
        if version != "5.0":
            print(f"Warning: renderer is designed for SVL 5.0, but file version is {version}.")
    
    def _parse_color(self, color_raw: Any) -> str:
        if color_raw is None:
            return WHITE
        
        if isinstance(color_raw, (int, float)):
            return WHITE
        
        if not isinstance(color_raw, str):
            return WHITE
        
        s = color_raw.strip()
        
        if s.lower() in ("none", "transparent"):
            return WHITE
        
        if s.startswith("#"):
            if len(s) == 7:  # #RRGGBB
                return s
            elif len(s) == 4:  # #RGB -> #RRGGBB
                r, g, b = s[1], s[2], s[3]
                return f"#{r}{r}{g}{g}{b}{b}"
        
        if s.lower().startswith("rgba("):
            try:
                rgba = s[5:-1].split(",")
                r, g, b = int(rgba[0]), int(rgba[1]), int(rgba[2])
                return f"#{r:02X}{g:02X}{b:02X}"
            except:
                return WHITE
        
        if s.lower().startswith("rgb("):
            try:
                rgb = s[4:-1].split(",")
                r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
                return f"#{r:02X}{g:02X}{b:02X}"
            except:
                return WHITE
        
        color_map = {
            "red": RED, "blue": BLUE, "green": GREEN, "yellow": YELLOW,
            "orange": ORANGE, "purple": PURPLE, "pink": PINK,
            "gray": GRAY, "grey": GRAY, "white": WHITE, "black": BLACK,
            "lightgray": LIGHT_GRAY, "lightgrey": LIGHT_GRAY,
            "darkgray": DARK_GRAY, "darkgrey": DARK_GRAY
        }
        
        return color_map.get(s.lower(), s)
    
    def _get_element_style(self, style_key: str) -> Tuple[str, str, str]:
        element_styles = self.styles.get("elementStyles", {})
        style = element_styles.get(style_key, {})
        
        if not style:
            style = self.styles.get(style_key, {})
        
        fill_raw = style.get("fill") or style.get("backgroundColor") or style.get("fillColor") or style.get("bgColor") or "#f0f0f0"
        stroke_raw = style.get("stroke") or style.get("strokeColor") or style.get("borderColor") or "#666666"
        text_raw = style.get("textColor") or style.get("labelColor") or style.get("color")
        
        stroke = self._parse_color(stroke_raw)
        fill = self._parse_color(fill_raw)
        text = self._parse_color(text_raw) if text_raw is not None else BLACK
        
        return stroke, fill, text

    def _get_array_cell_render_params(self, style_key: Any) -> Tuple[float, float]:
        s = str(style_key or "").lower()
        if (not s) or ("idle" in s) or (s in ("default", "normal")):
            return 0.12, 1.8  # lighter for idle
        if ("compare" in s) or ("comparing" in s) or ("current" in s) or ("pivot" in s) or ("target" in s) or ("active" in s):
            return 0.58, 3.2  # stronger/highlighted
        if ("swap" in s) or ("swapped" in s) or ("selected" in s) or ("changed" in s) or ("visited" in s) or ("done" in s):
            return 0.42, 2.6
        return 0.28, 2.1
    
    def _get_edge_style(self, style_key: str) -> Tuple[str, str, float]:
        edge_styles = self.styles.get("edgeStyles", {})
        if style_key in edge_styles:
            st = edge_styles[style_key]
        else:
            st = self.styles.get("elementStyles", {}).get(style_key, {})
        
        stroke_raw = st.get("stroke") or st.get("color") or st.get("strokeColor") or "#666666"
        text_raw = st.get("textColor") or st.get("labelColor") or st.get("color") or "#000000"
        lw = st.get("strokeWidth") or st.get("lineWidth") or 1.5
        
        return self._parse_color(stroke_raw), self._parse_color(text_raw), float(lw)
    
    def _get_temp_style(self, style_key: str) -> Dict:
        temp_styles = self.styles.get("tempStyles", {})
        return temp_styles.get(style_key, {})
    
    def _resolve_dep_style(self, style_key: str) -> Tuple[str, float]:
        if not style_key:
            return RED, 1.5
        
        sources = [
            self.styles.get("tempStyles", {}),
            self.styles.get("elementStyles", {}),
            self.styles.get("edgeStyles", {})
        ]
        
        keys_to_try = []
        if style_key.startswith("dep_") or style_key.startswith("edge_"):
            keys_to_try.append(style_key)
        else:
            keys_to_try.append(f"dep_{style_key}")
            keys_to_try.append(f"edge_{style_key}")
            keys_to_try.append(style_key)
        
        for key in keys_to_try:
            for source in sources:
                if key in source:
                    st = source[key]
                    color_raw = (st.get("color") or 
                                st.get("stroke") or 
                                st.get("strokeColor") or 
                                st.get("backgroundColor") or 
                                st.get("borderColor") or       # fallback
                                "#ff0000")
                    lw = st.get("strokeWidth") or st.get("lineWidth") or 2.5  # default slightly thicker
                    return self._parse_color(color_raw), float(lw)
        

        return RED, 2.5
    
    def _get_cell_style(self, style_key: str) -> Tuple[str, str]:

        element_styles = self.styles.get("elementStyles", {})
        style = element_styles.get(style_key, {})
        
        fill_raw = style.get("fill") or style.get("backgroundColor") or "#ffff00"
        stroke_raw = style.get("stroke") or style.get("strokeColor") or style.get("borderColor") or "#ffcc00"
        
        return self._parse_color(fill_raw), self._parse_color(stroke_raw)
    
    def construct(self):
        """Main Manim entry: build the full animation sequence (with smooth transitions)."""
        self._render_frame(frame_index=0, delta_info=None)
        self.wait(self.pause_time)
        
        total_deltas = len(self.svl_data["deltas"])
        total_frames = total_deltas + 1  # including initial frame
        for i, delta in enumerate(self.svl_data["deltas"]):
            current_frame = i + 2  # initial frame is #1, first delta is #2
            if current_frame % 10 == 0 or i == 0 or i == total_deltas - 1:
                print(f"  Frame: {current_frame}/{total_frames}", flush=True)
            
            # Apply data changes and collect animations.
            self._apply_delta_with_animation(delta)
            
            self._update_frame_with_transition(frame_index=i + 1, delta_info=delta)
            self.wait(self.pause_time)
    
    def _apply_delta_with_animation(self, delta):
        """Apply a delta and record corresponding animations (batched)."""
        for var_name, var_value in delta.get("meta", {}).items():
            if var_name in self.current_variables:
                self.current_variables[var_name] = var_value
        
        self.temp_elements = [e for e in self.temp_elements if e.get("type") == "boundary_box"]
        self.dependencies.clear()
        self.current_comment_text = None  # reset old comment text
        
        for op_group in delta.get("operations", []):
            for op in (op_group if isinstance(op_group, list) else [op_group]):
                if isinstance(op, dict) and op.get("op"):
                    self._process_operation_with_animation(op)
    
    def _process_operation_with_animation(self, op):
        """Handle a single operation and dispatch to animation handlers."""
        op_name = op.get("op")
        params = op.get("params", {})
        
        op_map = {
            "updateStyle": self._animate_update_style,
            "moveElements": self._animate_move_elements,
            "shiftElements": self._animate_shift_elements,
            "updateValues": self._animate_update_values,
            "updateNodeStyle": self._animate_update_node_style,
            "updateNodeProperties": self._animate_update_node_properties,
            "updateEdgeStyle": self._animate_update_edge_style,
            "updateTableCell": self._animate_update_table_cell,
            "highlightTableCell": self._animate_highlight_table_cell,
            "showDependency": self._animate_show_dependency,
            "updateBoundary": self._animate_update_boundary,
            "removeBoundary": self._animate_remove_boundary,
            "addNode": self._animate_add_node,
            "removeNode": self._animate_remove_node,
            "addEdge": self._animate_add_edge,
            "removeEdge": self._animate_remove_edge,
            "addAuxView": self._animate_add_aux_view,
            "removeAuxView": self._animate_remove_aux_view,
            "appendToList": self._animate_append_to_list,
            "popFromList": self._animate_pop_from_list,
            "clearList": self._animate_clear_list,
            "insertIntoBucket": self._animate_insert_into_bucket,
            "updateInBucket": self._animate_update_in_bucket,
            "removeFromBucket": self._animate_remove_from_bucket,
            "showHash": self._animate_show_hash,
            "highlightCollision": self._animate_highlight_collision,
            "highlightBucket": self._animate_highlight_bucket,
            "showComment": self._animate_show_comment,
            "addChild": self._animate_add_child,
            "removeChild": self._animate_remove_child,
            "reparent": self._animate_reparent,
            "swapNodes": self._animate_swap_nodes,
            "highlightPath": self._animate_highlight_path,
        }
        
        handler = op_map.get(op_name)
        if handler:
            handler(params)
        else:
            self._apply_operation_silent(op_name, params)
    
    # =================================================================
    # Frame rendering logic (optimized with smooth transitions)
    # =================================================================
    
    def _update_frame_with_transition(self, frame_index: int, delta_info: Optional[Dict]):
        """Update frame with a smooth transition using the same layout as _render_frame."""
        old_layout = self.mobject_cache.get('layout')
        
        title_group = self._create_title_and_vars(frame_index, delta_info)
        
        left_components = []
        
        if self.pseudocode:
            pseudo_group = self._create_pseudocode(delta_info)
            if pseudo_group and len(pseudo_group) > 0:
                left_components.append(pseudo_group)
        
        if self.current_aux_views:
            aux_group = self._create_aux_views()
            if aux_group and len(aux_group) > 0:
                left_components.append(aux_group)
        
        main_view = self._create_main_view()
        
        main_content = VGroup()
        
        if left_components or (main_view and len(main_view) > 0):
            if left_components:
                left_panel = VGroup(*left_components)
                left_panel.arrange(DOWN, buff=0.4, aligned_edge=LEFT)
            else:
                left_panel = VGroup()
            
            if main_view and len(main_view) > 0:
                right_panel = main_view
            else:
                right_panel = Text("No data", font_size=20, color=GRAY)
            
            if left_components and main_view and len(main_view) > 0:
                lr_group = VGroup(left_panel, right_panel)
                lr_group.arrange(RIGHT, buff=0.8, aligned_edge=UP)
                main_content.add(lr_group)
            elif left_components:
                main_content.add(left_panel)
            else:
                main_content.add(right_panel)
        else:
            placeholder = Text("No data to display", font_size=24, color=GRAY)
            main_content.add(placeholder)
        
        layout_components = []
        if title_group and len(title_group) > 0:
            layout_components.append(title_group)
        layout_components.append(main_content)
        
        comment_box = self._create_comment_box()
        layout_components.append(comment_box)
        
        new_layout = VGroup(*layout_components)
        new_layout.arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        
        max_height = 9.0
        max_width = 15.0
        
        scale_factor = 1.0
        if new_layout.width > max_width:
            scale_factor = min(scale_factor, max_width / new_layout.width)
        if new_layout.height > max_height:
            scale_factor = min(scale_factor, max_height / new_layout.height)
        
        if scale_factor < 0.85:
            new_layout.arrange(DOWN, buff=0.18, aligned_edge=LEFT)
            scale_factor = 1.0
            if new_layout.width > max_width:
                scale_factor = min(scale_factor, max_width / new_layout.width)
            if new_layout.height > max_height:
                scale_factor = min(scale_factor, max_height / new_layout.height)
        
        if scale_factor < 1.0:
            new_layout.scale(scale_factor)
        
        new_layout.move_to(ORIGIN)
        
        if old_layout:
            self.remove(old_layout)
        self.add(new_layout)
        self.skip_smooth_transition = False
        
        self.mobject_cache['layout'] = new_layout
        
        self._add_array_temp_elements_after_layout()
    
    # =================================================================
    # Initial frame rendering (no transitions)
    # =================================================================
    
    def _render_frame(self, frame_index: int, delta_info: Optional[Dict]):
        """Render a single frame with a 2-column layout (code+aux left, main view right)."""
        # Clear previous frame mobjects.
        self._clear_frame()
        
        # 1. Title and variables (top, full width).
        title_group = self._create_title_and_vars(frame_index, delta_info)
        
        # 2. Left column: pseudocode + auxiliary views.
        left_components = []
        
        # Pseudocode (if any).
        if self.pseudocode:
            pseudo_group = self._create_pseudocode(delta_info)
            if pseudo_group and len(pseudo_group) > 0:
                left_components.append(pseudo_group)
        
        # Auxiliary views (if any).
        if self.current_aux_views:
            aux_group = self._create_aux_views()
            if aux_group and len(aux_group) > 0:
                left_components.append(aux_group)
        
        # 3. Right column: main data view.
        main_view = self._create_main_view()
        
        # Assemble layout.
        main_content = VGroup()
        
        # If we have any content, create a 2-column layout.
        if left_components or (main_view and len(main_view) > 0):
            # Left column (stacked vertically).
            if left_components:
                left_panel = VGroup(*left_components)
                left_panel.arrange(DOWN, buff=0.4, aligned_edge=LEFT)
            else:
                # If there is no left content, create an empty placeholder.
                left_panel = VGroup()
            
            # Right column (main view).
            if main_view and len(main_view) > 0:
                right_panel = main_view
            else:
                # If there is no main view, create a placeholder.
                right_panel = Text("No data", font_size=20, color=GRAY)
            
            # Two-column horizontal layout.
            if left_components and main_view and len(main_view) > 0:
                # Both sides present.
                lr_group = VGroup(left_panel, right_panel)
                lr_group.arrange(RIGHT, buff=0.8, aligned_edge=UP)  # horizontal, top aligned
                main_content.add(lr_group)
            elif left_components:
                # Only left side.
                main_content.add(left_panel)
            else:
                # Only right side.
                main_content.add(right_panel)
        else:
            # No content at all.
            placeholder = Text("No data to display", font_size=24, color=GRAY)
            main_content.add(placeholder)
        
        # Combine title, main content and comment box (vertical stack).
        layout_components = []
        if title_group and len(title_group) > 0:
            layout_components.append(title_group)
        layout_components.append(main_content)
        
        # Fix: always add a comment box (content or placeholder) to keep layout stable.
        comment_box = self._create_comment_box()
        layout_components.append(comment_box)
        
        layout = VGroup(*layout_components)
        layout.arrange(DOWN, buff=0.25, aligned_edge=LEFT)
        
        # Smart scaling: ensure layout stays within the frame.
        max_height = 9.0  # frame_height=10.0, keep ~10% margin
        max_width = 15.0  # frame_width=16.0, keep ~6% margin
        
        # Compute scale factor based on width and height.
        scale_factor = 1.0
        if layout.width > max_width:
            scale_factor = min(scale_factor, max_width / layout.width)
        if layout.height > max_height:
            scale_factor = min(scale_factor, max_height / layout.height)
        
        # If scaling would be too strong, tighten vertical spacing first.
        if scale_factor < 0.85:
            layout.arrange(DOWN, buff=0.18, aligned_edge=LEFT)
            scale_factor = 1.0
            if layout.width > max_width:
                scale_factor = min(scale_factor, max_width / layout.width)
            if layout.height > max_height:
                scale_factor = min(scale_factor, max_height / layout.height)
        
        # Apply scaling (with a floor to avoid tiny text).
        if scale_factor < 1.0:
            layout.scale(max(scale_factor, 0.82))
        
        # Center on screen.
        layout.move_to(ORIGIN)
        
        # Add to scene.
        self.add(layout)
        self.mobject_cache['layout'] = layout
        
        # Important: add array temporary elements only after layout is final.
        self._add_array_temp_elements_after_layout()
    
    def _clear_frame(self):
        """Clear all objects from the current frame."""
        # Clear arrows first.
        self._clear_temp_arrows()
        
        # Then clear layout.
        if 'layout' in self.mobject_cache:
            self.remove(self.mobject_cache['layout'])
        self.mobject_cache.clear()
        self.array_mobjects.clear()
        self.graph_mobjects.clear()
        self.table_mobjects.clear()
    
    def _clear_temp_arrows(self):
        """Clear temporary arrows."""
        if 'temp_arrows' in self.mobject_cache:
            for arrow in self.mobject_cache['temp_arrows']:
                self.remove(arrow)
            self.mobject_cache['temp_arrows'] = []
    
    def _add_array_temp_elements_after_layout(self):
        """Add temporary elements (arrows, boundaries) after layout is finalized."""
        # Clear previous arrows.
        self._clear_temp_arrows()
        
        # Only for array type.
        if self.data_type != "array" or len(self.array_mobjects) == 0:
            return
        
        temp_arrows = []
        swap_mobjects = []
        
        # Draw compare lines first (under swap arrows) to reduce visual clutter.
        seen_pairs = set()
        for temp in self.temp_elements:
            if temp.get("type") == "array_compare":
                color, width = self._resolve_dep_style(temp.get("styleKey", "arrow"))
                pairs = temp.get("pairs", []) or []
                
                local_idx = 0
                for pair in pairs:
                    a, b = pair.get("a"), pair.get("b")
                    if a is None or b is None:
                        continue
                    a, b = int(a), int(b)
                    if a == b:
                        continue
                    key = (min(a, b), max(a, b))
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    
                    if 0 <= a < len(self.array_mobjects) and 0 <= b < len(self.array_mobjects):
                        cell_a = self.array_mobjects[a]
                        cell_b = self.array_mobjects[b]
                        
                        # Place lines near the top of cells and offset slightly when multiple lines.
                        y_off = UP * (0.05 + 0.06 * (local_idx % 3))
                        start = cell_a.get_top() + y_off
                        end = cell_b.get_top() + y_off
                        line = Line(
                            start,
                            end,
                            color=color,
                            buff=0.03,
                            stroke_width=max(1.8, float(width) * 0.9)
                        ).set_z_index(-1)  # draw under swap arrows
                        temp_arrows.append(line)
                        self.add(line)
                        local_idx += 1
        
        # Then draw swap arrows / boundary boxes.
        for temp in self.temp_elements:
            if temp.get("type") == "swap_arrows":
                color, width = self._resolve_dep_style(temp.get("styleKey", "arrow"))
                for pair in temp.get("pairs", []):
                    a, b = pair.get("a"), pair.get("b")
                    if 0 <= a < len(self.array_mobjects) and 0 <= b < len(self.array_mobjects):
                        cell_a = self.array_mobjects[a]
                        cell_b = self.array_mobjects[b]
                        
                        arrow = DoubleArrow(
                            cell_a.get_top(),
                            cell_b.get_top(),
                            color=color,
                            buff=0.3,
                            stroke_width=max(3, width),
                            tip_length=0.2
                        )
                        swap_mobjects.append(arrow)
            
            elif temp.get("type") == "boundary_box":
                start_idx, end_idx = temp.get("range", [0, 0])
                if 0 <= start_idx <= end_idx < len(self.array_mobjects):
                    cells = VGroup(*[self.array_mobjects[i] for i in range(start_idx, end_idx + 1)])
                    
                    style_key = temp.get('styleKey', 'default_boundary')
                    temp_style = self._get_temp_style(style_key)
                    color = self._parse_color(temp_style.get("stroke", "#ff0000"))
                    
                    box = SurroundingRectangle(cells, color=color, buff=0.1, stroke_width=2)
                    temp_arrows.append(box)
                    self.add(box)
                    
                    label = temp.get('label', '')
                    if label:
                        label_text = Text(str(label), font_size=18)
                        label_text.next_to(box, UP, buff=0.1)
                        temp_arrows.append(label_text)
                        self.add(label_text)

        if swap_mobjects:
            for m in swap_mobjects:
                temp_arrows.append(m)
                self.add(m)
        
        if 'temp_arrows' not in self.mobject_cache:
            self.mobject_cache['temp_arrows'] = []
        self.mobject_cache['temp_arrows'].extend(temp_arrows)

    def _create_title_and_vars(self, frame_index: int, delta_info: Optional[Dict]) -> VGroup:
        """Create title and current action subtitle for the frame."""
        group = VGroup()
        
        title = Text(self.algorithm_info.get('name', ''), font_size=48, weight=BOLD)
        group.add(title)
        
        action_desc = self._generate_action_description(delta_info) if delta_info else "Initial State"
        subtitle = Text(action_desc, font_size=22, color=GRAY_A)
        group.add(subtitle)
        
        # Note: we intentionally do not render variable list here to avoid layout jitter.
        
        group.arrange(DOWN, buff=0.2, aligned_edge=LEFT)
        return group

    def _create_vars_panel(self, view: Dict) -> VGroup:
        """Create a compact variables panel (multi-column if needed)."""
        data = view.get("data", []) or []
        items = []
        for row in data:
            name = str(row[0]) if len(row) > 0 and row[0] is not None else ""
            val = row[1] if len(row) > 1 else None
            val_str = "-" if val is None else str(val)
            text = Text(f"{name}: {val_str}", font_size=18, color=WHITE)
            max_width = 6.0
            if text.width > max_width and max_width > 0:
                text.scale(max_width / text.width)
            items.append(text)
        
        group = VGroup(*items)
        if len(items) >= 6:
            group.arrange_in_grid(rows=None, cols=2, buff=0.2)
        else:
            group.arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        return group
    
    def _create_comment_box(self) -> VGroup:
        """Create a fixed-height comment box to avoid layout jitter."""
        width = 14.0
        font_size = 18
        line_height = 0.48
        max_lines = 4
        fixed_height = 1.2  # fixed height keeps layout stable
        
        if not self.current_comment_text:
            placeholder = Rectangle(
                width=width,
                height=fixed_height,
                stroke_opacity=0,
                fill_opacity=0
            )
            return VGroup(placeholder)
        
        raw_text = str(self.current_comment_text)
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\s+", " ", text).strip()
        
        # Auto-wrap text; handle CJK and non-CJK slightly differently.
        lines = []
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text))
        if "\n" in text:
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        else:
            tokens = list(text) if has_cjk else (text.split(" ") if text else [])
            joiner = "" if has_cjk else " "
            max_chars = 42 if has_cjk else 60
            current = ""
            for tok in tokens:
                if not tok:
                    continue
                cand = tok if not current else (current + joiner + tok)
                if len(cand) > max_chars:
                    if current:
                        lines.append(current)
                    current = tok
                else:
                    current = cand
            if current:
                lines.append(current)
        
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            if lines:
                lines[-1] = lines[-1].rstrip(".") + "..."
        
        content = "\n".join(lines) if lines else ""
        comment_text = Text(content, font_size=font_size, color=WHITE, line_spacing=0.8)
        
        # Use a fixed height to avoid layout shifting when comments appear/disappear.
        target_height = fixed_height
        
        comment_bg = Rectangle(
            width=width,
            height=target_height,
            color=BLUE,
            fill_opacity=0.3,
            fill_color=BLUE_E,
            stroke_width=2
        )
        comment_text.move_to(comment_bg.get_center())
        comment_text.align_to(comment_bg, LEFT)
        comment_text.shift(RIGHT * 0.2)
        
        return VGroup(comment_bg, comment_text)
    
    def _create_pseudocode(self, delta_info: Optional[Dict]) -> VGroup:
        """Create pseudocode panel; highlight current line without layout jumps."""
        # Current highlighted line index.
        current_highlight = delta_info.get("code_highlight") if delta_info else self.initial_frame.get("code_highlight")
        
        # Some traces use a list for multi-line highlights; take the first.
        if isinstance(current_highlight, list):
            current_highlight = current_highlight[0] if current_highlight else None
        
        # Title.
        title = Text("Pseudocode:", font_size=20, weight=BOLD, color=WHITE)
        
        # Code lines container (fixed positioning to avoid overlap).
        code_lines_group = VGroup()
        
        y_offset = 0  # vertical offset
        line_height = 0.25  # fixed line height
        
        for i, line_text in enumerate(self.pseudocode):
            # Compute indentation level (number of leading spaces).
            indent_level = 0
            clean_text = line_text
            if line_text:
                indent_level = len(line_text) - len(line_text.lstrip(' '))
                clean_text = line_text.strip()
            
            # Skip empty lines (reserve half line height).
            if not clean_text:
                y_offset -= line_height * 0.5
                continue
            
            # Determine whether this line is highlighted.
            is_highlighted = (i + 1) == current_highlight
            
            # Create text object (without leading spaces).
            text_color = WHITE if is_highlighted else GRAY_A
            text_obj = Text(clean_text, font="monospace", font_size=14, color=text_color)
            
            # Horizontal offset determined by indentation.
            indent_offset = indent_level * 0.15
            
            # Position line (left-aligned + indent offset + vertical offset).
            text_obj.move_to([indent_offset, y_offset, 0], aligned_edge=LEFT)
            
            # If highlighted, draw a background rectangle (no animation here).
            if is_highlighted:
                bg = SurroundingRectangle(
                    text_obj,
                    color=YELLOW,
                    fill_opacity=0.2,
                    fill_color=YELLOW,
                    buff=0.05,
                    stroke_width=1.0
                )
                code_lines_group.add(bg)
            
            # Add text object.
            code_lines_group.add(text_obj)
            
            # Update vertical offset.
            y_offset -= line_height
        
        # Combine title and code lines.
        if len(code_lines_group) > 0:
            title.move_to([0, 0, 0], aligned_edge=LEFT)
            code_lines_group.next_to(title, DOWN, buff=0.2, aligned_edge=LEFT)
            result = VGroup(title, code_lines_group)
        else:
            result = VGroup(title)
        
        return result
    
    def _create_aux_views(self) -> VGroup:
        """Create all auxiliary views (tables, lists, arrays)."""
        view_groups = []
        
        for view in self.current_aux_views:
            view_group = VGroup()
            
            # Title
            title = Text(view.get('title', ''), font_size=24, weight=BOLD)
            view_group.add(title)
            
            # Render content based on view type.
            if view.get("type") == "table":
                if view.get("view_id") == "vars_panel":
                    vars_panel = self._create_vars_panel(view)
                    view_group.add(vars_panel)
                else:
                    table = self._create_table_view(view)
                    view_group.add(table)
            elif view.get("type") == "list":
                list_view = self._create_list_view(view)
                view_group.add(list_view)
            elif view.get("type") == "array":
                # Render an auxiliary array view.
                array_view = self._create_aux_array_view(view)
                view_group.add(array_view)
            
            view_group.arrange(DOWN, buff=0.2, aligned_edge=LEFT)
            view_groups.append(view_group)
        
        if not view_groups:
            return VGroup()
        
        # Layout auxiliary views in a grid to reduce vertical height.
        group = VGroup(*view_groups)
        if len(view_groups) >= 3:
            # Do not use col_alignments for compatibility across Manim versions.
            group.arrange_in_grid(rows=None, cols=2, buff=0.4)
        else:
            group.arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        return group
    
    def _create_main_view(self) -> Optional[VGroup]:
        """Create the main data view based on current data_state.type."""
        if self.data_type == "array":
            return self._create_array_view()
        elif self.data_type == "graph":
            return self._create_graph_view()
        elif self.data_type == "table":
            return self._create_table_view(self.current_data_state)
        elif self.data_type == "tree":
            return self._create_tree_view()
        elif self.data_type == "hashtable":
            return self._create_hashtable_view()
        return None
    
    # =================================================================
    # Array view (full style support)
    # =================================================================
    
    def _create_array_view(self) -> VGroup:
        """Create array visualization with automatic line wrapping."""
        arr = self._get_array_list()
        if not arr:
            return VGroup()
        
        # Compute maximum elements per row (to fit within the frame).
        max_width = 13.0  # Manim logical width is about 14
        cell_width = self.cell_size + 0.2  # cell width + spacing
        max_per_row = max(5, int(max_width / cell_width))  # at least 5 per row
        
        all_rows = VGroup()
        self.array_mobjects = []
        
        # Group elements into rows.
        for row_start in range(0, len(arr), max_per_row):
            row_end = min(row_start + max_per_row, len(arr))
            row_group = VGroup()
            
            for i in range(row_start, row_end):
                elem = arr[i]
                # Create cell visual.
                value = str(elem.get('value', ''))
                state = elem.get('state', 'idle')
                
                # Get style from trace definition.
                stroke_color, fill_color, text_color = self._get_element_style(state)
                fill_opacity, stroke_width = self._get_array_cell_render_params(state)
                
                # Create square and text.
                square = Square(
                    side_length=self.cell_size,
                    color=stroke_color,
                    fill_opacity=fill_opacity,
                    fill_color=fill_color,
                    stroke_width=stroke_width
                )
                text = Text(value, font_size=22, color=text_color)
                # Auto-scale text to fit the cell.
                max_text_width = self.cell_size * 0.85
                if text.width > max_text_width:
                    text.scale(max_text_width / text.width)
                cell = VGroup(square, text)
                
                # Index label.
                index_label = Text(str(i), font_size=14, color=GRAY)
                index_label.next_to(cell, DOWN, buff=0.08)
                
                cell_group = VGroup(cell, index_label)
                row_group.add(cell_group)
                self.array_mobjects.append(cell)
            
            row_group.arrange(RIGHT, buff=0.15)
            all_rows.add(row_group)
        
        # Stack all rows vertically.
        if len(all_rows) > 1:
            all_rows.arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        
        # Fix: do not add arrows here; they are added after layout is finalized.
        # Only return the array visual group.
        return all_rows
    
    def _add_boundary_boxes(self, array_group: VGroup):
        """Add boundary boxes around array segments."""
        for temp in self.temp_elements:
            if temp.get("type") == "boundary_box":
                start_idx, end_idx = temp.get("range", [0, 0])
                if 0 <= start_idx <= end_idx < len(array_group):
                    cells = VGroup(*[array_group[i] for i in range(start_idx, end_idx + 1)])
                    
                    # Get style for boundary.
                    style_key = temp.get('styleKey', 'default_boundary')
                    temp_style = self._get_temp_style(style_key)
                    color = self._parse_color(temp_style.get("stroke", "#ff0000"))
                    
                    box = SurroundingRectangle(cells, color=color, buff=0.1, stroke_width=2)
                    
                    label = temp.get('label', '')
                    if label:
                        label_text = Text(label, font_size=18)
                        label_text.next_to(box, UP, buff=0.1)
                        self.add(label_text)
                    
                    self.add(box)
    
    def _add_array_temp_elements(self, array_group: VGroup):
        """Add temporary visuals for arrays (using self.array_mobjects)."""
        for temp in self.temp_elements:
            if temp.get("type") == "swap_arrows":
                # Swap arrows (using trace style).
                color, width = self._resolve_dep_style(temp.get("styleKey", "arrow"))
                for pair in temp.get("pairs", []):
                    a, b = pair.get("a"), pair.get("b")
                    # Use self.array_mobjects instead of array_group,
                    # because array_group may be nested after wrapping.
                    if 0 <= a < len(self.array_mobjects) and 0 <= b < len(self.array_mobjects):
                        cell_a = self.array_mobjects[a]
                        cell_b = self.array_mobjects[b]
                        
                        arrow = DoubleArrow(
                            cell_a.get_top(),
                            cell_b.get_top(),
                            color=color,
                            buff=0.3,
                            stroke_width=max(2, width),
                            tip_length=0.2
                        )
                        self.add(arrow)
        
    
    # =================================================================
    # Graph view (full style support)
    # =================================================================
    
    def _create_graph_view(self) -> VGroup:
        """Create graph visualization with optimized spacing and edge drawing."""
        struct = self.current_data_state.get("structure", {})
        nodes = struct.get("nodes", []) or []
        edges = struct.get("edges", []) or []
        
        if not nodes:
            return VGroup()
        
        positions = self._compute_graph_layout(nodes)
        per_row = max(3, int(12.0 / self.graph_gap_x))
        
        nodes_group = VGroup()
        edges_group = VGroup()
        self.graph_mobjects = {}
        
        # Create node visuals first.
        for i, node in enumerate(nodes):
            # Create node with trace-defined style.
            node_id = node.get('id')
            label = str(node.get('label', node_id))
            style_key = node.get('styleKey', 'idle_node')
            
            stroke_color, fill_color, text_color = self._get_element_style(style_key)
            

            circle = Circle(
                radius=self.node_size,
                color=stroke_color,
                fill_opacity=0.35,
                fill_color=fill_color,
                stroke_width=2.5
            )
            text = Text(label, font_size=18, color=text_color, weight=BOLD)
            node_mob = VGroup(circle, text)
            pos = positions.get(node_id)
            if pos is None:
                col = i % per_row
                row = i // per_row
                x = col * self.graph_gap_x - (min(per_row, len(nodes)) - 1) * self.graph_gap_x / 2
                y = -row * self.graph_gap_y
                pos = np.array([x, y, 0.0])
            node_mob.move_to(pos)
            
            nodes_group.add(node_mob)
            self.graph_mobjects[node_id] = node_mob
        
        # Draw edges using styles from trace definition.
        for edge in edges:
            from_id = edge.get('from')
            to_id = edge.get('to')
            
            if from_id in self.graph_mobjects and to_id in self.graph_mobjects:
                from_node = self.graph_mobjects[from_id]
                to_node = self.graph_mobjects[to_id]
                
                directed = edge.get("directed", False)
                style_key = edge.get('styleKey', 'normal_edge')
                
                # Get edge style.
                edge_color, text_color, line_width = self._get_edge_style(style_key)
                
                # Shorten edges slightly to avoid overlapping node circles.
                buff_size = self.node_size + 0.05
                
                if directed:
                    arrow = Arrow(
                        from_node.get_center(),
                        to_node.get_center(),
                        color=edge_color,
                        buff=buff_size,
                        stroke_width=line_width,
                        max_tip_length_to_length_ratio=0.15,
                        max_stroke_width_to_length_ratio=5
                    )
                else:
                    arrow = Line(
                        from_node.get_center(),
                        to_node.get_center(),
                        color=edge_color,
                        stroke_width=line_width,
                        buff=buff_size
                    )
                
                edges_group.add(arrow)
                
                # Edge labels with correct text color.
                label = edge.get("label", "")
                if label:
                    label_text = Text(label, font_size=12, color=text_color, weight=BOLD)
                    label_text.move_to(arrow.get_center())
                    # Shift along normal direction to avoid overlapping with edge.
                    vec = np.array(to_node.get_center()) - np.array(from_node.get_center())
                    norm = np.linalg.norm(vec[:2]) if vec.shape[0] >= 2 else 0.0
                    if norm > 1e-6:
                        normal = np.array([-vec[1], vec[0], 0.0]) / norm
                        label_text.shift(normal * 0.2)
                    # Add white background for better readability.
                    label_bg = BackgroundRectangle(label_text, color=WHITE, fill_opacity=0.85, buff=0.05)
                    label_group = VGroup(label_bg, label_text)
                    edges_group.add(label_group)
        
        # Combine edges (below) and nodes (above).
        graph_group = VGroup(edges_group, nodes_group)
        
        return graph_group

    def _compute_graph_layout(self, nodes: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
        """Compute node positions.

        Priority:
        - If stage/layer/level is provided, use layered layout (larger stage lower).
        - Otherwise, fall back to a regular grid.
        """
        positions: Dict[str, np.ndarray] = {}
        if not nodes:
            return positions
        
        # Detect stage/layer/level fields.
        stage_map = {}
        has_stage = False
        for nd in nodes:
            nid = nd.get("id")
            stage = nd.get("stage")
            if stage is None:
                stage = nd.get("layer", nd.get("level"))
            if stage is not None:
                has_stage = True
                stage_map.setdefault(stage, []).append(nid)
        
        if has_stage:
            # Layered: nodes in the same stage horizontally, stages separated by graph_gap_y.
            sorted_stages = sorted(stage_map.keys())
            for layer_idx, stage in enumerate(sorted_stages):
                ids = stage_map[stage]
                k = len(ids)
                if k == 0:
                    continue
                # Adaptive horizontal spacing within a bounded width.
                hgap = max(1.8, min(3.8, self.graph_gap_x))
                width_span = hgap * max(0, k - 1)
                x_start = -width_span / 2
                y = -layer_idx * self.graph_gap_y
                for i, nid in enumerate(ids):
                    positions[nid] = np.array([x_start + i * hgap, y, 0.0])
            return positions
        
        # Fallback: regular grid layout.
        per_row = max(3, int(12.0 / self.graph_gap_x))
        for i, nd in enumerate(nodes):
            nid = nd.get("id")
            col = i % per_row
            row = i // per_row
            x = col * self.graph_gap_x - (min(per_row, len(nodes)) - 1) * self.graph_gap_x / 2
            y = -row * self.graph_gap_y
            positions[nid] = np.array([x, y, 0.0])
        return positions
    
    # =================================================================
    # Table view (full style support)
    # =================================================================
    
    def _create_table_view(self, table_data: Dict) -> VGroup:
        """Create table visualization with optimized layout, styles and text sizing."""
        data = table_data.get("data", [])
        if not data:
            return VGroup()
        
        view_id = table_data.get("view_id", "main_table")
        options = table_data.get("options", {}) or {}
        row_headers = options.get("row_headers") or []
        col_headers = options.get("col_headers") or []
        
        rows = len(data)
        cols = len(data[0]) if data else 0
        
        # Decide whether to skip first data column if it duplicates row headers.
        skip_first_col = False
        if row_headers and cols > 0:
            # Check if row headers match first data column to avoid double rendering.
            try:
                if all(r < len(data) and len(data[r]) > 0 and str(row_headers[r]) == str(data[r][0]) 
                       for r in range(min(len(row_headers), len(data)))):
                    skip_first_col = True
            except (IndexError, KeyError):
                skip_first_col = False
        
        # Effective column count for cell-size heuristics.
        effective_cols = (cols - 1) if skip_first_col else cols
        
        # Dynamically determine cell size.
        cell_size = 0.65
        if effective_cols > 10:
            cell_size = 0.5  
        elif effective_cols > 15:
            cell_size = 0.4  
        
        # Pre-scan: find max text length per column for text scaling.
        start_col = 1 if skip_first_col else 0
        max_char_lengths = []
        for c in range(start_col, cols):
            max_len = 0

            if col_headers and not skip_first_col and c < len(col_headers):
                max_len = max(max_len, len(str(col_headers[c])))
            elif col_headers and skip_first_col and (c - 1) < len(col_headers[1:]):
                max_len = max(max_len, len(str(col_headers[c])))

            for r in range(rows):
                if c < len(data[r]):
                    cell_str = str(data[r][c]) if data[r][c] is not None else "-"
                    max_len = max(max_len, len(cell_str))
            max_char_lengths.append(max_len)
        
        # Create base table structure.
        table_base = VGroup()
        self.table_mobjects[view_id] = {}
        
        # Column headers.
        if col_headers:
            # If skipping first data column, also skip first column header.
            effective_col_headers = col_headers[1:] if (skip_first_col and len(col_headers) > 1) else col_headers
            
            if effective_col_headers:
                header_row = VGroup()
                # Top-left placeholder for row headers alignment.
                if row_headers:
                    corner = Square(side_length=cell_size, fill_opacity=0, stroke_opacity=0)
                    header_row.add(corner)
                
                for col_idx, header in enumerate(effective_col_headers):
                    text = Text(str(header), font_size=16, color=GRAY, weight=BOLD)
                    # Auto-scale header text to fit the cell.
                    max_text_width = cell_size * 0.85
                    if text.width > max_text_width:
                        text.scale(max_text_width / text.width)
                    text_box = Square(side_length=cell_size, fill_opacity=0, stroke_opacity=0)
                    header_cell = VGroup(text_box, text)
                    header_row.add(header_cell)
                header_row.arrange(RIGHT, buff=0.03)
                table_base.add(header_row)
        
        # Data rows.
        for r, row in enumerate(data):
            row_group = VGroup()
            
            # Row header (if present).
            if row_headers and r < len(row_headers):
                header_text = Text(str(row_headers[r]), font_size=16, color=GRAY, weight=BOLD)
                # Auto-scale row header text.
                max_text_width = cell_size * 0.85
                if header_text.width > max_text_width:
                    header_text.scale(max_text_width / header_text.width)
                header_box = Square(side_length=cell_size, fill_opacity=0, stroke_opacity=0)
                header_cell = VGroup(header_box, header_text)
                row_group.add(header_cell)
            elif col_headers:
                # If column headers exist but row headers do not, add placeholder for alignment.
                placeholder = Square(side_length=cell_size, fill_opacity=0, stroke_opacity=0)
                row_group.add(placeholder)
            
            # Data cells (skipping duplicated column, if any).
            for col_idx, c in enumerate(range(start_col, len(row))):
                value = row[c]
                cell_value = str(value) if value is not None else "-"
                
                square = Square(
                    side_length=cell_size, 
                    color=WHITE, 
                    fill_opacity=0.08,
                    stroke_width=1.5
                )
                text = Text(cell_value, font_size=18)
                
                # Auto-scale text to fit within the cell (avoid overflow).
                max_text_width = cell_size * 0.85
                if text.width > max_text_width:
                    text.scale(max_text_width / text.width)
                
                cell = VGroup(square, text)
                
                row_group.add(cell)
                self.table_mobjects[view_id][(r, c)] = cell
            
            row_group.arrange(RIGHT, buff=0.03)
            table_base.add(row_group)
        
        table_base.arrange(DOWN, buff=0.03, aligned_edge=LEFT)
        
        # Combine table, highlights and dependency arrows into one group.
        table_with_decorations = VGroup(table_base)
        
        # Highlights and dependency arrows become part of the table group.
        highlights = self._create_table_highlights(view_id)
        dependencies = self._create_table_dependencies(view_id)
        
        if highlights:
            table_with_decorations.add(highlights)
        if dependencies:
            table_with_decorations.add(dependencies)
        
        return table_with_decorations
    
    def _create_table_highlights(self, view_id: str) -> Optional[VGroup]:
        """Create table cell highlight overlays as a VGroup (not added directly)."""
        highlights_group = VGroup()
        
        for temp in self.temp_elements:
            if temp.get("type") in ("table_highlight", "table_change_flash"):
                tv = temp.get("view_id")
                # Support multiple aliases for main view: None, view_id, "dp_table", "data_state", "main_table".
                if tv is None or tv == view_id or tv in ("dp_table", "data_state", "main_table"):
                    style_key = temp.get("styleKey", "current_cell")
                    fill_color, stroke_color = self._get_cell_style(style_key)
                    is_current = "current" in str(style_key or "").lower() or "active" in str(style_key or "").lower()
                    
                    for cell in temp.get("cells", []) or []:
                        r, c = cell.get("row"), cell.get("col")
                        if (r, c) in self.table_mobjects.get(view_id, {}):
                            cell_mob = self.table_mobjects[view_id][(r, c)]
                            # Solid fill + thicker border for highlight.
                            highlight = SurroundingRectangle(
                                cell_mob,
                                color=stroke_color,
                                fill_color=fill_color,
                                fill_opacity=0.45 if is_current else 0.3,
                                stroke_width=2.6 if is_current else 2.0,
                                buff=0
                            )
                            highlights_group.add(highlight)
                            if is_current:
                                # Slight flash layer (lighter outer ring).
                                flash = SurroundingRectangle(
                                    cell_mob,
                                    color=stroke_color,
                                    fill_color=fill_color,
                                    fill_opacity=0.12,
                                    stroke_width=1.2,
                                    buff=0.05
                                )
                                highlights_group.add(flash)
        
        return highlights_group if len(highlights_group) > 0 else None
    
    def _create_table_dependencies(self, view_id: str) -> Optional[VGroup]:
        """Create dependency arrows for tables as a VGroup (not added directly)."""
        dependencies_group = VGroup()
        
        # Determine whether current view is the main view.
        is_main_view = view_id in ("dp_table", "data_state", "main_table") or view_id == self.current_data_state.get("view_id")
        
        # Debug hook for dependency counts (kept commented out).
        # if len(self.dependencies) > 0 and is_main_view:
        #     print(f"  Creating {len(self.dependencies)} dependency arrows for view {view_id}...")
        
        for dep in self.dependencies:
            dv = dep.get("view_id")
            should_render = False
            if dv is None and is_main_view:
                should_render = True  
            elif dv == view_id:
                should_render = True  
            elif dv in ("dp_table", "data_state", "main_table") and is_main_view:
                should_render = True  
            
            if should_render:
                to_cell = dep.get("to_cell") or {}
                tr, tc = to_cell.get("row"), to_cell.get("col")
                
                if (tr, tc) in self.table_mobjects.get(view_id, {}):
                    to_mob = self.table_mobjects[view_id][(tr, tc)]
                    

                    color, width = self._resolve_dep_style(dep.get("styleKey", "arrow"))
                    
                    for fc in dep.get("from_cells", []) or []:
                        fr, fc_col = fc.get("row"), fc.get("col")
                        if (fr, fc_col) in self.table_mobjects.get(view_id, {}):
                            from_mob = self.table_mobjects[view_id][(fr, fc_col)]
                            
                            # Use curved arrows to avoid overlaps and improve visibility.
                            from_point = from_mob.get_center()
                            to_point = to_mob.get_center()
                            
                            # Use Manhattan distance to adjust curvature and width.
                            distance = abs(fr - tr) + abs(fc_col - tc)
                            
                            if distance > 2:
                                # Longer dependency: stronger curvature and thicker line.
                                path_arc = 0.8 if (fc_col < tc or fr < tr) else -0.8
                                stroke_w = max(3.0, width)  # slightly thicker line
                            else:
                                # Shorter dependency: smaller curvature.
                                path_arc = 0.5 if (fc_col < tc or fr < tr) else -0.5
                                stroke_w = max(2.5, width)
                            
                            # Create curved arrow (using angle parameter for curvature).
                            arrow = CurvedArrow(
                                from_point,
                                to_point,
                                color=color,
                                stroke_width=stroke_w,
                                angle=path_arc,
                                tip_length=0.25
                                # Note: CurvedArrow does not accept buff parameter.
                            )
                            dependencies_group.add(arrow)
        

        
        return dependencies_group if len(dependencies_group) > 0 else None
    
    # =================================================================
    # Tree view (full style support)
    # =================================================================
    
    def _create_tree_view(self) -> VGroup:
        """Create tree visualization."""
        struct = self.current_data_state.get("structure", {})
        nodes_list = struct.get("nodes", [])
        if not nodes_list:
            return VGroup()
        
        # Build tree structure.
        id_to_node = {n.get("id"): n for n in nodes_list if n.get("id") is not None}
        root_id = struct.get("root")
        
        if root_id not in id_to_node:
            cand = [n.get("id") for n in nodes_list if n.get("parent") in (None, "")]
            root_id = cand[0] if cand else nodes_list[0].get("id")
        
        # BFS layering.
        from collections import deque
        levels = []
        q = deque([root_id])
        seen = set([root_id])
        
        children_map = {nid: [] for nid in id_to_node}
        for nid, nd in id_to_node.items():
            for ch in (nd.get("children") or []):
                if ch in children_map:
                    children_map[nid].append(ch)
        
        while q:
            size = len(q)
            level = []
            for _ in range(size):
                u = q.popleft()
                level.append(u)
                for v in children_map.get(u, []):
                    if v not in seen:
                        seen.add(v)
                        q.append(v)
            if level:
                levels.append(level)
        
        # Render nodes with styles from trace definition.
        group = VGroup()
        self.tree_mobjects = {}
        vgap_base = 1.5
        
        for li, level in enumerate(levels):
            hgap = max(1.2, min(2.6, 3.6 / max(1, len(level) / 4)))
            y = -li * vgap_base
            
            for i, nid in enumerate(level):
                k = len(level)
                x = (i - (k - 1) / 2) * hgap
                
                node = id_to_node.get(nid, {})
                label = str(node.get('label', nid))
                style_key = node.get('styleKey', 'idle_node')
                
                stroke_color, fill_color, text_color = self._get_element_style(style_key)
                
                circle = Circle(
                    radius=0.3,
                    color=stroke_color,
                    fill_opacity=0.3,
                    fill_color=fill_color
                )
                text = Text(label, font_size=18, color=text_color)
                node_mob = VGroup(circle, text)
                node_mob.move_to([x, y, 0])
                
                group.add(node_mob)
                self.tree_mobjects[nid] = node_mob
        
        # Draw edges between parent and child.
        for pid, chs in children_map.items():
            for cid in chs:
                if pid in self.tree_mobjects and cid in self.tree_mobjects:
                    line = Line(
                        self.tree_mobjects[pid].get_bottom(),
                        self.tree_mobjects[cid].get_top(),
                        color=GRAY,
                        stroke_width=2
                    )
                    group.add(line)
        
        return group
    
    # =================================================================
    # Hashtable view
    # =================================================================
    
    def _create_hashtable_view(self) -> VGroup:
        """Create hashtable visualization (showing key-value pairs per bucket)."""
        struct = self.current_data_state.get("structure", {})
        size = struct.get("size", 8)
        buckets = struct.get("buckets", [])
        
        # Vertically arrange all buckets.
        group = VGroup()
        
        for i in range(size):
            bucket = buckets[i] if i < len(buckets) else {"index": i, "items": []}
            items = bucket.get("items", [])
            
            # Bucket index
            index_text = Text(f"[{i}]", font_size=20, color=GRAY, weight=BOLD)
            
            # Bucket content: Show key-value pairs
            if items:
                items_parts = []
                for it in items:
                    key = it.get('key', '')
                    value = it.get('value', '')
                    items_parts.append(f"{key}:{value}")
                items_str = ", ".join(items_parts)
            else:
                items_str = "empty"
            
            content_text = Text(items_str, font_size=18, color=WHITE)
            

            bucket_box = Rectangle(
                width=max(2.5, content_text.width + 0.3), 
                height=0.6, 
                color=BLUE,
                fill_opacity=0.1
            )
            

            bucket_group = VGroup()
            index_text.next_to(bucket_box, LEFT, buff=0.2)
            content_text.move_to(bucket_box.get_center())
            
            bucket_group.add(index_text, bucket_box, content_text)
            group.add(bucket_group)
        
        # Stack buckets vertically.
        group.arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        return group
    
    # =================================================================
    # List view
    # =================================================================
    
    def _create_list_view(self, view: Dict) -> VGroup:
        """Create list view for frontier/queue/stack style data."""
        data = view.get("data", {})
        if isinstance(data, list):
            data = {"List": data}
        if not isinstance(data, dict):
            data = {"List": []}

        options = view.get("options", {})
        if not isinstance(options, dict):
            options = {}

        max_items = options.get("max_items", 60)
        max_line_chars = options.get("max_line_chars", 52)
        max_item_chars = options.get("max_item_chars", 24)
        font_size = options.get("font_size", 18)
        header_font_size = options.get("header_font_size", font_size)

        def _to_item_str(x: Any) -> str:
            s = str(x)
            if isinstance(max_item_chars, int) and max_item_chars > 0 and len(s) > max_item_chars:
                s = s[: max(0, max_item_chars - 3)] + "..."
            return s

        def _split_lines(items: List[str]) -> List[str]:
            lines: List[str] = []
            current = ""
            for s in items:
                candidate = s if not current else f"{current}, {s}"
                if isinstance(max_line_chars, int) and max_line_chars > 0 and len(candidate) > max_line_chars and current:
                    lines.append(current)
                    current = s
                else:
                    current = candidate
            if current:
                lines.append(current)
            return lines

        group = VGroup()
        show_list_name = len(data) > 1
        for list_name, item_list in data.items():
            if not isinstance(item_list, list):
                item_list = []

            items = [_to_item_str(x) for x in item_list]
            omitted = 0
            if isinstance(max_items, int) and max_items > 0 and len(items) > max_items:
                omitted = len(items) - max_items
                items = items[-max_items:]

            if show_list_name or list_name != "List":
                group.add(Text(f"{list_name}:", font_size=header_font_size, weight=BOLD))

            for line in _split_lines(items):
                group.add(Text(line, font_size=font_size))

            if omitted > 0:
                group.add(Text(f"... (+{omitted})", font_size=font_size, color=GRAY))

        group.arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        return group
    
    def _create_aux_array_view(self, view: Dict) -> VGroup:

        data = view.get("data", [])
        if not data:
            return VGroup()
        

        row_group = VGroup()
        
        for idx, elem in enumerate(data):

            if isinstance(elem, dict):
                value = str(elem.get('value', ''))
                style_key = elem.get('styleKey', 'default')
            else:
                value = str(elem)
                style_key = 'default'
            

            stroke_color, fill_color, text_color = self._get_element_style(style_key)
            fill_opacity, stroke_width = self._get_array_cell_render_params(style_key)
            

            square = Square(
                side_length=self.cell_size,
                color=stroke_color,
                fill_opacity=fill_opacity,
                fill_color=fill_color,
                stroke_width=stroke_width
            )
            text = Text(value, font_size=20, color=text_color)
            

            max_text_width = self.cell_size * 0.85
            if text.width > max_text_width:
                text.scale(max_text_width / text.width)
            
            cell = VGroup(square, text)
            

            index_label = Text(str(idx), font_size=12, color=GRAY)
            index_label.next_to(cell, DOWN, buff=0.08)
            
            cell_group = VGroup(cell, index_label)
            row_group.add(cell_group)
        

        row_group.arrange(RIGHT, buff=0.15)
        
        return row_group
    
    
    def _animate_update_style(self, params):

        if self.data_type != "array":
            return
        
        arr, _ = self._get_array_list_ref()
        if not arr:
            return
        
        style_key = params.get("styleKey")
        indices = params.get("indices", [])
        

        for i in indices:
            if 0 <= i < len(arr):
                arr[i]["state"] = style_key


        style_key_lower = str(style_key or "").lower()
        if ("compare" in style_key_lower) and isinstance(indices, list) and len(indices) >= 2:
            valid = [int(i) for i in indices if isinstance(i, int) and 0 <= i < len(arr)]
            if len(valid) >= 2:
                uniq = sorted(set(valid))
                pairs = []
                for x in range(len(uniq)):
                    for y in range(x + 1, len(uniq)):
                        pairs.append({"a": uniq[x], "b": uniq[y]})
                        if len(pairs) >= 6:
                            break
                    if len(pairs) >= 6:
                        break
                if pairs:
                    merged = False
                    for t in self.temp_elements:
                        if t.get("type") == "array_compare" and t.get("styleKey") == style_key:
                            existing = t.get("pairs", []) or []
                            existing.extend(pairs)
                            t["pairs"] = existing
                            merged = True
                            break
                    if not merged:
                        self.temp_elements.append({
                            "type": "array_compare",
                            "pairs": pairs,
                            "styleKey": style_key
                        })
        
        if self.fast_mode:
            return
        
        animations = []
        stroke_color, fill_color, text_color = self._get_element_style(style_key)
        fill_opacity, stroke_width = self._get_array_cell_render_params(style_key)
        
        for i in indices:
            if 0 <= i < len(self.array_mobjects):
                cell = self.array_mobjects[i]
                animations.extend([
                    cell[0].animate.set_stroke(stroke_color, width=stroke_width),
                    cell[0].animate.set_fill(fill_color, opacity=fill_opacity)
                ])
                if len(cell) > 1:
                    animations.append(cell[1].animate.set_color(text_color))
        
        if animations:
            self.play(*animations, run_time=self.transition_time * 0.4)

    
    def _animate_move_elements(self, params):
        if self.data_type != "array":
            return
        
        pairs = params.get("pairs", [])
        arr, _ = self._get_array_list_ref()
        if not arr:
            return
        
        undirected = set()
        valid_pairs = []
        for p in pairs:
            src, dst = p.get("fromIndex"), p.get("toIndex")
            if src is None or dst is None or src == dst:
                continue
            if 0 <= src < len(arr) and 0 <= dst < len(arr):
                key = (min(src, dst), max(src, dst))
                if key in undirected:
                    continue  
                undirected.add(key)
                valid_pairs.append((src, dst))
        
        if not valid_pairs:
            return
        
        for src, dst in valid_pairs:
            arr[src], arr[dst] = arr[dst], arr[src]
            arr[src]["index"], arr[dst]["index"] = src, dst
        
        
        for src, dst in valid_pairs:
            if src < len(self.array_mobjects) and dst < len(self.array_mobjects):
                self.array_mobjects[src], self.array_mobjects[dst] = self.array_mobjects[dst], self.array_mobjects[src]
        
        if params.get("animationKey") == "swap":
            rec_pairs = [{"a": min(src, dst), "b": max(src, dst)} for src, dst in set((min(s, d), max(s, d)) for s, d in valid_pairs)]
            if rec_pairs:
                self.temp_elements.append({
                    "type": "swap_arrows",
                    "pairs": rec_pairs,
                    "styleKey": params.get("styleKey", "arrow")
                })
        
        if self.fast_mode:
            self.skip_smooth_transition = True
            return
        

        animations = []
        reset_anims = []
        
        for src, dst in valid_pairs:
            if src < len(self.array_mobjects) and dst < len(self.array_mobjects):
                cell_src, cell_dst = self.array_mobjects[src], self.array_mobjects[dst]
                

                animations.append(cell_src.animate.move_to(cell_dst.get_center()).set_color(YELLOW))
                animations.append(cell_dst.animate.move_to(cell_src.get_center()).set_color(YELLOW))
                

                _, fill_src, _ = self._get_element_style(arr[src].get("state", "idle"))
                _, fill_dst, _ = self._get_element_style(arr[dst].get("state", "idle"))
                reset_anims.extend([
                    cell_src[0].animate.set_color(fill_src),
                    cell_dst[0].animate.set_color(fill_dst)
                ])
        

        if animations:
            self.play(*animations, run_time=self.transition_time * 0.6)
            if reset_anims:
                self.play(*reset_anims, run_time=self.transition_time * 0.15)
            
            self.skip_smooth_transition = True
    
    def _animate_shift_elements(self, params):
        if self.data_type != "array":
            return
        
        shifts = params.get("shifts", [])
        pairs = [{"fromIndex": s.get("fromIndex"), "toIndex": s.get("toIndex")} for s in shifts]
        self._animate_move_elements({**params, "pairs": pairs})
    
    def _animate_update_values(self, params):
        if self.data_type != "array":
            return
        
        arr, _ = self._get_array_list_ref()
        if not arr:
            return
        
        snapshot = copy.deepcopy(arr)
        updates = params.get("updates", [])
        
        for u in updates:
            idx, val = u.get("index"), u.get("value")
            if idx is not None and 0 <= idx < len(arr):
                arr[idx]["value"] = val
        

        swap_arrow_mobjects = []
        try:
            updated_indices = [u.get("index") for u in updates if isinstance(u.get("index"), int)]
            prev_val = {i: snapshot[i]["value"] for i in range(len(snapshot))}
            new_val = {i: arr[i]["value"] for i in range(len(arr))}
            pairs = []
            for i, ui in enumerate(updated_indices):
                for uj in updated_indices[i + 1:]:
                    if ui != uj and new_val.get(ui) == prev_val.get(uj) and new_val.get(uj) == prev_val.get(ui):
                        pairs.append({"a": min(ui, uj), "b": max(ui, uj)})
            
            if pairs:

                self.temp_elements.append({
                    "type": "swap_arrows",
                    "pairs": list({(p["a"], p["b"]): p for p in pairs}.values()),
                    "styleKey": params.get("styleKey", "arrow")
                })
                
                if len(self.array_mobjects) > 0:
                    color, width = self._resolve_dep_style(params.get("styleKey", "arrow"))
                    for pair in pairs:
                        a, b = pair.get("a"), pair.get("b")
                        if 0 <= a < len(self.array_mobjects) and 0 <= b < len(self.array_mobjects):
                            cell_a = self.array_mobjects[a]
                            cell_b = self.array_mobjects[b]
                            
                            arrow = DoubleArrow(
                                cell_a.get_top(),
                                cell_b.get_top(),
                                color=color,
                                buff=0.3,
                                stroke_width=max(3, width),
                                tip_length=0.2
                            )
                            swap_arrow_mobjects.append(arrow)
                            self.add(arrow)
        except Exception:
            pass
        
        if swap_arrow_mobjects:
            if 'temp_arrows' not in self.mobject_cache:
                self.mobject_cache['temp_arrows'] = []
            self.mobject_cache['temp_arrows'].extend(swap_arrow_mobjects)
        

        if self.fast_mode:
            return
        
        animations = []
        for u in updates:
            idx, val = u.get("index"), u.get("value")
            if idx is not None and 0 <= idx < len(arr) and idx < len(self.array_mobjects):
                cell = self.array_mobjects[idx]
                if len(cell) > 1:
                    new_text = Text(str(val), font_size=22)
                    if len(cell) > 0:
                        cell_width = cell[0].width if hasattr(cell[0], 'width') else self.cell_size
                        max_text_width = cell_width * 0.85
                        if new_text.width > max_text_width:
                            new_text.scale(max_text_width / new_text.width)
                    new_text.move_to(cell[1].get_center())
                    _, _, text_color = self._get_element_style(arr[idx].get("state", "idle"))
                    new_text.set_color(text_color)
                    animations.append(Transform(cell[1], new_text))
        
        if animations:
            self.play(*animations, run_time=self.transition_time * 0.3)
        
        changed = [u.get("index") for u in updates if isinstance(u.get("index"), int) and 0 <= u.get("index") < len(arr)]
        if changed:
            self.temp_elements.append({
                "type": "array_change_flash",
                "indices": changed,
                "styleKey": params.get("styleKey", "changed")
            })
    
    def _animate_update_node_style(self, params):
        if self.data_type not in ("graph", "tree"):
            return
        
        nodes = self.current_data_state.get("structure", {}).get("nodes", [])
        ids = set(params.get("ids", []) or [])
        style_key = params.get("styleKey")
        

        for node in nodes:
            if node.get("id") in ids:
                node["styleKey"] = style_key
        

        if self.fast_mode:
            return
        

        animations = []
        mobject_dict = self.graph_mobjects if self.data_type == "graph" else self.tree_mobjects
        stroke_color, fill_color, text_color = self._get_element_style(style_key)
        
        for node_id in ids:
            if node_id in mobject_dict:
                node_mob = mobject_dict[node_id]
                if len(node_mob) > 0:
                    animations.extend([
                        node_mob[0].animate.set_stroke(stroke_color, width=2.5),
                        node_mob[0].animate.set_fill(fill_color, opacity=0.35)
                    ])
                if len(node_mob) > 1:
                    animations.append(node_mob[1].animate.set_color(text_color))
        

        if animations:
            self.play(*animations, run_time=self.transition_time * 0.4)
    
    def _animate_update_node_properties(self, params):

        if self.data_type not in ("graph", "tree"):
            return
        
        nodes = self.current_data_state.get("structure", {}).get("nodes", [])
        node_dict = {n.get("id"): n for n in nodes}
        
        for update in params.get("updates", []) or []:
            target_id = update.get("id")
            if target_id in node_dict:
                node_dict[target_id].setdefault("properties", {}).update(update.get("properties", {}))
    
    def _animate_update_edge_style(self, params):

        if self.data_type not in ("graph", "tree"):
            return
        
        edges = self.current_data_state.get("structure", {}).get("edges", [])
        edge_keys = set((e.get("from"), e.get("to")) if isinstance(e, dict) else e for e in params.get("edges", []) or [])
        style_key = params.get("styleKey")
        

        for edge in edges:
            if (edge.get("from"), edge.get("to")) in edge_keys:
                edge["styleKey"] = style_key
    
    def _animate_update_table_cell(self, params):

        view_id = params.get("view_id")
        updates = params.get("updates", [])
        
        def update_table_data(table_data, updates):
            for u in updates:
                r, c, val = u.get("row"), u.get("col"), u.get("value")
                if r is not None and c is not None and 0 <= r < len(table_data) and 0 <= c < len(table_data[r]):
                    table_data[r][c] = val
        
        def create_cell_animations(vid, updates):
            anims = []
            if vid in self.table_mobjects:
                for u in updates:
                    r, c, val = u.get("row"), u.get("col"), u.get("value")
                    if (r, c) in self.table_mobjects[vid]:
                        cell_mob = self.table_mobjects[vid][(r, c)]
                        if len(cell_mob) > 1:
                            new_text = Text(str(val), font_size=18)

                            if len(cell_mob) > 0:
                                cell_width = cell_mob[0].width if hasattr(cell_mob[0], 'width') else 0.65
                                max_text_width = cell_width * 0.85
                                if new_text.width > max_text_width:
                                    new_text.scale(max_text_width / new_text.width)
                            new_text.move_to(cell_mob[1].get_center())
                            anims.append(Transform(cell_mob[1], new_text))
            return anims
        

        for view in self.current_aux_views:
            if view.get("view_id") == view_id and view.get("type") == "table":
                update_table_data(view.get("data", []), updates)
        

        if self.data_type == "table":
            curr_vid = self.current_data_state.get("view_id", "main_table")

            if view_id in (None, curr_vid, "dp_table", "data_state", "main_table"):
                update_table_data(self.current_data_state.get("data", []), updates)
        

        if self.fast_mode:
            return
        
        animations = create_cell_animations(view_id, updates)
        if self.data_type == "table" and view_id in (None, self.current_data_state.get("view_id", "main_table"), "dp_table", "data_state", "main_table"):
            animations.extend(create_cell_animations(self.current_data_state.get("view_id", "main_table"), updates))
        
        if animations:
            self.play(*animations, run_time=self.transition_time * 0.3)
    
    def _animate_highlight_table_cell(self, params):
        self.temp_elements.append({"type": "table_highlight", **params})
    
    def _animate_show_dependency(self, params):
        self.dependencies.append(params)
    
    def _animate_update_boundary(self, params):
        boundary_element = {"type": "boundary_box", "original_type": params.get("type"), **params}
        boundary_element["type"] = "boundary_box"
        self.temp_elements.append(boundary_element)
    
    def _animate_remove_boundary(self, params):
        type_to_remove = params.get("type")
        self.temp_elements = [e for e in self.temp_elements 
                              if not (e.get("type") == "boundary_box" and e.get("original_type") == type_to_remove)]
    
    def _animate_add_node(self, params):
        if self.data_type != "graph":
            return
        
        node = params.get("node")
        if node and node.get("id"):
            nodes = self.current_data_state.get("structure", {}).setdefault("nodes", [])
            if node.get("id") not in {n.get("id") for n in nodes}:
                nodes.append(node)
    
    def _animate_remove_node(self, params):
        if self.data_type != "graph":
            return
        
        node_id = params.get("id")
        if node_id:
            struct = self.current_data_state.get("structure", {})
            struct["nodes"] = [n for n in struct.get("nodes", []) if n.get("id") != node_id]
    
    def _animate_add_edge(self, params):
        if self.data_type != "graph":
            return
        
        edge = params.get("edge")
        if edge:
            self.current_data_state.get("structure", {}).setdefault("edges", []).append(edge)
    
    def _animate_remove_edge(self, params):
        if self.data_type != "graph":
            return
        
        from_id, to_id = params.get("from"), params.get("to")
        if from_id and to_id:
            struct = self.current_data_state.get("structure", {})
            struct["edges"] = [e for e in struct.get("edges", []) if not (e.get("from") == from_id and e.get("to") == to_id)]
    
    def _animate_variable_change(self, var_name: str, old_val: Any, new_val: Any):
        pass
    
    
    def _animate_add_aux_view(self, params):
        view_data = params.get('view')
        if view_data:
            self.current_aux_views.append(view_data)
    
    def _animate_remove_aux_view(self, params):
        view_id_to_remove = params.get('view_id')
        self.current_aux_views = [v for v in self.current_aux_views 
                                   if v.get('view_id') != view_id_to_remove]
    
    def _find_aux_view_by_id(self, view_id):
        for view in self.current_aux_views:
            if view.get("view_id") == view_id:
                return view
        return None
    
    def _animate_append_to_list(self, params):
        view_id = params.get("view_id")
        value = params.get("value")
        list_key = params.get("list_key")
        
        view = self._find_aux_view_by_id(view_id)
        if not view:
            view = {
                "view_id": view_id,
                "type": "list",
                "title": view_id,
                "data": []
            }
            self.current_aux_views.append(view)
        
        data = view.get("data")
        if isinstance(data, dict):
            if list_key is None:
                return
            data.setdefault(list_key, [])
            data[list_key].append(value)
        else:
            if not isinstance(data, list):
                view["data"] = []
            view["data"].append(value)
    
    def _animate_pop_from_list(self, params):
        view_id = params.get("view_id")
        where = params.get("from")
        index = params.get("index")
        value = params.get("value")
        list_key = params.get("list_key")
        
        view = self._find_aux_view_by_id(view_id)
        if not view:
            return
        
        data = view.get("data")
        if isinstance(data, dict):
            if list_key is None or list_key not in data:
                return
            lst = data[list_key]
        else:
            lst = data
        
        if not isinstance(lst, list):
            return
        
        if value is not None:
            try:
                lst.remove(value)
            except ValueError:
                pass
        elif index is not None and isinstance(index, int) and 0 <= index < len(lst):
            lst.pop(index)
        elif where == "head" and lst:
            lst.pop(0)
        elif where == "tail" and lst:
            lst.pop()
    
    def _animate_clear_list(self, params):

        view_id = params.get("view_id")
        view = self._find_aux_view_by_id(view_id)
        if not view:
            return
        
        data = view.get("data")
        if isinstance(data, dict):
            for k in list(data.keys()):
                if isinstance(data[k], list):
                    data[k].clear()
        elif isinstance(data, list):
            data.clear()
    
    def _animate_insert_into_bucket(self, params):
        if self.data_type != "hashtable":
            return
        
        bucket_index = params.get("bucket_index")
        element = params.get("element")
        
        if bucket_index is None or element is None:
            return
        

        struct = self.current_data_state.get("structure", {})
        buckets = struct.get("buckets", [])
        

        if 0 <= bucket_index < len(buckets):
            bucket = buckets[bucket_index]
            items = bucket.setdefault("items", [])
            
            items.append(element)
    
    def _animate_update_in_bucket(self, params):
        if self.data_type != "hashtable":
            return
        
        bucket_index = params.get("bucket_index")
        key = params.get("key")
        value = params.get("value")
        
        if bucket_index is None or key is None:
            return
        
        struct = self.current_data_state.get("structure", {})
        buckets = struct.get("buckets", [])
        
        if 0 <= bucket_index < len(buckets):
            bucket = buckets[bucket_index]
            items = bucket.get("items", [])
            
            for item in items:
                if item.get("key") == key:
                    item["value"] = value
                    break
    
    def _animate_show_hash(self, params):
        pass
    
    def _animate_highlight_collision(self, params):

        pass
    
    def _animate_highlight_bucket(self, params):

        pass
    
    def _animate_show_comment(self, params):
        text = params.get("text")
        if text:
            self.current_comment_text = text
    
    def _animate_remove_from_bucket(self, params):
        if self.data_type != "hashtable":
            return
        
        bucket_index = params.get("bucket_index")
        key = params.get("key")
        
        if bucket_index is None or key is None:
            return
        

        struct = self.current_data_state.get("structure", {})
        buckets = struct.get("buckets", [])
        

        if 0 <= bucket_index < len(buckets):
            bucket = buckets[bucket_index]
            items = bucket.get("items", [])
            

            bucket["items"] = [item for item in items if item.get("key") != key]
    
    def _animate_add_child(self, params):
        if self.data_type != "tree":
            return
        
        parent_id = params.get("parent_id")
        node = params.get("node")
        index = params.get("index") 
        
        if node is None or not isinstance(node, dict):
            return
        

        struct = self.current_data_state.get("structure", {})
        nodes = struct.setdefault("nodes", [])
        

        node_id = node.get("id")
        if node_id and node_id not in {n.get("id") for n in nodes}:
            nodes.append(node)
        

        if parent_id:
            for n in nodes:
                if n.get("id") == parent_id:
                    children = n.setdefault("children", [])
                    if node_id not in children:
                        if index is not None and 0 <= index <= len(children):
                            children.insert(index, node_id)
                        else:
                            children.append(node_id)
                    break
        else:

            if not struct.get("root"):
                struct["root"] = node_id
    
    def _animate_remove_child(self, params):
        if self.data_type != "tree":
            return
        
        parent_id = params.get("parent_id")
        child_id = params.get("child_id")
        
        if not parent_id or not child_id:
            return
        
        struct = self.current_data_state.get("structure", {})
        nodes = struct.get("nodes", [])
        
        for node in nodes:
            if node.get("id") == parent_id:
                children = node.get("children", [])
                if child_id in children:
                    children.remove(child_id)
                break
    
    def _animate_reparent(self, params):
        if self.data_type != "tree":
            return
        
        node_id = params.get("node_id")
        new_parent_id = params.get("new_parent_id")
        index = params.get("index") 
        
        if not node_id:
            return
        
        struct = self.current_data_state.get("structure", {})
        nodes = struct.get("nodes", [])
        
        target_node = None
        for node in nodes:
            if node.get("id") == node_id:
                target_node = node
                break
        
        if not target_node:
            return
        
        old_parent_id = target_node.get("parent")
        if old_parent_id:
            for node in nodes:
                if node.get("id") == old_parent_id:
                    children = node.get("children", [])
                    if node_id in children:
                        children.remove(node_id)
                    break
        
        target_node["parent"] = new_parent_id
        if new_parent_id:
            for node in nodes:
                if node.get("id") == new_parent_id:
                    children = node.setdefault("children", [])
                    if node_id not in children:
                        if index is not None and 0 <= index <= len(children):
                            children.insert(index, node_id)
                        else:
                            children.append(node_id)
                    break
        else:
            struct["root"] = node_id
    
    def _animate_swap_nodes(self, params):
        if self.data_type != "tree":
            return
        
        a_id = params.get("a_id")
        b_id = params.get("b_id")
        swap_children = params.get("swap_children", False)
        
        if not a_id or not b_id:
            return
        
        struct = self.current_data_state.get("structure", {})
        nodes = struct.get("nodes", [])
        
        node_a, node_b = None, None
        for node in nodes:
            if node.get("id") == a_id:
                node_a = node
            elif node.get("id") == b_id:
                node_b = node
        
        if not node_a or not node_b:
            return
        
        if "label" in node_a and "label" in node_b:
            node_a["label"], node_b["label"] = node_b["label"], node_a["label"]
        
        if "properties" in node_a and "properties" in node_b:
            node_a["properties"], node_b["properties"] = node_b["properties"], node_a["properties"]
        
        if swap_children:
            if "children" in node_a and "children" in node_b:
                node_a["children"], node_b["children"] = node_b["children"], node_a["children"]
    
    def _animate_highlight_path(self, params):
        pass
    
    
    def _apply_operation_silent(self, op_name: str, params: Dict):
        pass
    
    def _get_array_list(self):
        if self.data_type != "array":
            return []
        ds = self.current_data_state
        arr = ds.get("data")
        if isinstance(arr, list):
            return arr
        struct = ds.get("structure")
        if isinstance(struct, list):
            return struct
        return []
    
    def _get_array_list_ref(self):
        if self.data_type != "array":
            return None, None
        ds = self.current_data_state
        if isinstance(ds.get("data"), list):
            return ds["data"], "data"
        if isinstance(ds.get("structure"), list):
            return ds["structure"], "structure"
        return None, None
    
    def _generate_action_description(self, delta):
        if not delta:
            return "Initial State"
        operations = delta.get("operations", [])
        if not operations:
            return "Process"
        
        flat_ops = [
            op for group in operations
            for op in (group if isinstance(group, list) else [group])
            if isinstance(op, dict) and op.get("op")
        ]
        op_names = [op.get("op") for op in flat_ops]
        unique_ops = list(dict.fromkeys(op_names))
        return " | ".join(unique_ops) if unique_ops else "Process"


def render_svl_to_video(json_path: str, output_path: str = "output.mp4", quality: str = "high_quality", clean_cache: bool = False):

    with open(json_path, 'r', encoding='utf-8') as f:
        svl_data = json.load(f)
    
    class TempScene(SVLManimRenderer):
        def __init__(self, **kwargs):
            super().__init__(svl_data, **kwargs)
    
    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    output_filename = os.path.basename(output_path)
    
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    config.pixel_height = 1080  
    config.pixel_width = 1920   
    config.frame_height = 10.0  
    config.frame_width = 16.0   
    
    config.quality = quality
    config.pixel_format = "yuv420p"
    config.background_color = "#1a1a1a"
    
    config.scene_names = ["TempScene"]
    config.output_file = output_filename.replace('.mp4', '')
    config.save_last_frame = False 
    config.write_to_movie = True 
    
    import logging
    logging.getLogger("manim").setLevel(logging.WARNING)

    try:
        config.disable_caching_warning = True
    except Exception:
        pass
    
    try:
        print(f"🎬 Rendering: {os.path.basename(json_path)}")
        print(f"📊 Total frames: {len(svl_data.get('deltas', [])) + 1}")
        
        scene = TempScene()
        scene.render()
        
        quality_dir_map = {
            "low_quality": "480p15",
            "medium_quality": "720p30", 
            "high_quality": "1080p60",
            "production_quality": "1440p60"
        }
        quality_dir = quality_dir_map.get(quality, "720p30")
        
        media_base = config.media_dir if hasattr(config, 'media_dir') and config.media_dir else "media"
        
        output_basename = output_filename.replace('.mp4', '')
        possible_sources = [
            os.path.join(media_base, "videos", quality_dir, f"{output_basename}.mp4"),
            os.path.join(media_base, "videos", quality_dir, "TempScene.mp4"),
            os.path.join(media_base, "videos", quality_dir, f"{config.output_file}.mp4"),
            os.path.join(media_base, "videos", "TempScene.mp4")
        ]
        
        source_file = None
        for src in possible_sources:
            if os.path.exists(src):
                source_file = src
                break
        
        if source_file:
            shutil.move(source_file, output_path)
            file_size_mb = os.path.getsize(output_path) / (1024*1024)
            print(f"✅ Done: {os.path.basename(output_path)} ({file_size_mb:.1f}MB)")
        else:
            print(f"  Could not find Manim output file, tried the following paths:")
            for src in possible_sources:
                print(f"    • {src}")
            print(f"📂 Current media/videos directory contents:")
            videos_dir = os.path.join(media_base, "videos")
            if os.path.exists(videos_dir):
                for root, dirs, files in os.walk(videos_dir):
                    for f in files:
                        if f.endswith('.mp4'):
                            full_path = os.path.join(root, f)
                            print(f"    • {full_path}")
        
        if clean_cache:
            import shutil as sh
            for qdir in quality_dir_map.values():
                partial_dir = os.path.join(media_base, "videos", qdir, "partial_movie_files")
                if os.path.exists(partial_dir):
                    try:
                        sh.rmtree(partial_dir)
                    except:
                        pass
    except Exception as e:
        print(f"❌ Failed: {str(e)[:100]}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SVL 5.0 Manim renderer - full version")
    parser.add_argument("json_file", help="Path to SVL JSON file")
    parser.add_argument("--output", "-o", help="Output video path", default="output.mp4")
    parser.add_argument("--quality", "-q", help="Video quality (default: high_quality, 1080p 60fps)", 
                       choices=["low_quality", "medium_quality", "high_quality", "production_quality"],
                       default="high_quality")
    parser.add_argument("--codec", "-c", help="Video codec", 
                       choices=["libx264", "libopenh264", "mpeg4"],
                       default="mpeg4")
    parser.add_argument("--clean-cache", action="store_true", 
                       help="Clean temporary files after rendering (save disk space)")
    parser.add_argument("--fast", action="store_true",
                       help="Fast mode: skip detailed animations and greatly speed up rendering")
    
    args = parser.parse_args()
    
    if args.fast:
        os.environ["SVL_FAST_MODE"] = "1"
        os.environ["SVL_TRANSITION_TIME"] = "0.3"
        os.environ["SVL_PAUSE_TIME"] = "0.1"
    
    if not os.path.exists(args.json_file):
        print(f"❌ Error: file not found '{args.json_file}'")
        sys.exit(1)
    
    print(f"🎬 Video quality: {args.quality}")
    print(f"🎞️  Video codec: {args.codec}")
    if args.fast:
        print(f"⚡ Fast mode enabled (skipping detailed animations)")
    
    config.video_codec = args.codec
    
    render_svl_to_video(args.json_file, args.output, args.quality, args.clean_cache)

