"""
HITL_DECISION Node - Handle human decision and resume workflow

Mode: Non-deterministic (depends on human input)
Tools: CheckpointStore
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog, HumanDecision
from src.integrations.checkpoint_store import CheckpointStore
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def hitl_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    HITL_DECISION Node: Handle human decision and prepare for resume.
    
    This node is called when workflow resumes after human review.
    - Reads human_decision from state (set by API endpoint)
    - Generates resume_token
    - Updates checkpoint store with decision
    - Routes to next stage based on decision
    
    Returns:
        State updates with human_decision, resume_token, and execution log
    """
    start_time = time.time()
    
    try:
        # Get human decision from state (set by API when resuming)
        human_decision = state.get("human_decision")
        
        if not human_decision:
            # If no decision yet, this node shouldn't have been called
            # But if we're here, it means we're resuming from checkpoint
            # In this case, we should wait for decision (but for demo, we'll raise error)
            logger.warning("[HITL_DECISION] No human decision found, cannot proceed")
            raise ValueError("human_decision is required for HITL_DECISION node. Workflow must be resumed with a decision.")
        
        # Validate decision
        if human_decision not in [HumanDecision.ACCEPT, HumanDecision.REJECT]:
            raise ValueError(f"Invalid human decision: {human_decision}")
        
        # Generate resume token
        resume_token = f"resume_{uuid.uuid4().hex[:12]}"
        
        # Update checkpoint store with decision
        hitl_checkpoint_id = state.get("hitl_checkpoint_id")
        reviewer_id = state.get("reviewer_id", "system")
        review_notes = state.get("review_notes")
        
        if hitl_checkpoint_id:
            checkpoint_store = CheckpointStore()
            await checkpoint_store.update_review_decision(
                hitl_checkpoint_id,
                human_decision.value,
                reviewer_id,
                review_notes
            )
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "HITL_DECISION",
            "timestamp": datetime.utcnow().isoformat(),
            "decision": human_decision.value,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[HITL_DECISION] ✓ Decision: {human_decision.value}")
        logger.info(f"[HITL_DECISION] ✓ Resume token: {resume_token}")
        
        # Determine next stage based on decision
        if human_decision == HumanDecision.ACCEPT:
            next_stage = "RECONCILE"
            logger.info(f"[HITL_DECISION] → Next: {next_stage}")
        else:
            next_stage = "COMPLETE"
            logger.info(f"[HITL_DECISION] → Next: {next_stage} (REJECT)")
        
        return {
            "human_decision": human_decision,
            "resume_token": resume_token,
            "review_timestamp": datetime.utcnow(),
            "current_stage": "HITL_DECISION",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"HITL_DECISION node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "HITL_DECISION",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

