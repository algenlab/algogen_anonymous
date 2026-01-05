#!/usr/bin/env python3


from openai import OpenAI
import json
import os
import re
from typing import Dict, Any, List, Set
from pathlib import Path
import jsonschema

# 初始化LLM客户端（从环境变量读取配置，避免硬编码密钥）
API_BASE = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("SILICONFLOW_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "SILICONFLOW_API_KEY 环境变量未设置，无法调用 SiliconFlow / OpenAI 接口，请先在环境变量中配置 API Key。"
    )

client = OpenAI(
    base_url=API_BASE,
    api_key=API_KEY,
)

CURRENT_MODEL = 'deepseek-ai/DeepSeek-V3.2'

def load_schema() -> dict:
    """加载渲染配置schema"""
    # 本文件位于 Algogen/renderer/rsl_style_controller/
    # 渲染配置 schema 位于 Algogen/renderer/render_config_schema.json
    schema_path = Path(__file__).parent.parent / 'render_config_schema.json'
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_trace_features(trace: dict) -> dict:
    """
    分析trace.json，提取关键特征
    
    返回:
        trace_info: 包含算法类型、数据规模、操作列表等信息的字典
    """
    algorithm = trace.get('algorithm', {})
    initial_frame = trace.get('initial_frame', {})
    deltas = trace.get('deltas', [])
    data_state = initial_frame.get('data_state', {})
    
    # 统计使用的操作
    operations_used: Set[str] = set()
    for delta in deltas:
        for op_group in delta.get('operations', []):
            if isinstance(op_group, list):
                for op in op_group:
                    if isinstance(op, dict):
                        operations_used.add(op.get('op', 'unknown'))
    
    # 分析数据规模
    data_type = data_state.get('type', 'unknown')
    data_scale = {}
    
    if data_type == 'array':
        structure = data_state.get('structure', data_state.get('data', []))
        data_scale['array_length'] = len(structure) if isinstance(structure, list) else 0
    
    elif data_type == 'graph':
        structure = data_state.get('structure', {})
        nodes = structure.get('nodes', [])
        edges = structure.get('edges', [])
        data_scale['node_count'] = len(nodes)
        data_scale['edge_count'] = len(edges)
        data_scale['is_directed'] = any(e.get('directed', False) for e in edges)
    
    elif data_type == 'table':
        data = data_state.get('data', [])
        if isinstance(data, list) and len(data) > 0:
            data_scale['rows'] = len(data)
            data_scale['cols'] = len(data[0]) if isinstance(data[0], list) else 0
    
    elif data_type == 'tree':
        structure = data_state.get('structure', {})
        nodes = structure.get('nodes', [])
        data_scale['node_count'] = len(nodes)
    
    elif data_type == 'hashtable':
        structure = data_state.get('structure', {})
        data_scale['bucket_count'] = structure.get('size', 0)
    
    # 辅助视图
    aux_views = initial_frame.get('auxiliary_views', [])
    aux_view_types = [v.get('type') for v in aux_views if isinstance(v, dict)]
    
    # 判断复杂度
    complexity = 'simple'
    if data_type == 'array':
        if data_scale.get('array_length', 0) > 20:
            complexity = 'complex'
        elif data_scale.get('array_length', 0) > 10:
            complexity = 'medium'
    elif data_type == 'graph':
        if data_scale.get('node_count', 0) > 10:
            complexity = 'complex'
        elif data_scale.get('node_count', 0) > 5:
            complexity = 'medium'
    elif data_type == 'table':
        if data_scale.get('rows', 0) * data_scale.get('cols', 0) > 100:
            complexity = 'complex'
        elif data_scale.get('rows', 0) * data_scale.get('cols', 0) > 25:
            complexity = 'medium'
    
    return {
        'algorithm': {
            'name': algorithm.get('name', 'Unknown'),
            'family': algorithm.get('family', 'Unknown')
        },
        'data_type': data_type,
        'data_scale': data_scale,
        'frame_count': len(deltas) + 1,
        'operations_used': sorted(operations_used),
        'auxiliary_views': aux_view_types,
        'has_pseudocode': len(initial_frame.get('pseudocode', [])) > 0,
        'complexity': complexity
    }

