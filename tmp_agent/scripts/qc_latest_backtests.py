#!/usr/bin/env python3
"""
QuantConnect API - Latest Backtests Fetcher
Created by Brain V9 Agent for AI_VAULT ecosystem
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

def load_qc_credentials():
    """Load QuantConnect credentials from secrets file"""
    secrets_path = Path("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
    
    if not secrets_path.exists():
        raise FileNotFoundError(f"QuantConnect credentials not found at {secrets_path}")
    
    with open(secrets_path, 'r') as f:
        return json.load(f)

def get_latest_backtests(user_id, api_token, limit=10):
    """Fetch latest backtests from QuantConnect API"""
    
    # QuantConnect API endpoint for backtests
    url = f"https://www.quantconnect.com/api/v2/backtests/read"
    
    headers = {
        'Authorization': f'Basic {api_token}',
        'Content-Type': 'application/json'
    }
    
    params = {
        'start': 0,
        'length': limit
    }
    
    try:
        print(f"Fetching latest {limit} backtests from QuantConnect...")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return None
            
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None

def format_backtest_info(backtests_data):
    """Format backtest information for display"""
    if not backtests_data or 'backtests' not in backtests_data:
        return "No backtests found or invalid response format"
    
    backtests = backtests_data['backtests']
    
    if not backtests:
        return "No backtests available"
    
    output = []
    output.append(f"=== LATEST {len(backtests)} BACKTESTS ===")
    output.append("")
    
    for i, bt in enumerate(backtests, 1):
        output.append(f"{i}. Backtest ID: {bt.get('backtestId', 'N/A')}")
        output.append(f"   Name: {bt.get('name', 'Unnamed')}")
        output.append(f"   Created: {bt.get('created', 'N/A')}")
        output.append(f"   Status: {bt.get('status', 'N/A')}")
        output.append(f"   Progress: {bt.get('progress', 'N/A')}%")
        
        # Performance metrics if available
        if 'statistics' in bt:
            stats = bt['statistics']
            output.append(f"   Return: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('TotalReturn', 'N/A')}")
            output.append(f"   Sharpe: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('SharpeRatio', 'N/A')}")
        
        output.append("")
    
    return "\n".join(output)

def main():
    """Main execution function"""
    try:
        print("QuantConnect Latest Backtests Fetcher")
        print("=====================================")
        
        # Load credentials
        credentials = load_qc_credentials()
        user_id = credentials.get('user_id')
        api_token = credentials.get('api_token')
        
        if not user_id or not api_token:
            print("ERROR: Missing user_id or api_token in credentials file")
            return
        
        print(f"Using User ID: {user_id}")
        
        # Fetch backtests
        backtests_data = get_latest_backtests(user_id, api_token, limit=10)
        
        if backtests_data:
            formatted_output = format_backtest_info(backtests_data)
            print(formatted_output)
            
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"C:/AI_VAULT/tmp_agent/results/qc_backtests_{timestamp}.txt"
            
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with open(output_file, 'w') as f:
                f.write(formatted_output)
            
            print(f"\nResults saved to: {output_file}")
        else:
            print("Failed to fetch backtests data")
            
    except Exception as e:
        print(f"Script execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
