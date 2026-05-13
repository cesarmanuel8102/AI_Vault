#!/usr/bin/env python3
"""
QuantConnect Live Metrics Fetcher
Fetches equity, drawdown, win rate and Sharpe ratio from QC API
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

class QCMetricsFetcher:
    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = os.getenv('QC_SECRETS', 'C:\\AI_VAULT\\tmp_agent\\Secrets\\quantconnect_access.json')
        
        self.credentials_path = credentials_path
        self.base_url = 'https://www.quantconnect.com/api/v2'
        self.credentials = self.load_credentials()
        
    def load_credentials(self):
        """Load QuantConnect API credentials"""
        try:
            with open(self.credentials_path, 'r') as f:
                creds = json.load(f)
            print(f"✓ Credentials loaded from {self.credentials_path}")
            return creds
        except FileNotFoundError:
            print(f"✗ Credentials file not found: {self.credentials_path}")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON in credentials file: {e}")
            return None
    
    def get_live_projects(self):
        """Get list of live projects"""
        if not self.credentials:
            return None
            
        url = f"{self.base_url}/projects/read"
        
        try:
            response = requests.get(
                url,
                auth=(self.credentials.get('user_id', ''), self.credentials.get('api_token', '')),
                timeout=30
            )
            
            if response.status_code == 200:
                projects = response.json()
                live_projects = [p for p in projects.get('projects', []) if p.get('liveResults')]
                print(f"✓ Found {len(live_projects)} live projects")
                return live_projects
            else:
                print(f"✗ API Error: {response.status_code} - {response.text}")
                return None
                
        except requests.RequestException as e:
            print(f"✗ Request failed: {e}")
            return None
    
    def get_live_results(self, project_id):
        """Get live results for a specific project"""
        if not self.credentials:
            return None
            
        url = f"{self.base_url}/live/read"
        params = {'projectId': project_id}
        
        try:
            response = requests.get(
                url,
                params=params,
                auth=(self.credentials.get('user_id', ''), self.credentials.get('api_token', '')),
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"✗ Live results API Error: {response.status_code} - {response.text}")
                return None
                
        except requests.RequestException as e:
            print(f"✗ Live results request failed: {e}")
            return None
    
    def extract_metrics(self, live_data):
        """Extract key metrics from live results"""
        if not live_data or 'liveResults' not in live_data:
            return None
        
        results = live_data['liveResults']
        
        # Extract key metrics
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'project_id': live_data.get('projectId'),
            'project_name': live_data.get('name', 'Unknown'),
            'status': results.get('status', 'Unknown'),
            'equity': results.get('equity', 0),
            'unrealized_profit': results.get('unrealizedProfit', 0),
            'total_profit': results.get('totalProfit', 0),
            'drawdown': results.get('drawdown', 0),
            'max_drawdown': results.get('maxDrawdown', 0),
            'win_rate': results.get('winRate', 0),
            'sharpe_ratio': results.get('sharpeRatio', 0),
            'total_trades': results.get('totalTrades', 0),
            'winning_trades': results.get('winningTrades', 0),
            'losing_trades': results.get('losingTrades', 0),
            'start_date': results.get('startDate'),
            'end_date': results.get('endDate'),
            'runtime': results.get('runtimeStatistics', {})
        }
        
        return metrics
    
    def fetch_all_metrics(self):
        """Fetch metrics for all live deployments"""
        print("=== QuantConnect Live Metrics Fetcher ===")
        print(f"Timestamp: {datetime.now()}")
        print()
        
        # Get live projects
        projects = self.get_live_projects()
        if not projects:
            print("No live projects found or API error")
            return []
        
        all_metrics = []
        
        for project in projects:
            project_id = project.get('projectId')
            project_name = project.get('name', f'Project {project_id}')
            
            print(f"\n--- Processing {project_name} (ID: {project_id}) ---")
            
            # Get live results
            live_data = self.get_live_results(project_id)
            if not live_data:
                print(f"✗ Could not fetch live results for {project_name}")
                continue
            
            # Extract metrics
            metrics = self.extract_metrics(live_data)
            if metrics:
                all_metrics.append(metrics)
                
                # Display key metrics
                print(f"Status: {metrics['status']}")
                print(f"Equity: ${metrics['equity']:,.2f}")
                print(f"Total Profit: ${metrics['total_profit']:,.2f}")
                print(f"Drawdown: {metrics['drawdown']:.2%}")
                print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
                print(f"Win Rate: {metrics['win_rate']:.2%}")
                print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.3f}")
                print(f"Total Trades: {metrics['total_trades']}")
            else:
                print(f"✗ Could not extract metrics for {project_name}")
        
        return all_metrics
    
    def save_metrics(self, metrics, output_path=None):
        """Save metrics to JSON file"""
        if output_path is None:
            output_path = f"C:\\AI_VAULT\\tmp_agent\\data\\qc_live_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            with open(output_path, 'w') as f:
                json.dump(metrics, f, indent=2)
            print(f"\n✓ Metrics saved to: {output_path}")
            return output_path
        except Exception as e:
            print(f"\n✗ Failed to save metrics: {e}")
            return None

def main():
    """Main execution"""
    fetcher = QCMetricsFetcher()
    
    # Fetch all metrics
    metrics = fetcher.fetch_all_metrics()
    
    if metrics:
        # Save to file
        output_file = fetcher.save_metrics(metrics)
        
        print(f"\n=== SUMMARY ===")
        print(f"Live deployments processed: {len(metrics)}")
        print(f"Output file: {output_file}")
        
        # Display summary
        for i, m in enumerate(metrics, 1):
            print(f"\n{i}. {m['project_name']}:")
            print(f"   Equity: ${m['equity']:,.2f}")
            print(f"   Drawdown: {m['drawdown']:.2%}")
            print(f"   Win Rate: {m['win_rate']:.2%}")
            print(f"   Sharpe: {m['sharpe_ratio']:.3f}")
    else:
        print("\n✗ No metrics retrieved")

if __name__ == '__main__':
    main()
