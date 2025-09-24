"""Data aggregator service for traffic intelligence."""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from collections import deque
import structlog

from models import (
    CameraDataMessage, CameraImage, TrafficSnapshot, IntersectionData,
    TrafficIntelligenceResponse, WeatherData, VLMAnalysisData
)
from .config import ConfigService
from .vlm_service import VLMService


logger = structlog.get_logger(__name__)


class DataAggregatorService:
    """
    Data aggregator service for traffic intelligence.
    
    Aggregates camera data, coordinates with weather and VLM services,
    and maintains current traffic state for API responses.
    """

    def __init__(self, config_service: ConfigService, vlm_service: VLMService):
        """
        Initialize data aggregator service.
        
        Args:
            config_service: Configuration service
            vlm_service: VLM service for traffic analysis
        """
        self.config = config_service
        self.vlm_service = vlm_service

        self.high_density_threshold: int = self.config.get_high_density_threshold()

        # traffic_config = config_service.get_traffic_config()
        # self.data_retention_minutes = traffic_config.get("data_retention_minutes", 60)
        # self.analysis_window_seconds = traffic_config.get("analysis_window_seconds", 30)
        # self.vlm_trigger_duration = traffic_config.get("vlm_trigger_duration_seconds", 15)
        
        # Data storage - separate temporary and VLM-analyzed data
        self.temp_camera_data: Dict[str, CameraDataMessage] = {}     # direction -> latest temp data
        self.temp_camera_images: Dict[str, CameraImage] = {}         # direction -> latest temp image
        self.temp_intersection_data: Optional[IntersectionData] = None
        
        # VLM-analyzed data storage (only data that was part of VLM analysis)
        self.vlm_analyzed_camera_images: Dict[str, CameraImage] = {}      # direction -> VLM-analyzed images
        self.vlm_analyzed_intersection_data: Optional[IntersectionData] = None
        self.vlm_analyzed_weather_data: Optional[WeatherData] = None
        
        # Check if traffic warrants analysis
        # self.traffic_history: deque = deque(maxlen=1000)  # Historical snapshots (VLM-analyzed only)
        
        # Current state
        self.current_vlm_analysis: Optional[VLMAnalysisData] = None
        self.last_analysis_time: Optional[float] = 0.0
        
        # Background tasks
        # self.analysis_task: Optional[asyncio.Task] = None
        # self.cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("Data aggregator service initialized")
    
    # async def start_background_tasks(self):
    #     """Start background analysis and cleanup tasks."""
    #     self.analysis_task = asyncio.create_task(self._periodic_analysis())
    #     self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
    #     logger.info("Background tasks started")
    
    # async def stop_background_tasks(self):
    #     """Stop background tasks."""
    #     if self.analysis_task:
    #         self.analysis_task.cancel()
    #     if self.cleanup_task:
    #         self.cleanup_task.cancel()
    #     logger.info("Background tasks stopped")
    
    async def process_camera_image(self, camera_image: CameraImage) -> None:
        """
        Process incoming camera image separately from data.
        
        Args:
            camera_image: Camera image data from MQTT
        """
        try:
            direction = camera_image.direction
            
            # Update temporary camera image
            self.temp_camera_images[direction] = camera_image
            
            logger.info("Camera image updated (temporary)", 
                       direction=direction,
                       camera_id=camera_image.camera_id,
                       image_size=camera_image.image_size_bytes,
                       has_image_data=bool(camera_image.image_base64),
                       total_temp_images_stored=len(self.temp_camera_images))
                    
        except Exception as e:
            logger.error("Failed to process camera image", error=str(e))

    async def process_camera_data(self, camera_message: CameraDataMessage) -> None:
        """
        Process incoming camera data and update current state.
        
        Args:
            camera_message: Camera data message from MQTT
        """
        try:
            direction = camera_message.direction
            
            # Update temporary camera data
            self.temp_camera_data[direction] = camera_message
            
            logger.info("Camera data updated (temporary)")          
            
            # Update temporary intersection data
            await self._update_temp_intersection_data()

            if len(self.temp_camera_data) == 4:
                # Check if VLM analysis should be triggered
                self.temp_camera_data = {}  # Clear after processing all directions
                await self._check_analysis_trigger()
                
                    
        except Exception as e:
            logger.error("Failed to process camera data", error=str(e))
    
    async def _update_temp_intersection_data(self) -> None:
        """Update temporary intersection data from camera inputs."""
        intersection_id = self.config.get_intersection_id()
        intersection_name = self.config.get_intersection_name()
        lat, lon = self.config.get_intersection_coordinates()
        
        # Calculate directional counts from temporary data
        north_count = self.temp_camera_data.get('north', CameraDataMessage('', '', 'north', 0)).vehicle_count
        south_count = self.temp_camera_data.get('south', CameraDataMessage('', '', 'south', 0)).vehicle_count
        east_count = self.temp_camera_data.get('east', CameraDataMessage('', '', 'east', 0)).vehicle_count
        west_count = self.temp_camera_data.get('west', CameraDataMessage('', '', 'west', 0)).vehicle_count
        
        # Calculate pedestrian counts from temporary data
        north_pedestrian = self.temp_camera_data.get('north', CameraDataMessage('', '', 'north', 0, 0)).pedestrian_count
        south_pedestrian = self.temp_camera_data.get('south', CameraDataMessage('', '', 'south', 0, 0)).pedestrian_count
        east_pedestrian = self.temp_camera_data.get('east', CameraDataMessage('', '', 'east', 0, 0)).pedestrian_count
        west_pedestrian = self.temp_camera_data.get('west', CameraDataMessage('', '', 'west', 0, 0)).pedestrian_count

        # Get Traffic data timestamps
        north_timestamp = self.temp_camera_data.get('north').timestamp if 'north' in self.temp_camera_data else None
        south_timestamp = self.temp_camera_data.get('south').timestamp if 'south' in self.temp_camera_data else None
        east_timestamp = self.temp_camera_data.get('east').timestamp if 'east' in self.temp_camera_data else None
        west_timestamp = self.temp_camera_data.get('west').timestamp if 'west' in self.temp_camera_data else None
        
        total_count = north_count + south_count + east_count + west_count
        total_pedestrian_count = north_pedestrian + south_pedestrian + east_pedestrian + west_pedestrian
        
        self.temp_intersection_data = IntersectionData(
            intersection_id=intersection_id,
            intersection_name=intersection_name,
            latitude=lat,
            longitude=lon,
            timestamp=datetime.now(timezone.utc),
            north_camera=north_count,
            south_camera=south_count,
            east_camera=east_count,
            west_camera=west_count,
            total_density=total_count,
            north_pedestrian=north_pedestrian,
            south_pedestrian=south_pedestrian,
            east_pedestrian=east_pedestrian,
            west_pedestrian=west_pedestrian,
            total_pedestrian_count=total_pedestrian_count,
            north_timestamp=north_timestamp,
            south_timestamp=south_timestamp,
            east_timestamp=east_timestamp,
            west_timestamp=west_timestamp,
        )
        
        logger.info("Temporary intersection data updated", 
                   total_density=total_count,
                   total_pedestrian_count=total_pedestrian_count,
                   north=north_count, south=south_count, 
                   east=east_count, west=west_count,
                   north_ped=north_pedestrian, south_ped=south_pedestrian,
                   east_ped=east_pedestrian, west_ped=west_pedestrian,
                   north_timestamp=north_timestamp,
                   south_timestamp=south_timestamp,
                   east_timestamp=east_timestamp,
                   west_timestamp=west_timestamp)

    def _create_temp_traffic_snapshot(self) -> Optional[TrafficSnapshot]:
        """Create a traffic snapshot from temporary data for VLM analysis."""
        if not self.temp_intersection_data:
            return None
        
        directional_counts = {
            'north': self.temp_intersection_data.north_camera,
            'south': self.temp_intersection_data.south_camera,
            'east': self.temp_intersection_data.east_camera,
            'west': self.temp_intersection_data.west_camera
        }
      
        return TrafficSnapshot(
            timestamp=datetime.now(timezone.utc),
            intersection_id=self.temp_intersection_data.intersection_id,
            directional_counts=directional_counts,
            total_count=self.temp_intersection_data.total_density,
            camera_images=self.temp_camera_images.copy(),
            intersection_data=self.temp_intersection_data,
        )
    
    def _save_vlm_analyzed_data(self, vlm_analysis: VLMAnalysisData, traffic_snapshot: TrafficSnapshot) -> None:
        """Save data that was used in VLM analysis as the current analyzed data."""

        self.current_vlm_analysis = vlm_analysis

        # Copy temporary camera data to VLM-analyzed storage
        self.vlm_analyzed_camera_images = traffic_snapshot.camera_images
        self.vlm_analyzed_intersection_data = traffic_snapshot.intersection_data
        self.vlm_analyzed_weather_data = self.vlm_service.get_weather_details()
    

        # Add to historical snapshots (only VLM-analyzed data)
        # self.traffic_history.append(traffic_snapshot)
        
        logger.info("VLM-analyzed data saved",
                   total_density=traffic_snapshot.total_count,
                   analyzed_cameras=list(self.vlm_analyzed_camera_images.keys()),
                   intersection_id=traffic_snapshot.intersection_id)

    async def _check_analysis_trigger(self) -> None:
        """Check if VLM analysis should be triggered based on traffic conditions."""
        
        if not self.temp_intersection_data:
            return
        
        if self.temp_intersection_data.total_density >= self.high_density_threshold:
            logger.info("High traffic detected, triggering VLM analysis",
                       total_density=self.temp_intersection_data.total_density,
                       threshold=self.high_density_threshold)
            await self._trigger_vlm_analysis()
            return
        
        # # Check any single direction
        # directional_counts = {
        #     'north': self.temp_intersection_data.north_camera,
        #     'south': self.temp_intersection_data.south_camera,
        #     'east': self.temp_intersection_data.east_camera,
        #     'west': self.temp_intersection_data.west_camera
        # }
        
        # high_directions = [
        #     direction for direction, count in directional_counts.items()
        #     if count >= high_density_threshold
        # ]
        
        # if high_directions:
        #     logger.info("High directional traffic detected, triggering VLM analysis",
        #                high_directions=high_directions,
        #                threshold=high_density_threshold)
        #     await self._trigger_vlm_analysis()
    
    async def _trigger_vlm_analysis(self) -> None:
        """Trigger VLM analysis with current traffic and weather data."""
        try:
            logger.info("Starting VLM analysis trigger")
            # Update weather data
            # try:
            #     self.current_weather_data = await self.weather_service.get_current_weather()
            # except Exception as e:
            #     logger.warning("Weather fetch failed during VLM analysis, using cached data", error=str(e))
            #     # Continue with cached weather data or None
            
            # Create traffic snapshot from temporary data
            # async with self.vlm_service.get_vlm_semaphore():
            traffic_snapshot = self._create_temp_traffic_snapshot()

            if not traffic_snapshot:
                logger.warning("Cannot trigger VLM analysis: no traffic snapshot available")
                return
        
            # Trigger VLM analysis
            logger.debug("HEY")
            logger.debug(traffic_snapshot.intersection_data.total_density)
            logger.debug(self.vlm_analyzed_intersection_data.total_density if self.vlm_analyzed_intersection_data else None)
            try:
                vlm_analysis: VLMAnalysisData = await self.vlm_service.analyze_traffic_non_blocking(
                    traffic_snapshot=traffic_snapshot
                )
            
                if vlm_analysis:
                    self._save_vlm_analyzed_data(vlm_analysis, traffic_snapshot)
                    self.last_analysis_time = datetime.now().timestamp()

                    logger.info("VLM analysis completed successfully and data saved",
                            alerts_count=len(vlm_analysis.alerts),
                            analyzed_total_density=traffic_snapshot.total_count)
                else:
                    logger.warning("VLM analysis returned no result - temporary data not saved")
                

            except Exception as vlm_error:
                logger.error("VLM analysis failed - temporary data not saved", error=str(vlm_error))
                # Don't update analysis on error
            
        except Exception as e:
            logger.error("Failed to trigger VLM analysis", error=str(e))
    
    async def get_current_traffic_intelligence(self) -> Optional[TrafficIntelligenceResponse]:
        """
        Get current traffic intelligence response.
        
        Returns:
            Complete traffic intelligence response or None if no VLM-analyzed data available
        """
        # Only return data that was part of VLM analysis
        if not self.vlm_analyzed_intersection_data or not self.current_vlm_analysis:
            logger.info("No VLM-analyzed data available for API response",
                       has_vlm_intersection_data=self.vlm_analyzed_intersection_data is not None,
                       has_vlm_analysis=self.current_vlm_analysis is not None)
            return None
        
        try:
            # Ensure we have current weather data
            # if not self.current_weather_data:
            #     try:
            #         self.current_weather_data = await self.weather_service.get_current_weather()
            #     except Exception as e:
            #         logger.warning("Weather fetch failed, using cached or default data", error=str(e))
            #         self.current_weather_data = self.current_weather_data or self._get_default_weather()
            
            # Prepare camera images for response (only VLM-analyzed images)
            camera_images_dict = {}
            for direction, camera_image in self.vlm_analyzed_camera_images.items():
                camera_images_dict[f"{direction}_camera"] = {
                    'camera_id': camera_image.camera_id,
                    'direction': camera_image.direction,
                    'timestamp': camera_image.timestamp,
                    'image_base64': camera_image.image_base64,  # Include full base64 image
                    'image_size_bytes': camera_image.image_size_bytes
                }
            
            # Create response with VLM-analyzed data only
            response = TrafficIntelligenceResponse(
                timestamp=datetime.now(timezone.utc).isoformat(),
                intersection_id=self.vlm_analyzed_intersection_data.intersection_id,
                data=self.vlm_analyzed_intersection_data,
                camera_images=camera_images_dict,
                weather_data=self.vlm_analyzed_weather_data,
                vlm_analysis=self.current_vlm_analysis,
                response_age=(datetime.now(timezone.utc).timestamp() - self.last_analysis_time),
            )
            
            # logger.info("VLM-analyzed traffic intelligence response created",
            #            intersection_id=response.intersection_id,
            #            total_density=self.vlm_analyzed_intersection_data.total_density,
            #            total_pedestrian_count=self.vlm_analyzed_intersection_data.total_pedestrian_count,
            #            camera_images_count=len(camera_images_dict),
            #            alerts_count=len(self.current_vlm_analysis.alerts))
            
            return response
            
        except Exception as e:
            logger.error("Failed to create traffic intelligence response", error=str(e))
            return None
    
    # async def _periodic_analysis(self) -> None:
    #     """Periodic background analysis task."""
    #     while True:
    #         try:
    #             # Refresh weather data periodically
    #             self.current_weather_data = await self.weather_service.get_current_weather()
                
    #             # Check if analysis is needed based on sustained traffic
    #             await self._check_sustained_traffic_analysis()
                
    #             # Sleep for analysis window duration
    #             await asyncio.sleep(self.analysis_window_seconds)
                
    #         except asyncio.CancelledError:
    #             break
    #         except Exception as e:
    #             logger.error("Error in periodic analysis", error=str(e))
    #             await asyncio.sleep(10)  # Wait before retrying
    
    # async def _check_sustained_traffic_analysis(self) -> None:
    #     """Check for sustained high traffic patterns that warrant analysis."""
    #     if len(self.traffic_history) < 3:  # Need some VLM-analyzed history
    #         return
        
    #     # Look at recent VLM-analyzed snapshots
    #     recent_snapshots = list(self.traffic_history)[-5:]  # Last 5 VLM-analyzed snapshots
    #     high_density_threshold = self.config.get_high_density_threshold()
        
    #     # Check if traffic has been consistently high in analyzed data
    #     high_traffic_count = sum(1 for snapshot in recent_snapshots 
    #                            if snapshot.total_count >= high_density_threshold)
        
    #     if high_traffic_count >= 3:  # 3 out of 5 recent analyzed snapshots show high traffic
    #         # Check if we haven't analyzed recently
    #         if not self.last_analysis_time or \
    #            (datetime.now(timezone.utc) - self.last_analysis_time).total_seconds() > self.vlm_trigger_duration * 2:
    #             logger.info("Sustained high traffic detected in analyzed data, triggering analysis")
    #             await self._trigger_vlm_analysis()
    
    # async def _periodic_cleanup(self) -> None:
    #     """Periodic cleanup of old data."""
    #     while True:
    #         try:
    #             await asyncio.sleep(300)  # Run every 5 minutes
                
    #             # Clean up old traffic history
    #             cutoff_time = datetime.utcnow() - timedelta(minutes=self.data_retention_minutes)
                
    #             # Remove old snapshots
    #             while self.traffic_history and self.traffic_history[0].timestamp < cutoff_time:
    #                 self.traffic_history.popleft()
                
    #             logger.debug("Data cleanup completed", 
    #                        history_size=len(self.traffic_history))
                
    #         except asyncio.CancelledError:
    #             break
    #         except Exception as e:
    #             logger.error("Error in periodic cleanup", error=str(e))

    def _get_default_weather(self) -> WeatherData:
        """Get default weather data when none is available."""
        return WeatherData(
            name="Unknown", 
            temperature=72, 
            temperature_unit="F",
            detailed_forecast="Weather data unavailable", 
            fetched_at=datetime.now(timezone.utc),
            is_precipitation=False,
            is_mock=True
        )
    
    # def _get_default_vlm_analysis(self) -> VLMAnalysisData:
    #     """Get default VLM analysis when none is available."""
    #     return VLMAnalysisData(
    #         traffic_summary="Analysis pending",
    #         alerts=[],
    #         recommendations=[],
    #         analysis_timestamp=datetime.utcnow()
    #     )
    
    # def get_traffic_history(self, minutes: int = 30) -> List[TrafficSnapshot]:
    #     """
    #     Get VLM-analyzed traffic history for the specified time period.
        
    #     Args:
    #         minutes: Number of minutes of history to return
            
    #     Returns:
    #         List of VLM-analyzed traffic snapshots
    #     """
    #     cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
    #     return [
    #         snapshot for snapshot in self.traffic_history
    #         if snapshot.timestamp >= cutoff_time
    #     ]
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status and statistics."""
        return {
            "intersection_id": self.config.get_intersection_id(),
            "intersection_name": self.config.get_intersection_name(),
            "current_traffic_density": self.vlm_analyzed_intersection_data.total_density if self.vlm_analyzed_intersection_data else 0,
            "current_pedestrian_count": self.vlm_analyzed_intersection_data.total_pedestrian_count if self.vlm_analyzed_intersection_data else 0,
            "analyzed_camera_directions": list(self.vlm_analyzed_camera_images.keys()),
            "active_analyzed_cameras": len(self.vlm_analyzed_camera_images),
            "has_weather_data": self.vlm_analyzed_weather_data is not None,
            "has_vlm_analysis": self.current_vlm_analysis is not None,
            "last_analysis_time": self.last_analysis_time.isoformat() if self.last_analysis_time else None,
            # "vlm_analyzed_history_count": len(self.traffic_history),
            # "analysis_tasks_running": self.analysis_task is not None and not self.analysis_task.done()
        }