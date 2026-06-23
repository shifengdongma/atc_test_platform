import os
import re
from typing import List, Dict, Any

from utils import (
    validate_skill_structure,
    read_file,
    find_files
)


def validate_skill_content(skill_path: str) -> Dict[str, Any]:
    """Validate skill content"""
    results = {
        'valid': True,
        'errors': [],
        'warnings': []
    }
    
    # Validate SKILL.md
    skill_md_path = os.path.join(skill_path, 'SKILL.md')
    if os.path.exists(skill_md_path):
        skill_content = read_file(skill_md_path)
        
        # Check for required sections
        required_sections = [
            'What it does',
            'How to use it',
            'Example use cases'
        ]
        
        for section in required_sections:
            if f'## {section}' not in skill_content:
                results['errors'].append(f"Missing required section: {section}")
                results['valid'] = False
        
        # Check for skill name
        if 'Skill Creator' not in skill_content:
            results['warnings'].append('Skill name not found in SKILL.md')
    
    # Validate LICENSE.txt
    license_path = os.path.join(skill_path, 'LICENSE.txt')
    if os.path.exists(license_path):
        license_content = read_file(license_path)
        if 'MIT License' not in license_content:
            results['warnings'].append('MIT License not found in LICENSE.txt')
    
    # Check for Python files
    python_files = find_files(skill_path, '**/*.py')
    for python_file in python_files:
        try:
            with open(python_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # Check for syntax errors
            compile(content, python_file, 'exec')
        except SyntaxError as e:
            results['errors'].append(f"Syntax error in {python_file}: {e}")
            results['valid'] = False
        except Exception as e:
            results['errors'].append(f"Error reading {python_file}: {e}")
            results['valid'] = False
    
    # Check for file size limits
    max_file_size = 10 * 1024 * 1024  # 10MB
    for root, dirs, files in os.walk(skill_path):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.getsize(file_path) > max_file_size:
                results['errors'].append(f"File too large: {file_path}")
                results['valid'] = False
    
    return results


def quick_validate(skill_path: str) -> bool:
    """Quick validate skill"""
    print(f"Validating skill: {skill_path}")
    
    # Validate structure
    if not validate_skill_structure(skill_path):
        return False
    
    # Validate content
    content_results = validate_skill_content(skill_path)
    
    # Print results
    if content_results['errors']:
        print("\nErrors:")
        for error in content_results['errors']:
            print(f"- {error}")
    
    if content_results['warnings']:
        print("\nWarnings:")
        for warning in content_results['warnings']:
            print(f"- {warning}")
    
    if content_results['valid']:
        print("\nSkill validation passed!")
    else:
        print("\nSkill validation failed!")
    
    return content_results['valid']


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Quick validate skill")
    parser.add_argument("skill_path", help="Path to skill directory")
    
    args = parser.parse_args()
    
    quick_validate(args.skill_path)


if __name__ == "__main__":
    main()