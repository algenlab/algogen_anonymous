import json

"""
Plan JSON:
{
  "pseudocode": [
    "def count_primes(n):",
    "    if n <= 2: return 0",
    "    is_prime = [True] * n",
    "    is_prime[0] = is_prime[1] = False",
    "    for i in range(2, int(n**0.5)+1):",
    "        if is_prime[i]:",
    "            for j in range(i*i, n, i):",
    "                is_prime[j] = False",
    "    return sum(is_prime)"
  ]
}
"""

input_data = "10"

def main():
    n = int(input_data)
    
    # Build initial data state (array of booleans)
    is_prime = [True] * n
    structure = []
    for i in range(n):
        structure.append({
            "index": i,
            "value": "T" if is_prime[i] else "F",
            "state": "idle"
        })
    
    trace = {
        "svl_version": "5.0",
        "algorithm": {
            "name": "Sieve of Eratosthenes",
            "family": "array"
        },
        "required_extensions": [
            "svl-ext-primitive-array",
            "svl-ext-view-table"
        ],
        "initial_frame": {
            "data_schema": {},
            "data_state": {
                "type": "array",
                "structure": structure
            },
            "auxiliary_views": [
                {
                    "view_id": "vars_panel",
                    "type": "table",
                    "title": "Variables",
                    "data": [
                        ["i", "None"],
                        ["j", "None"],
                        ["count", "None"]
                    ],
                    "options": {
                        "row_headers": ["i", "j", "count"],
                        "col_headers": ["name", "value"]
                    }
                }
            ],
            "variables_schema": [
                {"name": "i", "initial_value": None},
                {"name": "j", "initial_value": None},
                {"name": "count", "initial_value": None}
            ],
            "pseudocode": [
                "def count_primes(n):",
                "    if n <= 2: return 0",
                "    is_prime = [True] * n",
                "    is_prime[0] = is_prime[1] = False",
                "    for i in range(2, int(n**0.5)+1):",
                "        if is_prime[i]:",
                "            for j in range(i*i, n, i):",
                "                is_prime[j] = False",
                "    return sum(is_prime)"
            ],
            "code_highlight": 1,
            "styles": {
                "elementStyles": {
                    "idle": {"backgroundColor": "#F0F0F0", "textColor": "#000000"},
                    "current": {"backgroundColor": "#4CAF50", "textColor": "#FFFFFF"},
                    "marking": {"backgroundColor": "#FFD700", "textColor": "#000000"},
                    "prime": {"backgroundColor": "#90EE90", "textColor": "#000000"},
                    "non_prime": {"backgroundColor": "#FF9999", "textColor": "#000000"}
                }
            }
        },
        "deltas": []
    }
    
    # Handle n <= 2 case
    if n <= 2:
        trace["deltas"].append({
            "code_highlight": 2,
            "operations": [[
                {"op": "updateTableCell", "params": {
                    "view_id": "vars_panel",
                    "updates": [{"row": 2, "col": 1, "value": "0"}]
                }},
                {"op": "showComment", "params": {
                    "text": f"n={n} <= 2, return 0",
                    "anchor": "global"
                }}
            ]]
        })
        
        with open('trace.json', 'w', encoding='utf-8') as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
        print("trace.json generated successfully")
        return
    
    # Mark 0 and 1 as non-prime
    is_prime[0] = False
    is_prime[1] = False
    
    # Update array visualization for 0 and 1
    trace["deltas"].append({
        "code_highlight": 3,
        "operations": [[
            {"op": "updateValues", "params": {
                "updates": [
                    {"index": 0, "value": "F"},
                    {"index": 1, "value": "F"}
                ]
            }},
            {"op": "updateStyle", "params": {"indices": [0, 1], "styleKey": "non_prime"}}
        ]]
    })
    
    # Initialize prime count
    prime_count = 0
    
    # Main sieve loop
    limit = int(n ** 0.5)
    
    for i in range(2, limit + 1):
        # Highlight current i (line 5 in pseudocode)
        trace["deltas"].append({
            "code_highlight": 5,
            "operations": [[
                {"op": "updateStyle", "params": {"indices": [i], "styleKey": "current"}},
                {"op": "updateTableCell", "params": {
                    "view_id": "vars_panel",
                    "updates": [{"row": 0, "col": 1, "value": str(i)}]
                }}
            ]]
        })
        
        if is_prime[i]:
            # i is prime - mark it and count it (line 6 in pseudocode)
            prime_count += 1
            trace["deltas"].append({
                "code_highlight": 6,
                "operations": [[
                    {"op": "updateStyle", "params": {"indices": [i], "styleKey": "prime"}},
                    {"op": "updateTableCell", "params": {
                        "view_id": "vars_panel",
                        "updates": [{"row": 2, "col": 1, "value": str(prime_count)}]
                    }}
                ]]
            })
            
            # Mark multiples of i as non-prime (line 7 in pseudocode)
            for j in range(i*i, n, i):
                if is_prime[j]:
                    is_prime[j] = False
                    trace["deltas"].append({
                        "code_highlight": 7,
                        "operations": [[
                            {"op": "updateTableCell", "params": {
                                "view_id": "vars_panel",
                                "updates": [{"row": 1, "col": 1, "value": str(j)}]
                            }},
                            {"op": "updateValues", "params": {
                                "updates": [{"index": j, "value": "F"}]
                            }},
                            {"op": "updateStyle", "params": {"indices": [j], "styleKey": "marking"}}
                        ]]
                    })
        
        # Reset i style after processing (line 4 in pseudocode - end of outer loop)
        final_style = "prime" if is_prime[i] else "non_prime"
        trace["deltas"].append({
            "code_highlight": 4,
            "operations": [[
                {"op": "updateStyle", "params": {"indices": [i], "styleKey": final_style}}
            ]]
        })
    
    # Count remaining primes beyond sqrt(n)
    for idx in range(max(2, limit + 1), n):
        if is_prime[idx]:
            prime_count += 1
    
    # Final result (line 9 in pseudocode)
    trace["deltas"].append({
        "code_highlight": 9,
        "operations": [[
            {"op": "updateTableCell", "params": {
                "view_id": "vars_panel",
                "updates": [{"row": 2, "col": 1, "value": str(prime_count)}]
            }},
            {"op": "showComment", "params": {
                "text": f"Found {prime_count} prime numbers less than {n}",
                "anchor": "global"
            }}
        ]]
    })
    
    # Write trace.json
    with open('trace.json', 'w', encoding='utf-8') as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
    
    print("trace.json generated successfully")

if __name__ == "__main__":
    main()