"""
RETRIEVE Node - Fetch PO/GRN from ERP

Mode: Non-deterministic (depends on ERP tool)
Tools: Bigtool (ERP), MCP ATLAS (fetch_po, fetch_grn)
"""

import time
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog
from src.integrations.bigtool import BigtoolPicker
from src.integrations.mcp_client import AtlasClient
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def retrieve_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    RETRIEVE Node: Fetch matching PO/GRN from ERP.
    
    - Selects ERP tool via Bigtool
    - Fetches matching Purchase Orders via MCP ATLAS
    - Fetches Goods Receipt Notes for matched POs
    
    Returns:
        State updates with matched_pos, matched_grns, and execution log
    """
    start_time = time.time()
    
    try:
        parsed_invoice = state.get("parsed_invoice", {})
        vendor_normalized_name = state.get("vendor_normalized_name", "")
        
        if not parsed_invoice:
            raise ValueError("parsed_invoice is required")
        
        invoice_date = parsed_invoice.get("invoice_date", "")
        invoice_amount = parsed_invoice.get("amount", 0.0)
        
        # Select ERP tool via Bigtool
        bigtool = BigtoolPicker()
        erp_tool = await bigtool.select("erp", context={})
        
        log_execution(logger, "RETRIEVE", tool_selected=erp_tool)
        
        # Fetch POs via MCP ATLAS
        atlas_client = AtlasClient()
        try:
            po_result = await atlas_client.fetch_po(
                vendor_normalized_name,
                invoice_date,
                invoice_amount
            )
            
            matched_pos = po_result.get("pos", [])
            
            # Fetch GRNs for matched POs
            matched_grns: List[Dict[str, Any]] = []
            if matched_pos:
                po_ids = [po.get("po_id") for po in matched_pos if po.get("po_id")]
                if po_ids:
                    grn_result = await atlas_client.fetch_grn(po_ids, invoice_date)
                    matched_grns = grn_result.get("grns", [])
        finally:
            await atlas_client.close()
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "RETRIEVE",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_selected": erp_tool,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[RETRIEVE] ✓ Found {len(matched_pos)} matching POs")
        logger.info(f"[RETRIEVE] ✓ Found {len(matched_grns)} matching GRNs")
        
        return {
            "matched_pos": matched_pos,
            "matched_grns": matched_grns,
            "retrieval_tool_used": erp_tool,
            "current_stage": "RETRIEVE",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"RETRIEVE node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "RETRIEVE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

