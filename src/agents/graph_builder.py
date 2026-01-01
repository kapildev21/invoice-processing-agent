"""
LangGraph Construction

Builds the complete invoice processing workflow graph with conditional routing
and checkpoint support.
"""

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    # Fallback to MemorySaver if SqliteSaver not available
    from langgraph.checkpoint.memory import MemorySaver as SqliteSaver
from pathlib import Path
import json
import logging

from src.agents.state_schema import InvoiceWorkflowState, MatchResult, HumanDecision
from src.agents.nodes.intake_node import intake_node
from src.agents.nodes.understand_node import understand_node
from src.agents.nodes.prepare_node import prepare_node
from src.agents.nodes.retrieve_node import retrieve_node
from src.agents.nodes.match_node import match_node
from src.agents.nodes.checkpoint_node import checkpoint_node
from src.agents.nodes.hitl_node import hitl_node
from src.agents.nodes.reconcile_node import reconcile_node
from src.agents.nodes.approve_node import approve_node
from src.agents.nodes.posting_node import posting_node
from src.agents.nodes.notify_node import notify_node
from src.agents.nodes.complete_node import complete_node
from src.config.settings import settings

logger = logging.getLogger(__name__)


def route_after_match(state: InvoiceWorkflowState) -> Literal["CHECKPOINT_HITL", "RECONCILE"]:
    """
    Route after MATCH_TWO_WAY stage.
    
    - If match_result == FAILED → CHECKPOINT_HITL
    - Else → RECONCILE
    """
    match_result = state.get("match_result")
    
    if match_result == MatchResult.FAILED:
        logger.info("[ROUTING] Match failed → CHECKPOINT_HITL")
        return "CHECKPOINT_HITL"
    else:
        logger.info("[ROUTING] Match passed → RECONCILE")
        return "RECONCILE"


def route_after_checkpoint(state: InvoiceWorkflowState) -> Literal["HITL_DECISION", "__end__"]:
    """
    Route after CHECKPOINT_HITL stage.
    
    - If human_decision exists → HITL_DECISION (resuming from checkpoint)
    - Else → __end__ (pause workflow, wait for human decision)
    """
    human_decision = state.get("human_decision")
    
    if human_decision:
        logger.info("[ROUTING] Human decision found → HITL_DECISION")
        return "HITL_DECISION"
    else:
        logger.info("[ROUTING] No human decision yet → __end__ (paused)")
        return "__end__"


def route_after_hitl(state: InvoiceWorkflowState) -> Literal["RECONCILE", "COMPLETE"]:
    """
    Route after HITL_DECISION stage.
    
    - If human_decision == ACCEPT → RECONCILE
    - If human_decision == REJECT → COMPLETE (with MANUAL_HANDOFF status)
    """
    human_decision = state.get("human_decision")
    
    if human_decision == HumanDecision.ACCEPT:
        logger.info("[ROUTING] Human accepted → RECONCILE")
        return "RECONCILE"
    elif human_decision == HumanDecision.REJECT:
        logger.info("[ROUTING] Human rejected → COMPLETE")
        return "COMPLETE"
    else:
        # Default to COMPLETE if no decision (shouldn't happen)
        logger.warning("[ROUTING] No human decision found → COMPLETE")
        return "COMPLETE"


