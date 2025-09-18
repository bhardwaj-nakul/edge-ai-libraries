"""API routes for traffic intelligence service."""

from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
import structlog


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
        data_aggregator = get_data_aggregator(request)
        
        # Get current traffic intelligence
        traffic_response = await data_aggregator.get_current_traffic_intelligence()
        
        if not traffic_response:
            raise HTTPException(status_code=404, detail="No traffic data available")
        
        # Convert to dict for JSON response
        response_dict = {
            "timestamp": traffic_response.timestamp,
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
                "total_density": traffic_response.data.total_density
            },
            "camera_images": traffic_response.camera_images,
            "weather_data": {
                "name": traffic_response.weather_data.name,
                "temperature": traffic_response.weather_data.temperature,
                "temperature_unit": traffic_response.weather_data.temperature_unit,
                "detailed_forecast": traffic_response.weather_data.detailed_forecast,
                "fetched_at": traffic_response.weather_data.fetched_at.isoformat(),
                "is_precipitation": traffic_response.weather_data.is_precipitation,
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
            "fetched_at": weather_data.fetched_at.isoformat(),
            "is_precipitation": weather_data.is_precipitation,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get current weather", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/analysis/trigger")
async def trigger_analysis(request: Request) -> Dict[str, Any]:
    """Manually trigger VLM traffic analysis."""
    try:
        data_aggregator = get_data_aggregator(request)
        
        # Trigger analysis
        await data_aggregator._trigger_vlm_analysis()
        
        return {
            "message": "Analysis triggered successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to trigger analysis", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status")
async def get_service_status(request: Request) -> Dict[str, Any]:
    """Get service status and statistics."""
    try:
        data_aggregator = get_data_aggregator(request)
        config_service = get_config_service(request)
        vlm_service = get_vlm_service(request)
        
        # Get MQTT status if available
        mqtt_status = {}
        if hasattr(request.app.state, 'mqtt'):
            mqtt_service = request.app.state.mqtt
            mqtt_status = mqtt_service.get_connection_status()
        
        # Get service status
        service_status = data_aggregator.get_service_status()
        
        # Get VLM service status
        vlm_status = vlm_service.get_service_status()
        
        return {
            "service": "traffic-intelligence",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "intersection": {
                "id": config_service.get_intersection_id(),
                "name": config_service.get_intersection_name(),
                "coordinates": config_service.get_intersection_coordinates()
            },
            "traffic": service_status,
            "vlm": vlm_status,
            "mqtt": mqtt_status
        }
        
    except Exception as e:
        logger.error("Failed to get service status", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/config")
async def get_service_config(request: Request) -> Dict[str, Any]:
    """Get service configuration (excluding sensitive data)."""
    try:
        config_service = get_config_service(request)
        
        return {
            "intersection": {
                "id": config_service.get_intersection_id(),
                "name": config_service.get_intersection_name(),
                "coordinates": config_service.get_intersection_coordinates()
            },
            "camera_topics": config_service.get_camera_topics(),
            "traffic": {
                "high_density_threshold": config_service.get_high_density_threshold(),
                **{k: v for k, v in config_service.get_traffic_config().items() 
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
        
        # Update configuration
        config_service.update_config("traffic.high_density_threshold", threshold)
        
        logger.info("High density threshold updated", threshold=threshold)
        
        return {
            "message": "Threshold updated successfully",
            "new_threshold": threshold,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to update threshold", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")