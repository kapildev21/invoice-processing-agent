"""
HITL (Human-in-the-Loop) Tests

Tests for checkpoint creation, human review, and resume functionality.
"""

import pytest
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.integrations.checkpoint_store import CheckpointStore
from src.agents.state_schema import HumanDecision, MatchResult
from src.agents.nodes.checkpoint_node import checkpoint_node
from src.agents.nodes.hitl_node import hitl_node
from langchain_core.runnables import RunnableConfig


@pytest.fixture
def checkpoint_store():
    """Checkpoint store instance for testing"""
    return CheckpointStore()


@pytest.fixture
def sample_checkpoint_state():
    """Sample state for checkpoint testing"""
    return {
        "workflow_id": "wf_test_001",
        "invoice_payload": {
            "invoice_id": "INV-TEST-001",
            "vendor_name": "Test Vendor",
            "amount": 15000.0
        },
        "parsed_invoice": {
            "invoice_id": "INV-TEST-001",
            "vendor_name": "Test Vendor",
            "amount": 15000.0
        },
        "match_result": MatchResult.FAILED,
        "match_score": 0.75,
        "match_details": {"threshold": 0.90},
        "execution_history": [],
        "errors": []
    }


@pytest.mark.asyncio
async def test_checkpoint_creation(checkpoint_store, sample_checkpoint_state):
    """Test checkpoint creation"""
    checkpoint_id = checkpoint_store.generate_checkpoint_id()
    
    await checkpoint_store.save_checkpoint(
        checkpoint_id,
        sample_checkpoint_state,
        sample_checkpoint_state["workflow_id"]
    )
    
    # Verify checkpoint was saved
    loaded_state = await checkpoint_store.load_checkpoint(checkpoint_id)
    assert loaded_state is not None
    assert loaded_state["workflow_id"] == sample_checkpoint_state["workflow_id"]


@pytest.mark.asyncio
async def test_review_ticket_creation(checkpoint_store, sample_checkpoint_state):
    """Test review ticket creation"""
    checkpoint_id = checkpoint_store.generate_checkpoint_id()
    
    await checkpoint_store.save_checkpoint(
        checkpoint_id,
        sample_checkpoint_state,
        sample_checkpoint_state["workflow_id"]
    )
    
    review_url = await checkpoint_store.create_review_ticket(
        checkpoint_id,
        sample_checkpoint_state["parsed_invoice"],
        "Match failed for testing"
    )
    
    assert review_url is not None
    assert "checkpoint" in review_url.lower() or "review" in review_url.lower()
    
    # Verify ticket is in pending reviews
    pending = await checkpoint_store.list_pending_reviews()
    assert any(ticket["checkpoint_id"] == checkpoint_id for ticket in pending)


@pytest.mark.asyncio
async def test_review_decision_update(checkpoint_store, sample_checkpoint_state):
    """Test updating review decision"""
    checkpoint_id = checkpoint_store.generate_checkpoint_id()
    
    await checkpoint_store.save_checkpoint(
        checkpoint_id,
        sample_checkpoint_state,
        sample_checkpoint_state["workflow_id"]
    )
    
    await checkpoint_store.create_review_ticket(
        checkpoint_id,
        sample_checkpoint_state["parsed_invoice"],
        "Match failed"
    )
    
    # Update with decision
    success = await checkpoint_store.update_review_decision(
        checkpoint_id,
        "ACCEPT",
        "test_reviewer",
        "Test acceptance"
    )
    
    assert success is True
    
    # Verify ticket is no longer pending
    pending = await checkpoint_store.list_pending_reviews()
    assert not any(ticket["checkpoint_id"] == checkpoint_id for ticket in pending)


@pytest.mark.asyncio
async def test_checkpoint_node(sample_checkpoint_state):
    """Test CHECKPOINT_HITL node"""
    config = RunnableConfig()
    
    result = await checkpoint_node(sample_checkpoint_state, config)
    
    assert "checkpoint_id" in result
    assert "review_url" in result
    assert result["status"] == "PAUSED"
    assert result["current_stage"] == "CHECKPOINT_HITL"


@pytest.mark.asyncio
async def test_hitl_node_accept(sample_checkpoint_state):
    """Test HITL_DECISION node with ACCEPT"""
    config = RunnableConfig()
    
    # Set human decision
    sample_checkpoint_state["human_decision"] = HumanDecision.ACCEPT
    sample_checkpoint_state["reviewer_id"] = "test_reviewer"
    sample_checkpoint_state["checkpoint_id"] = "ckpt_test123"
    
    result = await hitl_node(sample_checkpoint_state, config)
    
    assert "resume_token" in result
    assert result["human_decision"] == HumanDecision.ACCEPT
    assert result["current_stage"] == "HITL_DECISION"


@pytest.mark.asyncio
async def test_hitl_node_reject(sample_checkpoint_state):
    """Test HITL_DECISION node with REJECT"""
    config = RunnableConfig()
    
    # Set human decision
    sample_checkpoint_state["human_decision"] = HumanDecision.REJECT
    sample_checkpoint_state["reviewer_id"] = "test_reviewer"
    sample_checkpoint_state["checkpoint_id"] = "ckpt_test123"
    
    result = await hitl_node(sample_checkpoint_state, config)
    
    assert "resume_token" in result
    assert result["human_decision"] == HumanDecision.REJECT
    assert result["current_stage"] == "HITL_DECISION"

