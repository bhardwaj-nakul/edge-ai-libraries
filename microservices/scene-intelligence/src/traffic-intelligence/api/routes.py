"""API routes for traffic intelligence service."""

from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
import structlog

from services.data_aggregator import DataAggregatorService
from models import WeatherType, IncidentType


logger = structlog.get_logger(__name__)

router = APIRouter()


def get_data_aggregator(request):
    """Dependency to get data aggregator service from app state."""
    return request.app.state.data_aggregator


def get_weather_service(request):
    """Dependency to get weather service from app state."""
    return request.app.state.weather_service


def get_vlm_service(request):
    """Dependency to get VLM service from app state."""
    return request.app.state.vlm_service


def get_config_service(request):
    """Dependency to get config service from app state."""
    return request.app.state.config


@router.get("/traffic/current", response_model=Dict[str, Any])
async def get_current_traffic_intelligence(request: Request) -> Dict[str, Any]:
    """
    Get current traffic intelligence data for the intersection.
    
    Returns complete traffic intelligence response matching data.json schema
    with weather data and VLM analysis.
    """
    try:
        data_aggregator: DataAggregatorService = get_data_aggregator(request)
        
        # Get current traffic intelligence
        traffic_response = await data_aggregator.get_current_traffic_intelligence()
        
        if not traffic_response:
            raise HTTPException(status_code=404, detail="No traffic data available")
        
        # Convert to dict for JSON response
        response_dict = {
            "timestamp": traffic_response.timestamp,
            "response_age": traffic_response.response_age if traffic_response.response_age else None,
            "intersection_id": traffic_response.intersection_id,
            "data": {
                "intersection_id": traffic_response.data.intersection_id,
                "intersection_name": traffic_response.data.intersection_name,
                "latitude": traffic_response.data.latitude,
                "longitude": traffic_response.data.longitude,
                "timestamp": traffic_response.data.timestamp.isoformat(),
                "north_camera": traffic_response.data.north_camera,
                "south_camera": traffic_response.data.south_camera,
                "east_camera": traffic_response.data.east_camera,
                "west_camera": traffic_response.data.west_camera,
                "total_density": traffic_response.data.total_density,
                "intersection_status": traffic_response.data.intersection_status,
                "north_pedestrian": traffic_response.data.north_pedestrian,
                "south_pedestrian": traffic_response.data.south_pedestrian,
                "east_pedestrian": traffic_response.data.east_pedestrian,
                "west_pedestrian": traffic_response.data.west_pedestrian,
                "total_pedestrian_count": traffic_response.data.total_pedestrian_count,
                "north_timestamp": traffic_response.data.north_timestamp,
                "south_timestamp": traffic_response.data.south_timestamp,
                "east_timestamp": traffic_response.data.east_timestamp,
                "west_timestamp": traffic_response.data.west_timestamp,
            },
            "camera_images": traffic_response.camera_images,
            "weather_data": {
                "name": traffic_response.weather_data.name,
                "temperature": traffic_response.weather_data.temperature,
                "temperature_unit": traffic_response.weather_data.temperature_unit,
                "detailed_forecast": traffic_response.weather_data.detailed_forecast,
                "short_forecast": traffic_response.weather_data.short_forecast,
                "wind_speed": traffic_response.weather_data.wind_speed,
                "wind_direction": traffic_response.weather_data.wind_direction,
                "wind_info": f"{traffic_response.weather_data.wind_speed.replace(' ', '')}/{traffic_response.weather_data.wind_direction}",
                "fetched_at": traffic_response.weather_data.fetched_at.isoformat(),
                "is_precipitation": traffic_response.weather_data.is_precipitation,
                "precipitation_prob": traffic_response.weather_data.precipitation_prob,
                "dewpoint": traffic_response.weather_data.dewpoint,
                "relative_humidity": traffic_response.weather_data.relative_humidity,
                "is_daytime": traffic_response.weather_data.is_daytime,
                "start_time": traffic_response.weather_data.start_time,
                "end_time": traffic_response.weather_data.end_time,
                "is_cached": traffic_response.weather_data.is_cached,
            },
            "vlm_analysis": {
                "traffic_summary": traffic_response.vlm_analysis.traffic_summary,
                "alerts": [
                    {
                        "alert_type": alert.alert_type.value,
                        "level": alert.level.value,
                        "description": alert.description,
                        "weather_related": alert.weather_related
                    }
                    for alert in traffic_response.vlm_analysis.alerts
                ],
                "recommendations": traffic_response.vlm_analysis.recommendations or [],
                "analysis_timestamp": traffic_response.vlm_analysis.analysis_timestamp.isoformat() if traffic_response.vlm_analysis.analysis_timestamp else None
            }
        }
        
        logger.info("Current traffic intelligence served",
                   intersection_id=traffic_response.intersection_id,
                   total_density=traffic_response.data.total_density,
                   total_pedestrian_count=traffic_response.data.total_pedestrian_count,
                   alerts_count=len(traffic_response.vlm_analysis.alerts))
        
        return response_dict
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get current traffic intelligence", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/weather/current")
async def get_current_weather(request: Request) -> Dict[str, Any]:
    """Get current weather data for the intersection location."""
    try:
        weather_service = get_weather_service(request)
        
        weather_data = await weather_service.get_current_weather()
        
        if not weather_data:
            raise HTTPException(status_code=404, detail="Weather data not available")
        
        # Ensure we have a WeatherData object
        if not hasattr(weather_data, 'name'):
            logger.error("Weather data is not a WeatherData object", weather_data_type=type(weather_data))
            raise HTTPException(status_code=500, detail="Invalid weather data format")
        
        return {
            "name": weather_data.name,
            "temperature": weather_data.temperature,
            "temperature_unit": weather_data.temperature_unit,
            "detailed_forecast": weather_data.detailed_forecast,
            "short_forecast": weather_data.short_forecast,
            "wind_speed": weather_data.wind_speed,
            "wind_direction": weather_data.wind_direction,
            "wind_info": f"{weather_data.wind_speed.replace(' ', '')}/{weather_data.wind_direction}",
            "fetched_at": weather_data.fetched_at.isoformat(),
            "is_precipitation": weather_data.is_precipitation,
            "precipitation_prob": weather_data.precipitation_prob,
            "dewpoint": weather_data.dewpoint,
            "relative_humidity": weather_data.relative_humidity,
            "is_daytime": weather_data.is_daytime,
            "start_time": weather_data.start_time,
            "end_time": weather_data.end_time,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get current weather", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/config")
