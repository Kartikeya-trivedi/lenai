"""
Config-driven model registry — add a new model by editing YAML, no code changes.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

from app.utils.logging import get_logger

logger = get_logger(__name__)

REGISTRY_PATH = Path(__file__).parent.parent.parent / "model_registry.yaml"


class ModelConfig:
    """Parsed model configuration."""

    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.modality: str = config["modality"]
        self.endpoint: str = config["endpoint"]
        self.health_check: str = config.get("health_check", "/health")
        self.input_schema: Dict[str, Any] = config.get("input_schema", {})
        self.output_format: str = config.get("output_format", "json")
        self.max_concurrent: int = config.get("max_concurrent", 1)
        self.timeout_seconds: int = config.get("timeout_seconds", 300)
        self.resource_limits: Dict[str, str] = config.get("resource_limits", {})

    @property
    def health_url(self) -> str:
        return f"{self.endpoint}{self.health_check}"

    def __repr__(self) -> str:
        return f"<ModelConfig {self.name} [{self.modality}] @ {self.endpoint}>"


class ModelRegistry:
    """
    Loads model configuration from YAML at startup.
    Adding a new model = adding a YAML entry + restarting the service.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or REGISTRY_PATH
        self._models: Dict[str, ModelConfig] = {}
        self._load()

    def _load(self) -> None:
        """Load models from YAML config file."""
        if not self.config_path.exists():
            logger.warning("model_registry_not_found", path=str(self.config_path))
            return

        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}

        models = data.get("models", {})
        for name, config in models.items():
            self._models[name] = ModelConfig(name, config)

        logger.info(
            "model_registry_loaded",
            model_count=len(self._models),
            models=list(self._models.keys()),
        )

    def get_model_config(self, modality: str) -> Optional[ModelConfig]:
        """Get the first model config for a given modality."""
        for model in self._models.values():
            if model.modality == modality:
                return model
        return None

    def get_model_by_name(self, name: str) -> Optional[ModelConfig]:
        """Get a model config by its registry name."""
        return self._models.get(name)

    def get_all_models(self) -> List[ModelConfig]:
        """Get all registered models."""
        return list(self._models.values())

    def get_models_by_modality(self, modality: str) -> List[ModelConfig]:
        """Get all models for a given modality."""
        return [m for m in self._models.values() if m.modality == modality]

    async def check_model_health(self, modality: str) -> tuple[bool, float]:
        """Check if a model for the given modality is healthy."""
        model = self.get_model_config(modality)
        if model is None:
            return False, 0.0

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(model.health_url)
                latency = (time.monotonic() - start) * 1000
                healthy = resp.status_code < 500
                return healthy, round(latency, 2)
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.warning(
                "model_health_check_failed",
                model=model.name,
                error=str(e),
            )
            return False, round(latency, 2)

    def validate_input(self, modality: str, params: dict) -> dict:
        """
        Validate input params against the model's input schema.
        Returns cleaned params.
        """
        model = self.get_model_config(modality)
        if model is None:
            raise ValueError(f"No model registered for modality: {modality}")

        validated = {}
        for field_name, field_spec in model.input_schema.items():
            value = params.get(field_name)
            required = field_spec.get("required", False)
            default = field_spec.get("default")

            if value is None and required:
                raise ValueError(f"Missing required field: {field_name}")

            if value is None:
                value = default

            if value is not None:
                # Type checking
                expected_type = field_spec.get("type", "string")
                if expected_type == "integer" and not isinstance(value, int):
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        raise ValueError(f"{field_name} must be an integer")

                # Range checking
                min_val = field_spec.get("min")
                max_val = field_spec.get("max")
                if min_val is not None and value < min_val:
                    raise ValueError(f"{field_name} must be >= {min_val}")
                if max_val is not None and value > max_val:
                    raise ValueError(f"{field_name} must be <= {max_val}")

            validated[field_name] = value

        return validated


# Module-level singleton
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get or create the model registry singleton."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
