"""
AI_VAULT Construction Supervisor
Monitors Brain progress every 3 minutes and reports to user
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

class ConstructionSupervisor:
    def __init__(self):
        self.roadmap_v2_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system\ROADMAP_V2_AUTONOMY.json")
        self.brain_roadmap_path = Path(r"C:\AI_VAULT\tmp_agent\state\roadmap.json")
        self.autonomy_state_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system\autonomy_state.json")
        self.progress_log_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system\logs\construction_progress.log")
        self.progress_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.current_phase = None
        self.current_bl_item = None
        self.start_time = datetime.now(timezone.utc)
        self.check_count = 0
    
    def load_roadmaps(self) -> Dict[str, Any]:
        """Load both active roadmaps"""
        roadmaps = {}
        
        if self.roadmap_v2_path.exists():
            with open(self.roadmap_v2_path, 'r') as f:
                roadmaps['v2'] = json.load(f)
        
        if self.brain_roadmap_path.exists():
            with open(self.brain_roadmap_path, 'r') as f:
                roadmaps['brain_lab'] = json.load(f)
        
        return roadmaps
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current construction status"""
        roadmaps = self.load_roadmaps()
        
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_time": str(datetime.now(timezone.utc) - self.start_time),
            "check_number": self.check_count,
            "phases": {}
        }
        
        # Phase 6.1 Status
        if 'v2' in roadmaps:
            v2 = roadmaps['v2']
            for phase in v2.get('phases', []):
                if phase.get('status') == 'active':
                    status['phases']['6.1'] = {
                        "name": phase.get('name'),
                        "description": phase.get('description'),
                        "goals": phase.get('goals', []),
                        "success_criteria": phase.get('success_criteria', []),
                        "progress": self._calculate_phase_progress(phase)
                    }
                    self.current_phase = phase
                    break
        
        # Brain Lab BL-02 Status
        if 'brain_lab' in roadmaps:
            bl = roadmaps['brain_lab']
            for item in bl.get('work_items', []):
                if item.get('status') == 'in_progress':
                    status['phases']['BL-02'] = {
                        "id": item.get('id'),
                        "title": item.get('title'),
                        "objective": item.get('objective'),
                        "deliverable": item.get('deliverable'),
                        "room_id": item.get('room_id'),
                        "progress": self._calculate_bl_progress(item)
                    }
                    self.current_bl_item = item
                    break
        
        return status
    
    def _calculate_phase_progress(self, phase: Dict) -> Dict[str, Any]:
        """Calculate progress for Phase 6.1"""
        goals = phase.get('goals', [])
        criteria = phase.get('success_criteria', [])
        
        # Check which files exist to determine progress
        progress = {
            "goals_total": len(goals),
            "criteria_total": len(criteria),
            "completed_goals": [],
            "pending_goals": [],
            "completed_criteria": [],
            "pending_criteria": []
        }
        
        # Check for trading engine files
        trading_files = [
            Path(r"C:\AI_VAULT\00_identity\trading_engine.py"),
            Path(r"C:\AI_VAULT\00_identity\risk_manager.py"),
            Path(r"C:\AI_VAULT\00_identity\backtest_engine.py")
        ]
        
        for goal in goals:
            if "trading" in goal.lower() and any(f.exists() for f in trading_files):
                progress["completed_goals"].append(goal)
            elif "capital" in goal.lower() and Path(r"C:\AI_VAULT\00_identity\capital_manager.py").exists():
                progress["completed_goals"].append(goal)
            elif "simulación" in goal.lower() and Path(r"C:\AI_VAULT\00_identity\backtest_engine.py").exists():
                progress["completed_goals"].append(goal)
            elif "datos" in goal.lower():
                progress["completed_goals"].append(goal)  # Already done
            else:
                progress["pending_goals"].append(goal)
        
        progress["percentage"] = len(progress["completed_goals"]) / len(goals) * 100 if goals else 0
        
        return progress
    
    def _calculate_bl_progress(self, item: Dict) -> Dict[str, Any]:
        """Calculate progress for BL-02"""
        deliverable = item.get('deliverable', '')
        deliverables = [d.strip() for d in deliverable.split(',')]
        
        progress = {
            "deliverables_total": len(deliverables),
            "completed": [],
            "pending": []
        }
        
        for d in deliverables:
            file_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system") / d
            if file_path.exists():
                progress["completed"].append(d)
            else:
                progress["pending"].append(d)
        
        progress["percentage"] = len(progress["completed"]) / len(deliverables) * 100 if deliverables else 0
        
        return progress
    
    def format_report(self, status: Dict[str, Any]) -> str:
        """Format status report for user"""
        lines = []
        lines.append("=" * 70)
        lines.append("AI_VAULT CONSTRUCTION SUPERVISOR - PROGRESS REPORT")
        lines.append("=" * 70)
        lines.append(f"Check #{status['check_number']} | Elapsed: {status['elapsed_time']}")
        lines.append(f"Timestamp: {status['timestamp']}")
        lines.append("")
        
        # Phase 6.1 Report
        if '6.1' in status['phases']:
            phase = status['phases']['6.1']
            lines.append("PHASE 6.1: MOTOR FINANCIERO")
            lines.append("-" * 70)
            lines.append(f"Name: {phase['name']}")
            lines.append(f"Description: {phase['description']}")
            lines.append("")
            
            progress = phase['progress']
            lines.append(f"Progress: {progress['percentage']:.1f}%")
            lines.append(f"   Completed Goals: {len(progress['completed_goals'])}/{progress['goals_total']}")
            
            if progress['completed_goals']:
                lines.append("   Done:")
                for goal in progress['completed_goals'][:3]:
                    lines.append(f"     * {goal[:60]}...")
            
            if progress['pending_goals']:
                lines.append("   Next:")
                for goal in progress['pending_goals'][:2]:
                    lines.append(f"     > {goal[:60]}...")
            
            lines.append("")
        
        # BL-02 Report
        if 'BL-02' in status['phases']:
            bl = status['phases']['BL-02']
            lines.append("BRAIN LAB: BL-02 - Operativizacion de la funcion U")
            lines.append("-" * 70)
            lines.append(f"Title: {bl['title']}")
            lines.append(f"Objective: {bl['objective'][:100]}...")
            lines.append("")
            
            progress = bl['progress']
            lines.append(f"Progress: {progress['percentage']:.1f}%")
            lines.append(f"   Completed: {len(progress['completed'])}/{progress['deliverables_total']}")
            
            if progress['completed']:
                lines.append("   Files created:")
                for d in progress['completed'][:3]:
                    lines.append(f"     * {d}")
            
            if progress['pending']:
                lines.append("   Pending files:")
                for d in progress['pending'][:3]:
                    lines.append(f"     > {d}")
            
            lines.append("")
        
        # Action Items
        lines.append("IMMEDIATE ACTION ITEMS")
        lines.append("-" * 70)
        
        if '6.1' in status['phases']:
            phase = status['phases']['6.1']
            if phase['progress']['pending_goals']:
                lines.append(f"1. Continue: {phase['progress']['pending_goals'][0][:70]}")
        
        if 'BL-02' in status['phases']:
            bl = status['phases']['BL-02']
            if bl['progress']['pending']:
                lines.append(f"2. Create: {bl['progress']['pending'][0]}")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    async def run_check(self):
        """Run a single check cycle"""
        self.check_count += 1
        status = self.get_current_status()
        report = self.format_report(status)
        
        # Log to file
        with open(self.progress_log_path, 'a') as f:
            f.write(report + "\n\n")
        
        # Print to console
        print(report)
        
        return status
    
    async def run(self):
        """Main supervision loop - checks every 3 minutes"""
        print("\nAI_VAULT Construction Supervisor Started")
        print("   Monitoring Brain progress every 3 minutes...")
        print("   Press Ctrl+C to stop\n")
        
        try:
            while True:
                await self.run_check()
                print("\nNext check in 3 minutes...\n")
                await asyncio.sleep(180)  # 3 minutes
        except KeyboardInterrupt:
            print("\n\nSupervisor stopped by user")
            print(f"   Total checks: {self.check_count}")
            print(f"   Log saved to: {self.progress_log_path}")

if __name__ == "__main__":
    supervisor = ConstructionSupervisor()
    asyncio.run(supervisor.run())
