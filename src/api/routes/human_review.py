"""
Human Review Routes

Endpoints for human-in-the-loop review and decision making.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uuid
import logging
from datetime import datetime

from src.api.main import workflow_graph
from src.integrations.checkpoint_store import CheckpointStore
from src.agents.state_schema import HumanDecision

logger = logging.getLogger(__name__)

router = APIRouter()


class DecisionRequest(BaseModel):
    """Human review decision request"""
    checkpoint_id: str
    decision: str  # "ACCEPT" or "REJECT"
    reviewer_id: str
    review_notes: Optional[str] = None


def get_workflow_graph():
    """Dependency to get workflow graph"""
    if workflow_graph is None:
        raise HTTPException(status_code=503, detail="Workflow graph not initialized")
    return workflow_graph


@router.get("/pending")
async def list_pending_reviews() -> List[Dict[str, Any]]:
    """
    Return all invoices waiting for human review.
    
    Returns:
        List of pending review tickets
    """
    try:
        checkpoint_store = CheckpointStore()
        pending_reviews = await checkpoint_store.list_pending_reviews()
        
        return pending_reviews
    
    except Exception as e:
        logger.error(f"Error listing pending reviews: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list pending reviews: {str(e)}")


@router.get("/{checkpoint_id}")
async def get_review_details(checkpoint_id: str) -> Dict[str, Any]:
    """
    Get details for a specific review checkpoint.
    
    Args:
        checkpoint_id: Checkpoint identifier
    
    Returns:
        Review details including invoice data and match information
    """
    try:
        checkpoint_store = CheckpointStore()
        checkpoint_state = await checkpoint_store.load_checkpoint(checkpoint_id)
        
        if checkpoint_state is None:
            raise HTTPException(
                status_code=404,
                detail=f"Checkpoint {checkpoint_id} not found"
            )
        
        # Extract relevant information for review
        parsed_invoice = checkpoint_state.get("parsed_invoice", {})
        match_details = checkpoint_state.get("match_details", {})
        
        return {
            "hitl_checkpoint_id": checkpoint_id,
            "invoice_id": parsed_invoice.get("invoice_id") or checkpoint_state.get("raw_id"),
            "vendor_name": checkpoint_state.get("vendor_normalized_name") or parsed_invoice.get("vendor_name"),
            "amount": parsed_invoice.get("amount", 0.0),
            "currency": parsed_invoice.get("currency", "USD"),
            "invoice_date": parsed_invoice.get("invoice_date"),
            "match_score": checkpoint_state.get("match_score"),
            "match_details": match_details,
            "reason_for_hold": checkpoint_state.get("paused_reason"),
            "review_url": checkpoint_state.get("review_url"),
            "created_at": checkpoint_state.get("created_at")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting review details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get review details: {str(e)}")


@router.post("/decision")
async def submit_decision(
    decision_request: DecisionRequest,
    graph=Depends(get_workflow_graph)
) -> Dict[str, Any]:
    """
    Accept human decision (ACCEPT/REJECT) and resume workflow.
    
    Args:
        decision_request: Decision request with checkpoint_id, decision, reviewer_id
    
    Returns:
        Resume token and next stage
    """
    try:
        # Validate decision
        if decision_request.decision.upper() not in ["ACCEPT", "REJECT"]:
            raise HTTPException(
                status_code=400,
                detail="Decision must be 'ACCEPT' or 'REJECT'"
            )
        
        human_decision = HumanDecision[decision_request.decision.upper()]
        
        # Load checkpoint state
        checkpoint_store = CheckpointStore()
        checkpoint_state = await checkpoint_store.load_checkpoint(decision_request.checkpoint_id)
        
        if checkpoint_state is None:
            raise HTTPException(
                status_code=404,
                detail=f"Checkpoint {decision_request.checkpoint_id} not found"
            )
        
        # Update state with human decision
        workflow_id = checkpoint_state.get("workflow_id")
        resume_token = f"resume_{uuid.uuid4().hex[:12]}"
        
        updated_state = {
            **checkpoint_state,
            "human_decision": human_decision,
            "reviewer_id": decision_request.reviewer_id,
            "review_notes": decision_request.review_notes,
            "review_timestamp": datetime.utcnow(),
            "resume_token": resume_token
        }
        
        # Update checkpoint store with decision
        await checkpoint_store.update_review_decision(
            decision_request.checkpoint_id,
            human_decision.value,
            decision_request.reviewer_id,
            decision_request.review_notes
        )
        
        # Resume workflow by invoking graph with updated state
        thread_id = workflow_id or decision_request.checkpoint_id
        config = {
            "configurable": {
                "thread_id": thread_id,
                "hitl_checkpoint_id": decision_request.checkpoint_id
            }
        }
        
        logger.info(
            f"Resuming workflow from checkpoint {decision_request.checkpoint_id} "
            f"with decision: {human_decision.value}"
        )
        
        # Invoke graph with updated state
        result = await graph.ainvoke(updated_state, config)
        
        # Determine next stage
        if human_decision == HumanDecision.ACCEPT:
            next_stage = "RECONCILE"
        else:
            next_stage = "COMPLETE"
        
        return {
            "hitl_checkpoint_id": decision_request.checkpoint_id,
            "decision": human_decision.value,
            "resume_token": resume_token,
            "next_stage": next_stage,
            "workflow_id": workflow_id,
            "status": result.get("status"),
            "current_stage": result.get("current_stage")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting decision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit decision: {str(e)}")