def build_invoice_graph(workflow_config: Dict[str, Any] = None) -> StateGraph:
    """
    Construct LangGraph from workflow configuration.
    
    Key features:
    - Sequential deterministic nodes
    - Conditional edge from MATCH_TWO_WAY:
      - If match_result == 'FAILED' → CHECKPOINT_HITL
      - Else → RECONCILE
    - Conditional edge from HITL_DECISION:
      - If human_decision == 'ACCEPT' → RECONCILE
      - If human_decision == 'REJECT' → COMPLETE (with MANUAL_HANDOFF status)
    - Use SqliteSaver for checkpoint persistence
    
    Args:
        workflow_config: Optional workflow configuration dict.
                        If None, loads from workflow.json or uses defaults.
    
    Returns:
        Compiled LangGraph workflow
    """
    if workflow_config is None:
        workflow_config = _load_workflow_config()
    
    # Create state graph
    workflow = StateGraph(InvoiceWorkflowState)
    
    # Add all nodes
    logger.info("Adding workflow nodes...")
    workflow.add_node("INTAKE", intake_node)
    workflow.add_node("UNDERSTAND", understand_node)
    workflow.add_node("PREPARE", prepare_node)
    workflow.add_node("RETRIEVE", retrieve_node)
    workflow.add_node("MATCH_TWO_WAY", match_node)
    workflow.add_node("CHECKPOINT_HITL", checkpoint_node)
    workflow.add_node("HITL_DECISION", hitl_node)
    workflow.add_node("RECONCILE", reconcile_node)
    workflow.add_node("APPROVE", approve_node)
    workflow.add_node("POSTING", posting_node)
    workflow.add_node("NOTIFY", notify_node)
    workflow.add_node("COMPLETE", complete_node)
    
    # Add sequential edges
    logger.info("Adding sequential edges...")
    workflow.add_edge("INTAKE", "UNDERSTAND")
    workflow.add_edge("UNDERSTAND", "PREPARE")
    workflow.add_edge("PREPARE", "RETRIEVE")
    workflow.add_edge("RETRIEVE", "MATCH_TWO_WAY")
    
    # Conditional routing after matching
    workflow.add_conditional_edges(
        "MATCH_TWO_WAY",
        route_after_match,
        {
            "CHECKPOINT_HITL": "CHECKPOINT_HITL",
            "RECONCILE": "RECONCILE"
        }
    )
    
    # CHECKPOINT creates review and pauses
    # When workflow resumes with human_decision, it goes to HITL_DECISION
    # Use conditional edge: if human_decision exists, continue; otherwise pause (END)
    workflow.add_conditional_edges(
        "CHECKPOINT_HITL",
        route_after_checkpoint,
        {
            "HITL_DECISION": "HITL_DECISION",
            "__end__": END  # Pause if no decision yet
        }
    )
    
    # HITL decision routes based on human decision
    workflow.add_conditional_edges(
        "HITL_DECISION",
        route_after_hitl,
        {
            "RECONCILE": "RECONCILE",
            "COMPLETE": "COMPLETE"
        }
    )
    
    # Continue sequential flow after reconciliation
    workflow.add_edge("RECONCILE", "APPROVE")
    workflow.add_edge("APPROVE", "POSTING")
    workflow.add_edge("POSTING", "NOTIFY")
    workflow.add_edge("NOTIFY", "COMPLETE")
    workflow.add_edge("COMPLETE", END)
    
    # Set entry point
    workflow.set_entry_point("INTAKE")
    
    # Configure checkpoint saver - use MemorySaver for demo (works without SQLite setup)
    # In production, you would use SqliteSaver for persistence
    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    logger.info("Using MemorySaver for checkpoints (demo mode)")
    
    logger.info("Compiling workflow graph...")
    compiled_graph = workflow.compile(checkpointer=memory)
    
    logger.info("✓ Workflow graph compiled successfully")
    return compiled_graph


def _load_workflow_config() -> Dict[str, Any]:
    """
    Load workflow configuration from workflow.json.
    
    Returns:
        Workflow configuration dictionary
    """
    config_path = Path(__file__).parent.parent / "config" / "workflow.json"
    
    try:
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
            logger.info(f"Loaded workflow config from {config_path}")
            return config
        else:
            logger.warning(f"Workflow config not found at {config_path}, using defaults")
            return _get_default_workflow_config()
    except Exception as e:
        logger.error(f"Error loading workflow config: {e}, using defaults")
        return _get_default_workflow_config()


def _get_default_workflow_config() -> Dict[str, Any]:
    """Get default workflow configuration"""
    return {
        "config": {
            "default_db": settings.DATABASE_URL
        },
        "stages": {
            "INTAKE": {
                "mode": "deterministic",
                "tools": ["storage"]
            },
            "UNDERSTAND": {
                "mode": "non-deterministic",
                "tools": ["ocr"]
            },
            "PREPARE": {
                "mode": "deterministic",
                "tools": ["enrichment"]
            },
            "RETRIEVE": {
                "mode": "non-deterministic",
                "tools": ["erp"]
            },
            "MATCH_TWO_WAY": {
                "mode": "deterministic",
                "tools": []
            },
            "CHECKPOINT_HITL": {
                "mode": "deterministic",
                "tools": []
            },
            "HITL_DECISION": {
                "mode": "non-deterministic",
                "tools": []
            },
            "RECONCILE": {
                "mode": "deterministic",
                "tools": []
            },
            "APPROVE": {
                "mode": "deterministic",
                "tools": []
            },
            "POSTING": {
                "mode": "non-deterministic",
                "tools": ["erp"]
            },
            "NOTIFY": {
                "mode": "non-deterministic",
                "tools": ["email"]
            },
            "COMPLETE": {
                "mode": "deterministic",
                "tools": []
            }
        }
    }

