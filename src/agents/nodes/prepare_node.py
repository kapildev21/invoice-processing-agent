"""
PREPARE Node - Normalize vendor and compute risk flags

Mode: Non-deterministic (depends on enrichment tool)
Tools: Bigtool (enrichment), MCP COMMON (normalize_vendor, compute_flags)
"""

import time
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog
from src.integrations.bigtool import BigtoolPicker
from src.integrations.mcp_client import CommonClient, AtlasClient
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def prepare_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    PREPARE Node: Normalize vendor and compute risk flags.
    
    - Normalizes vendor name and tax ID via MCP COMMON
    - Enriches vendor data via Bigtool and MCP ATLAS
    - Computes risk flags and metadata via MCP COMMON
    
    Returns:
        State updates with vendor_profile, flags, and execution log
    """
    start_time = time.time()
    
    try:
        parsed_invoice = state.get("parsed_invoice", {})
        
        if not parsed_invoice:
            raise ValueError("parsed_invoice is required")
        
        vendor_name = parsed_invoice.get("vendor_name", "")
        vendor_tax_id = parsed_invoice.get("vendor_tax_id")
        invoice_amount = parsed_invoice.get("amount", 0.0)
        
        # Normalize vendor via MCP COMMON
        common_client = CommonClient()
        try:
            normalized = await common_client.normalize_vendor(vendor_name, vendor_tax_id)
            
            vendor_normalized_name = normalized.get("normalized_name", vendor_name)
            normalized_tax_id = normalized.get("normalized_tax_id", vendor_tax_id)
            
            # Enrich vendor via Bigtool and MCP ATLAS
            bigtool = BigtoolPicker()
            enrichment_tool = await bigtool.select("enrichment", context={})
            
            log_execution(logger, "PREPARE", tool_selected=enrichment_tool)
            
            atlas_client = AtlasClient()
            try:
                enriched = await atlas_client.enrich_vendor(vendor_normalized_name)
            finally:
                await atlas_client.close()
            
            # Build vendor profile
            vendor_profile = {
                "original_name": vendor_name,
                "normalized_name": vendor_normalized_name,
                "tax_id": normalized_tax_id,
                "enriched_data": enriched.get("vendor_data", {}),
                "enrichment_tool": enrichment_tool
            }
            
            # Compute flags via MCP COMMON
            flags_result = await common_client.compute_flags(
                vendor_profile,
                invoice_amount,
                parsed_invoice
            )
        finally:
            await common_client.close()
        
        flags = flags_result.get("flags", {})
        risk_score = flags_result.get("risk_score", 0.5)
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "PREPARE",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_selected": enrichment_tool,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        risk_level = "LOW" if risk_score < 0.3 else "MEDIUM" if risk_score < 0.7 else "HIGH"
        logger.info(f"[PREPARE] ✓ Enriched vendor: {vendor_normalized_name} (Tax: {normalized_tax_id})")
        logger.info(f"[PREPARE] ✓ Risk score: {risk_score:.2f} ({risk_level})")
        
        return {
            "vendor_profile": vendor_profile,
            "vendor_normalized_name": vendor_normalized_name,
            "vendor_tax_id": normalized_tax_id,
            "flags": flags,
            "risk_score": risk_score,
            "current_stage": "PREPARE",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"PREPARE node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "PREPARE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

