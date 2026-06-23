# Analyzer Agent

The analyzer agent is responsible for analyzing skill performance and identifying areas for improvement.

## What it does

- Analyzes skill execution logs
- Identifies performance bottlenecks
- Detects errors and exceptions
- Provides recommendations for improvement

## How it works

1. **Collects data**: Gathers execution logs and performance metrics
2. **Analyzes data**: Examines the collected data for patterns and issues
3. **Identifies problems**: Detects specific issues affecting skill performance
4. **Provides recommendations**: Suggests improvements to address identified issues

## Example analysis

```
Analysis of Skill: weather-forecast

Issues found:
1. API call latency (average: 1.2s)
2. Error rate: 5% (mostly API timeouts)
3. Incomplete error handling

Recommendations:
1. Implement API caching
2. Add retry logic for API timeouts
3. Improve error handling and user feedback
```