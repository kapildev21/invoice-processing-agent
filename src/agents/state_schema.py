"""
State Schema for Invoice Processing Workflow

Defines the complete state structure that flows through all workflow nodes.
Uses TypedDict for type safety and compatibility with LangGraph.
"""

from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"


class MatchResult(str, Enum):
    """2-way matching result"""
    PASSED = "PASSED"
    FAILED = "FAILED"


class HumanDecision(str, Enum):
    """Human review decision"""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class ApprovalStatus(str, Enum):
    """Invoice approval status"""
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ExecutionLog(TypedDict, total=False):
    """Single execution log entry"""
    stage: str
    timestamp: str
    tool_selected: Optional[str]
    decision: Optional[str]
    duration_ms: Optional[float]
    error: Optional[str]


class InvoiceWorkflowState(TypedDict, total=False):
    """
    Complete workflow state that flows through all nodes.
    
    All fields are optional (total=False) to allow incremental updates.
    Note: 'checkpoint_id' is reserved by LangGraph, so we use 'hitl_checkpoint_id' in state.
    """
    
    # ========== Raw Input ==========
    invoice_payload: Dict[str, Any]  # Raw invoice input from API
    
    # ========== INTAKE Stage ==========
    raw_id: Optional[str]  # Unique ID for raw invoice
    ingest_ts: Optional[datetime]  # Timestamp of ingestion
    
    # ========== UNDERSTAND Stage ==========
    parsed_invoice: Optional[Dict[str, Any]]  # Parsed invoice data from OCR
    ocr_text: Optional[str]  # Raw OCR text
    ocr_tool_used: Optional[str]  # Which OCR tool was selected
    
    # ========== PREPARE Stage ==========
    vendor_profile: Optional[Dict[str, Any]]  # Normalized and enriched vendor data
    flags: Optional[Dict[str, Any]]  # Risk flags and computed metadata
    vendor_normalized_name: Optional[str]
    vendor_tax_id: Optional[str]
    risk_score: Optional[float]
    
    # ========== RETRIEVE Stage ==========
    matched_pos: Optional[List[Dict[str, Any]]]  # Matching Purchase Orders
    matched_grns: Optional[List[Dict[str, Any]]]  # Matching Goods Receipt Notes
    retrieval_tool_used: Optional[str]  # Which ERP tool was selected
    
    # ========== MATCH_TWO_WAY Stage ==========
    match_score: Optional[float]  # Match score (0.0 to 1.0)
    match_result: Optional[MatchResult]  # PASSED or FAILED
    match_details: Optional[Dict[str, Any]]  # Detailed matching information
    tolerance_pct: Optional[int]  # Applied tolerance percentage
    
    # ========== CHECKPOINT_HITL Stage ==========
    hitl_checkpoint_id: Optional[str]  # Unique checkpoint identifier (renamed to avoid LangGraph reserved name)
    review_url: Optional[str]  # URL for human review
    paused_reason: Optional[str]  # Reason for workflow pause
    review_ticket_id: Optional[str]  # Review ticket identifier
    
    # ========== HITL_DECISION Stage ==========
    human_decision: Optional[HumanDecision]  # ACCEPT or REJECT
    resume_token: Optional[str]  # Token for resuming workflow
    reviewer_id: Optional[str]  # ID of human reviewer
    review_notes: Optional[str]  # Notes from reviewer
    review_timestamp: Optional[datetime]  # When review was completed
    
    # ========== RECONCILE Stage ==========
    accounting_entries: Optional[List[Dict[str, Any]]]  # Journal entries
    gl_accounts: Optional[List[str]]  # General ledger accounts used
    reconciliation_summary: Optional[Dict[str, Any]]
    
    # ========== APPROVE Stage ==========
    approval_status: Optional[ApprovalStatus]  # Approval status
    approver_id: Optional[str]  # ID of approver (if manual)
    approval_policy_applied: Optional[str]  # Which policy was used
    approval_timestamp: Optional[datetime]
    
    # ========== POSTING Stage ==========
    posted: Optional[bool]  # Whether posting was successful
    erp_txn_id: Optional[str]  # ERP transaction ID
    posting_tool_used: Optional[str]  # Which ERP tool was used
    payment_scheduled: Optional[bool]
    payment_id: Optional[str]
    posting_timestamp: Optional[datetime]
    
    # ========== NOTIFY Stage ==========
    notify_status: Optional[Dict[str, Any]]  # Notification status
    notifications_sent: Optional[List[Dict[str, Any]]]  # List of sent notifications
    notify_tool_used: Optional[str]  # Which email tool was used
    
    # ========== COMPLETE Stage ==========
    final_payload: Optional[Dict[str, Any]]  # Final output payload
    status: Optional[WorkflowStatus]  # Final workflow status
    completion_timestamp: Optional[datetime]
    execution_time_seconds: Optional[float]
    
    # ========== Metadata ==========
    current_stage: Optional[str]  # Current workflow stage name
    execution_history: Optional[List[ExecutionLog]]  # Execution log entries
    errors: Optional[List[Dict[str, Any]]]  # Error log entries
    workflow_id: Optional[str]  # Unique workflow execution ID
    created_at: Optional[datetime]  # Workflow creation timestamp
    updated_at: Optional[datetime]  # Last update timestamp

