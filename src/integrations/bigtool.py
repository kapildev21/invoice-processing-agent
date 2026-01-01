"""
Bigtool Framework - Dynamic Tool Selection System

Intelligently selects the best tool from a pool based on:
- Capability match
- Context requirements
- Availability/cost
- Performance history
"""

import os
import yaml
import asyncio
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ToolConfig:
    """Configuration for a single tool"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.enabled = config.get("enabled", False)
        self.cost_per_call = config.get("cost_per_call", 0.0)
        self.priority = config.get("priority", 999)
        self.capabilities = config.get("capabilities", [])
        self.config = config
    
    def is_available(self) -> bool:
        """Check if tool is enabled and has required credentials"""
        if not self.enabled:
            return False
        
        # Check for required API keys
        if "api_key_env" in self.config:
            api_key = os.getenv(self.config["api_key_env"])
            if not api_key:
                return False
        
        return True


class BigtoolPicker:
    """
    Dynamic tool selector that chooses the best tool from a pool
    based on context and requirements.
    """
    
    def __init__(self, tools_config_path: Optional[str] = None):
        """
        Initialize BigtoolPicker with tool configuration.
        
        Args:
            tools_config_path: Path to tools.yaml file. If None, uses default.
        """
        if tools_config_path is None:
            tools_config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
        
        self.tools_config_path = Path(tools_config_path)
        self.tool_pools: Dict[str, Dict[str, ToolConfig]] = {}
        self.performance_history: Dict[str, Dict[str, float]] = {}  # tool_name -> {success_rate, avg_latency}
        
        self._load_config()
    
    def _load_config(self):
        """Load tool configuration from YAML file"""
        try:
            with open(self.tools_config_path, "r") as f:
                config = yaml.safe_load(f)
            
            for capability, tools in config.items():
                self.tool_pools[capability] = {}
                for tool_name, tool_config in tools.items():
                    self.tool_pools[capability][tool_name] = ToolConfig(tool_name, tool_config)
            
            logger.info(f"Loaded {len(self.tool_pools)} tool pools from {self.tools_config_path}")
        except FileNotFoundError:
            logger.warning(f"Tools config not found at {self.tools_config_path}, using defaults")
            self._load_default_config()
        except Exception as e:
            logger.error(f"Error loading tools config: {e}")
            self._load_default_config()
    
    def _load_default_config(self):
        """Load default tool configuration"""
        # Minimal default config for demo purposes
        self.tool_pools = {
            "ocr": {
                "tesseract": ToolConfig("tesseract", {
                    "enabled": True,
                    "cost_per_call": 0.0,
                    "priority": 1,
                    "capabilities": ["local_execution"]
                })
            },
            "erp": {
                "mock_erp": ToolConfig("mock_erp", {
                    "enabled": True,
                    "cost_per_call": 0.0,
                    "priority": 1,
                    "capabilities": ["demo_mode"]
                })
            },
            "storage": {
                "local_fs": ToolConfig("local_fs", {
                    "enabled": True,
                    "cost_per_call": 0.0,
                    "priority": 1,
                    "capabilities": ["local_storage"]
                })
            }
        }
    
    async def select(
        self,
        capability: str,
        context: Optional[Dict[str, Any]] = None,
        pool_hint: Optional[List[str]] = None
    ) -> str:
        """
        Select the best tool from a capability pool.
        
        Args:
            capability: Tool capability category (e.g., "ocr", "erp", "email")
            context: Contextual requirements (e.g., {"high_quality_required": True})
            pool_hint: Preferred tool names to consider first
        
        Returns:
            Selected tool name
        
        Raises:
            ValueError: If no available tool found for capability
        """
        if context is None:
            context = {}
        
        if capability not in self.tool_pools:
            raise ValueError(f"Unknown capability: {capability}")
        
        available_tools = [
            tool for tool in self.tool_pools[capability].values()
            if tool.is_available()
        ]
        
        if not available_tools:
            raise ValueError(f"No available tools for capability: {capability}")
        
        # Filter by pool_hint if provided
        if pool_hint:
            available_tools = [
                tool for tool in available_tools
                if tool.name in pool_hint
            ]
            if not available_tools:
                # Fallback to all available if hint doesn't match
                available_tools = [
                    tool for tool in self.tool_pools[capability].values()
                    if tool.is_available()
                ]
        
        # Score tools based on multiple factors
        scored_tools = []
        for tool in available_tools:
            score = self._score_tool(tool, context)
            scored_tools.append((score, tool))
        
        # Sort by score (higher is better), then by priority (lower is better)
        scored_tools.sort(key=lambda x: (-x[0], x[1].priority))
        
        selected_tool = scored_tools[0][1]
        logger.info(
            f"Selected tool '{selected_tool.name}' for capability '{capability}' "
            f"(score: {scored_tools[0][0]:.2f})"
        )
        
        return selected_tool.name
    
    def _score_tool(self, tool: ToolConfig, context: Dict[str, Any]) -> float:
        """
        Score a tool based on context requirements.
        
        Returns:
            Score from 0.0 to 100.0 (higher is better)
        """
        score = 50.0  # Base score
        
        # Priority factor (lower priority number = higher score)
        priority_bonus = (10 - min(tool.priority, 10)) * 2
        score += priority_bonus
        
        # Cost factor (lower cost = higher score)
        if tool.cost_per_call == 0:
            score += 10
        elif tool.cost_per_call < 0.001:
            score += 5
        
        # Capability matching
        required_caps = context.get("required_capabilities", [])
        if required_caps:
            matching_caps = set(required_caps) & set(tool.capabilities)
            score += len(matching_caps) * 5
        
        # Context-specific scoring
        if context.get("high_quality_required") and "high_accuracy" in tool.capabilities:
            score += 15
        if context.get("cost_sensitive") and tool.cost_per_call == 0:
            score += 10
        if context.get("fast_execution") and "local_execution" in tool.capabilities:
            score += 10
        
        # Performance history
        if tool.name in self.performance_history:
            history = self.performance_history[tool.name]
            success_rate = history.get("success_rate", 0.5)
            score += success_rate * 20
        
        return min(score, 100.0)
    
    async def execute(self, tool_name: str, capability: str, **kwargs) -> Any:
        """
        Execute a selected tool with fallback logic.
        
        Args:
            tool_name: Name of the tool to execute
            capability: Tool capability category
            **kwargs: Tool-specific parameters
        
        Returns:
            Tool execution result
        
        Raises:
            ValueError: If tool not found
            RuntimeError: If tool execution fails
        """
        if capability not in self.tool_pools:
            raise ValueError(f"Unknown capability: {capability}")
        
        if tool_name not in self.tool_pools[capability]:
            raise ValueError(f"Tool '{tool_name}' not found in capability '{capability}'")
        
        tool_config = self.tool_pools[capability][tool_name]
        
        if not tool_config.is_available():
            # Try to find a fallback
            logger.warning(f"Tool '{tool_name}' not available, attempting fallback")
            fallback_tool = await self.select(capability, kwargs.get("context", {}))
            if fallback_tool == tool_name:
                raise RuntimeError(f"Tool '{tool_name}' not available and no fallback found")
            tool_name = fallback_tool
            tool_config = self.tool_pools[capability][tool_name]
        
        # Execute tool (delegates to specific tool implementations)
        try:
            result = await self._execute_tool(tool_name, capability, tool_config, **kwargs)
            
            # Update performance history
            self._update_performance(tool_name, success=True)
            
            return result
        except Exception as e:
            self._update_performance(tool_name, success=False)
            logger.error(f"Tool execution failed for '{tool_name}': {e}")
            raise RuntimeError(f"Tool execution failed: {e}") from e
    
    async def _execute_tool(
        self,
        tool_name: str,
        capability: str,
        tool_config: ToolConfig,
        **kwargs
    ) -> Any:
        """
        Execute a specific tool implementation.
        
        This method dispatches to tool-specific execution logic.
        In a production system, this would call actual tool APIs.
        """
        # Mock implementations for demo purposes
        if capability == "ocr":
            return await self._execute_ocr_tool(tool_name, **kwargs)
        elif capability == "enrichment":
            return await self._execute_enrichment_tool(tool_name, **kwargs)
        elif capability == "erp":
            return await self._execute_erp_tool(tool_name, **kwargs)
        elif capability == "email":
            return await self._execute_email_tool(tool_name, **kwargs)
        elif capability == "storage":
            return await self._execute_storage_tool(tool_name, **kwargs)
        else:
            raise ValueError(f"No execution logic for capability: {capability}")
    
    async def _execute_ocr_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute OCR tool"""
        # Mock implementation
        if tool_name == "tesseract":
            return {
                "text": kwargs.get("text", "Mock OCR text"),
                "confidence": 0.95,
                "tool": "tesseract"
            }
        elif tool_name == "google_vision":
            return {
                "text": kwargs.get("text", "Mock Google Vision text"),
                "confidence": 0.98,
                "tool": "google_vision"
            }
        else:
            return {"text": "", "confidence": 0.0, "tool": tool_name}
    
    async def _execute_enrichment_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute enrichment tool"""
        vendor_name = kwargs.get("vendor_name", "")
        return {
            "vendor_name": vendor_name,
            "normalized_name": vendor_name.upper(),
            "tax_id": kwargs.get("tax_id"),
            "enriched": True,
            "tool": tool_name
        }
    
    async def _execute_erp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute ERP tool"""
        action = kwargs.get("action", "fetch_po")
        
        if action == "fetch_po":
            return {
                "pos": [
                    {
                        "po_id": "PO-001",
                        "vendor": kwargs.get("vendor_name", ""),
                        "amount": 15000.0,
                        "status": "open"
                    }
                ],
                "tool": tool_name
            }
        elif action == "post":
            return {
                "erp_txn_id": f"TXN-{tool_name}-{kwargs.get('invoice_id', 'UNKNOWN')}",
                "posted": True,
                "tool": tool_name
            }
        else:
            return {"result": "success", "tool": tool_name}
    
    async def _execute_email_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute email tool"""
        recipients = kwargs.get("to", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        elif not isinstance(recipients, list):
            recipients = []
        
        return {
            "sent": True,
            "message_id": f"msg-{tool_name}-{uuid.uuid4().hex[:8]}",
            "delivered": True,
            "recipients": recipients,
            "tool": tool_name
        }
    
    async def _execute_storage_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute storage tool"""
        action = kwargs.get("action", "save")
        
        if action == "save":
            return {
                "saved": True,
                "path": f"./data/{kwargs.get('filename', 'unknown')}",
                "tool": tool_name
            }
        else:
            return {"result": "success", "tool": tool_name}
    
    def _update_performance(self, tool_name: str, success: bool):
        """Update performance history for a tool"""
        if tool_name not in self.performance_history:
            self.performance_history[tool_name] = {
                "success_rate": 1.0 if success else 0.0,
                "total_calls": 1,
                "successful_calls": 1 if success else 0
            }
        else:
            history = self.performance_history[tool_name]
            history["total_calls"] += 1
            if success:
                history["successful_calls"] += 1
            history["success_rate"] = history["successful_calls"] / history["total_calls"]

