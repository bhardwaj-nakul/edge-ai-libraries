"""
Data loader module for the RSU Monitoring System
"""
import json
import logging
from typing import Optional
from pathlib import Path

from models import (
    MonitoringData, IntersectionData, RegionCount, 
    VLMAnalysis, WeatherData, CameraData, TrafficContext
)

logger = logging.getLogger(__name__)


def load_monitoring_data(file_path: str = "data.json") -> Optional[MonitoringData]:
    """
    Load monitoring data from JSON file and convert to data classes
    
    Args:
        file_path: Path to the JSON data file
        
    Returns:
        MonitoringData object or None if loading fails
    """
    try:
        if not Path(file_path).exists():
            logger.error(f"Data file {file_path} not found")
            return None
            
        with open(file_path, 'r') as f:
            raw_data = json.load(f)
        
        # Parse region counts
        region_counts = {}
        for region_id, counts in raw_data["data"]["region_counts"].items():
            region_counts[region_id] = RegionCount(
                vehicle=counts["vehicle"],
                pedestrian=counts["pedestrian"]
            )
        
        # Parse intersection data
        intersection_data = IntersectionData(
            intersection_id=raw_data["data"]["intersection_id"],
            intersection_name=raw_data["data"]["intersection_name"],
            latitude=raw_data["data"]["latitude"],
            longitude=raw_data["data"]["longitude"],
            timestamp=raw_data["data"]["timestamp"],
            northbound_density=raw_data["data"]["northbound_density"],
            southbound_density=raw_data["data"]["southbound_density"],
            eastbound_density=raw_data["data"]["eastbound_density"],
            westbound_density=raw_data["data"]["westbound_density"],
            total_density=raw_data["data"]["total_density"],
            region_counts=region_counts
        )
        
        # Parse camera data
        camera_images = {}
        for camera_name, camera_info in raw_data["camera_images"].items():
            camera_images[camera_name] = CameraData(
                camera_id=camera_info["camera_id"],
                direction=camera_info["direction"],
                timestamp=camera_info["timestamp"],
                image_base64=camera_info.get("image_base64")
            )
        
        # Parse traffic context
        traffic_context = TrafficContext(
            analysis_period=raw_data["vlm_analysis"]["traffic_context"]["analysis_period"],
            avg_densities=raw_data["vlm_analysis"]["traffic_context"]["avg_densities"],
            peak_densities=raw_data["vlm_analysis"]["traffic_context"]["peak_densities"]
        )
        
        # Parse VLM analysis
        vlm_analysis = VLMAnalysis(
            analysis=raw_data["vlm_analysis"]["analysis"],
            high_density_directions=raw_data["vlm_analysis"]["high_density_directions"],
            analysis_timestamp=raw_data["vlm_analysis"]["analysis_timestamp"],
            current_high_directions=raw_data["vlm_analysis"]["current_high_directions"],
            analysis_age_minutes=raw_data["vlm_analysis"]["analysis_age_minutes"],
            traffic_context=traffic_context,
            alerts=raw_data["vlm_analysis"]["alerts"]
        )
        
        # Parse weather data
        weather_data = WeatherData(
            timestamp=raw_data["weather_data"]["timestamp"],
            temperature_celsius=raw_data["weather_data"]["temperature_celsius"],
            humidity_percent=raw_data["weather_data"]["humidity_percent"],
            precipitation_mm=raw_data["weather_data"]["precipitation_mm"],
            wind_speed_kph=raw_data["weather_data"]["wind_speed_kph"],
            wind_direction_degrees=raw_data["weather_data"]["wind_direction_degrees"],
            conditions=raw_data["weather_data"]["conditions"]
        )
        
        # Create complete monitoring data object
        monitoring_data = MonitoringData(
            timestamp=raw_data["timestamp"],
            intersection_id=raw_data["intersection_id"],
            data=intersection_data,
            camera_images=camera_images,
            vlm_analysis=vlm_analysis,
            weather_data=weather_data
        )
        
        return monitoring_data
        
    except Exception as e:
        logger.error(f"Error loading monitoring data: {str(e)}")
        return None


def get_last_update_time(monitoring_data: MonitoringData) -> str:
    """
    Get formatted last update time
    
    Args:
        monitoring_data: MonitoringData object
        
    Returns:
        Formatted timestamp string
    """
    try:
        from datetime import datetime
        timestamp = datetime.fromisoformat(monitoring_data.timestamp.replace('Z', '+00:00'))
        return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        return monitoring_data.timestamp