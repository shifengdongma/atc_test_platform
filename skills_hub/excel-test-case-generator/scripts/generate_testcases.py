#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Case Generator CLI - Command-line tool for generating test case Excel files

Usage:
    # From JSON file
    python generate_testcases.py --input testcases.json --output test_cases.xlsx
    
    # Single test case from command line
    python generate_testcases.py --name "登录测试" --preconditions "..." --steps "..." --expected "..." --priority P0 --output test.xlsx
    
    # Multiple test cases from JSON
    python generate_testcases.py --input testcases.json --output test_cases.xlsx --sheet-name "功能测试"
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional

# Import the generator
from test_case_generator import TestCaseGenerator


def load_testcases_from_json(json_path: str) -> List[Dict[str, str]]:
    """
    Load test cases from a JSON file.
    
    Expected JSON format:
    [
        {
            "name": "测试用例名称",
            "preconditions": "前置条件",
            "steps": "测试步骤",
            "expected_result": "预期结果",
            "priority": "P0",
            "test_type": "功能测试",
            "execution_result": ""
        },
        ...
    ]
    """
    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of test cases")
    
    return data


def validate_test_case(test_case: Dict[str, str]) -> bool:
    """Validate that a test case has required fields."""
    required_fields = ['name', 'preconditions', 'steps', 'expected_result']
    for field in required_fields:
        if field not in test_case or not test_case[field]:
            return False
    return True


def generate_from_json(input_path: str, output_path: str, sheet_name: str = "测试用例"):
    """Generate Excel file from JSON input."""
    try:
        test_cases = load_testcases_from_json(input_path)
        
        # Validate test cases
        invalid_cases = []
        for i, tc in enumerate(test_cases, 1):
            if not validate_test_case(tc):
                invalid_cases.append(i)
        
        if invalid_cases:
            print(f"Warning: {len(invalid_cases)} test case(s) missing required fields: {invalid_cases}")
            print("Required fields: name, preconditions, steps, expected_result")
        
        # Generate Excel
        generator = TestCaseGenerator()
        generator._setup_worksheet(sheet_name)
        generator.add_test_cases(test_cases)
        generator.wb.save(output_path)
        
        print(f"Successfully generated {len(test_cases)} test cases to: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error generating from JSON: {e}", file=sys.stderr)
        sys.exit(1)


def generate_single_test_case(name: str, preconditions: str, steps: str, 
                              expected_result: str, output_path: str,
                              priority: str = "P1", test_type: str = "功能测试"):
    """Generate Excel file with a single test case from command line arguments."""
    try:
        generator = TestCaseGenerator()
        generator.add_test_case(
            name=name,
            preconditions=preconditions,
            steps=steps,
            expected_result=expected_result,
            priority=priority,
            test_type=test_type
        )
        generator.wb.save(output_path)
        
        print(f"Successfully generated test case to: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error generating test case: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Generate test case Excel files from JSON or command line arguments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From JSON file
  python generate_testcases.py --input testcases.json --output test_cases.xlsx
  
  # Single test case
  python generate_testcases.py --name "登录测试" --preconditions "系统已启动" \\
      --steps "1. 打开登录页面\\n2. 输入用户名密码" --expected "登录成功" \\
      --priority P0 --output test.xlsx
        """
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--input', '-i',
        type=str,
        help='Path to JSON file containing test cases'
    )
    input_group.add_argument(
        '--name', '-n',
        type=str,
        help='Test case name (for single test case mode)'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        type=str,
        required=True,
        help='Output Excel file path'
    )
    
    parser.add_argument(
        '--sheet-name', '-s',
        type=str,
        default='测试用例',
        help='Excel sheet name (default: 测试用例)'
    )
    
    # Single test case options (only used when --name is provided)
    parser.add_argument(
        '--preconditions', '-p',
        type=str,
        help='Preconditions for test execution'
    )
    
    parser.add_argument(
        '--steps', '-t',
        type=str,
        help='Test steps (use \\n for newlines)'
    )
    
    parser.add_argument(
        '--expected', '-e',
        type=str,
        dest='expected_result',
        help='Expected result'
    )
    
    parser.add_argument(
        '--priority',
        type=str,
        default='P1',
        choices=['P0', 'P1', 'P2'],
        help='Test case priority (default: P1)'
    )
    
    parser.add_argument(
        '--test-type',
        type=str,
        default='功能测试',
        help='Test type (default: 功能测试)'
    )
    
    args = parser.parse_args()
    
    # Determine mode and generate
    if args.input:
        # JSON file mode
        generate_from_json(args.input, args.output, args.sheet_name)
    else:
        # Single test case mode
        if not all([args.name, args.preconditions, args.steps, args.expected_result]):
            parser.error("When using --name, you must also provide --preconditions, --steps, and --expected")
        
        # Replace \n with actual newlines in steps
        steps = args.steps.replace('\\n', '\n')
        
        generate_single_test_case(
            name=args.name,
            preconditions=args.preconditions,
            steps=steps,
            expected_result=args.expected_result,
            output_path=args.output,
            priority=args.priority,
            test_type=args.test_type
        )


if __name__ == "__main__":
    main()
