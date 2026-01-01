"""
CHECKPOINT_HITL Node - Create checkpoint if match fails

Mode: Deterministic
Tools: CheckpointStore
"""

import time
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog, MatchResult
from src.integrations.checkpoint_store import CheckpointStore
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def checkpoint_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    CHECKPOINT_HITL Node: Create checkpoint if match fails.
    
    CRITICAL: This node pauses the workflow and creates a human review ticket.
    - Generates checkpoint_id
    - Persists full state to database
    - Creates review ticket in human_review_queue
    - Returns checkpoint_id and review_url
    - Workflow pauses here (no outgoing edge until HITL decision)
    
    Returns:
        State updates with hitl_checkpoint_id, review_url, and execution log
    """
    start_time = time.time()
    
    try:
        match_result = state.get("match_result")
        
        # Only create checkpoint if match failed
        if match_result != MatchResult.FAILED:
            logger.info(f"[CHECKPOINT_HITL] Match passed, skipping checkpoint")
            return {
                "current_stage": "CHECKPOINT_HITL",
                "updated_at": datetime.utcnow()
            }
        
        # Initialize checkpoint store
        checkpoint_store = CheckpointStore()
        
        # Generate checkpoint ID
        checkpoint_id = checkpoint_store.generate_checkpoint_id()
        
        # Persist full state to database
        workflow_id = state.get("workflow_id")
        await checkpoint_store.save_checkpoint(checkpoint_id, state, workflow_id)
        
        # Prepare invoice data for review ticket
        parsed_invoice = state.get("parsed_invoice", {})
        invoice_data = {
            "invoice_id": parsed_invoice.get("invoice_id") or state.get("raw_id"),
            "vendor_name": state.get("vendor_normalized_name") or parsed_invoice.get("vendor_name"),
            "amount": parsed_invoice.get("amount", 0.0),
            "match_score": state.get("match_score"),
            "match_details": state.get("match_details", {})
        }
        
        # Create review ticket
        reason_for_hold = (
            f"2-way match failed. Match score: {state.get('match_score', 0):.2f} "
            f"(threshold: {state.get('match_details', {}).get('threshold', 0.90)})"
        )
        
        review_url = await checkpoint_store.create_review_ticket(
            checkpoint_id,
            invoice_data,
            reason_for_hold
        )
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "CHECKPOINT_HITL",
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[CHECKPOINT_HITL] ✓ Checkpoint ID: {checkpoint_id}")
        logger.info(f"[CHECKPOINT_HITL] ✓ Review URL: {review_url}")
        logger.info(f"[CHECKPOINT_HITL] ⏸️  WORKFLOW PAUSED - Awaiting human review")
        
        return {
            "hitl_checkpoint_id": checkpoint_id,  # Use hitl_checkpoint_id to avoid LangGraph reserved name
            "review_url": review_url,
            "paused_reason": reason_for_hold,
            "current_stage": "CHECKPOINT_HITL",
            "status": "PAUSED",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"CHECKPOINT_HITL node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "CHECKPOINT_HITL",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

