"""
RECONCILE Node - Build accounting entries

Mode: Deterministic
Tools: None (pure computation)
"""

import time
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def reconcile_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    RECONCILE Node: Build accounting entries from invoice data.
    
    - Extracts invoice line items
    - Creates journal entries (debit/credit)
    - Maps to GL accounts
    - Calculates tax and totals
    
    Returns:
        State updates with accounting_entries and execution log
    """
    start_time = time.time()
    
    try:
        # Extract invoice data
        parsed_invoice = state.get("parsed_invoice", {})
        vendor_profile = state.get("vendor_profile", {})
        
        if not parsed_invoice:
            raise ValueError("parsed_invoice is required for reconciliation")
        
        invoice_id = parsed_invoice.get("invoice_id") or state.get("raw_id", "UNKNOWN")
        amount = parsed_invoice.get("amount", 0.0)
        currency = parsed_invoice.get("currency", "USD")
        line_items = parsed_invoice.get("line_items", [])
        
        # Build accounting entries
        accounting_entries: List[Dict[str, Any]] = []
        gl_accounts: List[str] = []
        
        # Main invoice entry: Debit Accounts Payable, Credit Expense/Asset
        for line_item in line_items:
            item_amount = line_item.get("total", 0.0)
            description = line_item.get("desc", "Invoice line item")
            
            # Determine GL account based on line item description
            # In production, this would use a mapping service
            gl_account = _determine_gl_account(description, vendor_profile)
            
            if gl_account not in gl_accounts:
                gl_accounts.append(gl_account)
            
            # Debit entry (expense/asset)
            accounting_entries.append({
                "entry_id": f"ENTRY-{len(accounting_entries) + 1}",
                "account": gl_account,
                "debit": item_amount,
                "credit": 0.0,
                "description": description,
                "invoice_id": invoice_id,
                "line_item_id": line_item.get("line_item_id")
            })
        
        # Credit entry: Accounts Payable
        accounts_payable_account = "2000-AP"  # Standard AP account
        if accounts_payable_account not in gl_accounts:
            gl_accounts.append(accounts_payable_account)
        
        accounting_entries.append({
            "entry_id": f"ENTRY-{len(accounting_entries) + 1}",
            "account": accounts_payable_account,
            "debit": 0.0,
            "credit": amount,
            "description": f"Invoice {invoice_id} - Accounts Payable",
            "invoice_id": invoice_id
        })
        
        # Calculate totals
        total_debits = sum(entry.get("debit", 0.0) for entry in accounting_entries)
        total_credits = sum(entry.get("credit", 0.0) for entry in accounting_entries)
        
        # Verify double-entry accounting
        if abs(total_debits - total_credits) > 0.01:
            logger.warning(
                f"[RECONCILE] Debits ({total_debits}) != Credits ({total_credits}), "
                f"difference: {abs(total_debits - total_credits)}"
            )
        
        reconciliation_summary = {
            "total_debits": total_debits,
            "total_credits": total_credits,
            "entry_count": len(accounting_entries),
            "gl_accounts_used": gl_accounts,
            "currency": currency,
            "balanced": abs(total_debits - total_credits) < 0.01
        }
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "RECONCILE",
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[RECONCILE] ✓ Created {len(accounting_entries)} journal entries")
        logger.info(f"[RECONCILE] ✓ GL accounts: {', '.join(gl_accounts)}")
        
        return {
            "accounting_entries": accounting_entries,
            "gl_accounts": gl_accounts,
            "reconciliation_summary": reconciliation_summary,
            "current_stage": "RECONCILE",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"RECONCILE node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "RECONCILE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }


def _determine_gl_account(description: str, vendor_profile: Dict[str, Any]) -> str:
    """
    Determine GL account for a line item based on description.
    
    In production, this would use a sophisticated mapping service.
    For now, uses simple keyword matching.
    """
    description_lower = description.lower()
    
    # Professional services
    if any(keyword in description_lower for keyword in ["service", "consulting", "professional"]):
        return "6000-PROF-SERVICES"
    
    # Software/Technology
    if any(keyword in description_lower for keyword in ["software", "license", "saas", "subscription"]):
        return "5000-SOFTWARE"
    
    # Office supplies
    if any(keyword in description_lower for keyword in ["supply", "office", "material"]):
        return "7000-OFFICE-SUPPLIES"
    
    # Travel
    if any(keyword in description_lower for keyword in ["travel", "hotel", "flight", "transport"]):
        return "8000-TRAVEL"
    
    # Default expense account
    return "9000-OTHER-EXPENSE"

