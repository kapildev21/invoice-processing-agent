"""
FastAPI Application

Main FastAPI app with workflow execution and human review endpoints.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from src.api.routes import workflow, human_review
from src.agents.graph_builder import build_invoice_graph
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Global graph instance
workflow_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Initializes graph and dependencies on startup,
    cleans up on shutdown.
    """
    global workflow_graph
    
    logger.info("Starting Invoice Processing Agent API...")
    
    # Initialize workflow graph
    try:
        workflow_graph = build_invoice_graph()
        logger.info("✓ Workflow graph initialized")
    except Exception as e:
        logger.error(f"Failed to initialize workflow graph: {e}")
        raise
    
    yield
    
    # Cleanup
    logger.info("Shutting down Invoice Processing Agent API...")
    workflow_graph = None


# Create FastAPI app
app = FastAPI(
    title="Invoice Processing Agent",
    description="LangGraph-based invoice processing workflow with HITL checkpointing",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
app.include_router(human_review.router, prefix="/human-review", tags=["human-review"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Invoice Processing Agent",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "graph_initialized": workflow_graph is not None
    }

