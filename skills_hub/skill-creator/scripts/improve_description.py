import os
from typing import Optional

from utils import (
    read_file,
    write_file
)


def improve_skill_description(skill_path: str, output_path: Optional[str] = None) -> str:
    """Improve skill description"""
    # Read SKILL.md
    skill_md_path = os.path.join(skill_path, 'SKILL.md')
    if not os.path.exists(skill_md_path):
        print("SKILL.md not found")
        return ""
    
    skill_content = read_file(skill_md_path)
    
    # Improve description
    # This is a placeholder for actual improvement logic
    # In a real implementation, this would use AI to improve the description
    improved_content = skill_content
    
    # Determine output path
    if output_path is None:
        output_path = skill_md_path
    
    # Write improved content
    write_file(improved_content, output_path)
    
    print(f"Skill description improved: {output_path}")
    
    return output_path


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Improve skill description")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--output", help="Output file path")
    
    args = parser.parse_args()
    
    improve_skill_description(args.skill_path, args.output)


if __name__ == "__main__":
    main()