import json

"""
Plan JSON:
{
  "pseudocode": [
    "def sum_of_distances_in_tree(n, edges):",
    "    # Build adjacency list",
    "    adj = [[] for _ in range(n)]",
    "    for u, v in edges:",
    "        adj[u].append(v)",
    "        adj[v].append(u)",
    "    subtree_size = [0] * n",
    "    answer = [0] * n",
    "    # DFS1: compute subtree sizes and answer[0] (sum of distances from root)",
    "    def dfs1(node, parent):",
    "        subtree_size[node] = 1",
    "        for neighbor in adj[node]:",
    "            if neighbor == parent:",
    "                continue",
    "            dfs1(neighbor, node)",
    "            subtree_size[node] += subtree_size[neighbor]",
    "            answer[0] += subtree_size[neighbor]  # add for each edge",
    "    dfs1(0, -1)",
    "    # DFS2: rerooting to compute all answers",
    "    def dfs2(node, parent):",
    "        for neighbor in adj[node]:",
    "            if neighbor == parent:",
    "                continue",
    "            answer[neighbor] = answer[node] - subtree_size[neighbor] + (n - subtree_size[neighbor])",
    "            dfs2(neighbor, node)",
    "    dfs2(0, -1)",
    "    return answer"
}
"""

input_data = {
    "n": 6,
    "edges": [[0,1],[0,2],[2,3],[2,4],[2,5]]
}

