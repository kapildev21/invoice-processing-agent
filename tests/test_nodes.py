"""
Node Unit Tests

Tests for individual workflow nodes.
"""

import pytest
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.nodes.intake_node import intake_node
from src.agents.nodes.understand_node import understand_node
from src.agents.nodes.prepare_node import prepare_node
from src.agents.nodes.match_node import match_node
from src.agents.nodes.reconcile_node import reconcile_node
from src.agents.nodes.approve_node import approve_node
from src.agents.state_schema import InvoiceWorkflowState, MatchResult, ApprovalStatus
from langchain_core.runnables import RunnableConfig


@pytest.fixture
def sample_state():
    """Sample workflow state for testing"""
    return {
        "invoice_payload": {
            "invoice_id": "INV-TEST-001",
            "vendor_name": "Test Vendor",
            "amount": 10000.0,
            "currency": "USD"
        },
        "workflow_id": "wf_test_001",
        "current_stage": "INTAKE",
        "execution_history": [],
        "errors": [],
        "created_at": datetime.utcnow()
    }


@pytest.fixture
def config():
    """Runnable config for testing"""
    return RunnableConfig()


@pytest.mark.asyncio
async def test_intake_node(sample_state, config):
    """Test INTAKE node"""
    result = await intake_node(sample_state, config)
    
    assert "raw_id" in result
    assert "ingest_ts" in result
    assert result["raw_id"].startswith("raw_")
    assert result["current_stage"] == "INTAKE"


@pytest.mark.asyncio
async def test_intake_node_missing_fields(sample_state, config):
    """Test INTAKE node with missing required fields"""
    invalid_state = {
        "invoice_payload": {},  # Missing required fields
        "workflow_id": "wf_test",
        "execution_history": [],
        "errors": []
    }
    
    result = await intake_node(invalid_state, config)
    
    assert "errors" in result
    assert len(result["errors"]) > 0
    assert result["status"] == "FAILED"


@pytest.mark.asyncio
async def test_understand_node(sample_state, config):
    """Test UNDERSTAND node"""
    # Set up state after INTAKE
    sample_state["raw_id"] = "raw_test123"
    sample_state["ingest_ts"] = datetime.utcnow()
    
    result = await understand_node(sample_state, config)
    
    assert "parsed_invoice" in result or "ocr_text" in result
    assert result["current_stage"] == "UNDERSTAND"


@pytest.mark.asyncio
async def test_prepare_node(sample_state, config):
    """Test PREPARE node"""
    # Set up state after UNDERSTAND
    sample_state["parsed_invoice"] = {
        "invoice_id": "INV-TEST-001",
        "vendor_name": "Test Vendor",
        "amount": 10000.0
    }
    sample_state["ocr_text"] = "Mock OCR text"
    
    result = await prepare_node(sample_state, config)
    
    assert "vendor_profile" in result or "vendor_normalized_name" in result
    assert result["current_stage"] == "PREPARE"


@pytest.mark.asyncio
async def test_match_node(sample_state, config):
    """Test MATCH_TWO_WAY node"""
    # Set up state with matched POs
    sample_state["matched_pos"] = [
        {
            "po_id": "PO-001",
            "amount": 10000.0,
            "vendor": "Test Vendor"
        }
    ]
    sample_state["parsed_invoice"] = {
        "invoice_id": "INV-TEST-001",
        "vendor_name": "Test Vendor",
        "amount": 10000.0
    }
    
    result = await match_node(sample_state, config)
    
    assert "match_score" in result
    assert "match_result" in result
    assert result["current_stage"] == "MATCH_TWO_WAY"
    assert isinstance(result["match_score"], (int, float))


@pytest.mark.asyncio
async def test_reconcile_node(sample_state, config):
    """Test RECONCILE node"""
    # Set up state with parsed invoice
    sample_state["parsed_invoice"] = {
        "invoice_id": "INV-TEST-001",
        "amount": 10000.0,
        "currency": "USD",
        "line_items": [
            {
                "line_item_id": "LI-001",
                "desc": "Test Services",
                "total": 10000.0
            }
        ]
    }
    
    result = await reconcile_node(sample_state, config)
    
    assert "accounting_entries" in result
    assert "gl_accounts" in result
    assert len(result["accounting_entries"]) > 0
    assert result["current_stage"] == "RECONCILE"


@pytest.mark.asyncio
async def test_approve_node(sample_state, config):
    """Test APPROVE node"""
    # Set up state with parsed invoice and low risk
    sample_state["parsed_invoice"] = {
        "invoice_id": "INV-TEST-001",
        "amount": 5000.0  # Under threshold
    }
    sample_state["risk_score"] = 0.15  # Low risk
    sample_state["flags"] = {"high_risk": False}
    
    result = await approve_node(sample_state, config)
    
    assert "approval_status" in result
    assert "approval_policy_applied" in result
    assert result["current_stage"] == "APPROVE"
    # Should be auto-approved for low amount
    assert result["approval_status"] in [ApprovalStatus.AUTO_APPROVED, "AUTO_APPROVED"]