def build_config_prompt(features: Dict, schema: Dict) -> str:
    """
    构建LLM生成配置的prompt
    
    参数:
        features: extract_trace_features的返回结果
        schema: 渲染配置schema
    
    返回:
        完整的prompt字符串
    """
    algorithm_name = features['algorithm']['name']
    algorithm_family = features['algorithm']['family']
    data_type = features['data_type']
    
    prompt = f"""你是一个算法可视化渲染配置专家。为 {algorithm_name} 算法生成Manim渲染配置（JSON格式）。

## 输入信息
- 算法名称: {algorithm_name}
- 算法家族: {algorithm_family}
- 数据类型: {data_type}
- 数据规模: {features['data_scale']}
- 帧数统计: {features['frame_count']} 帧
- 使用操作: {', '.join(features['operations_used'])}
- 辅助视图: {', '.join(features['auxiliary_views']) if features['auxiliary_views'] else '无'}
- 伪代码: {'有' if features['has_pseudocode'] else '无'}
- 复杂度: {features['complexity']}

## 配置Schema（必须严格遵守）
```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 设计原则

### 1. 布局策略选择
根据算法类型选择最合适的布局：
- **图算法** (graph_search, graph_topology, graph_mst, graph_flow) → force_directed 或 hierarchical
  - 节点间距: 3.5-5.0（根据节点数量调整，节点多则间距小）
  
- **DP算法** (dp) + table类型 → matrix
  - 单元格大小: 0.5-0.8（根据行列数调整）
  - 间距: 0.1-0.2
  
- **排序算法** (sorting) + array类型 → horizontal_array
  - 单元格大小: 0.8
  - 间距: 0.15
  
- **树算法** (tree, data_structure) + tree类型 → hierarchical
  - 节点间距: 2.0-3.0

### 2. 颜色方案设计
- **背景**: 必须使用深色 #1a1a1a
- **主色** (当前/活跃状态): 鲜艳暖色，如 #3498db (蓝), #e74c3c (红), #f39c12 (橙)
- **次色** (已访问/已完成): 柔和冷色，如 #2ecc71 (绿), #95a5a6 (灰)
- **强调色** (路径/关键元素): 对比色，如 #e74c3c (红)
- **文本色**: #FFFFFF 或 #ecf0f1
- **禁止使用**: #FFFFFF 作为元素填充色（对比度不足）

### 3. 元素样式定义
必须为以下常见状态定义样式（根据operations_used判断）：
- **数组**: idle, comparing, swapping, sorted, current
- **图节点**: idle_node, current_node, visited_node, finalized_node
- **图边**: normal_edge, active_edge, relaxed_edge, shortest_path_edge
- **表格单元格**: idle_cell, current_cell, computed_cell, result_cell

样式字段：
- fill: 填充色（十六进制）
- stroke: 边框色（十六进制）
- stroke_width: 1.5-3.0（重要元素用粗边框）
- text_color: 文本颜色
- opacity: 0.3-1.0（非当前元素降低透明度）
- scale: 1.0-1.3（当前元素可以放大）
- glow: true/false（关键元素加辉光）

### 4. 动画节奏
根据复杂度和帧数调整：
- **simple** (帧数<20): transition=0.5, pause=0.3
- **medium** (帧数20-50): transition=0.4, pause=0.2
- **complex** (帧数>50): transition=0.3, pause=0.15

具体操作时长：
- node_highlight: 0.3（节点状态变化）
- edge_update: 0.4（边状态变化）
- cell_update: 0.3（单元格更新）
- array_swap: 0.5（数组交换）

### 5. 视觉增强
根据算法类型启用相应特性：
- **图搜索** (Dijkstra, BFS, A*): show_distance_labels=true, highlight_shortest_path=true
- **DP**: show_dp_dependencies=true
- **排序**: emphasize_comparisons=true
- **图松弛**: animate_relaxation=true

### 6. 辅助视图布局
- 如果有辅助视图，position="left", max_width=0.3
- 伪代码: position="top-left", font_size=14

## 输出要求
1. 只输出一个有效的JSON配置，不要任何解释
2. 确保所有字段类型符合schema
3. 颜色必须是 #RRGGBB 格式
4. 数值必须在schema规定的范围内
5. 根据当前算法的operations_used定义相应的element_styles

开始生成配置:"""

    return prompt

