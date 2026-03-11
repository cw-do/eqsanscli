#!/usr/bin/env python3
"""
Update JSON parameter values across multiple configuration files.

Usage:
    python updatejsonparam.py <files...> <param_name> <value>

Examples:
    python updatejsonparam.py *.json outputDir './output/'
    python updatejsonparam.py conf_4m*.json cutTOFmin 500
    python updatejsonparam.py file1.json file2.json useLogSlice false
    python updatejsonparam.py *.json detector1 '[1.0, 1.0, 1]'

Features:
    - Works with shell-expanded globs (*.json) or quoted patterns
    - Case-insensitive parameter name matching (outputdir → outputDir)
    - Supports nested parameters (e.g., configuration.cutTOFmin)
    - Handles strings, numbers, booleans, null, arrays, and objects
    - Preserves original parameter name casing in JSON files
"""

import json
import sys
from pathlib import Path
from glob import glob


def find_param_key(obj, target_key_lower, current_path=""):
    """
    Recursively search for a parameter key in a nested dict.
    Returns (actual_key, parent_dict, path) if found, or (None, None, None).
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_path = f"{current_path}.{key}" if current_path else key
            if key.lower() == target_key_lower:
                return (key, obj, key_path)
            result = find_param_key(value, target_key_lower, key_path)
            if result[0] is not None:
                return result
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            result = find_param_key(item, target_key_lower, f"{current_path}[{i}]")
            if result[0] is not None:
                return result
    return (None, None, None)


def parse_value(value_str):
    """
    Parse a string value into the appropriate Python type.
    """
    value_str = value_str.strip()

    try:
        return json.loads(value_str)
    except json.JSONDecodeError:
        pass

    if value_str.lower() in ('true', 'yes', 'on'):
        return True
    if value_str.lower() in ('false', 'no', 'off'):
        return False
    if value_str.lower() in ('null', 'none'):
        return None

    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return value_str[1:-1]

    try:
        if '.' in value_str or 'e' in value_str.lower():
            return float(value_str)
        return int(value_str)
    except ValueError:
        pass

    return value_str


def expand_file_pattern(pattern):
    """
    Expand a file pattern to a list of matching JSON files.
    """
    script_dir = Path(__file__).parent

    if '*' in pattern:
        matches = glob(str(script_dir / pattern))
        matches = [m for m in matches if m.endswith('.json')]
    else:
        if not pattern.endswith('.json'):
            pattern = f"{pattern}.json"
        matches = glob(str(script_dir / pattern))

    if not matches:
        matches = glob(pattern)
        matches = [m for m in matches if m.endswith('.json')]

    return sorted(matches)


def update_json_param(file_path, param_name, new_value):
    """
    Update a parameter in a JSON file.
    Returns (success, message).
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return (False, f"Invalid JSON: {e}")
    except FileNotFoundError:
        return (False, "File not found")

    actual_key, parent_dict, key_path = find_param_key(data, param_name.lower())

    if actual_key is None or parent_dict is None:
        return (False, f"Parameter '{param_name}' not found")

    old_value = parent_dict[actual_key]
    parent_dict[actual_key] = new_value

    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
            f.write('\n')
    except Exception as e:
        return (False, f"Failed to write file: {e}")
    
    return (True, f"Updated {key_path}: {old_value!r} → {new_value!r}")


def parse_args(args):
    """
    Parse command line arguments.
    Handles both shell-expanded file lists and glob patterns.
    
    Returns (files, param_name, value) or raises SystemExit.
    """
    if len(args) < 3:
        return None, None, None
    
    files = []
    param_name = None
    value_parts = []
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if param_name is None:
            if arg.endswith('.json') and Path(arg).exists():
                files.append(arg)
            elif arg.endswith('.json'):
                expanded = expand_file_pattern(arg)
                if expanded:
                    files.extend(expanded)
                else:
                    print(f"Error: No files matching '{arg}'")
                    sys.exit(1)
            else:
                param_name = arg
        else:
            value_parts.append(arg)
        i += 1
    
    if not files:
        if len(args) >= 2:
            files = expand_file_pattern(args[0])
            if len(args) >= 3 and not files:
                print(f"Error: No files matching '{args[0]}'")
                sys.exit(1)
            param_name = args[1]
            value_parts = args[2:]
    
    value = parse_value(' '.join(value_parts)) if value_parts else None
    
    return files, param_name, value


def main():
    args = sys.argv[1:]
    
    files, param_name, new_value = parse_args(args)
    
    if not files or param_name is None or new_value is None:
        print(__doc__)
        print("\nError: Missing arguments")
        print(f"Usage: {sys.argv[0]} <files...> <param_name> <value>")
        print(f"Examples:")
        print(f"  {sys.argv[0]} *.json outputDir './output/'")
        print(f"  {sys.argv[0]} conf_4m*.json cutTOFmin 500")
        print(f"  {sys.argv[0]} * useLogSlice false")
        sys.exit(1)
    
    print(f"Updating parameter '{param_name}' to {new_value!r}")
    print(f"Matching files: {len(files)}")
    print("-" * 60)
    
    success_count = 0
    fail_count = 0
    
    for file_path in files:
        rel_path = Path(file_path).name
        success, message = update_json_param(file_path, param_name, new_value)
        
        if success:
            print(f"✓ {rel_path}: {message}")
            success_count += 1
        else:
            print(f"✗ {rel_path}: {message}")
            fail_count += 1
    
    print("-" * 60)
    print(f"Summary: {success_count} updated, {fail_count} failed")
    
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == '__main__':
    main()