import os
import json
from typing import Dict, Any, List

from utils import (
    read_file,
    write_file,
    get_skill_name
)


def generate_skill_report(skill_path: str, output_path: str) -> None:
    """Generate skill report"""
    skill_name = get_skill_name(skill_path)
    
    # Read SKILL.md
    skill_md_path = os.path.join(skill_path, 'SKILL.md')
    skill_content = read_file(skill_md_path) if os.path.exists(skill_md_path) else ''
    
    # Read LICENSE.txt
    license_path = os.path.join(skill_path, 'LICENSE.txt')
    license_content = read_file(license_path) if os.path.exists(license_path) else ''
    
    # Count files
    file_count = 0
    directory_count = 0
    
    for root, dirs, files in os.walk(skill_path):
        directory_count += 1
        file_count += len(files)
    
    # Collect Python files
    python_files = []
    for root, dirs, files in os.walk(skill_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, skill_path)
                python_files.append(relative_path)
    
    # Generate report
    report = {
        'skill_name': skill_name,
        'skill_path': skill_path,
        'file_count': file_count,
        'directory_count': directory_count,
        'python_files': python_files,
        'skill_content': skill_content,
        'license_content': license_content
    }
    
    # Write report
    write_file(json.dumps(report, indent=2, ensure_ascii=False), output_path)
    
    print(f"Skill report generated: {output_path}")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate skill report")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("output_path", help="Output report file path")
    
    args = parser.parse_args()
    
    generate_skill_report(args.skill_path, args.output_path)


if __name__ == "__main__":
    main()