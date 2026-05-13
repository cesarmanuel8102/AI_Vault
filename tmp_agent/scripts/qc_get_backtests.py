#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QuantConnect API Backtest Retrieval Script
Created by Brain V9 Agent for AI_VAULT ecosystem
"""

import json
import os
import requests
from datetime import datetime
from typing import Dict, List, Optional

class QuantConnectAPI:
    def __init__(self, credentials_path: str = None):
        """Initialize QuantConnect API client"""
        self.base_url = "https://www.quantconnect.com/api/v2"
        self.credentials_path = credentials_path or os.environ.get(
            'QC_SECRETS', 
            r'C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json'
        )
        self.credentials = self._load_credentials()
        
    def _load_credentials(self) -> Dict:
        """Load QuantConnect API credentials"""
        try:
            with open(self.credentials_path, 'r') as f:
                creds = json.load(f)
            print(f"✓ Credentials loaded from {self.credentials_path}")
            return creds
        except FileNotFoundError:
            print(f"❌ Credentials file not found: {self.credentials_path}")
            return {}
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in credentials file: {self.credentials_path}")
            return {}
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make authenticated request to QuantConnect API"""
        if not self.credentials:
            print("❌ No credentials available")
            return None
            
        url = f"{self.base_url}/{endpoint}"
        auth = (self.credentials.get('user_id', ''), self.credentials.get('api_token', ''))
        
        try:
            response = requests.get(url, auth=auth, params=params or {})
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API request failed: {e}")
            return None
    
    def get_projects(self) -> Optional[List[Dict]]:
        """Get all projects from QuantConnect"""
        print("📡 Fetching projects...")
        result = self._make_request("projects/read")
        if result and result.get('success'):
            projects = result.get('projects', [])
            print(f"✓ Found {len(projects)} projects")
            return projects
        return None
    
    def get_backtests(self, project_id: int, limit: int = 10) -> Optional[List[Dict]]:
        """Get backtests for a specific project"""
        print(f"📡 Fetching backtests for project {project_id}...")
        params = {'projectId': project_id, 'limit': limit}
        result = self._make_request("backtests/read", params)
        if result and result.get('success'):
            backtests = result.get('backtests', [])
            print(f"✓ Found {len(backtests)} backtests for project {project_id}")
            return backtests
        return None
    
    def get_all_backtests(self, limit_per_project: int = 5) -> Dict[str, List[Dict]]:
        """Get backtests from all projects"""
        print("🚀 Starting comprehensive backtest retrieval...")
        all_backtests = {}
        
        projects = self.get_projects()
        if not projects:
            return all_backtests
        
        for project in projects:
            project_id = project.get('projectId')
            project_name = project.get('name', f'Project_{project_id}')
            
            if project_id:
                backtests = self.get_backtests(project_id, limit_per_project)
                if backtests:
                    all_backtests[project_name] = backtests
        
        return all_backtests
    
    def print_summary(self, all_backtests: Dict[str, List[Dict]]):
        """Print a summary of retrieved backtests"""
        print("\n" + "="*60)
        print("📊 QUANTCONNECT BACKTESTS SUMMARY")
        print("="*60)
        
        total_backtests = sum(len(backtests) for backtests in all_backtests.values())
        print(f"Total Projects: {len(all_backtests)}")
        print(f"Total Backtests: {total_backtests}")
        print(f"Retrieved at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        for project_name, backtests in all_backtests.items():
            print(f"\n📁 {project_name} ({len(backtests)} backtests)")
            for i, backtest in enumerate(backtests[:3], 1):  # Show first 3
                name = backtest.get('name', 'Unnamed')
                created = backtest.get('created', 'Unknown date')
                print(f"  {i}. {name} | {created}")
            if len(backtests) > 3:
                print(f"  ... and {len(backtests) - 3} more")
    
    def save_results(self, all_backtests: Dict[str, List[Dict]], output_path: str = None):
        """Save results to JSON file"""
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"C:\\AI_VAULT\\tmp_agent\\data\\qc_backtests_{timestamp}.json"
        
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(all_backtests, f, indent=2, default=str)
            print(f"\n💾 Results saved to: {output_path}")
        except Exception as e:
            print(f"❌ Failed to save results: {e}")

def main():
    """Main execution function"""
    print("🧠 Brain V9 - QuantConnect Backtest Retrieval")
    print("=" * 50)
    
    # Initialize API client
    qc_api = QuantConnectAPI()
    
    if not qc_api.credentials:
        print("\n❌ Cannot proceed without valid credentials")
        print("Expected location: C:\\AI_VAULT\\tmp_agent\\Secrets\\quantconnect_access.json")
        print("Expected format: {\"user_id\": \"your_user_id\", \"api_token\": \"your_token\"}")
        return
    
    # Retrieve all backtests
    all_backtests = qc_api.get_all_backtests(limit_per_project=10)
    
    if all_backtests:
        # Print summary
        qc_api.print_summary(all_backtests)
        
        # Save results
        qc_api.save_results(all_backtests)
        
        print("\n✅ Backtest retrieval completed successfully!")
    else:
        print("\n❌ No backtests retrieved")

if __name__ == "__main__":
    main()