def llm_generate_config(prompt: str) -> dict:
    """
    调用LLM生成配置
    
    参数:
        prompt: 构建好的prompt
    
    返回:
        解析后的配置dict
    """
    try:
        response = client.chat.completions.create(
            model=CURRENT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个算法可视化渲染配置专家。只输出JSON配置，不要解释。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        content = response.choices[0].message.content
        
        # 提取JSON
        config = extract_json_from_response(content)
        
        return config
        
    except Exception as e:
        print(f"LLM调用失败: {e}")
        raise

def extract_json_from_response(response: str) -> dict:
    """从LLM响应中提取JSON配置"""
    # 尝试查找JSON代码块
    json_pattern = r'```json\s*(.*?)\s*```'
    match = re.search(json_pattern, response, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 尝试直接解析整个响应
        json_str = response.strip()
    
    # 移除注释（JSON不支持注释，但LLM可能添加）
    json_str = re.sub(r'//.*?\n', '\n', json_str)
    
    try:
        config = json.loads(json_str)
        return config
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        print(f"原始响应:\n{response}")
        raise

def validate_config(config: dict, schema: dict) -> tuple[bool, str]:
    """
    校验配置是否符合schema
    
    返回:
        (is_valid, error_message)
    """
    try:
        jsonschema.validate(instance=config, schema=schema)
        return True, ""
    except jsonschema.ValidationError as e:
        return False, str(e)

def generate_render_config(trace_path: str, output_path: str = None) -> dict:
    """
    主函数：分析trace并生成渲染配置
    
    参数:
        trace_path: trace.json文件路径
        output_path: 配置输出路径（可选，默认为trace同目录下的_render_config.json）
    
    返回:
        生成的配置dict
    """
    # 1. 读取trace
    with open(trace_path, 'r', encoding='utf-8') as f:
        trace = json.load(f)
    
    # 2. 提取特征
    print(f"分析trace特征...")
    features = extract_trace_features(trace)
    print(f"  算法: {features['algorithm']['name']} ({features['algorithm']['family']})")
    print(f"  数据类型: {features['data_type']}")
    print(f"  规模: {features['data_scale']}")
    print(f"  帧数: {features['frame_count']}")
    print(f"  复杂度: {features['complexity']}")
    
    # 3. 加载schema
    schema = load_schema()
    
    # 4. 构建prompt
    prompt = build_config_prompt(features, schema)
    
    # 5. LLM生成配置
    print(f"LLM生成配置...")
    config = llm_generate_config(prompt)
    
    # 6. 校验配置
    print(f"校验配置...")
    is_valid, error_msg = validate_config(config, schema)
    if not is_valid:
        print(f"配置校验失败: {error_msg}")
        print(f"尝试修复...")
        # 简单修复：添加缺失的必填字段
        config = fix_config_basic(config, schema)
        is_valid, error_msg = validate_config(config, schema)
        if not is_valid:
            raise ValueError(f"配置校验失败: {error_msg}")
    
    print(f"✓ 配置生成成功")
    
    # 7. 保存配置
    if output_path is None:
        output_path = trace_path.replace('.json', '_render_config.json')
    
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"配置已保存: {output_path}")
    
    return config

def fix_config_basic(config: dict, schema: dict) -> dict:
    """基础配置修复：添加缺失的必填字段"""
    # 确保必填顶层字段存在
    if 'algorithm_info' not in config:
        config['algorithm_info'] = {
            'name': 'Unknown',
            'family': 'array',
            'data_type': 'array'
        }
    
    if 'layout_strategy' not in config:
        config['layout_strategy'] = {
            'main_view': {
                'type': 'horizontal_array'
            }
        }
    
    if 'style_overrides' not in config:
        config['style_overrides'] = {}
    
    # 确保main_view有type字段
    if 'main_view' not in config['layout_strategy']:
        config['layout_strategy']['main_view'] = {'type': 'horizontal_array'}
    elif 'type' not in config['layout_strategy']['main_view']:
        config['layout_strategy']['main_view']['type'] = 'horizontal_array'
    
    return config

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SVL Manim渲染配置生成器")
    parser.add_argument("trace_path", help="trace.json文件路径")
    parser.add_argument("--output", "-o", help="配置输出路径")
    
    args = parser.parse_args()
    
    try:
        config = generate_render_config(args.trace_path, args.output)
        print(f"\n生成的配置:")
        print(json.dumps(config, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
