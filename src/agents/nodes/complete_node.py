"""
COMPLETE Node - Finalize and audit workflow

Mode: Deterministic
Tools: None (finalization)
"""

import time
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog, WorkflowStatus, HumanDecision
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def complete_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    COMPLETE Node: Finalize workflow and create audit payload.
    
    - Determines final workflow status
    - Builds final payload with all relevant data
    - Calculates execution time
    - Logs completion
    
    Returns:
        State updates with final_payload, status, and execution log
    """
    start_time = time.time()
    
    try:
        # Determine final status
        human_decision = state.get("human_decision")
        posted = state.get("posted", False)
        errors = state.get("errors", [])
        
        if errors:
            final_status = WorkflowStatus.FAILED
        elif human_decision == HumanDecision.REJECT:
            final_status = WorkflowStatus.MANUAL_HANDOFF
        elif posted:
            final_status = WorkflowStatus.COMPLETED
        else:
            final_status = WorkflowStatus.COMPLETED  # Even if not posted, workflow completed
        
        # Calculate execution time
        created_at = state.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                try:
                    from dateutil.parser import parse
                    created_at = parse(created_at)
                except ImportError:
                    # Fallback if dateutil not available
                    try:
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except:
                        created_at = datetime.utcnow()
            if isinstance(created_at, datetime):
                execution_time = (datetime.utcnow() - created_at).total_seconds()
            else:
                execution_time = 0.0
        else:
            execution_time = 0.0
        
        # Build final payload
        parsed_invoice = state.get("parsed_invoice", {})
        final_payload = {
            "invoice_id": parsed_invoice.get("invoice_id") or state.get("raw_id", "UNKNOWN"),
            "status": final_status.value,
            "vendor": state.get("vendor_normalized_name") or parsed_invoice.get("vendor_name", "Unknown"),
            "amount": parsed_invoice.get("amount", 0.0),
            "currency": parsed_invoice.get("currency", "USD"),
            "erp_txn_id": state.get("erp_txn_id"),
            "approval_status": state.get("approval_status", {}).value if state.get("approval_status") else None,
            "human_reviewed": human_decision is not None,
            "hitl_checkpoint_id": state.get("hitl_checkpoint_id"),
            "execution_time_seconds": execution_time,
            "workflow_id": state.get("workflow_id"),
            "execution_history": [
                {
                    "stage": log.get("stage"),
                    "timestamp": log.get("timestamp"),
                    "tool_selected": log.get("tool_selected"),
                    "decision": log.get("decision"),
                    "duration_ms": log.get("duration_ms")
                }
                for log in state.get("execution_history", [])
            ],
            "completed_at": datetime.utcnow().isoformat()
        }
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "COMPLETE",
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[COMPLETE] ✓ Status: {final_status.value}")
        logger.info(f"[COMPLETE] ✓ Execution time: {execution_time:.2f}s")
        logger.info(f"[COMPLETE] ✓ Audit log persisted")
        
        return {
            "final_payload": final_payload,
            "status": final_status,
            "completion_timestamp": datetime.utcnow(),
            "execution_time_seconds": execution_time,
            "current_stage": "COMPLETE",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"COMPLETE node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "COMPLETE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": WorkflowStatus.FAILED,
            "final_payload": {
                "status": WorkflowStatus.FAILED.value,
                "error": str(e)
            }
        }

