"""
MATCH_TWO_WAY Node - Perform 2-way matching

Mode: Deterministic
Tools: None (pure computation)
"""

import time
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog, MatchResult
from src.config.settings import settings
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def match_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    MATCH_TWO_WAY Node: Perform 2-way matching between invoice, PO, and GRN.
    
    - Computes match score based on:
      * Amount matching (with tolerance)
      * Line item matching
      * Date matching
      * Vendor matching
    - Compares against threshold
    - Returns PASSED or FAILED
    
    Returns:
        State updates with match_score, match_result, and execution log
    """
    start_time = time.time()
    
    try:
        parsed_invoice = state.get("parsed_invoice", {})
        matched_pos = state.get("matched_pos", [])
        matched_grns = state.get("matched_grns", [])
        
        if not parsed_invoice:
            raise ValueError("parsed_invoice is required")
        
        invoice_amount = parsed_invoice.get("amount", 0.0)
        invoice_line_items = parsed_invoice.get("line_items", [])
        invoice_date = parsed_invoice.get("invoice_date", "")
        
        # Initialize match score components
        amount_score = 0.0
        line_item_score = 0.0
        date_score = 0.0
        vendor_score = 1.0  # Vendor already matched in PREPARE
        
        match_details = {
            "invoice_amount": invoice_amount,
            "matched_pos_count": len(matched_pos),
            "matched_grns_count": len(matched_grns)
        }
        
        # Amount matching with tolerance
        if matched_pos:
            po_amounts = [po.get("amount", 0.0) for po in matched_pos]
            total_po_amount = sum(po_amounts)
            
            tolerance_pct = settings.TWO_WAY_TOLERANCE_PCT
            tolerance = invoice_amount * (tolerance_pct / 100.0)
            
            amount_diff = abs(invoice_amount - total_po_amount)
            if amount_diff <= tolerance:
                amount_score = 1.0 - (amount_diff / invoice_amount) if invoice_amount > 0 else 1.0
            else:
                amount_score = max(0.0, 1.0 - (amount_diff / invoice_amount))
            
            match_details["po_total_amount"] = total_po_amount
            match_details["amount_diff"] = amount_diff
            match_details["tolerance"] = tolerance
            match_details["tolerance_pct"] = tolerance_pct
        
        # Line item matching
        if invoice_line_items and matched_pos:
            # Simple line item count matching
            po_line_items = []
            for po in matched_pos:
                po_line_items.extend(po.get("line_items", []))
            
            if len(invoice_line_items) == len(po_line_items):
                line_item_score = 1.0
            elif len(po_line_items) > 0:
                line_item_score = min(len(invoice_line_items), len(po_line_items)) / max(len(invoice_line_items), len(po_line_items))
            
            match_details["invoice_line_items_count"] = len(invoice_line_items)
            match_details["po_line_items_count"] = len(po_line_items)
        
        # Date matching (invoice date should be after PO date)
        if matched_pos and invoice_date:
            # Simple date validation (in production, would parse and compare)
            date_score = 1.0  # Assume valid for demo
            match_details["date_validation"] = "passed"
        
        # Calculate overall match score (weighted average)
        weights = {
            "amount": 0.4,
            "line_items": 0.3,
            "date": 0.1,
            "vendor": 0.2
        }
        
        match_score = (
            amount_score * weights["amount"] +
            line_item_score * weights["line_items"] +
            date_score * weights["date"] +
            vendor_score * weights["vendor"]
        )
        
        # Compare against threshold
        threshold = settings.MATCH_THRESHOLD
        match_result = MatchResult.PASSED if match_score >= threshold else MatchResult.FAILED
        
        match_details["match_score"] = match_score
        match_details["threshold"] = threshold
        match_details["components"] = {
            "amount_score": amount_score,
            "line_item_score": line_item_score,
            "date_score": date_score,
            "vendor_score": vendor_score
        }
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "MATCH_TWO_WAY",
            "timestamp": datetime.utcnow().isoformat(),
            "decision": match_result.value,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        if match_result == MatchResult.PASSED:
            logger.info(f"[MATCH_TWO_WAY] ✓ Match score: {match_score:.2f} (threshold: {threshold})")
            logger.info(f"[MATCH_TWO_WAY] ✓ Result: {match_result.value}")
        else:
            logger.warning(f"[MATCH_TWO_WAY] ✗ Match score: {match_score:.2f} (threshold: {threshold})")
            logger.warning(f"[MATCH_TWO_WAY] ✗ Result: {match_result.value}")
        
        return {
            "match_score": match_score,
            "match_result": match_result,
            "match_details": match_details,
            "tolerance_pct": settings.TWO_WAY_TOLERANCE_PCT,
            "current_stage": "MATCH_TWO_WAY",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"MATCH_TWO_WAY node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "MATCH_TWO_WAY",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED",
            "match_result": MatchResult.FAILED
        }

