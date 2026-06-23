import os
import json
from typing import Dict, Any, List

from utils import (
    read_file,
    write_file
)


def aggregate_benchmark_results(results_dir: str, output_path: str) -> Dict[str, Any]:
    """Aggregate benchmark results"""
    results = []
    
    # Collect all result files
    for root, dirs, files in os.walk(results_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                try:
                    result = json.loads(read_file(file_path))
                    results.append(result)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    # Aggregate results
    aggregate = {
        'total_runs': len(results),
        'results': results
    }
    
    # Write aggregate
    write_file(json.dumps(aggregate, indent=2, ensure_ascii=False), output_path)
    
    print(f"Benchmark results aggregated: {output_path}")
    
    return aggregate


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Aggregate benchmark results")
    parser.add_argument("results_dir", help="Directory containing benchmark results")
    parser.add_argument("output_path", help="Output aggregate file path")
    
    args = parser.parse_args()
    
    aggregate_benchmark_results(args.results_dir, args.output_path)


if __name__ == "__main__":
    main()