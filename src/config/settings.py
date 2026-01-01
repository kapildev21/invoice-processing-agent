"""
Application Settings

Environment configuration using Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    DATABASE_URL: str = "sqlite:///./invoice_processing.db"
    
    # MCP Servers
    COMMON_SERVER_URL: str = "http://localhost:8001"
    ATLAS_SERVER_URL: str = "http://localhost:8002"
    
    # Workflow Configuration
    MATCH_THRESHOLD: float = 0.90
    TWO_WAY_TOLERANCE_PCT: int = 5
    
    # Tool API Keys
    GOOGLE_VISION_KEY: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    
    # Enrichment Services
    CLEARBIT_API_KEY: Optional[str] = None
    PEOPLE_DATA_LABS_API_KEY: Optional[str] = None
    
    # Email Services
    SENDGRID_API_KEY: Optional[str] = None
    SMARTLEAD_API_KEY: Optional[str] = None
    AWS_SES_REGION: str = "us-east-1"
    
    # ERP Configuration
    SAP_SANDBOX_URL: str = "http://localhost:8003"
    NETSUITE_API_KEY: Optional[str] = None
    
    # Application
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()

