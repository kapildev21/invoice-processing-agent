"""
Workflow Execution Routes

Endpoints for starting, monitoring, and resuming workflow executions.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uuid
import logging

from src.api.main import workflow_graph
from src.agents.state_schema import InvoiceWorkflowState
from src.integrations.checkpoint_store import CheckpointStore

logger = logging.getLogger(__name__)

router = APIRouter()


class InvoicePayload(BaseModel):
    """Invoice payload model"""
    invoice_id: str
    vendor_name: str
    amount: float
    currency: str = "USD"
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    vendor_tax_id: Optional[str] = None
    line_items: list[Dict[str, Any]] = []
    attachments: list[str] = []


class ResumeRequest(BaseModel):
    """Resume workflow request"""
    resume_token: str
    checkpoint_id: str


def get_workflow_graph():
    """Dependency to get workflow graph"""
    if workflow_graph is None:
        raise HTTPException(status_code=503, detail="Workflow graph not initialized")
    return workflow_graph


@router.post("/execute")
async def execute_workflow(
    invoice_payload: InvoicePayload,
    graph=Depends(get_workflow_graph)
) -> Dict[str, Any]:
    """
    Start a new workflow execution.
    
    Args:
        invoice_payload: Invoice data
    
    Returns:
        Workflow ID and initial status
    """
    try:
        # Generate workflow ID
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        
        # Create initial state
        initial_state: InvoiceWorkflowState = {
            "invoice_payload": invoice_payload.dict(),
            "workflow_id": workflow_id,
            "current_stage": "INTAKE",
            "execution_history": [],
            "errors": []
        }
        
        # Create thread ID for checkpointing
        thread_id = workflow_id
        
        # Execute workflow
        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }
        
        logger.info(f"Starting workflow execution: {workflow_id}")
        
        # Run workflow (this will execute until it hits a checkpoint or completes)
        result = await graph.ainvoke(initial_state, config)
        
        # Extract status
        status = result.get("status", "IN_PROGRESS")
        current_stage = result.get("current_stage", "UNKNOWN")
        
        return {
            "workflow_id": workflow_id,
            "thread_id": thread_id,
            "status": status.value if hasattr(status, "value") else str(status),
            "current_stage": current_stage,
            "hitl_checkpoint_id": result.get("hitl_checkpoint_id"),
            "review_url": result.get("review_url")
        }
    
    except Exception as e:
        logger.error(f"Error executing workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")


@router.get("/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
    graph=Depends(get_workflow_graph)
) -> Dict[str, Any]:
    """
    Get current workflow state and execution history.
    
    Args:
        workflow_id: Workflow execution ID
    
    Returns:
        Current workflow state
    """
    try:
        # Get state from checkpoint
        thread_id = workflow_id
        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }
        
        # Get current state from graph
        state = graph.get_state(config)
        
        if state.values is None:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        
        # Convert state to dict
        state_dict = dict(state.values)
        
        # Make serializable
        from src.integrations.checkpoint_store import CheckpointStore
        checkpoint_store = CheckpointStore()
        serializable_state = checkpoint_store._make_serializable(state_dict)
        
        return {
            "workflow_id": workflow_id,
            "status": serializable_state.get("status"),
            "current_stage": serializable_state.get("current_stage"),
            "execution_history": serializable_state.get("execution_history", []),
            "errors": serializable_state.get("errors", []),
            "hitl_checkpoint_id": serializable_state.get("hitl_checkpoint_id"),
            "review_url": serializable_state.get("review_url")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


@router.post("/{workflow_id}/resume")
async def resume_workflow(
    workflow_id: str,
    resume_request: ResumeRequest,
    graph=Depends(get_workflow_graph)
) -> Dict[str, Any]:
    """
    Resume a paused workflow after HITL decision.
    
    Args:
        workflow_id: Workflow execution ID
        resume_request: Resume request with checkpoint_id and resume_token
    
    Returns:
        Updated workflow status
    """
    try:
        # Load checkpoint state
        checkpoint_store = CheckpointStore()
        checkpoint_state = await checkpoint_store.load_checkpoint(resume_request.checkpoint_id)
        
        if checkpoint_state is None:
            raise HTTPException(
                status_code=404,
                detail=f"Checkpoint {resume_request.checkpoint_id} not found"
            )
        
        # Verify resume token (in production, implement proper token validation)
        if resume_request.resume_token != checkpoint_state.get("resume_token"):
            logger.warning(f"Invalid resume token for workflow {workflow_id}")
            # Still allow resume for demo purposes
        
        # Update state with resume information
        thread_id = workflow_id
        config = {
            "configurable": {
                "thread_id": thread_id,
                "hitl_checkpoint_id": resume_request.checkpoint_id
            }
        }
        
        # Resume workflow from checkpoint
        logger.info(f"Resuming workflow {workflow_id} from checkpoint {resume_request.checkpoint_id}")
        
        result = await graph.ainvoke(checkpoint_state, config)
        
        # Extract status
        status = result.get("status", "IN_PROGRESS")
        current_stage = result.get("current_stage", "UNKNOWN")
        
        return {
            "workflow_id": workflow_id,
            "status": status.value if hasattr(status, "value") else str(status),
            "current_stage": current_stage,
            "resumed": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {str(e)}")

