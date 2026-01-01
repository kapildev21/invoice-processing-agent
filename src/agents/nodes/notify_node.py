"""
NOTIFY Node - Send notifications

Mode: Non-deterministic (external service)
Tools: Bigtool (email), MCP ATLAS
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


async def notify_node(
    state: InvoiceWorkflowState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    NOTIFY Node: Send notifications to stakeholders.
    
    - Selects email tool via Bigtool
    - Sends notifications via MCP ATLAS
    - Notifies vendor and internal finance team
    - Records notification status
    
    Returns:
        State updates with notify_status and execution log
    """
    start_time = time.time()
    
    try:
        # Extract invoice data
        parsed_invoice = state.get("parsed_invoice", {})
        vendor_profile = state.get("vendor_profile", {})
        erp_txn_id = state.get("erp_txn_id")
        posted = state.get("posted", False)
        
        if not parsed_invoice:
            raise ValueError("parsed_invoice is required for notifications")
        
        invoice_id = parsed_invoice.get("invoice_id") or state.get("raw_id", "UNKNOWN")
        vendor_name = state.get("vendor_normalized_name") or parsed_invoice.get("vendor_name", "Unknown")
        amount = parsed_invoice.get("amount", 0.0)
        currency = parsed_invoice.get("currency", "USD")
        
        # Select email tool via Bigtool
        bigtool = BigtoolPicker()
        email_tool = await bigtool.select("email", context={"action": "send"})
        
        log_execution(logger, "NOTIFY", tool_selected=email_tool)
        
        # Prepare notification recipients
        # In production, these would come from vendor profile and config
        vendor_email = vendor_profile.get("email") or f"vendor@{vendor_name.lower().replace(' ', '')}.com"
        finance_email = "finance@company.com"  # From config
        
        recipients = [vendor_email, finance_email]
        
        # Prepare notification content
        subject = f"Invoice {invoice_id} Processed"
        body = f"""
Invoice Processing Complete

Invoice ID: {invoice_id}
Vendor: {vendor_name}
Amount: {currency} {amount:,.2f}
ERP Transaction ID: {erp_txn_id}
Status: {'Posted successfully' if posted else 'Processing'}
        
This is an automated notification from the Invoice Processing System.
        """.strip()
        
        # Send notifications via MCP ATLAS
        atlas_client = AtlasClient()
        notifications_sent: List[Dict[str, Any]] = []
        
        try:
            for recipient in recipients:
                try:
                    result = await atlas_client.send_notification(
                        to=[recipient],
                        subject=subject,
                        body=body,
                        notification_type="email"
                    )
                    
                    notifications_sent.append({
                        "recipient": recipient,
                        "sent": result.get("sent", False),
                        "message_id": result.get("message_id"),
                        "delivered": result.get("delivered", False),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.warning(f"[NOTIFY] Failed to send to {recipient}: {e}")
                    notifications_sent.append({
                        "recipient": recipient,
                        "sent": False,
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
        finally:
            await atlas_client.close()
        
        # Calculate notification status
        successful = sum(1 for n in notifications_sent if n.get("sent", False))
        total = len(notifications_sent)
        
        notify_status = {
            "total_recipients": total,
            "successful": successful,
            "failed": total - successful,
            "all_sent": successful == total
        }
        
        # Create execution log entry
        execution_log: ExecutionLog = {
            "stage": "NOTIFY",
            "timestamp": datetime.utcnow().isoformat(),
            "tool_selected": email_tool,
            "duration_ms": (time.time() - start_time) * 1000
        }
        
        execution_history = state.get("execution_history", [])
        execution_history.append(execution_log)
        
        logger.info(f"[NOTIFY] ✓ Notified {successful}/{total} recipients")
        for notification in notifications_sent:
            if notification.get("sent"):
                logger.info(f"[NOTIFY] ✓ Sent to: {notification['recipient']}")
        
        return {
            "notify_status": notify_status,
            "notifications_sent": notifications_sent,
            "notify_tool_used": email_tool,
            "current_stage": "NOTIFY",
            "execution_history": execution_history,
            "updated_at": datetime.utcnow()
        }
    
    except Exception as e:
        error_msg = f"NOTIFY node error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        errors = state.get("errors", [])
        errors.append({
            "stage": "NOTIFY",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "errors": errors,
            "status": "FAILED"
        }

