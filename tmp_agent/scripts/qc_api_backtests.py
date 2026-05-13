#!/usr/bin/env python3
"""
QuantConnect API Backtest Fetcher
Created by Brain V9 Agent
Fetches backtests from QuantConnect API using stored credentials
"""

import json
import requests
import os
from datetime import datetime
from typing import Dict, List, Optional

class QuantConnectAPI:
    def __init__(self, credentials_path: str = None):
        """Initialize QuantConnect API client"""
        if credentials_path is None:
            credentials_path = os.environ.get('QC_SECRETS', 'C:\\AI_VAULT\\tmp_agent\\Secrets\\quantconnect_access.json')
        
        self.credentials_path = credentials_path
        self.base_url = "https://www.quantconnect.com/api/v2"
        self.session = requests.Session()
        self._load_credentials()
    
    def _load_credentials(self):
        """Load credentials from JSON file"""
        try:
            with open(self.credentials_path, 'r') as f:
                creds = json.load(f)
                self.user_id = creds.get('user_id')
                self.api_token = creds.get('api_token')
                
            if not self.user_id or not self.api_token:
                raise ValueError("Missing user_id or api_token in credentials")
                
            # Set up authentication
            self.session.auth = (self.user_id, self.api_token)
            print(f"✓ Credentials loaded from {self.credentials_path}")
            
        except FileNotFoundError:
            print(f"❌ Credentials file not found: {self.credentials_path}")
            raise
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in credentials file: {e}")
            raise
        except Exception as e:
            print(f"❌ Error loading credentials: {e}")
            raise
    
    def get_projects(self) -> List[Dict]:
        """Get list of projects"""
        try:
            url = f"{self.base_url}/projects/read"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                projects = data.get('projects', [])
                print(f"✓ Found {len(projects)} projects")
                return projects
            else:
                print(f"❌ API Error: {data.get('errors', 'Unknown error')}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return []
    
    def get_backtests(self, project_id: int, limit: int = 10) -> List[Dict]:
        """Get backtests for a specific project"""
        try:
            url = f"{self.base_url}/backtests/read"
            params = {
                'projectId': project_id,
                'includeStatistics': True,
                'start': 0,
                'length': limit
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                backtests = data.get('backtests', [])
                print(f"✓ Found {len(backtests)} backtests for project {project_id}")
                return backtests
            else:
                print(f"❌ API Error: {data.get('errors', 'Unknown error')}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return []
    
    def get_all_backtests(self, limit_per_project: int = 5) -> Dict:
        """Get backtests from all projects"""
        print("🔍 Fetching all backtests from QuantConnect...")
        print("=" * 50)
        
        projects = self.get_projects()
        if not projects:
            return {}
        
        all_backtests = {}
        
        for project in projects:
            project_id = project.get('projectId')
            project_name = project.get('name', f'Project {project_id}')
            
            print(f"\n📊 Project: {project_name} (ID: {project_id})")
            backtests = self.get_backtests(project_id, limit_per_project)
            
            if backtests:
                all_backtests[project_id] = {
                    'project_name': project_name,
                    'backtests': backtests
                }
                
                # Show summary of each backtest
                for bt in backtests[:3]:  # Show first 3
                    name = bt.get('name', 'Unnamed')
                    created = bt.get('created', 'Unknown')
                    completed = bt.get('completed', False)
                    
                    # Extract key metrics if available
                    stats = bt.get('statistics', {})
                    total_return = stats.get('Total Performance', {}).get('PortfolioStatistics', {}).get('TotalPerformance', 'N/A')
                    sharpe = stats.get('Total Performance', {}).get('PortfolioStatistics', {}).get('SharpeRatio', 'N/A')
                    
                    status = "✅ Completed" if completed else "⏳ Running"
                    print(f"  • {name} | {created} | {status}")
                    if total_return != 'N/A':
                        print(f"    Return: {total_return}, Sharpe: {sharpe}")
        
        print(f"\n📈 Summary: Found backtests in {len(all_backtests)} projects")
        return all_backtests
    
    def save_results(self, results: Dict, output_file: str = None):
        """Save results to JSON file"""
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f'C:\\AI_VAULT\\tmp_agent\\data\\qc_backtests_{timestamp}.json'
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            print(f"💾 Results saved to: {output_file}")
            return output_file
        except Exception as e:
            print(f"❌ Error saving results: {e}")
            return None

def main():
    """Main execution function"""
    try:
        print("🚀 QuantConnect Backtest Fetcher")
        print("=" * 40)
        
        # Initialize API client
        qc_api = QuantConnectAPI()
        
        # Fetch all backtests
        results = qc_api.get_all_backtests(limit_per_project=10)
        
        if results:
            # Save results
            output_file = qc_api.save_results(results)
            
            # Summary stats
            total_backtests = sum(len(data['backtests']) for data in results.values())
            print(f"\n📊 FINAL SUMMARY:")
            print(f"   Projects: {len(results)}")
            print(f"   Total Backtests: {total_backtests}")
            if output_file:
                print(f"   Saved to: {output_file}")
        else:
            print("❌ No backtests found or API error")
            
    except Exception as e:
        print(f"❌ Script failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
