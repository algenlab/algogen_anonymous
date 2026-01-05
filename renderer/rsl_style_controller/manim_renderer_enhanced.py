#!/usr/bin/env python3
"""
SVL 5.0 Manim 渲染器 - LLM配置增强版
基于原 manim_renderer.py，新增配置驱动的布局和样式系统
"""

import sys
import os
import json
from typing import Dict, Any, Optional, Tuple

base_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(base_dir, '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
manim_dir = os.path.join(project_root, 'manim')
if manim_dir not in sys.path:
    sys.path.insert(0, manim_dir)

# 导入Manim库
from manim import *
import numpy as np

# 导入用户的SVL Manim渲染器
from manim_renderer import SVLManimRenderer

class ConfigurableSVLRenderer(SVLManimRenderer):
    
    def __init__(self, svl_data: Dict[str, Any], render_config: Optional[Dict] = None, **kwargs):
        # 先保存配置，再调用父类初始化
        self.render_config = render_config or {}
        
        # 调用父类初始化
        super().__init__(svl_data, **kwargs)
        
        # 应用配置覆盖
        if self.render_config:
            self._apply_config_overrides()
    
    def _apply_config_overrides(self):

        timing = self.render_config.get('style_overrides', {}).get('animation_timing', {})
        if timing:
            self.transition_time = timing.get('transition', self.transition_time)
            self.pause_time = timing.get('pause', self.pause_time)
        
        layout = self.render_config.get('layout_strategy', {}).get('main_view', {})
        layout_type = layout.get('type')
        params = layout.get('params', {})
        
        if layout_type == 'force_directed' and params:

            self.graph_gap_x = params.get('node_spacing', self.graph_gap_x)
            self.graph_gap_y = params.get('node_spacing', self.graph_gap_y)

        
        elif layout_type in ('grid', 'matrix') and params:
            self.cell_size = params.get('cell_size', self.cell_size)
        
        elif layout_type == 'horizontal_array' and params:
            self.cell_size = params.get('cell_size', self.cell_size)
            self.elem_spacing = params.get('spacing', self.elem_spacing)
        
        self._merge_config_styles()
    
    def _merge_config_styles(self):
        style_overrides = self.render_config.get('style_overrides', {})
        
        element_styles = style_overrides.get('element_styles', {})
        if element_styles:
            if 'elementStyles' not in self.styles:
                self.styles['elementStyles'] = {}
            
            for style_key, style_def in element_styles.items():
                # 转换配置格式到trace格式
                self.styles['elementStyles'][style_key] = {
                    'fill': style_def.get('fill', '#f0f0f0'),
                    'stroke': style_def.get('stroke', '#666666'),
                    'strokeWidth': style_def.get('stroke_width', 2),
                    'textColor': style_def.get('text_color', '#000000'),
                    'opacity': style_def.get('opacity', 1.0)
                }
            
        
        color_scheme = style_overrides.get('color_scheme', {})
        if color_scheme:
            pass
    
    def _get_element_style(self, style_key: str) -> Tuple[str, str, str]:
        # 先尝试从配置读取
        if self.render_config:
            custom_styles = self.render_config.get('style_overrides', {}).get('element_styles', {})
            if style_key in custom_styles:
                style = custom_styles[style_key]
                stroke = self._parse_color(style.get('stroke', '#666666'))
                fill = self._parse_color(style.get('fill', '#f0f0f0'))
                text_color = self._parse_color(style.get('text_color', '#FFFFFF'))
                return stroke, fill, text_color
        
        # 回退到父类的样式解析
        return super()._get_element_style(style_key)
    
    def _create_graph_view(self) -> VGroup:
        layout_config = self.render_config.get('layout_strategy', {}).get('main_view', {})
        layout_type = layout_config.get('type', 'force_directed')
        
        if self.data_type == 'graph' and layout_type == 'circular':
            return self._create_graph_view_circular()
        elif self.data_type == 'graph' and layout_type == 'hierarchical':
            return self._create_graph_view_hierarchical()
        else:
            return super()._create_graph_view()
    
    def _create_graph_view_circular(self) -> VGroup:
        struct = self.current_data_state.get("structure", {})
        nodes = struct.get("nodes", []) or []
        edges = struct.get("edges", []) or []
        
        if not nodes:
            return VGroup()
        
        nodes_group = VGroup()
        edges_group = VGroup()
        self.graph_mobjects = {}
        
        radius = min(4.0, 2.0 + len(nodes) * 0.3)
        angle_step = 2 * PI / len(nodes)
        
        for i, node in enumerate(nodes):
            angle = i * angle_step
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)
            
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
            node_mob.move_to([x, y, 0])
            
            nodes_group.add(node_mob)
            self.graph_mobjects[node_id] = node_mob
        
        for edge in edges:
            from_id = edge.get('from')
            to_id = edge.get('to')
            
            if from_id in self.graph_mobjects and to_id in self.graph_mobjects:
                from_node = self.graph_mobjects[from_id]
                to_node = self.graph_mobjects[to_id]
                
                directed = edge.get("directed", False)
                style_key = edge.get('styleKey', 'normal_edge')
                
                edge_color, text_color, line_width = self._get_edge_style(style_key)
                
                buff_size = self.node_size + 0.05
                
                if directed:
                    arrow = Arrow(
                        from_node.get_center(),
                        to_node.get_center(),
                        color=edge_color,
                        buff=buff_size,
                        stroke_width=line_width,
                        max_tip_length_to_length_ratio=0.15
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
                
                # 边标签
                label = edge.get("label", "")
                if label:
                    label_text = Text(label, font_size=12, color=text_color, weight=BOLD)
                    label_text.move_to(arrow.get_center())
                    label_bg = BackgroundRectangle(label_text, color=WHITE, fill_opacity=0.85, buff=0.05)
                    label_group = VGroup(label_bg, label_text)
                    edges_group.add(label_group)
        
        return VGroup(edges_group, nodes_group)
    
    def _create_graph_view_hierarchical(self) -> VGroup:
        struct = self.current_data_state.get("structure", {})
        nodes = struct.get("nodes", []) or []
        edges = struct.get("edges", []) or []
        
        if not nodes:
            return VGroup()
        
        from collections import deque, defaultdict
        
        in_degree = defaultdict(int)
        adj_list = defaultdict(list)
        
        for edge in edges:
            from_id = edge.get('from')
            to_id = edge.get('to')
            in_degree[to_id] += 1
            adj_list[from_id].append(to_id)
        
        roots = [n.get('id') for n in nodes if in_degree[n.get('id')] == 0]
        if not roots:
            roots = [nodes[0].get('id')]
        
        levels = []
        visited = set()
        q = deque([(r, 0) for r in roots])
        
        while q:
            node_id, level = q.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            
            if level >= len(levels):
                levels.append([])
            levels[level].append(node_id)
            
            for child_id in adj_list[node_id]:
                if child_id not in visited:
                    q.append((child_id, level + 1))
        
        nodes_group = VGroup()
        edges_group = VGroup()
        self.graph_mobjects = {}
        
        id_to_node = {n.get('id'): n for n in nodes}
        vgap = 2.0
        
        for level_idx, level_nodes in enumerate(levels):
            hgap = min(3.0, 10.0 / max(len(level_nodes), 1))
            y = -level_idx * vgap
            
            for i, node_id in enumerate(level_nodes):
                x = (i - (len(level_nodes) - 1) / 2) * hgap
                
                node = id_to_node.get(node_id, {})
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
                node_mob.move_to([x, y, 0])
                
                nodes_group.add(node_mob)
                self.graph_mobjects[node_id] = node_mob
        
        for edge in edges:
            from_id = edge.get('from')
            to_id = edge.get('to')
            
            if from_id in self.graph_mobjects and to_id in self.graph_mobjects:
                from_node = self.graph_mobjects[from_id]
                to_node = self.graph_mobjects[to_id]
                
                directed = edge.get("directed", False)
                style_key = edge.get('styleKey', 'normal_edge')
                
                edge_color, text_color, line_width = self._get_edge_style(style_key)
                
                buff_size = self.node_size + 0.05
                
                if directed:
                    arrow = Arrow(
                        from_node.get_center(),
                        to_node.get_center(),
                        color=edge_color,
                        buff=buff_size,
                        stroke_width=line_width,
                        max_tip_length_to_length_ratio=0.15
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
                
                label = edge.get("label", "")
                if label:
                    label_text = Text(label, font_size=12, color=text_color, weight=BOLD)
                    label_text.move_to(arrow.get_center())
                    label_bg = BackgroundRectangle(label_text, color=WHITE, fill_opacity=0.85, buff=0.05)
                    label_group = VGroup(label_bg, label_text)
                    edges_group.add(label_group)
        
        return VGroup(edges_group, nodes_group)


def render_svl_with_config(
    trace_path: str, 
    config_path: str = None,
    output_path: str = "output.mp4", 
    quality: str = "medium_quality",
    clean_cache: bool = False
):
    with open(trace_path, 'r', encoding='utf-8') as f:
        svl_data = json.load(f)
    
    if config_path is None:
        config_path = trace_path.replace('.json', '_render_config.json')
    
    render_config = None
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            render_config = json.load(f)
    else:
        print(f"未找到配置文件: {config_path}")
        print(f"使用默认配置")
    
    class TempScene(ConfigurableSVLRenderer):
        def __init__(self, **kwargs):
            super().__init__(svl_data, render_config, **kwargs)
    
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
    
    if render_config:
        bg_color = render_config.get('style_overrides', {}).get('color_scheme', {}).get('background', '#1a1a1a')
    else:
        bg_color = "#1a1a1a"
    try:
        from manim.utils.color import Color as MColor
        config.background_color = MColor(bg_color)
    except Exception:
        config.background_color = "#1a1a1a"
    
    config.scene_names = ["TempScene"]
    config.output_file = output_filename.replace('.mp4', '')
    config.save_last_frame = False
    config.write_to_movie = True
    
    import logging
    logging.getLogger("manim").setLevel(logging.WARNING)
    
    os.environ['TQDM_DISABLE'] = '1'
    
    import sys
    from io import StringIO
    
    class FilteredStdout:
        """过滤输出，只保留包含'帧:'的行，丢弃所有其他输出（包括Animation进度条、tqdm等）"""
        def __init__(self, original):
            self.original = original
            self.buffer = ""
        
        def write(self, text):
            # 累积输出到buffer（tqdm可能分多次写入）
            self.buffer += text
            
            # 检查buffer中是否有完整的行包含"帧:"
            if "\n" in self.buffer:
                lines = self.buffer.split("\n")
                # 保留最后一行（可能不完整）
                self.buffer = lines[-1]
                # 处理完整的行
                for line in lines[:-1]:
                    if "帧:" in line:
                        self.original.write(line + "\n")
                        self.original.flush()
                    # 其他行（包括Animation、tqdm进度条等）全部丢弃
            # 如果没有换行符，继续累积
        
        def flush(self):
            # 处理剩余的buffer
            if self.buffer and "帧:" in self.buffer:
                self.original.write(self.buffer)
                self.original.flush()
            self.buffer = ""
            self.original.flush()
        
        def __getattr__(self, name):
            return getattr(self.original, name)
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = FilteredStdout(old_stdout)
    sys.stderr = StringIO()  # stderr 完全禁用
    
    try:
        # 减少输出，只保留关键信息
        # print(f"🎬 渲染: {os.path.basename(trace_path)}")
        # if render_config:
        #     algo_name = render_config.get('algorithm_info', {}).get('name', 'Unknown')
        #     print(f"📊 算法: {algo_name}")
        # print(f"📊 总帧数: {len(svl_data.get('deltas', [])) + 1}")
        
        scene = TempScene()
        scene.render()
        
        # 查找并移动输出文件
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
        ]
        
        source_file = None
        for src in possible_sources:
            if os.path.exists(src):
                source_file = src
                break
        
        if source_file:
            import shutil
            shutil.move(source_file, output_path)
            file_size_mb = os.path.getsize(output_path) / (1024*1024)
            # 减少输出，不打印完成信息（由llm_render.py统一打印）
            # print(f"✅ 完成: {os.path.basename(output_path)} ({file_size_mb:.1f}MB)")
        else:
            # 恢复输出以显示错误
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            print(f"⚠️  未找到Manim输出文件")
            sys.stdout = StringIO()
            sys.stderr = StringIO()
        
        # 清理临时文件
        if clean_cache:
            import shutil as sh
            for qdir in quality_dir_map.values():
                partial_dir = os.path.join(media_base, "videos", qdir, "partial_movie_files")
                if os.path.exists(partial_dir):
                    try:
                        sh.rmtree(partial_dir)
                    except:
                        pass
        
        # 恢复 stdout/stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    
    except Exception as e:
        # 恢复输出以显示错误
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        print(f"❌ 失败: {str(e)[:100]}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SVL 5.0 Manim 渲染器 - LLM配置增强版")
    parser.add_argument("json_file", help="SVL JSON 文件路径")
    parser.add_argument("--config", "-c", help="渲染配置文件路径")
    parser.add_argument("--output", "-o", help="输出视频路径", default="output.mp4")
    parser.add_argument("--quality", "-q", help="视频质量",
                       choices=["low_quality", "medium_quality", "high_quality", "production_quality"],
                       default="medium_quality")
    parser.add_argument("--clean-cache", action="store_true",
                       help="渲染后清理临时文件")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.json_file):
        print(f"❌ 错误: 找不到文件 '{args.json_file}'")
        sys.exit(1)
    
    render_svl_with_config(
        args.json_file,
        args.config,
        args.output,
        args.quality,
        args.clean_cache
    )
