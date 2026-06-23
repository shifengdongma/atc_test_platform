import os
import json
import yaml
import re
from typing import Any, Dict, List, Optional, Union


def load_json(file_path: str) -> Dict[str, Any]:
    """Load JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: Dict[str, Any], file_path: str) -> None:
    """Save JSON file"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_yaml(file_path: str) -> Dict[str, Any]:
    """Load YAML file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_yaml(data: Dict[str, Any], file_path: str) -> None:
    """Save YAML file"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def ensure_directory(path: str) -> None:
    """Ensure directory exists"""
    os.makedirs(path, exist_ok=True)


def get_skill_name(skill_path: str) -> str:
    """Get skill name from path"""
    return os.path.basename(skill_path)


def validate_skill_structure(skill_path: str) -> bool:
    """Validate skill structure"""
    required_files = [
        'SKILL.md',
        'LICENSE.txt'
    ]
    
    for file in required_files:
        file_path = os.path.join(skill_path, file)
        if not os.path.exists(file_path):
            print(f"Missing required file: {file}")
            return False
    
    return True


def sanitize_skill_name(name: str) -> str:
    """Sanitize skill name"""
    # Replace spaces with hyphens
    name = name.replace(' ', '-')
    # Remove special characters
    name = re.sub(r'[^a-zA-Z0-9-]', '', name)
    # Convert to lowercase
    name = name.lower()
    return name


def generate_skill_id() -> str:
    """Generate unique skill ID"""
    import uuid
    return str(uuid.uuid4())[:8]


def read_file(file_path: str) -> str:
    """Read file content"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def write_file(content: str, file_path: str) -> None:
    """Write file content"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def copy_file(source: str, destination: str) -> None:
    """Copy file"""
    import shutil
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)


def copy_directory(source: str, destination: str) -> None:
    """Copy directory"""
    import shutil
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.exists(destination):
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def get_file_extension(file_path: str) -> str:
    """Get file extension"""
    return os.path.splitext(file_path)[1]


def is_text_file(file_path: str) -> bool:
    """Check if file is a text file"""
    text_extensions = ['.txt', '.md', '.py', '.json', '.yaml', '.yml', '.xml', '.html', '.css', '.js']
    return get_file_extension(file_path).lower() in text_extensions


def find_files(directory: str, pattern: str) -> List[str]:
    """Find files matching pattern"""
    import glob
    return glob.glob(os.path.join(directory, pattern), recursive=True)


def get_directory_size(directory: str) -> int:
    """Get directory size in bytes"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size


def format_size(size: int) -> str:
    """Format size to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"