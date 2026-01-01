"""
Checkpoint Store - State Persistence for HITL

Manages checkpoint storage and retrieval for workflow state persistence.
Supports SQLite and PostgreSQL backends.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from sqlalchemy import create_engine, Column, String, JSON, DateTime, Boolean, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

Base = declarative_base()


class CheckpointModel(Base):
    """Database model for checkpoints"""
    __tablename__ = "checkpoints"
    
    checkpoint_id = Column(String, primary_key=True)  # Keep as checkpoint_id in DB
    state_blob = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String, default="active")
    workflow_id = Column(String, index=True)


class HumanReviewQueueModel(Base):
    """Database model for human review queue"""
    __tablename__ = "human_review_queue"
    
    checkpoint_id = Column(String, primary_key=True)
    invoice_id = Column(String, index=True)
    vendor_name = Column(String)
    amount = Column(Float)
    reason_for_hold = Column(Text)
    review_url = Column(String)
    status = Column(String, default="pending")  # pending, reviewed, resolved
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer_id = Column(String, nullable=True)
    decision = Column(String, nullable=True)  # ACCEPT, REJECT


class CheckpointStore:
    """
    Manages checkpoint storage and retrieval for workflow state persistence.
    
    Supports both SQLite (for development) and PostgreSQL (for production).
    """
    
    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize checkpoint store.
        
        Args:
            db_url: Database URL. If None, uses SQLite default.
        """
        if db_url is None:
            db_path = Path("./invoice_processing.db")
            db_url = f"sqlite:///{db_path.absolute()}"
        
        # For SQLite, use StaticPool to allow multiple connections
        if db_url.startswith("sqlite"):
            self.engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool
            )
        else:
            self.engine = create_engine(db_url)
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logger.info(f"Initialized CheckpointStore with database: {db_url}")
    
    def _get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()
    
    async def save_checkpoint(
        self,
        checkpoint_id: str,
        state: Dict[str, Any],
        workflow_id: Optional[str] = None
    ) -> str:
        """
        Persist workflow state to database.
        
        Args:
            checkpoint_id: Unique checkpoint identifier
            state: Workflow state dictionary
            workflow_id: Optional workflow ID
        
        Returns:
            Checkpoint ID
        """
        session = self._get_session()
        try:
            # Convert datetime objects to strings for JSON serialization
            serializable_state = self._make_serializable(state)
            
            checkpoint = CheckpointModel(
                checkpoint_id=checkpoint_id,
                state_blob=serializable_state,
                workflow_id=workflow_id or state.get("workflow_id"),
                status="active"
            )
            
            session.merge(checkpoint)
            session.commit()
            
            logger.info(f"Saved checkpoint {checkpoint_id}")
            return checkpoint_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving checkpoint {checkpoint_id}: {e}")
            raise
        finally:
            session.close()
    
    async def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint state from database.
        
        Args:
            checkpoint_id: Checkpoint identifier
        
        Returns:
            Workflow state dictionary, or None if not found
        """
        session = self._get_session()
        try:
            checkpoint = session.query(CheckpointModel).filter_by(
                checkpoint_id=checkpoint_id
            ).first()
            
            if checkpoint is None:
                logger.warning(f"Checkpoint {checkpoint_id} not found")
                return None
            
            state = checkpoint.state_blob
            logger.info(f"Loaded checkpoint {checkpoint_id}")
            return state
        except Exception as e:
            logger.error(f"Error loading checkpoint {checkpoint_id}: {e}")
            raise
        finally:
            session.close()
    
    async def create_review_ticket(
        self,
        checkpoint_id: str,
        invoice_data: Dict[str, Any],
        reason_for_hold: str,
        review_url: Optional[str] = None
    ) -> str:
        """
        Create a human review ticket in the review queue.
        
        Args:
            checkpoint_id: Checkpoint identifier
            invoice_data: Invoice data dictionary
            reason_for_hold: Reason why invoice needs review
            review_url: Optional review URL (will be generated if not provided)
        
        Returns:
            Review URL
        """
        session = self._get_session()
        try:
            if review_url is None:
                review_url = f"http://localhost:8000/human-review/{checkpoint_id}"
            
            invoice_id = invoice_data.get("invoice_id", invoice_data.get("raw_id", "UNKNOWN"))
            vendor_name = invoice_data.get("vendor_name", invoice_data.get("vendor_normalized_name", "Unknown"))
            amount = invoice_data.get("amount", 0.0)
            
            review_ticket = HumanReviewQueueModel(
                checkpoint_id=checkpoint_id,
                invoice_id=invoice_id,
                vendor_name=vendor_name,
                amount=amount,
                reason_for_hold=reason_for_hold,
                review_url=review_url,
                status="pending"
            )
            
            session.merge(review_ticket)
            session.commit()
            
            logger.info(f"Created review ticket for checkpoint {checkpoint_id}: {review_url}")
            return review_url
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating review ticket for {checkpoint_id}: {e}")
            raise
        finally:
            session.close()
    
    async def update_review_decision(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer_id: str,
        review_notes: Optional[str] = None
    ) -> bool:
        """
        Update review ticket with human decision.
        
        Args:
            checkpoint_id: Checkpoint identifier
            decision: Decision (ACCEPT or REJECT)
            reviewer_id: ID of reviewer
            review_notes: Optional review notes
        
        Returns:
            True if updated successfully
        """
        session = self._get_session()
        try:
            review_ticket = session.query(HumanReviewQueueModel).filter_by(
                checkpoint_id=checkpoint_id
            ).first()
            
            if review_ticket is None:
                logger.warning(f"Review ticket for checkpoint {checkpoint_id} not found")
                return False
            
            review_ticket.status = "reviewed"
            review_ticket.decision = decision
            review_ticket.reviewer_id = reviewer_id
            review_ticket.reviewed_at = datetime.utcnow()
            
            session.commit()
            
            logger.info(f"Updated review decision for {checkpoint_id}: {decision}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating review decision for {checkpoint_id}: {e}")
            raise
        finally:
            session.close()
    
    async def list_pending_reviews(self) -> list[Dict[str, Any]]:
        """
        List all pending review tickets.
        
        Returns:
            List of review ticket dictionaries
        """
        session = self._get_session()
        try:
            tickets = session.query(HumanReviewQueueModel).filter_by(
                status="pending"
            ).all()
            
            return [
                {
                    "checkpoint_id": ticket.checkpoint_id,
                    "invoice_id": ticket.invoice_id,
                    "vendor_name": ticket.vendor_name,
                    "amount": ticket.amount,
                    "reason_for_hold": ticket.reason_for_hold,
                    "review_url": ticket.review_url,
                    "created_at": ticket.created_at.isoformat() if ticket.created_at else None
                }
                for ticket in tickets
            ]
        except Exception as e:
            logger.error(f"Error listing pending reviews: {e}")
            raise
        finally:
            session.close()
    
    def _make_serializable(self, obj: Any) -> Any:
        """
        Convert object to JSON-serializable format.
        
        Handles datetime objects, enums, and other non-serializable types.
        """
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "value"):  # Enum
            return obj.value
        elif hasattr(obj, "__dict__"):
            return self._make_serializable(obj.__dict__)
        else:
            return obj
    
    def generate_checkpoint_id(self) -> str:
        """Generate a unique checkpoint ID"""
        return f"ckpt_{uuid.uuid4().hex[:12]}"

