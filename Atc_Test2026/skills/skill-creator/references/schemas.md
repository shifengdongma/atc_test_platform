# Skill Schemas

This document provides schemas for skill-related files and structures.

## SKILL.md Schema

The SKILL.md file should follow this structure:

```markdown
# Skill Name

A brief description of what the skill does.

## What it does

A detailed description of the skill's functionality.

## How to use it

Instructions on how to use the skill.

## Example use cases

Examples of how the skill can be used.

## Files included

A list of files included in the skill.

## Requirements

Any requirements for the skill.

## License

The license under which the skill is distributed.
```

## Skill Directory Structure

A skill should have the following directory structure:

```
skill-name/
├── SKILL.md
├── LICENSE.txt
├── scripts/           # Python scripts
├── examples/          # Example inputs/outputs
├── resources/         # Additional resources
└── templates/         # Templates
```

## Script Requirements

- Python 3.7+
- No external dependencies (preferred)
- Clear documentation
- Proper error handling

## File Size Limits

- Individual files: 10MB maximum
- Total skill size: 50MB maximum

## Naming Conventions

- Skill name: lowercase with hyphens (e.g., weather-forecast)
- File names: lowercase with underscores (e.g., get_weather.py)
- Directory names: lowercase with hyphens (e.g., data-sources)

## Best Practices

- Keep skills focused on a single task
- Provide clear documentation
- Test thoroughly
- Handle errors gracefully
- Follow Python best practices
- Use consistent naming conventions
- Minimize dependencies
- Optimize performance

## Submission Guidelines

1. Ensure all required files are present
2. Validate skill structure and content
3. Test the skill with various inputs
4. Package the skill as a zip file
5. Submit the zip file through the appropriate channel