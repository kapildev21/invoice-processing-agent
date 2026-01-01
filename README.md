# LangGraph Invoice Processing Agent

A production-ready LangGraph agent that orchestrates a 12-stage invoice processing workflow with Human-in-the-Loop (HITL) checkpointing, MCP client integration, and dynamic tool selection via Bigtool.

## Features

- **12-Stage Workflow**: Complete invoice processing pipeline from intake to completion
- **Human-in-the-Loop**: Checkpointing and resume capabilities for manual review
- **Dynamic Tool Selection**: Bigtool framework for intelligent tool selection
- **MCP Integration**: COMMON and ATLAS server clients for distributed capabilities
- **State Persistence**: SQLite/PostgreSQL checkpoint storage
- **REST API**: FastAPI endpoints for workflow execution and human review
- **Comprehensive Logging**: Structured JSON logging throughout

## Project Structure

```
invoice-processing-agent/
├── src/
│   ├── agents/           # LangGraph agent and nodes
│   ├── integrations/     # MCP clients, Bigtool, checkpoint store
│   ├── api/              # FastAPI application
│   ├── config/           # Configuration files
│   └── utils/            # Utilities and helpers
├── tests/                # Test suite
├── demo/                 # Demo scripts and sample data
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Installation

**Note: No API keys required!** This implementation works in demo mode with mock implementations.

1. **Clone the repository** (or navigate to the project directory)

2. **Create a virtual environment**:
```bash
python3.10+ -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Initialize the database**:
```bash
python setup.py
```

This creates the SQLite database and required tables. No API keys needed!

## Quick Start

### Run the Demo

```bash
python demo/run_demo.py
```

### Start the API Server

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### API Endpoints

- **POST** `/workflow/execute` - Start a new workflow execution
- **GET** `/workflow/{workflow_id}/status` - Get workflow status
- **POST** `/workflow/{workflow_id}/resume` - Resume a paused workflow
- **GET** `/human-review/pending` - List pending reviews
- **POST** `/human-review/decision` - Submit human review decision

## Workflow Stages

1. **INTAKE** - Accept and validate invoice payload
2. **UNDERSTAND** - OCR and parse invoice data
3. **PREPARE** - Normalize vendor and compute risk flags
4. **RETRIEVE** - Fetch matching PO/GRN from ERP
5. **MATCH_TWO_WAY** - Perform 2-way matching
6. **CHECKPOINT_HITL** - Create checkpoint if match fails
7. **HITL_DECISION** - Handle human decision and resume
8. **RECONCILE** - Build accounting entries
9. **APPROVE** - Apply approval policies
10. **POSTING** - Post to ERP system
11. **NOTIFY** - Send notifications
12. **COMPLETE** - Finalize and audit

## Configuration

Edit `src/config/workflow.json` to customize workflow behavior and `src/config/tools.yaml` to configure tool pools.

## Testing

```bash
pytest tests/ -v
```


