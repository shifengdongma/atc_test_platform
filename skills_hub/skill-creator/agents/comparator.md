# Comparator Agent

The comparator agent is responsible for comparing different versions of a skill to identify improvements and regressions.

## What it does

- Compares skill versions
- Identifies changes and improvements
- Detects regressions and issues
- Provides a detailed comparison report

## How it works

1. **Collects versions**: Gathers different versions of the skill
2. **Compares code**: Analyzes changes between versions
3. **Tests functionality**: Tests each version to measure performance
4. **Generates report**: Creates a detailed comparison report

## Example comparison

```
Comparison of Skill: weather-forecast (v1.0 vs v1.1)

Changes:
1. Added API caching
2. Improved error handling
3. Updated UI components

Performance:
- API response time: 1.2s → 0.3s (75% improvement)
- Error rate: 5% → 1% (80% improvement)
- User satisfaction: 4.2/5 → 4.8/5 (14% improvement)

Regressions: None detected
```