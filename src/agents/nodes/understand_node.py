"""
UNDERSTAND Node - OCR and parse invoice data

Mode: Non-deterministic (depends on OCR tool)
Tools: Bigtool (OCR), MCP COMMON (parse_invoice)
"""

import time
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog
from src.integrations.bigtool import BigtoolPicker
from src.integrations.mcp_client import CommonClient
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def understand_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    UNDERSTAND Node: OCR and parse invoice data.
    
    - Selects OCR tool via Bigtool
    - Performs OCR on invoice attachments
    - Parses invoice using MCP COMMON
    - Extracts structured invoice data
    
    Returns:
        State updates with parsed_invoice, ocr_text, and execution log
    """
    start_time = time.time()
    
    try:
        invoice_payload = state.get("invoice_payload", {})
        raw_id = state.get("raw_id")
        
        if not invoice_payload:
            raise ValueError("invoice_payload is required")
        
        # Get invoice attachments
        attachments = invoice_payload.get("attachments", [])
        if not attachments:
            # If no attachments, try to extract text from payload
            invoice_text = invoice_payload.get("text", "")
            ocr_tool_used = None
        else:
            # Select OCR tool via Bigtool
            bigtool = BigtoolPicker()
            ocr_tool = await bigtool.select(
                "ocr",
                context={
                    "high_quality_required": True,
                    "required_capabilities": ["pdf_support"]
                }
            )
            
            log_execution(logger, "UNDERSTAND", tool_selected=ocr_tool)
            
            # Perform OCR (mock implementation)
            ocr_result = await bigtool.execute(
                ocr_tool,
                "ocr",
                text=invoice_payload.get("text", ""),
                attachments=attachments
            )
            
            invoice_text = ocr_result.get("text", "")
            ocr_tool_used = ocr_tool
        
        # Parse invoice using MCP COMMON
        common_client = CommonClient()
        try:
            parsed_result = await common_client.parse_invoice(invoice_text)
        finally:
            await common_client.close()
        
        # Extract structured data
        parsed_invoice = {
            "invoice_id": invoice_payload.get("invoice_id"),
            "vendor_name": invoice_payload.get("vendor_name"),
            "vendor_tax_id": invoice_payload.get("vendor_tax_id"),
            "invoice_date": invoice_payload.get("invoice_date"),
            "due_date": invoice_payload.get("due_date"),
            "amount": invoice_payload.get("amount"),
            "currency": invoice_payload.get("currency", "USD"),
            "line_items": invoice_payload.get("line_items", []),
            "parsed_data": parsed_result
        }
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "UNDERSTAND",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_selected": ocr_tool_used,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[UNDERSTAND] ✓ Extracted {len(invoice_text)} characters")
        logger.info(f"[UNDERSTAND] ✓ Parsed {len(parsed_invoice.get('line_items', []))} line items")
        
        return {
            "parsed_invoice": parsed_invoice,
            "ocr_text": invoice_text,
            "ocr_tool_used": ocr_tool_used,
            "current_stage": "UNDERSTAND",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"UNDERSTAND node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "UNDERSTAND",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

