#!/usr/bin/env python3
"""
QuantConnect API - Get Latest Backtest
Created by Brain V9 Agent
"""

import json
import requests
import os
from datetime import datetime

def load_qc_credentials():
    """Load QuantConnect credentials from config file"""
    secrets_path = os.environ.get('QC_SECRETS', 'C:\\AI_VAULT\\tmp_agent\\Secrets\\quantconnect_access.json')
    
    try:
        with open(secrets_path, 'r') as f:
            creds = json.load(f)
        return creds.get('user_id'), creds.get('api_token')
    except FileNotFoundError:
        print(f"ERROR: Credentials file not found at {secrets_path}")
        return None, None
    except json.JSONDecodeError:
        print(f"ERROR: Invalid JSON in credentials file {secrets_path}")
        return None, None

def get_latest_backtest(user_id, api_token):
    """Get the latest backtest from QuantConnect API"""
    
    # QuantConnect API endpoint for backtests
    url = f"https://www.quantconnect.com/api/v2/backtests/read"
    
    headers = {
        'Authorization': f'Basic {user_id}:{api_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'backtests' in data and len(data['backtests']) > 0:
                # Get the most recent backtest (assuming they're sorted by date)
                latest = data['backtests'][0]
                
                print("=== LATEST QUANTCONNECT BACKTEST ===")
                print(f"Backtest ID: {latest.get('backtestId', 'N/A')}")
                print(f"Name: {latest.get('name', 'N/A')}")
                print(f"Created: {latest.get('created', 'N/A')}")
                print(f"Completed: {latest.get('completed', 'N/A')}")
                print(f"Progress: {latest.get('progress', 'N/A')}")
                print(f"Result: {latest.get('result', 'N/A')}")
                
                # Show performance stats if available
                if 'statistics' in latest:
                    stats = latest['statistics']
                    print("\n=== PERFORMANCE STATS ===")
                    for key, value in stats.items():
                        print(f"{key}: {value}")
                
                return latest
            else:
                print("No backtests found in the account")
                return None
                
        else:
            print(f"API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return None

def main():
    print("QuantConnect Latest Backtest Retrieval")
    print("=" * 40)
    
    # Load credentials
    user_id, api_token = load_qc_credentials()
    
    if not user_id or not api_token:
        print("Failed to load QuantConnect credentials")
        return
    
    print(f"Using credentials for user: {user_id[:8]}...")
    
    # Get latest backtest
    backtest = get_latest_backtest(user_id, api_token)
    
    if backtest:
        print("\nBacktest retrieved successfully!")
    else:
        print("\nFailed to retrieve backtest")

if __name__ == "__main__":
    main()
