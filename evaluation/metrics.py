"""Evaluation metrics for compliance system."""

from typing import List, Dict, Any, Optional
import json
from pathlib import Path
from sklearn.metrics import precision_recall_fscore_support, accuracy_score, cohen_kappa_score
import numpy as np


class ComplianceEvaluator:
    """Evaluates compliance system performance against ground truth."""
    
    def __init__(self, ground_truth_path: str):
        """
        Initialize evaluator with ground truth data.
        
        Args:
            ground_truth_path: Path to JSON file with ground truth labels
        """
        self.ground_truth = self._load_ground_truth(ground_truth_path)
    
    def _load_ground_truth(self, path: str) -> Dict[str, str]:
        """Load ground truth labels."""
        gt_file = Path(path)
        if not gt_file.exists():
            raise FileNotFoundError(f"Ground truth file not found: {path}")
        
        with open(gt_file, 'r') as f:
            data = json.load(f)
        
        # Convert to dict: requirement_id -> label
        if isinstance(data, list):
            return {item["requirement_id"]: item["label"] for item in data}
        elif isinstance(data, dict):
            return data
        else:
            raise ValueError("Ground truth must be dict or list")
    
    def evaluate(
        self,
        system_output_path: str,
        output_metrics_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate system output against ground truth.
        
        Args:
            system_output_path: Path to system output JSON
            output_metrics_path: Optional path to save metrics
        
        Returns:
            Dictionary with evaluation metrics
        """
        # Load system output
        system_output = self._load_system_output(system_output_path)
        predicted_labels = system_output["labels"]
        confidence_by_requirement = system_output["confidences"]
        
        # Extract labels
        y_true = []
        y_pred = []
        requirement_ids = []
        
        for req_id, true_label in self.ground_truth.items():
            pred_label = predicted_labels.get(req_id, "not_addressed")
            
            requirement_ids.append(req_id)
            y_true.append(true_label)
            y_pred.append(pred_label)
        
        # Calculate metrics
        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "cohen_kappa": cohen_kappa_score(y_true, y_pred),
            "per_label_metrics": {},
            "confusion_matrix": self._build_confusion_matrix(y_true, y_pred),
            "calibration": self._calculate_calibration(
                requirement_ids,
                y_true,
                y_pred,
                confidence_by_requirement,
            ),
        }
        
        # Per-label precision, recall, F1
        labels = sorted(set(y_true + y_pred))
        precision, recall, f1, support = precision_recall_fscore_support(
            y_true, y_pred, labels=labels, zero_division=0
        )
        
        for i, label in enumerate(labels):
            metrics["per_label_metrics"][label] = {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i])
            }
        
        # Overall macro and micro averages
        metrics["macro_avg"] = {
            "precision": float(np.mean(precision)),
            "recall": float(np.mean(recall)),
            "f1": float(np.mean(f1))
        }
        
        # Save metrics if path provided
        if output_metrics_path:
            output_file = Path(output_metrics_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(metrics, f, indent=2)
        
        return metrics
    
    def _load_system_output(self, path: str) -> Dict[str, Dict[str, Any]]:
        """Load system output and extract labels plus confidence values when present."""
        output_file = Path(path)
        if not output_file.exists():
            raise FileNotFoundError(f"System output file not found: {path}")
        
        with open(output_file, 'r') as f:
            data = json.load(f)
        
        # Extract labels from system output
        labels = {}
        confidences = {}
        
        if "requirements" in data:
            for req_data in data["requirements"]:
                req_id = req_data.get("requirement", {}).get("req_id", "")
                decision = req_data.get("decision", {})
                label = decision.get("label", "not_addressed")
                labels[req_id] = label
                confidence = decision.get("confidence")
                if confidence is not None:
                    confidences[req_id] = float(confidence)
        elif isinstance(data, dict):
            # Assume it's a flat dict of requirement_id -> label
            labels = data
        
        return {
            "labels": labels,
            "confidences": confidences,
        }
    
    def _build_confusion_matrix(self, y_true: List[str], y_pred: List[str]) -> Dict[str, Dict[str, int]]:
        """Build confusion matrix."""
        labels = sorted(set(y_true + y_pred))
        matrix = {label: {label2: 0 for label2 in labels} for label in labels}
        
        for true_label, pred_label in zip(y_true, y_pred):
            matrix[true_label][pred_label] = matrix[true_label].get(pred_label, 0) + 1
        
        return matrix
    
    def _calculate_calibration(
        self,
        requirement_ids: List[str],
        y_true: List[str],
        y_pred: List[str],
        confidence_by_requirement: Dict[str, float],
    ) -> Dict[str, Any]:
        """Calculate confidence calibration when confidence scores are available."""
        bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        scored_items = []

        for req_id, true_label, pred_label in zip(requirement_ids, y_true, y_pred):
            if req_id in confidence_by_requirement:
                scored_items.append({
                    "requirement_id": req_id,
                    "confidence": confidence_by_requirement[req_id],
                    "correct": float(true_label == pred_label),
                })

        if not scored_items:
            return {
                "available": False,
                "expected_calibration_error": None,
                "reason": "No confidence scores found in the system output.",
                "bins": [],
            }

        calibration_bins = []
        total_items = len(scored_items)
        expected_calibration_error = 0.0

        for start, end in zip(bins[:-1], bins[1:]):
            if end == 1.0:
                items = [item for item in scored_items if start <= item["confidence"] <= end]
            else:
                items = [item for item in scored_items if start <= item["confidence"] < end]

            if not items:
                calibration_bins.append({
                    "range": [start, end],
                    "count": 0,
                    "avg_confidence": None,
                    "accuracy": None,
                })
                continue

            avg_confidence = float(np.mean([item["confidence"] for item in items]))
            accuracy = float(np.mean([item["correct"] for item in items]))
            weight = len(items) / total_items
            expected_calibration_error += abs(accuracy - avg_confidence) * weight

            calibration_bins.append({
                "range": [start, end],
                "count": len(items),
                "avg_confidence": avg_confidence,
                "accuracy": accuracy,
            })

        return {
            "available": True,
            "expected_calibration_error": float(expected_calibration_error),
            "reason": "",
            "bins": calibration_bins,
        }
    
    def generate_evaluation_report(
        self,
        metrics: Dict[str, Any],
        output_path: str
    ):
        """Generate human-readable evaluation report."""
        report_lines = [
            "# Evaluation Report",
            "",
            "## Overall Metrics",
            "",
            f"- **Accuracy:** {metrics['accuracy']:.3f}",
            f"- **Cohen's Kappa:** {metrics['cohen_kappa']:.3f}",
            "",
            "## Per-Label Metrics",
            ""
        ]
        
        for label, label_metrics in metrics["per_label_metrics"].items():
            report_lines.extend([
                f"### {label.replace('_', ' ').title()}",
                "",
                f"- Precision: {label_metrics['precision']:.3f}",
                f"- Recall: {label_metrics['recall']:.3f}",
                f"- F1 Score: {label_metrics['f1']:.3f}",
                f"- Support: {label_metrics['support']}",
                ""
            ])
        
        report_lines.extend([
            "## Macro Averages",
            "",
            f"- Precision: {metrics['macro_avg']['precision']:.3f}",
            f"- Recall: {metrics['macro_avg']['recall']:.3f}",
            f"- F1 Score: {metrics['macro_avg']['f1']:.3f}",
            ""
        ])
        
        # Confusion matrix
        report_lines.extend([
            "## Confusion Matrix",
            ""
        ])
        
        labels = sorted(metrics["confusion_matrix"].keys())
        report_lines.append("| True \\ Pred | " + " | ".join(labels) + " |")
        report_lines.append("|" + "---|" * (len(labels) + 1))
        
        for true_label in labels:
            row = [true_label]
            for pred_label in labels:
                count = metrics["confusion_matrix"][true_label].get(pred_label, 0)
                row.append(str(count))
            report_lines.append("| " + " | ".join(row) + " |")
        
        # Write report
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write('\n'.join(report_lines))
