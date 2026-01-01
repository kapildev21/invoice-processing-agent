"""
Setup script for Invoice Processing Agent

Initializes database and creates necessary directories.
"""

import asyncio
from pathlib import Path
from src.integrations.checkpoint_store import CheckpointStore
from src.config.settings import settings


async def setup():
    """Initialize database and directories"""
    print("Setting up Invoice Processing Agent...")
    
    # Create data directory
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
    print(f"✓ Created data directory: {data_dir}")
    
    # Initialize checkpoint store (creates database tables)
    checkpoint_store = CheckpointStore()
    print(f"✓ Initialized checkpoint store: {settings.DATABASE_URL}")
    
    print("\nSetup complete!")
    print("\nNext steps:")
    print("1. Copy .env.example to .env and configure your API keys")
    print("2. Run the demo: python demo/run_demo.py")
    print("3. Start the API: uvicorn src.api.main:app --reload")


if __name__ == "__main__":
    asyncio.run(setup())

