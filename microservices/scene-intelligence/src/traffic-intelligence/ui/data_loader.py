"""
Data loader module for the RSU Monitoring System
"""
import json
import logging
import requests
from typing import Optional
from pathlib import Path

from models import (
    MonitoringData, IntersectionData, RegionCount, 
    VLMAnalysis, WeatherData, CameraData, TrafficContext
)

logger = logging.getLogger(__name__)


def load_monitoring_data_from_api(api_url: str = "http://localhost:8081/api/v1/traffic/current") -> Optional[MonitoringData]:
    """
    Load monitoring data from the traffic intelligence API
    
    Args:
        api_url: URL of the traffic intelligence API endpoint
        
    Returns:
        MonitoringData object or None if loading fails
    """
    try:
        logger.info(f"Fetching data from API: {api_url}")
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        raw_data = response.json()
        
        # Parse the API response and convert to UI data structure
        return parse_api_response(raw_data)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data from API: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing API response: {str(e)}")
        return None


def parse_api_response(raw_data: dict) -> Optional[MonitoringData]:
    """
    Parse the traffic intelligence API response and convert to MonitoringData
    
    Args:
        raw_data: Raw API response dictionary
        
    Returns:
        MonitoringData object or None if parsing fails
    """
    try:
        # Extract traffic data
        traffic_data = raw_data.get("data", {})
        
        # Create region counts mapping pedestrian data from API
        # Map directional pedestrian counts to regions
        region_counts = {
            "region_1": RegionCount(  # North
                vehicle=0,  # API doesn't provide region-specific vehicle counts
                pedestrian=traffic_data.get("north_pedestrian", 0)
            ),
            "region_2": RegionCount(  # South  
                vehicle=0,
                pedestrian=traffic_data.get("south_pedestrian", 0)
            ),
            "region_3": RegionCount(  # East
                vehicle=0,
                pedestrian=traffic_data.get("east_pedestrian", 0)
            ),
            "region_4": RegionCount(  # West
                vehicle=0,
                pedestrian=traffic_data.get("west_pedestrian", 0)
            )
        }
        
        # Parse intersection data
        # Create IntersectionData from the main data
        # Map API field names to model field names
        intersection_data = IntersectionData(
            intersection_id=traffic_data["intersection_id"],
            intersection_name=traffic_data["intersection_name"],
            latitude=traffic_data["latitude"],
            longitude=traffic_data["longitude"],
            timestamp=traffic_data["timestamp"],
            northbound_density=traffic_data.get("north_camera", 0),  # Map north_camera to northbound_density
            southbound_density=traffic_data.get("south_camera", 0),  # Map south_camera to southbound_density
            eastbound_density=traffic_data.get("east_camera", 0),    # Map east_camera to eastbound_density
            westbound_density=traffic_data.get("west_camera", 0),    # Map west_camera to westbound_density
            total_density=traffic_data.get("total_density", 0),
            region_counts=region_counts,  # Use the region_counts created above
            total_pedestrian_count=traffic_data.get("total_pedestrian_count", 0)  # Get total pedestrian count from API
        )
        
        # Parse camera data - handle the new API structure
        camera_images = {}
        camera_data = raw_data.get("camera_images", {})
        
        # Handle the new API format where cameras are named like "west_camera", "north_camera", etc.
        for camera_key, camera_info in camera_data.items():
            if isinstance(camera_info, dict):
                camera_images[camera_key] = camera_info  # Store as dict for UI compatibility
            else:
                # Fallback: create CameraData object if needed for old format
                camera_images[camera_key] = CameraData(
                    camera_id=camera_info.get("camera_id", camera_key),
                    direction=camera_info.get("direction", "unknown"),
                    timestamp=camera_info.get("timestamp", ""),
                    image_base64=camera_info.get("image_base64")
                )
        
        # Parse VLM analysis
        vlm_data = raw_data.get("vlm_analysis", {})
        
        # Create traffic context (simplified for API data)
        traffic_context = TrafficContext(
            analysis_period={"start": "", "end": ""},
            avg_densities={
                "northbound": traffic_data.get("north_camera", 0),
                "southbound": traffic_data.get("south_camera", 0),
                "eastbound": traffic_data.get("east_camera", 0),
                "westbound": traffic_data.get("west_camera", 0)
            },
            peak_densities={
                "northbound": traffic_data.get("north_camera", 0),
                "southbound": traffic_data.get("south_camera", 0),
                "eastbound": traffic_data.get("east_camera", 0),
                "westbound": traffic_data.get("west_camera", 0)
            }
        )
        
        # Process alerts from the new API format
        alerts = []
        api_alerts = vlm_data.get("alerts", [])
        for alert in api_alerts:
            if isinstance(alert, dict):
                # Store the full alert structure for UI processing
                alerts.append(alert)
            else:
                # Fallback for string format
                alerts.append(str(alert))
        
        # Process recommendations from the new API format
        recommendations = vlm_data.get("recommendations", [])
        
        # Calculate high density directions (threshold of 3+ vehicles)
        high_density_directions = []
        current_high_directions = []
        if traffic_data.get("north_camera", 0) >= 3:
            high_density_directions.append("northbound")
            current_high_directions.append("northbound")
        if traffic_data.get("south_camera", 0) >= 3:
            high_density_directions.append("southbound")
            current_high_directions.append("southbound")
        if traffic_data.get("east_camera", 0) >= 3:
            high_density_directions.append("eastbound")
            current_high_directions.append("eastbound")
        if traffic_data.get("west_camera", 0) >= 3:
            high_density_directions.append("westbound")
            current_high_directions.append("westbound")
        
        vlm_analysis = VLMAnalysis(
            analysis=vlm_data.get("traffic_summary", "No analysis available"),
            high_density_directions=high_density_directions,
            analysis_timestamp=vlm_data.get("analysis_timestamp", ""),
            current_high_directions=current_high_directions,
            analysis_age_minutes=0.0,  # Will be calculated if needed
            traffic_context=traffic_context,
            alerts=alerts,
            recommendations=recommendations
        )
        
        # Parse weather data
        weather_data_raw = raw_data.get("weather_data", {})
        
        # Extract wind information from the new API format
        wind_speed_str = weather_data_raw.get("wind_speed", "0 mph")
        wind_direction_str = weather_data_raw.get("wind_direction", "N")
        
        # Parse wind speed to mph
        import re
        speed_match = re.search(r'(\d+)', wind_speed_str)
        wind_speed_mph = float(speed_match.group(1)) if speed_match else 0.0
        
        # Convert wind direction to degrees
        direction_map = {
            "N": 0, "NNE": 22, "NE": 45, "ENE": 67,
            "E": 90, "ESE": 112, "SE": 135, "SSE": 157,
            "S": 180, "SSW": 202, "SW": 225, "WSW": 247,
            "W": 270, "WNW": 292, "NW": 315, "NNW": 337
        }
        wind_direction_degrees = direction_map.get(wind_direction_str.upper(), 0)
        
        # Estimate precipitation based on forecast and is_precipitation flag
        precipitation_mm = 0.0
        if weather_data_raw.get("is_precipitation", False):
            # Estimate precipitation amount based on forecast text
            forecast = weather_data_raw.get("detailed_forecast", "").lower()
            if "heavy" in forecast or "storm" in forecast:
                precipitation_mm = 10.0
            elif "moderate" in forecast or "rain" in forecast:
                precipitation_mm = 5.0
            elif "light" in forecast or "slight" in forecast or "chance" in forecast:
                precipitation_mm = 1.0
        
        # Convert temperature to Fahrenheit if needed (API provides in F)
        temperature_f = weather_data_raw.get("temperature", 70)
        
        # Estimate humidity (API doesn't provide this, use reasonable default based on precipitation)
        humidity = 50
        if weather_data_raw.get("is_precipitation", False):
            humidity = 75
        elif "clear" in weather_data_raw.get("short_forecast", "").lower():
            humidity = 40
        
        # Use short_forecast for conditions if available, otherwise detailed_forecast
        conditions = weather_data_raw.get("short_forecast", 
                                         weather_data_raw.get("detailed_forecast", "Unknown"))
        
        weather_data = WeatherData(
            timestamp=weather_data_raw.get("fetched_at", ""),
            temperature_fahrenheit=temperature_f,
            humidity_percent=humidity,
            precipitation_mm=precipitation_mm,
            wind_speed_mph=wind_speed_mph,
            wind_direction_degrees=wind_direction_degrees,
            conditions=conditions
        )
        
        # Create complete monitoring data object
        monitoring_data = MonitoringData(
            timestamp=traffic_data.get("timestamp", ""),
            intersection_id=traffic_data.get("intersection_id", "intersection_1"),
            data=intersection_data,
            camera_images=camera_images,
            vlm_analysis=vlm_analysis,
            weather_data=weather_data
        )
        
        return monitoring_data
        
    except Exception as e:
        logger.error(f"Error parsing API response: {str(e)}")
        return None


def convert_fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius"""
    return (fahrenheit - 32) * 5.0 / 9.0
def load_monitoring_data(file_path: str = "data.json", use_api: bool = True, api_url: str = None) -> Optional[MonitoringData]:
    """
    Load monitoring data from API or JSON file
    
    Args:
        file_path: Path to the JSON data file (fallback)
        use_api: Whether to use API endpoint (default: True)
        api_url: API endpoint URL (if None, uses default)
        
    Returns:
        MonitoringData object or None if loading fails
    """
    if use_api:
        # Try to load from API first
        api_data = load_monitoring_data_from_api(api_url) if api_url else load_monitoring_data_from_api()
        if api_data:
            return api_data
        logger.warning("Failed to load from API, falling back to JSON file")
    
    # Fallback to original JSON file loading
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
            temperature_fahrenheit=raw_data["weather_data"]["temperature_fahrenheit"],
            humidity_percent=raw_data["weather_data"]["humidity_percent"],
            precipitation_mm=raw_data["weather_data"]["precipitation_mm"],
            wind_speed_mph=raw_data["weather_data"]["wind_speed_mph"],
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
        logger.error(f"Error loading monitoring data from file: {str(e)}")
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