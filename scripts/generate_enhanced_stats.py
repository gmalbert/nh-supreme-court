"""
Enhanced statistics and analysis for oral arguments.
Generates additional metrics beyond basic attorney/firm stats.
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter
import re

def load_oral_arguments():
    """Load oral arguments data."""
    path = Path(__file__).parent.parent / "data/processed/oral_arguments.json"
    with open(path, "r") as f:
        return json.load(f)

def load_attorney_stats():
    """Load attorney statistics."""
    path = Path(__file__).parent.parent / "data/processed/oral_arguments_attorney_stats.json"
    with open(path, "r") as f:
        return json.load(f)

def analyze_temporal_trends():
    """Analyze temporal trends in oral arguments."""
    args = load_oral_arguments()
    attorney_stats = load_attorney_stats()
    
    # Convert to dataframe for easier analysis
    df = pd.DataFrame(args)
    df['argument_date'] = pd.to_datetime(df['argument_date'])
    df['year'] = df['argument_date'].dt.year
    df['month'] = df['argument_date'].dt.month
    df['quarter'] = df['argument_date'].dt.quarter
    df['day_of_week'] = df['argument_date'].dt.dayofweek
    df['duration_minutes'] = df['duration_seconds'] / 60
    
    trends = {}
    
    # Yearly trends
    yearly = df.groupby('year').agg({
        'case_number': 'count',
        'duration_minutes': ['mean', 'median', 'sum']
    }).round(2)
    yearly.columns = ['total_arguments', 'avg_duration_min', 'median_duration_min', 'total_hours']
    yearly['total_hours'] = (yearly['total_hours'] / 60).round(2)
    trends['yearly'] = yearly.to_dict('index')
    
    # Monthly distribution (aggregated across all years)
    monthly = df.groupby('month').agg({
        'case_number': 'count',
        'duration_minutes': 'mean'
    }).round(2)
    monthly.columns = ['total_arguments', 'avg_duration_min']
    trends['monthly'] = monthly.to_dict('index')
    
    # Quarterly distribution
    quarterly = df.groupby('quarter').agg({
        'case_number': 'count',
        'duration_minutes': 'mean'
    }).round(2)
    quarterly.columns = ['total_arguments', 'avg_duration_min']
    trends['quarterly'] = quarterly.to_dict('index')
    
    # Day of week distribution
    dow = df.groupby('day_of_week').agg({
        'case_number': 'count',
        'duration_minutes': 'mean'
    }).round(2)
    dow.columns = ['total_arguments', 'avg_duration_min']
    trends['day_of_week'] = dow.to_dict('index')
    
    # Year-over-year growth
    yearly_counts = df.groupby('year')['case_number'].count()
    yoy_growth = yearly_counts.pct_change() * 100
    trends['yoy_growth'] = yoy_growth.round(2).to_dict()
    
    # Duration trends over time
    duration_trends = df.groupby('year')['duration_minutes'].agg(['mean', 'median', 'std']).round(2)
    trends['duration_by_year'] = duration_trends.to_dict('index')
    
    return trends

def analyze_case_complexity():
    """Analyze case complexity indicators."""
    args = load_oral_arguments()
    df = pd.DataFrame(args)
    df['duration_minutes'] = df['duration_seconds'] / 60
    
    # Complexity quartiles based on duration
    df['complexity'] = pd.qcut(df['duration_minutes'], q=4, labels=['Simple', 'Moderate', 'Complex', 'Very Complex'])
    
    complexity_stats = df.groupby('complexity').agg({
        'case_number': 'count',
        'duration_minutes': ['mean', 'min', 'max'],
        'segment_count': 'mean'
    }).round(2)
    
    # Convert to simple dict format
    result = {}
    for complexity_level in complexity_stats.index:
        result[str(complexity_level)] = {
            'count': int(complexity_stats.loc[complexity_level, ('case_number', 'count')]),
            'avg_duration': float(complexity_stats.loc[complexity_level, ('duration_minutes', 'mean')]),
            'min_duration': float(complexity_stats.loc[complexity_level, ('duration_minutes', 'min')]),
            'max_duration': float(complexity_stats.loc[complexity_level, ('duration_minutes', 'max')]),
            'avg_segments': float(complexity_stats.loc[complexity_level, ('segment_count', 'mean')])
        }
    
    return result

def analyze_attorney_networks():
    """Analyze attorney co-counsel and firm networks."""
    # For now, analyze firm-attorney relationships
    attorney_stats = load_attorney_stats()
    
    networks = {
        'firm_attorney_map': defaultdict(list),
        'attorney_firm_history': defaultdict(set),
        'top_firms': [],
        'solo_practitioners': []
    }
    
    for attorney in attorney_stats.get('attorney_stats', []):
        firm = attorney.get('firm', 'Solo Practitioner')
        attorney_name = attorney['attorney_name']
        
        networks['firm_attorney_map'][firm].append({
            'name': attorney_name,
            'arguments': attorney['total_arguments'],
            'duration_hours': attorney.get('total_duration_hours', 0)
        })
        networks['attorney_firm_history'][attorney_name].add(firm)
    
    # Top firms by attorney count
    networks['top_firms'] = sorted(
        [
            {'firm': firm, 'attorney_count': len(attorneys)}
            for firm, attorneys in networks['firm_attorney_map'].items()
        ],
        key=lambda x: x['attorney_count'],
        reverse=True
    )[:20]
    
    # Solo practitioners
    networks['solo_practitioners'] = [
        a['attorney_name'] 
        for a in attorney_stats.get('attorney_stats', [])
        if a.get('firm') == 'Solo Practitioner'
    ]
    
    # Convert sets to lists for JSON serialization
    networks['attorney_firm_history'] = {
        k: list(v) for k, v in networks['attorney_firm_history'].items()
    }
    networks['firm_attorney_map'] = dict(networks['firm_attorney_map'])
    
    return networks

def analyze_case_parties():
    """Extract and analyze case party information from case names."""
    args = load_oral_arguments()
    
    parties_info = {
        'state_cases': [],
        'civil_cases': [],
        'family_cases': [],
        'case_types': Counter()
    }
    
    for arg in args:
        case_name = arg.get('case_name', '').lower()
        case_num = arg['case_number']
        
        # Identify case types
        if 'state of new hampshire v.' in case_name or 'state v.' in case_name:
            parties_info['state_cases'].append(case_num)
            parties_info['case_types']['Criminal'] += 1
        elif ' v. ' in case_name:
            parties_info['civil_cases'].append(case_num)
            parties_info['case_types']['Civil'] += 1
        elif 'in re' in case_name or 'in the matter' in case_name:
            parties_info['family_cases'].append(case_num)
            parties_info['case_types']['Family/Probate'] += 1
        else:
            parties_info['case_types']['Other'] += 1
    
    parties_info['case_types'] = dict(parties_info['case_types'])
    
    return parties_info

def generate_enhanced_statistics():
    """Generate all enhanced statistics."""
    print("Generating temporal trends...")
    temporal = analyze_temporal_trends()
    
    print("Analyzing case complexity...")
    complexity = analyze_case_complexity()
    
    print("Analyzing attorney networks...")
    networks = analyze_attorney_networks()
    
    print("Analyzing case parties...")
    parties = analyze_case_parties()
    
    enhanced_stats = {
        'temporal_trends': temporal,
        'complexity_analysis': complexity,
        'attorney_networks': networks,
        'case_parties': parties,
        'generated_at': datetime.now().isoformat()
    }
    
    # Save to file
    output_path = Path(__file__).parent.parent / "data/processed/oral_arguments_enhanced_stats.json"
    with open(output_path, 'w') as f:
        json.dump(enhanced_stats, f, indent=2)
    
    print(f"Enhanced statistics saved to {output_path}")
    print(f"- Temporal trends: {len(temporal)} categories")
    print(f"- Complexity levels: {len(complexity)} levels")
    print(f"- Top firms: {len(networks['top_firms'])} firms")
    print(f"- Case types: {len(parties['case_types'])} types")
    
    return enhanced_stats

if __name__ == '__main__':
    generate_enhanced_statistics()