def main():
    n = input_data["n"]
    edges = input_data["edges"]
    
    # Build adjacency list
    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    for i in range(n):
        adj[i].sort()
    
    subtree_size = [0] * n
    answer = [0] * n
    
    # Create initial state
    nodes = []
    for i in range(n):
        nodes.append({
            "id": str(i),
            "label": str(i),
            "styleKey": "idle_node",
            "properties": {"subtree_size": 0, "answer": 0}
        })
    
    edges_list = []
    for u, v in edges:
        edges_list.append({
            "from": str(u),
            "to": str(v),
            "directed": False,
            "label": "",
            "styleKey": "normal_edge"
        })
    
    trace = {
        "svl_version": "5.0",
        "algorithm": {
            "name": "Sum of Distances in Tree",
            "family": "graph"
        },
        "required_extensions": [
            "svl-ext-primitive-graph",
            "svl-ext-view-table"
        ],
        "initial_frame": {
            "data_schema": {},
            "data_state": {
                "type": "graph",
                "structure": {
                    "nodes": nodes,
                    "edges": edges_list
                }
            },
            "auxiliary_views": [
                {
                    "view_id": "subtree_table",
                    "type": "table",
                    "title": "Subtree Sizes & Answers",
                    "data": [
                        ["Node", "Subtree Size", "Answer"],
                        ["0", "0", "0"],
                        ["1", "0", "0"],
                        ["2", "0", "0"],
                        ["3", "0", "0"],
                        ["4", "0", "0"],
                        ["5", "0", "0"]
                    ],
                    "options": {
                        "row_headers": ["0","1","2","3","4","5"],
                        "col_headers": ["Node", "Subtree Size", "Answer"]
                    }
                },
                {
                    "view_id": "vars_panel",
                    "type": "table",
                    "title": "Variables",
                    "data": [
                        ["current_node", "None"],
                        ["neighbor", "None"],
                        ["new_answer", "None"]
                    ],
                    "options": {
                        "row_headers": ["current_node", "neighbor", "new_answer"],
                        "col_headers": ["Variable", "Value"]
                    }
                }
            ],
            "variables_schema": [
                {"name": "current_node", "initial_value": None},
                {"name": "neighbor", "initial_value": None},
                {"name": "new_answer", "initial_value": None}
            ],
            "pseudocode": [
                "def sum_of_distances_in_tree(n, edges):",
                "    # Build adjacency list",
                "    adj = [[] for _ in range(n)]",
                "    for u, v in edges:",
                "        adj[u].append(v)",
                "        adj[v].append(u)",
                "    subtree_size = [0] * n",
                "    answer = [0] * n",
                "    # DFS1: compute subtree sizes and answer[0] (sum of distances from root)",
                "    def dfs1(node, parent):",
                "        subtree_size[node] = 1",
                "        for neighbor in adj[node]:",
                "            if neighbor == parent:",
                "                continue",
                "            dfs1(neighbor, node)",
                "            subtree_size[node] += subtree_size[neighbor]",
                "            answer[0] += subtree_size[neighbor]  # add for each edge",
                "    dfs1(0, -1)",
                "    # DFS2: rerooting to compute all answers",
                "    def dfs2(node, parent):",
                "        for neighbor in adj[node]:",
                "            if neighbor == parent:",
                "                continue",
                "            answer[neighbor] = answer[node] - subtree_size[neighbor] + (n - subtree_size[neighbor])",
                "            dfs2(neighbor, node)",
                "    dfs2(0, -1)",
                "    return answer"
            ],
            "code_highlight": 1,
            "styles": {
                "elementStyles": {
                    "idle_node": {"backgroundColor": "#F0F0F0", "textColor": "#000000"},
                    "current_node": {"backgroundColor": "#4CAF50", "textColor": "#FFFFFF"},
                    "visited_node": {"backgroundColor": "#CCCCCC", "textColor": "#000000"},
                    "processing_node": {"backgroundColor": "#FF9800", "textColor": "#000000"}
                },
                "edgeStyles": {
                    "normal_edge": {"stroke": "#666666"},
                    "active_edge": {"stroke": "#FF5722", "strokeWidth": 3}
                }
            }
        },
        "deltas": []
    }
    
    # Helper to add a delta
    def add_delta(code_line, operations):
        # Ensure operations is a 2D array
        if operations and isinstance(operations[0], dict):
            operations = [operations]
        trace["deltas"].append({
            "code_highlight": code_line,
            "operations": operations
        })
    
    # DFS1: recursive simulation
    def dfs1(node, parent):
        # Enter node
        operations = []
        operations.append({
            "op": "updateNodeStyle",
            "params": {"ids": [str(node)], "styleKey": "current_node"}
        })
        operations.append({
            "op": "updateTableCell",
            "params": {
                "view_id": "vars_panel",
                "updates": [{"row": 0, "col": 1, "value": str(node)}]
            }
        })
        add_delta(10, operations)
        
        # Initialize subtree_size to 1
        subtree_size[node] = 1
        operations = []
        operations.append({
            "op": "updateNodeProperties",
            "params": {
                "updates": [{"id": str(node), "properties": {"subtree_size": 1}}]
            }
        })
        operations.append({
            "op": "updateTableCell",
            "params": {
                "view_id": "subtree_table",
                "updates": [{"row": node, "col": 1, "value": "1"}]
            }
        })
        add_delta(11, operations)
        
        # Process children
        for neighbor in adj[node]:
            if neighbor == parent:
                continue
            
            # Highlight edge
            operations = []
            operations.append({
                "op": "updateEdgeStyle",
                "params": {
                    "edges": [{"from": str(node), "to": str(neighbor)}],
                    "styleKey": "active_edge"
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "vars_panel",
                    "updates": [{"row": 1, "col": 1, "value": str(neighbor)}]
                }
            })
            add_delta(12, operations)
            
            # Recursive call
            dfs1(neighbor, node)
            
            # After returning from child: update parent's subtree_size
            subtree_size[node] += subtree_size[neighbor]
            operations = []
            operations.append({
                "op": "updateNodeProperties",
                "params": {
                    "updates": [{"id": str(node), "properties": {"subtree_size": subtree_size[node]}}]
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "subtree_table",
                    "updates": [{"row": node, "col": 1, "value": str(subtree_size[node])}]
                }
            })
            add_delta(14, operations)
            
            # Update answer[0] using this edge
            answer[0] += subtree_size[neighbor]
            operations = []
            operations.append({
                "op": "showComment",
                "params": {
                    "text": f"answer[0] += subtree_size[{neighbor}] = {subtree_size[neighbor]} (total = {answer[0]})",
                    "anchor": "global"
                }
            })
            operations.append({
                "op": "updateNodeProperties",
                "params": {
                    "updates": [{"id": "0", "properties": {"answer": answer[0]}}]
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "subtree_table",
                    "updates": [{"row": 0, "col": 2, "value": str(answer[0])}]
                }
            })
            add_delta(15, operations)
            
            # Deactivate edge
            operations = []
            operations.append({
                "op": "updateEdgeStyle",
                "params": {
                    "edges": [{"from": str(node), "to": str(neighbor)}],
                    "styleKey": "normal_edge"
                }
            })
            add_delta(16, operations)
        
        # Mark node as visited
        operations = []
        operations.append({
            "op": "updateNodeStyle",
            "params": {"ids": [str(node)], "styleKey": "visited_node"}
        })
        operations.append({
            "op": "updateTableCell",
            "params": {
                "view_id": "vars_panel",
                "updates": [
                    {"row": 0, "col": 1, "value": "None"},
                    {"row": 1, "col": 1, "value": "None"}
                ]
            }
        })
        add_delta(17, operations)
    
    # Start DFS1 from root 0
    dfs1(0, -1)
    
    # DFS2: rerooting
    def dfs2(node, parent):
        operations = []
        operations.append({
            "op": "updateNodeStyle",
            "params": {"ids": [str(node)], "styleKey": "current_node"}
        })
        operations.append({
            "op": "updateTableCell",
            "params": {
                "view_id": "vars_panel",
                "updates": [{"row": 0, "col": 1, "value": str(node)}]
            }
        })
        add_delta(21, operations)
        
        for neighbor in adj[node]:
            if neighbor == parent:
                continue
            
            # Highlight edge
            operations = []
            operations.append({
                "op": "updateEdgeStyle",
                "params": {
                    "edges": [{"from": str(node), "to": str(neighbor)}],
                    "styleKey": "active_edge"
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "vars_panel",
                    "updates": [
                        {"row": 1, "col": 1, "value": str(neighbor)}
                    ]
                }
            })
            add_delta(22, operations)
            
            # Apply rerooting formula
            new_answer = answer[node] - subtree_size[neighbor] + (n - subtree_size[neighbor])
            answer[neighbor] = new_answer
            
            operations = []
            operations.append({
                "op": "showComment",
                "params": {
                    "text": f"answer[{neighbor}] = answer[{node}] - subtree_size[{neighbor}] + (n - subtree_size[{neighbor}]) = {answer[node]} - {subtree_size[neighbor]} + {n - subtree_size[neighbor]} = {new_answer}",
                    "anchor": "global"
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "vars_panel",
                    "updates": [{"row": 2, "col": 1, "value": str(new_answer)}]
                }
            })
            operations.append({
                "op": "updateNodeProperties",
                "params": {
                    "updates": [{"id": str(neighbor), "properties": {"answer": new_answer}}]
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "subtree_table",
                    "updates": [{"row": neighbor, "col": 2, "value": str(new_answer)}]
                }
            })
            add_delta(23, operations)
            
            # Deactivate edge
            operations = []
            operations.append({
                "op": "updateEdgeStyle",
                "params": {
                    "edges": [{"from": str(node), "to": str(neighbor)}],
                    "styleKey": "normal_edge"
                }
            })
            operations.append({
                "op": "updateTableCell",
                "params": {
                    "view_id": "vars_panel",
                    "updates": [
                        {"row": 1, "col": 1, "value": "None"},
                        {"row": 2, "col": 1, "value": "None"}
                    ]
                }
            })
            add_delta(24, operations)
            
            dfs2(neighbor, node)
        
        operations = []
        operations.append({
            "op": "updateNodeStyle",
            "params": {"ids": [str(node)], "styleKey": "visited_node"}
        })
        operations.append({
            "op": "updateTableCell",
            "params": {
                "view_id": "vars_panel",
                "updates": [
                    {"row": 0, "col": 1, "value": "None"}
                ]
            }
        })
        add_delta(25, operations)
    
    # Start DFS2 from root 0
    dfs2(0, -1)
    
    # Final frame: show result and reset styles
    operations = []
    operations.append({
        "op": "showComment",
        "params": {
            "text": f"Algorithm completed. Final answer array: {answer}",
            "anchor": "global"
        }
    })
    for i in range(n):
        operations.append({
            "op": "updateNodeStyle",
            "params": {"ids": [str(i)], "styleKey": "idle_node"}
        })
    add_delta(27, operations)
    
    with open('trace.json', 'w', encoding='utf-8') as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
    
    print("trace.json generated successfully")

if __name__ == "__main__":
    main()