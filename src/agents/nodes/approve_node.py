"""
APPROVE Node - Apply approval policies

Mode: Deterministic
Tools: None (policy-based)
"""

import time
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog, ApprovalStatus
from src.config.settings import settings
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def approve_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    APPROVE Node: Apply approval policies to invoice.
    
    - Checks invoice amount against thresholds
    - Applies vendor-specific policies
    - Checks risk flags
    - Determines if auto-approval is allowed
    
    Returns:
        State updates with approval_status and execution log
    """
    start_time = time.time()
    
    try:
        # Extract invoice data
        parsed_invoice = state.get("parsed_invoice", {})
        vendor_profile = state.get("vendor_profile", {})
        flags = state.get("flags", {})
        risk_score = state.get("risk_score", 1.0)
        
        if not parsed_invoice:
            raise ValueError("parsed_invoice is required for approval")
        
        invoice_amount = parsed_invoice.get("amount", 0.0)
        invoice_id = parsed_invoice.get("invoice_id") or state.get("raw_id", "UNKNOWN")
        
        # Apply approval policies
        approval_status, policy_applied = _apply_approval_policy(
            invoice_amount,
            risk_score,
            flags,
            vendor_profile
        )
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "APPROVE",
            "timestamp": datetime.utcnow().isoformat(),
            "decision": approval_status.value,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        if approval_status == ApprovalStatus.AUTO_APPROVED:
            logger.info(f"[APPROVE] ✓ Auto-approved (policy: {policy_applied})")
        elif approval_status == ApprovalStatus.PENDING_APPROVAL:
            logger.info(f"[APPROVE] ⚠️  Requires manual approval (policy: {policy_applied})")
        else:
            logger.info(f"[APPROVE] ✓ Status: {approval_status.value} (policy: {policy_applied})")
        
        return {
            "approval_status": approval_status,
            "approval_policy_applied": policy_applied,
            "approval_timestamp": datetime.utcnow(),
            "current_stage": "APPROVE",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"APPROVE node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "APPROVE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }


def _apply_approval_policy(
    invoice_amount: float,
    risk_score: float,
    flags: Dict[str, Any],
    vendor_profile: Dict[str, Any]
) -> tuple[ApprovalStatus, str]:
    """
    Apply approval policy based on invoice characteristics.
    
    Returns:
        Tuple of (approval_status, policy_name)
    """
    # Policy 1: High risk score requires manual approval
    if risk_score > 0.7:
        return ApprovalStatus.PENDING_APPROVAL, "HIGH_RISK_POLICY"
    
    # Policy 2: High risk flags require manual approval
    if flags.get("high_risk", False):
        return ApprovalStatus.PENDING_APPROVAL, "HIGH_RISK_FLAG_POLICY"
    
    # Policy 3: New vendor requires manual approval for amounts > $5K
    if flags.get("new_vendor", False) and invoice_amount > 5000.0:
        return ApprovalStatus.PENDING_APPROVAL, "NEW_VENDOR_POLICY"
    
    # Policy 4: Amount threshold - auto-approve if under threshold
    # Default threshold is $20K, but can be configured
    auto_approval_threshold = getattr(settings, "AUTO_APPROVAL_THRESHOLD", 20000.0)
    
    if invoice_amount <= auto_approval_threshold:
        return ApprovalStatus.AUTO_APPROVED, "AMOUNT_THRESHOLD_POLICY"
    
    # Policy 5: Large amounts require manual approval
    if invoice_amount > auto_approval_threshold:
        return ApprovalStatus.PENDING_APPROVAL, "LARGE_AMOUNT_POLICY"
    
    # Default: auto-approve
    return ApprovalStatus.AUTO_APPROVED, "DEFAULT_POLICY"

