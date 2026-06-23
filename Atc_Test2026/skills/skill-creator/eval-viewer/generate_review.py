import os
import json
from typing import Dict, Any


def generate_review(evaluation_data: Dict[str, Any], output_path: str) -> None:
    """Generate evaluation review HTML"""
    # Read template
    template_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'eval_review.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # Replace placeholders
    review_html = template
    review_html = review_html.replace('{{skill_name}}', evaluation_data.get('skill_name', 'Unknown'))
    review_html = review_html.replace('{{eval_date}}', evaluation_data.get('evaluation_date', 'Unknown'))
    review_html = review_html.replace('{{overall_score}}', str(evaluation_data.get('overall_score', 0)))
    
    # Generate criteria scores
    criteria_html = ''
    for criterion in evaluation_data.get('criteria', []):
        criteria_html += f"\n                <div class='criterion'>\n                    <span class='criterion-name'>{criterion['name']}:</span>\n                    <span class='criterion-score'>{criterion['score']}/10</span>\n                </div>"
    review_html = review_html.replace('{{criteria_scores}}', criteria_html)
    
    # Replace feedback
    review_html = review_html.replace('{{feedback}}', evaluation_data.get('feedback', ''))
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(review_html)
    
    print(f"Evaluation review generated: {output_path}")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate evaluation review")
    parser.add_argument("evaluation_data", help="Path to evaluation data JSON file")
    parser.add_argument("output_path", help="Output HTML file path")
    
    args = parser.parse_args()
    
    # Read evaluation data
    with open(args.evaluation_data, 'r', encoding='utf-8') as f:
        evaluation_data = json.load(f)
    
    generate_review(evaluation_data, args.output_path)


if __name__ == "__main__":
    main()