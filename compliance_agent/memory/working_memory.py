"""Working memory for tracking agent execution and intermediate states."""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import json
from pathlib import Path


@dataclass
class RunLog:
    """Log entry for a single agent execution."""
    timestamp: str
    agent_name: str
    action: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class WorkingMemory:
    """Manages working memory for a single compliance check run."""
    
    def __init__(self, run_id: str = None):
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = run_id
        
        self.logs: List[RunLog] = []
        self.intermediate_results: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.start_time = datetime.now()
    
    def log_agent_action(
        self,
        agent_name: str,
        action: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        error: Optional[str] = None,
        duration_seconds: Optional[float] = None
    ):
        """Log an agent action."""
        log_entry = RunLog(
            timestamp=datetime.now().isoformat(),
            agent_name=agent_name,
            action=action,
            input_data=input_data,
            output_data=output_data,
            error=error,
            duration_seconds=duration_seconds
        )
        self.logs.append(log_entry)
    
    def store_intermediate_result(self, key: str, value: Any):
        """Store an intermediate result."""
        self.intermediate_results[key] = value
    
    def get_intermediate_result(self, key: str) -> Optional[Any]:
        """Retrieve an intermediate result."""
        return self.intermediate_results.get(key)
    
    def log_error(self, error_message: str):
        """Log an error."""
        self.errors.append(f"{datetime.now().isoformat()}: {error_message}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the run."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "total_logs": len(self.logs),
            "total_errors": len(self.errors),
            "agents_executed": list(set(log.agent_name for log in self.logs)),
            "errors": self.errors
        }
    
    def export_logs(self, output_path: Path):
        """Export logs to JSON file."""
        logs_dict = [asdict(log) for log in self.logs]
        output_path.write_text(json.dumps(logs_dict, indent=2, default=str))
    
    def export_summary(self, output_path: Path):
        """Export summary to JSON file."""
        summary = self.get_summary()
        summary["intermediate_results"] = self.intermediate_results
        output_path.write_text(json.dumps(summary, indent=2, default=str))
