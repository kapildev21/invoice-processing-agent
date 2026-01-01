"""
INTAKE Node - Accept and validate invoice payload

Mode: Deterministic
Tools: Bigtool (storage)
"""

import uuid
from datetime import datetime
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from src.agents.state_schema import InvoiceWorkflowState, ExecutionLog
from src.integrations.bigtool import BigtoolPicker
from src.utils.logger import setup_logger, log_execution

logger = setup_logger(__name__)


async def intake_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    INTAKE Node: Accept and validate invoice payload.
    
    - Validates invoice payload structure
    - Generates unique raw_id
    - Persists to storage using Bigtool
    - Records ingestion timestamp
    
    Returns:
        State updates with raw_id, ingest_ts, and execution log
    """
    import time
    start_time = time.time()
    
    try:
        # Extract invoice payload
        invoice_payload = state.get("invoice_payload", {})
        
        if not invoice_payload:
            raise ValueError("invoice_payload is required")
        
        # Validate required fields
        required_fields = ["invoice_id", "vendor_name", "amount"]
        missing_fields = [field for field in required_fields if field not in invoice_payload]
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")
        
        # Generate unique raw_id
        raw_id = f"raw_{uuid.uuid4().hex[:12]}"
        ingest_ts = datetime.utcnow()
        
        # Select storage tool via Bigtool
        bigtool = BigtoolPicker()
        storage_tool = await bigtool.select("storage", context={"action": "save"})
        
        log_execution(logger, "INTAKE", tool_selected=storage_tool)
        
        # Persist invoice payload
        await bigtool.execute(
            storage_tool,
            "storage",
            action="save",
            filename=f"{raw_id}.json",
            data=invoice_payload
        )
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "INTAKE",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_selected": storage_tool,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        # Update execution history
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[INTAKE] ✓ Persisted raw_id: {raw_id}")
        
        return {
            "raw_id": raw_id,
            "ingest_ts": ingest_ts,
            "current_stage": "INTAKE",
            "execution_history": execution_history,
            "workflow_id": state.get("workflow_id") or f"wf_{uuid.uuid4().hex[:12]}",
            "created_at": state.get("created_at") or ingest_ts,
            "updated_at": ingest_ts
        }
    
    except Exception as e:
        error_msg = f"INTAKE node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "INTAKE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

