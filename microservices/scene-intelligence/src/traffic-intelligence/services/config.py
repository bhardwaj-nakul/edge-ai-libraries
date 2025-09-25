"""Configuration service for traffic intelligence."""

import os
import json
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class ConfigService:
    """
    Configuration service for traffic intelligence.
    
    Manages configuration for single intersection monitoring,
    MQTT topics, weather API, and VLM service settings.
    """
    
    def __init__(self):
        """Initialize configuration service."""
        self.config = self._load_config()
        logger.info("Configuration service initialized", 
                   intersection_id=self.get_intersection_id())
    
    def _load_config(self) -> dict:
        """Load configuration from environment and file."""
        config = {}
        
        # Load from config file if specified
        config_file = os.getenv("TRAFFIC_INTELLIGENCE_CONFIG", "config/traffic_intelligence.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    file_config = json.load(f)
                config.update(file_config)
                logger.info("Loaded configuration from file", path=config_file)
            except Exception as e:
                logger.warning("Failed to load config file", path=config_file, error=str(e))
               
        return config

    
    def get_intersection_id(self) -> str:
        """Get the intersection ID."""
        return self.config.get("intersection", {}).get("id", "cb1cf1a0-b936-4d47-9221-3fd5cf24857d")
    
    def get_intersection_name(self) -> str:
        """Get the intersection name."""
        return self.config.get("intersection", {}).get("name", "Intersection-1")
    
    def get_intersection_coordinates(self) -> tuple:
        """Get intersection coordinates (lat, lon)."""
        intersection = self.config.get("intersection", {})
        return (
            intersection.get("latitude", 33.3091336),
            intersection.get("longitude", -111.9353095)
        )
    
    def get_camera_topics(self) -> List[str]:
        """Get MQTT camera topics."""
        return self.config.get("mqtt", {}).get("camera_topics", [
            "scenescape/data/camera/camera1",
            "scenescape/data/camera/camera2", 
            "scenescape/data/camera/camera3",
            "scenescape/data/camera/camera4"
        ])

    def get_image_topics(self) -> List[str]:
        """Get MQTT image topics."""
        return self.config.get("mqtt", {}).get("image_topics", [
            "scenescape/image/camera/camera1",
            "scenescape/image/camera/camera2", 
            "scenescape/image/camera/camera3",
            "scenescape/image/camera/camera4"
        ])
    
    def get_mqtt_config(self) -> dict:
        """Get MQTT configuration."""
        return self.config.get("mqtt", {})
    
    def get_weather_config(self) -> dict:
        """Get weather API configuration."""
        return self.config.get("weather", {})
    
    def get_vlm_config(self) -> dict:
        """Get VLM service configuration."""
        return self.config.get("vlm", {})
    
    def get_traffic_config(self) -> dict:
        """Get traffic analysis configuration."""
        return self.config.get("traffic", {})
    
    def get_high_density_threshold(self) -> int:
        """Get high density threshold for traffic analysis."""
        return self.config.get("traffic", {}).get("high_density_threshold", 5)
    
    def update_config(self, key: str, value: any) -> None:
        """Update configuration value."""
        keys = key.split('.')
        config_ref = self.config
        
        # Navigate to the nested key
        for k in keys[:-1]:
            if k not in config_ref:
                config_ref[k] = {}
            config_ref = config_ref[k]
        
        # Set the value
        config_ref[keys[-1]] = value
        logger.info("Configuration updated", key=key, value=value)