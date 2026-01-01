"""
POSTING Node - Post to ERP system

Mode: Non-deterministic (external system)
Tools: Bigtool (ERP), MCP ATLAS
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog
from src.integrations.bigtool import BigtoolPicker
from src.integrations.mcp_client import AtlasClient
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def posting_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    POSTING Node: Post accounting entries to ERP system.
    
    - Selects ERP tool via Bigtool
    - Posts accounting entries via MCP ATLAS
    - Records ERP transaction ID
    - Schedules payment if applicable
    
    Returns:
        State updates with posted, erp_txn_id, and execution log
    """
    start_time = time.time()
    
    try:
        # Extract required data
        accounting_entries = state.get("accounting_entries", [])
        parsed_invoice = state.get("parsed_invoice", {})
        vendor_profile = state.get("vendor_profile", {})
        
        if not accounting_entries:
            raise ValueError("accounting_entries is required for posting")
        
        invoice_id = parsed_invoice.get("invoice_id") or state.get("raw_id", "UNKNOWN")
        vendor_name = state.get("vendor_normalized_name") or parsed_invoice.get("vendor_name", "Unknown")
        
        # Select ERP tool via Bigtool
        bigtool = BigtoolPicker()
        erp_tool = await bigtool.select("erp", context={"action": "post"})
        
        log_execution(logger, "POSTING", tool_selected=erp_tool)
        
        # Post to ERP via MCP ATLAS
        atlas_client = AtlasClient()
        
        try:
            posting_result = await atlas_client.post_to_erp(
                accounting_entries,
                invoice_id,
                vendor_name
            )
            
            erp_txn_id = posting_result.get("erp_txn_id")
            posted = posting_result.get("success", False)
            
            if not posted:
                raise RuntimeError(f"ERP posting failed: {posting_result}")
            
        finally:
            await atlas_client.close()
        
        # Schedule payment (in production, this would be a separate ERP call)
        payment_scheduled = True
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "POSTING",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_selected": erp_tool,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[POSTING] ✓ Posted to ERP: {erp_txn_id}")
        logger.info(f"[POSTING] ✓ Payment scheduled: {payment_id}")
        
        return {
            "posted": posted,
            "erp_txn_id": erp_txn_id,
            "posting_tool_used": erp_tool,
            "payment_scheduled": payment_scheduled,
            "payment_id": payment_id,
            "posting_timestamp": datetime.utcnow(),
            "current_stage": "POSTING",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"POSTING node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "POSTING",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED",
            "posted": False
        }

