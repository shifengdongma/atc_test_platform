import os
import zipfile
import tempfile
from typing import Optional

from utils import (
    validate_skill_structure,
    get_skill_name,
    get_directory_size,
    format_size
)


def package_skill(skill_path: str, output_path: Optional[str] = None) -> str:
    """Package skill into zip file"""
    # Validate skill structure
    if not validate_skill_structure(skill_path):
        print("Skill validation failed")
        return ""
    
    # Get skill name
    skill_name = get_skill_name(skill_path)
    
    # Determine output path
    if output_path is None:
        output_path = os.path.join(os.path.dirname(skill_path), f"{skill_name}.zip")
    
    # Create zip file
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Walk through directory
        for root, dirs, files in os.walk(skill_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                # Skip hidden files
                if file.startswith('.'):
                    continue
                
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, skill_path)
                
                # Add file to zip
                zipf.write(file_path, arcname)
    
    # Get package size
    package_size = get_directory_size(skill_path)
    
    print(f"Skill packaged successfully: {output_path}")
    print(f"Package size: {format_size(package_size)}")
    
    return output_path


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Package skill into zip file")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--output", help="Output zip file path")
    
    args = parser.parse_args()
    
    package_skill(args.skill_path, args.output)


if __name__ == "__main__":
    main()