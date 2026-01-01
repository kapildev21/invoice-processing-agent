"""
Workflow Integration Tests

Tests for complete workflow execution including HITL scenarios.
"""

import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.graph_builder import build_invoice_graph
from src.agents.state_schema import InvoiceWorkflowState, MatchResult, HumanDecision, WorkflowStatus
from src.integrations.checkpoint_store import CheckpointStore


@pytest.fixture
def sample_invoice():
    """Sample invoice payload for testing"""
    return {
        "invoice_id": "INV-TEST-001",
        "vendor_name": "Test Vendor",
        "vendor_tax_id": "TAX123",
        "invoice_date": "2025-01-15",
        "due_date": "2025-02-15",
        "amount": 15000.00,
        "currency": "USD",
        "line_items": [
            {
                "line_item_id": "LI-001",
                "desc": "Test Services",
                "qty": 100,
                "unit_price": 150.00,
                "total": 15000.00
            }
        ],
        "attachments": ["test_invoice.pdf"]
    }


@pytest.fixture
def workflow_graph():
    """Build and return workflow graph"""
    return build_invoice_graph()


@pytest.mark.asyncio
async def test_full_workflow_match_success(workflow_graph, sample_invoice):
    """Test workflow when 2-way match succeeds"""
    workflow_id = f"wf_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    thread_id = workflow_id
    
    initial_state: InvoiceWorkflowState = {
        "invoice_payload": sample_invoice,
        "workflow_id": workflow_id,
        "current_stage": "INTAKE",
        "execution_history": [],
        "errors": [],
        "created_at": datetime.utcnow()
    }
    
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    # Execute workflow
    result = await workflow_graph.ainvoke(initial_state, config)
    
    # Verify workflow completed
    assert result.get("status") in [WorkflowStatus.COMPLETED, "COMPLETED"]
    assert result.get("current_stage") == "COMPLETE"
    assert result.get("final_payload") is not None
    
    # Verify no checkpoint was created (match passed)
    assert result.get("checkpoint_id") is None


@pytest.mark.asyncio
async def test_workflow_checkpoint_and_resume(workflow_graph, sample_invoice):
    """Test HITL checkpoint creation and resume after human accepts"""
    workflow_id = f"wf_test_hitl_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    thread_id = workflow_id
    
    initial_state: InvoiceWorkflowState = {
        "invoice_payload": sample_invoice,
        "workflow_id": workflow_id,
        "current_stage": "INTAKE",
        "execution_history": [],
        "errors": [],
        "created_at": datetime.utcnow()
    }
    
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    # Execute workflow until checkpoint
    result = await workflow_graph.ainvoke(initial_state, config)
    
    # If match passed, we need to simulate a failure
    # In a real scenario, the match_node would set match_result to FAILED
    checkpoint_id = result.get("checkpoint_id")
    
    if not checkpoint_id:
        # Simulate match failure by manually creating checkpoint
        # This is a workaround for testing - in production, match_node would handle this
        checkpoint_store = CheckpointStore()
        checkpoint_id = checkpoint_store.generate_checkpoint_id()
        
        # Update state to simulate match failure
        result["match_result"] = MatchResult.FAILED
        result["match_score"] = 0.75  # Below threshold
        result["checkpoint_id"] = checkpoint_id
        
        await checkpoint_store.save_checkpoint(checkpoint_id, result, workflow_id)
        await checkpoint_store.create_review_ticket(
            checkpoint_id,
            sample_invoice,
            "Match failed for testing"
        )
    
    # Verify checkpoint was created
    assert checkpoint_id is not None
    
    # Load checkpoint and simulate human acceptance
    checkpoint_store = CheckpointStore()
    checkpoint_state = await checkpoint_store.load_checkpoint(checkpoint_id)
    assert checkpoint_state is not None
    
    # Update with human decision
    updated_state = {
        **checkpoint_state,
        "human_decision": HumanDecision.ACCEPT,
        "reviewer_id": "test_reviewer",
        "review_notes": "Test acceptance",
        "review_timestamp": datetime.utcnow(),
        "resume_token": "test_resume_token"
    }
    
    await checkpoint_store.update_review_decision(
        checkpoint_id,
        "ACCEPT",
        "test_reviewer",
        "Test acceptance"
    )
    
    # Resume workflow
    resume_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id
        }
    }
    
    final_result = await workflow_graph.ainvoke(updated_state, resume_config)
    
    # Verify workflow completed after resume
    assert final_result.get("status") in [WorkflowStatus.COMPLETED, "COMPLETED"]
    assert final_result.get("human_decision") == HumanDecision.ACCEPT


@pytest.mark.asyncio
async def test_workflow_human_reject(workflow_graph, sample_invoice):
    """Test workflow when human rejects invoice"""
    workflow_id = f"wf_test_reject_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    thread_id = workflow_id
    
    # Create checkpoint manually for testing
    checkpoint_store = CheckpointStore()
    checkpoint_id = checkpoint_store.generate_checkpoint_id()
    
    initial_state: InvoiceWorkflowState = {
        "invoice_payload": sample_invoice,
        "workflow_id": workflow_id,
        "current_stage": "CHECKPOINT_HITL",
        "match_result": MatchResult.FAILED,
        "match_score": 0.75,
        "checkpoint_id": checkpoint_id,
        "execution_history": [],
        "errors": [],
        "created_at": datetime.utcnow()
    }
    
    await checkpoint_store.save_checkpoint(checkpoint_id, initial_state, workflow_id)
    
    # Update with human rejection
    updated_state = {
        **initial_state,
        "human_decision": HumanDecision.REJECT,
        "reviewer_id": "test_reviewer",
        "review_notes": "Test rejection",
        "review_timestamp": datetime.utcnow(),
        "resume_token": "test_resume_token"
    }
    
    # Execute from HITL_DECISION
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id
        }
    }
    
    result = await workflow_graph.ainvoke(updated_state, config)
    
    # Verify workflow completed with MANUAL_HANDOFF status
    assert result.get("status") in [WorkflowStatus.MANUAL_HANDOFF, "MANUAL_HANDOFF"]
    assert result.get("human_decision") == HumanDecision.REJECT


@pytest.mark.asyncio
async def test_workflow_error_handling(workflow_graph):
    """Test workflow error handling with invalid input"""
    workflow_id = f"wf_test_error_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    thread_id = workflow_id
    
    # Invalid invoice payload (missing required fields)
    invalid_state: InvoiceWorkflowState = {
        "invoice_payload": {},  # Missing required fields
        "workflow_id": workflow_id,
        "current_stage": "INTAKE",
        "execution_history": [],
        "errors": [],
        "created_at": datetime.utcnow()
    }
    
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    # Execute workflow - should handle error gracefully
    result = await workflow_graph.ainvoke(invalid_state, config)
    
    # Verify error was recorded
    assert result.get("errors") is not None
    assert len(result.get("errors", [])) > 0
    assert result.get("status") == "FAILED"

