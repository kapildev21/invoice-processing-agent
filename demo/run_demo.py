"""
Demo Script - Run Invoice Processing Workflow

Demonstrates the complete workflow with match failure, checkpoint, and resume.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.graph_builder import build_invoice_graph
from src.agents.state_schema import InvoiceWorkflowState, HumanDecision
from src.integrations.checkpoint_store import CheckpointStore


async def run_demo():
    """
    Run complete workflow demo:
    1. Load sample invoice
    2. Execute workflow until checkpoint
    3. Simulate human review → accept
    4. Resume and complete workflow
    5. Print final payload
    
    Requirements:
    - Execute each stage exactly once (12 stages total)
    - Use single thread_id for entire workflow
    - Pass returned result state back when resuming
    - Only update human_decision fields without resetting other state
    - Use same config object for both initial invoke and resume
    """
    print("=" * 50)
    print("=== Invoice Processing Workflow Demo ===")
    print("=" * 50)
    print()
    
    # Load sample invoice
    invoice_path = Path(__file__).parent / "sample_invoice.json"
    with open(invoice_path, "r") as f:
        invoice_payload = json.load(f)
    
    invoice_id = invoice_payload["invoice_id"]
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting workflow for invoice {invoice_id}")
    print()
    
    # Build workflow graph
    graph = build_invoice_graph()
    
    # Generate workflow ID and thread_id - use same thread_id for entire workflow
    workflow_id = f"wf_demo_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    thread_id = workflow_id
    
    # Create initial state
    initial_state: InvoiceWorkflowState = {
        "invoice_payload": invoice_payload,
        "workflow_id": workflow_id,
        "current_stage": "INTAKE",
        "execution_history": [],
        "errors": [],
        "created_at": datetime.utcnow()
    }
    
    # Create config with thread_id - use same config for entire workflow
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    print("Executing workflow...")
    print()
    
    # Execute workflow until checkpoint (if match fails)
    # This executes stages 1-6: INTAKE → UNDERSTAND → PREPARE → RETRIEVE → MATCH_TWO_WAY → CHECKPOINT_HITL
    result = await graph.ainvoke(initial_state, config)
    
    # Check if we hit a checkpoint
    checkpoint_id = result.get("hitl_checkpoint_id")
    checkpoint_created = checkpoint_id is not None
    
    # If checkpoint was created, simulate human review and resume
    if checkpoint_created:
        print(f"[CHECKPOINT_HITL] ⏸️  WORKFLOW PAUSED - Awaiting human review")
        print(f"[CHECKPOINT_HITL] ✓ Checkpoint ID: {checkpoint_id}")
        print(f"[CHECKPOINT_HITL] ✓ Review URL: {result.get('review_url')}")
        print()
        
        print("--- Human Reviewer Action (Simulated) ---")
        print(f"Reviewing invoice {invoice_id}...")
        print(f"Match score: {result.get('match_score', 0):.2f}")
        print(f"Decision: ACCEPT")
        print('Notes: "Verified with vendor, PO mismatch due to revised quote"')
        print()
        
        # Update checkpoint store with decision
        checkpoint_store = CheckpointStore()
        await checkpoint_store.update_review_decision(
            checkpoint_id,
            "ACCEPT",
            "demo_reviewer_001",
            "Verified with vendor, PO mismatch due to revised quote"
        )
        
        # CRITICAL: Use the result state from checkpoint
        # Save checkpoint execution_history separately, then clear it from updated_state
        # This prevents nodes from appending to existing history during resume
        checkpoint_history = result.get("execution_history", [])
        
        updated_state = dict(result)  # Copy all state
        # Clear execution_history so resume execution builds fresh history
        updated_state["execution_history"] = []
        updated_state.update({
            "human_decision": HumanDecision.ACCEPT,
            "reviewer_id": "demo_reviewer_001",
            "review_notes": "Verified with vendor, PO mismatch due to revised quote",
            "review_timestamp": datetime.utcnow(),
            "resume_token": f"resume_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        })
        
        print("[HITL_DECISION] Resuming workflow with human decision...")
        print()
        
        # Resume workflow using the SAME config (same thread_id)
        # Pass the updated_state with human_decision - CHECKPOINT_HITL will route to HITL_DECISION
        # Note: LangGraph will re-execute all nodes, so we need to deduplicate execution_history
        resume_result = await graph.ainvoke(updated_state, config)
        
        # CRITICAL: Merge execution_history from checkpoint and resume
        # Checkpoint has stages 1-6: INTAKE through CHECKPOINT_HITL
        # Resume has stages 1-12 (re-executed), but we only want stages 7-12: HITL_DECISION through COMPLETE
        resume_history = resume_result.get("execution_history", [])
        
        # Expected stages in order
        expected_stages = [
            "INTAKE", "UNDERSTAND", "PREPARE", "RETRIEVE", "MATCH_TWO_WAY", 
            "CHECKPOINT_HITL", "HITL_DECISION", "RECONCILE", "APPROVE", 
            "POSTING", "NOTIFY", "COMPLETE"
        ]
        
        # Get first 6 stages from checkpoint (stages 1-6)
        checkpoint_stages_found = {}
        for entry in checkpoint_history:
            stage = entry.get("stage")
            if stage in expected_stages[:6] and stage not in checkpoint_stages_found:
                checkpoint_stages_found[stage] = entry
        
        # Get last 6 stages from resume (stages 7-12: HITL_DECISION through COMPLETE)
        # Note: Resume will re-execute all nodes, so we need to filter to only get stages 7-12
        resume_stages_found = {}
        for entry in resume_history:
            stage = entry.get("stage")
            # Only take stages 7-12 (HITL_DECISION through COMPLETE)
            if stage in expected_stages[6:]:
                if stage not in resume_stages_found:
                    resume_stages_found[stage] = entry
        
        # Build final history in expected order
        unique_history = []
        for stage in expected_stages:
            if stage in checkpoint_stages_found:
                unique_history.append(checkpoint_stages_found[stage])
            elif stage in resume_stages_found:
                unique_history.append(resume_stages_found[stage])
        
        # Debug: Verify all stages are present
        found_stages = {e.get('stage') for e in unique_history}
        missing_stages = set(expected_stages) - found_stages
        
        # Update result with merged execution_history (should have exactly 12 entries)
        result = dict(resume_result)
        result["execution_history"] = unique_history
        
        # CRITICAL: Update final_payload.execution_history to include COMPLETE
        # complete_node creates final_payload before adding COMPLETE to execution_history
        # So we need to update final_payload to use the deduplicated history
        if result.get("final_payload"):
            result["final_payload"]["execution_history"] = unique_history
        
        # Verify we have exactly 12 unique stages
        if len(unique_history) != 12 or missing_stages:
            print(f"WARNING: Expected 12 unique stages, got {len(unique_history)} entries")
            print(f"  Checkpoint had {len(checkpoint_history)} entries: {[e.get('stage') for e in checkpoint_history]}")
            print(f"  Resume had {len(resume_history)} entries")
            print(f"  Checkpoint stages found: {list(checkpoint_stages_found.keys())}")
            print(f"  Resume stages found: {list(resume_stages_found.keys())}")
            print(f"  Final stages: {[e.get('stage') for e in unique_history]}")
            if missing_stages:
                print(f"  Missing stages: {missing_stages}")
        else:
            print(f"✓ Deduplication successful: {len(unique_history)} unique stages")
            
    # Print final payload
    print("=" * 50)
    print("=== Final Payload ===")
    print("=" * 50)
    if result:
        final_payload = result.get("final_payload", {})
        if not final_payload:
            # Build final payload from state if not already created
            final_payload = {
                "invoice_id": result.get("parsed_invoice", {}).get("invoice_id") or result.get("raw_id", "UNKNOWN"),
                "status": result.get("status", {}).value if hasattr(result.get("status"), "value") else str(result.get("status", "UNKNOWN")),
                "vendor": result.get("vendor_normalized_name") or result.get("parsed_invoice", {}).get("vendor_name", "Unknown"),
                "amount": result.get("parsed_invoice", {}).get("amount", 0.0),
                "currency": result.get("parsed_invoice", {}).get("currency", "USD"),
                "erp_txn_id": result.get("erp_txn_id"),
                "approval_status": result.get("approval_status", {}).value if result.get("approval_status") and hasattr(result.get("approval_status"), "value") else str(result.get("approval_status")) if result.get("approval_status") else None,
                "human_reviewed": result.get("human_decision") is not None,
                "hitl_checkpoint_id": result.get("hitl_checkpoint_id"),
                "execution_time_seconds": result.get("execution_time_seconds", 0.0),
                "workflow_id": result.get("workflow_id"),
                "execution_history": result.get("execution_history", []),
                "completed_at": result.get("completion_timestamp") or datetime.utcnow().isoformat()
            }
        print(json.dumps(final_payload, indent=2, default=str))
    else:
        print("ERROR: No result returned from workflow")
    
    print()
    print("=" * 50)
    print("Demo completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_demo())
