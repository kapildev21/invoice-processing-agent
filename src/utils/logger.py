"""
Structured Logging Setup

Provides JSON-structured logging for all workflow nodes.
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

try:
    from src.config.settings import settings
    LOG_LEVEL = settings.LOG_LEVEL
except:
    LOG_LEVEL = "INFO"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "stage"):
            log_data["stage"] = record.stage
        if hasattr(record, "tool_selected"):
            log_data["tool_selected"] = record.tool_selected
        if hasattr(record, "decision"):
            log_data["decision"] = record.decision
        if hasattr(record, "workflow_id"):
            log_data["workflow_id"] = record.workflow_id
        if hasattr(record, "checkpoint_id"):
            log_data["checkpoint_id"] = record.checkpoint_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Set up a structured logger with both console and file output.
    
    Args:
        name: Logger name (typically __name__)
        level: Log level (defaults to settings.LOG_LEVEL)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if level is None:
        level = LOG_LEVEL
    
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)
    
    # Create file handler for persistent logging
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create log file with timestamp
    log_filename = log_dir / f"workflow_{datetime.utcnow().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def log_execution(
    logger: logging.Logger,
    stage: str,
    tool_selected: Optional[str] = None,
    decision: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
    **extra: Any
):
    """
    Log a workflow execution event.
    
    Args:
        logger: Logger instance
        stage: Workflow stage name
        tool_selected: Selected tool (if applicable)
        decision: Decision made (if applicable)
        duration_ms: Execution duration in milliseconds
        error: Error message (if applicable)
        **extra: Additional fields to log
    """
    # Use extra dict for custom fields (not as keyword arguments)
    extra_fields = {
        "stage": stage,
        **extra
    }
    
    if tool_selected:
        extra_fields["tool_selected"] = tool_selected
    
    if decision:
        extra_fields["decision"] = decision
    
    if duration_ms:
        extra_fields["duration_ms"] = duration_ms
    
    if error:
        extra_fields["error"] = error
        logger.error(f"[{stage}] {error}", extra=extra_fields)
    else:
        message = f"[{stage}]"
        if tool_selected:
            message += f" ✓ Bigtool selected: {tool_selected}"
        if decision:
            message += f" ✓ Decision: {decision}"
        logger.info(message, extra=extra_fields)