async def get_service_config(request: Request) -> Dict[str, Any]:
    """Get service configuration (excluding sensitive data)."""
    try:
        config_service = get_config_service(request)
        
        # Get traffic config and add resolved incident type
        traffic_config = config_service.get_traffic_config().copy()
        traffic_config["incident_type"] = config_service.get_incident_type()
        traffic_config["incident_reporting_enabled"] = config_service.is_incident_reporting_enabled()
        
        return {
            "intersection": {
                "id": config_service.get_intersection_id(),
                "name": config_service.get_intersection_name(),
                "coordinates": config_service.get_intersection_coordinates()
            },
            "camera_topics": config_service.get_camera_topics(),
            "traffic": {
                "high_density_threshold": config_service.get_high_density_threshold(),
                **{k: v for k, v in traffic_config.items() 
                   if k != "high_density_threshold"}
            },
            "weather": {
                "cache_duration_minutes": config_service.get_weather_config().get("cache_duration_minutes", 15)
            }
        }
        
    except Exception as e:
        logger.error("Failed to get service config", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/config/threshold")
async def update_threshold(
    request: Request,
    threshold: int = Query(ge=1, le=50, description="New high density threshold")
) -> Dict[str, Any]:
    """Update high density threshold for traffic analysis."""
    try:
        config_service = get_config_service(request)
        
        # Get old threshold for logging
        old_threshold = config_service.get_high_density_threshold()
        
        # Update configuration
        config_service.update_config("traffic.high_density_threshold", threshold)
        
        logger.info("High density threshold updated", 
                   old_threshold=old_threshold,
                   new_threshold=threshold)
        
        return {
            "message": "Threshold updated successfully",
            "old_threshold": old_threshold,
            "new_threshold": threshold,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to update threshold", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/config/weather")
async def update_weather_markers(
    request: Request,
    marker_type: WeatherType = Query(description="Type of weather markers to enable (clear, fires, storm, flood)"),
) -> Dict[str, Any]:
    """Update weather markers configuration."""
    try:
        config_service = get_config_service(request)
        key_map = {WeatherType.CLEAR: None, WeatherType.FIRES: "enable_fire_markers", WeatherType.STORM: "enable_storm_markers", 
                   WeatherType.FLOOD: "enable_flood_markers"}
        
        config_key = key_map.get(marker_type, None)
        old_setting = None
        if config_key:
            old_setting = config_service.get_weather_config().get(config_key, False)
            config_service.update_config(f"weather.{config_key}", True)
            for k in key_map.values():
                if k and k != config_key:
                    config_service.update_config(f"weather.{k}", False)
        elif marker_type == WeatherType.CLEAR:
            for k in key_map.values():
                if k:
                    old_setting = config_service.get_weather_config().get(k, False)
                    config_service.update_config(f"weather.{k}", False)
        else:
            raise HTTPException(status_code=400, detail="Invalid marker type")

        logger.info("Weather markers configuration updated", 
                   marker_type=marker_type.value,
                   old_setting=old_setting,
                   new_setting=True if config_key else False)

        weather_service = get_weather_service(request)
        await weather_service.get_current_weather(force_refresh=True)

        return {
            "message": "Weather markers configuration updated successfully",
            "marker_type": marker_type.value,
            "old_setting": old_setting,
            "new_setting": True if config_key else False,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error("Failed to update weather markers", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/config/incident")
async def update_incident_markers(
    request: Request,
    incident_type: IncidentType = Query(description="Type of incident markers to enable (accident, crowding, roadblock, maintenance, clear)"),
) -> Dict[str, Any]:
    """Update incident markers configuration."""
    try:
        config_service = get_config_service(request)
        old_setting = config_service.get_traffic_config().get("incident_reporting_enabled", False)
        old_type = config_service.get_traffic_config().get("incident_type")
        
        is_clear = incident_type == IncidentType.CLEAR
        config_service.update_config("traffic.incident_reporting_enabled", not is_clear)
        config_service.update_config("traffic.incident_type", None if is_clear else incident_type.value)

        logger.info("Incident markers updated", incident_type=incident_type.value, 
                    old_setting=old_setting, new_setting=not is_clear)

        return {
            "message": "Incident markers updated",
            "incident_type": incident_type.value,
            "old_setting": old_setting,
            "old_type": old_type,
            "new_setting": not is_clear,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error("Failed to update incident markers", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
