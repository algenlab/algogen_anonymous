import json

"""
Plan JSON:
{
  "pseudocode": [
    "def numFactoredBinaryTrees(arr):",
    "    arr.sort()",
    "    n = len(arr)",
    "    dp = [1] * n",
    "    index = {x: i for i, x in enumerate(arr)}",
    "    MOD = 10**9 + 7",
    "    for i in range(n):",
    "        for j in range(i):",
    "            if arr[i] % arr[j] == 0:",
    "                right = arr[i] // arr[j]",
    "                if right in index:",
    "                    k = index[right]",
    "                    dp[i] = (dp[i] + dp[j] * dp[k]) % MOD",
    "    return sum(dp) % MOD"
  ]
}
"""

input_data = "[2,4]"

def main():
    arr = json.loads(input_data)
    arr.sort()
    n = len(arr)
    dp = [1] * n
    index = {x: i for i, x in enumerate(arr)}
    MOD = 10**9 + 7

    trace = {
        "svl_version": "5.0",
        "algorithm": {
            "name": "Binary Trees With Factors",
            "family": "Dynamic Programming"
        },
        "required_extensions": [
            "svl-ext-view-table"
        ],
        "initial_frame": {
            "data_schema": {},
            "data_state": {
                "type": "table",
                "data": [dp.copy()],
                "options": {
                    "row_headers": ["dp"],
                    "col_headers": [str(x) for x in arr]
                }
            },
            "auxiliary_views": [
                {
                    "view_id": "vars_panel",
                    "type": "table",
                    "title": "Variables",
                    "data": [
                        ["i", None],
                        ["j", None],
                        ["right", None],
                        ["k", None]
                    ],
                    "options": {
                        "row_headers": ["i", "j", "right", "k"],
                        "col_headers": ["name", "value"]
                    }
                }
            ],
            "variables_schema": [
                {"name": "i", "initial_value": None},
                {"name": "j", "initial_value": None},
                {"name": "right", "initial_value": None},
                {"name": "k", "initial_value": None}
            ],
            "pseudocode": [
                "def numFactoredBinaryTrees(arr):",
                "    arr.sort()",
                "    n = len(arr)",
                "    dp = [1] * n",
                "    index = {x: i for i, x in enumerate(arr)}",
                "    MOD = 10**9 + 7",
                "    for i in range(n):",
                "        for j in range(i):",
                "            if arr[i] % arr[j] == 0:",
                "                right = arr[i] // arr[j]",
                "                if right in index:",
                "                    k = index[right]",
                "                    dp[i] = (dp[i] + dp[j] * dp[k]) % MOD",
                "    return sum(dp) % MOD"
            ],
            "code_highlight": 1,
            "styles": {
                "elementStyles": {
                    "idle": {"backgroundColor": "#F0F0F0", "textColor": "#000000"},
                    "current_cell": {"backgroundColor": "#FFD700", "textColor": "#000000"},
                    "dependency_cell": {"backgroundColor": "#90EE90", "textColor": "#000000"}
                },
                "tempStyles": {
                    "dep_arrow": {"color": "#FF0000", "strokeWidth": 2.5}
                }
            }
        },
        "deltas": []
    }

    # Main algorithm loop
    for i in range(n):
        # Update variable i
        trace["deltas"].append({
            "code_highlight": 7,
            "operations": [[
                {"op": "updateTableCell", "params": {
                    "view_id": "vars_panel",
                    "updates": [{"row": 0, "col": 1, "value": str(i)}]
                }},
                {"op": "highlightTableCell", "params": {
                    "view_id": "data_state",
                    "cells": [{"row": 0, "col": i}],
                    "styleKey": "current_cell"
                }}
            ]]
        })
        for j in range(i):
            # Update variable j
            trace["deltas"].append({
                "code_highlight": 8,
                "operations": [[
                    {"op": "updateTableCell", "params": {
                        "view_id": "vars_panel",
                        "updates": [{"row": 1, "col": 1, "value": str(j)}]
                    }},
                    {"op": "highlightTableCell", "params": {
                        "view_id": "data_state",
                        "cells": [{"row": 0, "col": j}],
                        "styleKey": "current_cell"
                    }}
                ]]
            })
            if arr[i] % arr[j] == 0:
                right = arr[i] // arr[j]
                trace["deltas"].append({
                    "code_highlight": 9,
                    "operations": [[
                        {"op": "updateTableCell", "params": {
                            "view_id": "vars_panel",
                            "updates": [{"row": 2, "col": 1, "value": str(right)}]
                        }}
                    ]]
                })
                if right in index:
                    k = index[right]
                    # Update dp[i] first (Python variable), then render
                    new_val = (dp[i] + dp[j] * dp[k]) % MOD
                    dp[i] = new_val
                    trace["deltas"].append({
                        "code_highlight": 11,
                        "operations": [[
                            {"op": "updateTableCell", "params": {
                                "view_id": "vars_panel",
                                "updates": [{"row": 3, "col": 1, "value": str(k)}]
                            }},
                            {"op": "highlightTableCell", "params": {
                                "view_id": "data_state",
                                "cells": [{"row": 0, "col": k}],
                                "styleKey": "dependency_cell"
                            }},
                            {"op": "showDependency", "params": {
                                "view_id": "data_state",
                                "from_cells": [
                                    {"row": 0, "col": j},
                                    {"row": 0, "col": k}
                                ],
                                "to_cell": {"row": 0, "col": i},
                                "styleKey": "dep_arrow"
                            }},
                            {"op": "updateTableCell", "params": {
                                "view_id": "data_state",
                                "updates": [{"row": 0, "col": i, "value": str(new_val)}]
                            }}
                        ]]
                    })
            # Reset j cell style
            trace["deltas"].append({
                "code_highlight": 13,
                "operations": [[
                    {"op": "highlightTableCell", "params": {
                        "view_id": "data_state",
                        "cells": [{"row": 0, "col": j}],
                        "styleKey": "idle"
                    }}
                ]]
            })
        # Reset i cell style
        trace["deltas"].append({
            "code_highlight": 14,
            "operations": [[
                {"op": "highlightTableCell", "params": {
                    "view_id": "data_state",
                    "cells": [{"row": 0, "col": i}],
                    "styleKey": "idle"
                }}
            ]]
        })

    # Final answer
    answer = sum(dp) % MOD
    trace["deltas"].append({
        "code_highlight": 15,
        "operations": [[
            {"op": "showComment", "params": {
                "text": f"Total number of binary trees = {answer} (mod {MOD})",
                "anchor": "global"
            }}
        ]]
    })

    with open('trace.json', 'w', encoding='utf-8') as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)

    print("trace.json generated successfully")

if __name__ == "__main__":
    main()