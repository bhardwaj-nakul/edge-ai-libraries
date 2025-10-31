import requests
from typing import Optional, List

from config import (
    SCENE_INTELLIGENCE_API_BASE,
    SCENE_INTELLIGENCE_ENDPOINTS,
)
from controllers.route_interface import RouteStatusInterface
from schema import GeoCoordinates, LiveTrafficData
from utils.logging_config import get_logger
from utils.helper import read_config_json

logger = get_logger(__name__)


class LiveTrafficController(RouteStatusInterface):
    """
    Controller for handling live traffic data from an external API.
    """

    def __init__(self, latitude: Optional[float] = None, longitude: Optional[float] = None):
        self._latitude = latitude
        self._longitude = longitude

    @property
    def latitude(self) -> Optional[float]:
        return self._latitude

    @property
    def longitude(self) -> Optional[float]:
        return self._longitude

    @property
    def proximity_factor(self) -> float:
        """
        A float integer to help consider nearby latitude and longitudes as matching location coordinates.
        Uses the configured COORDINATE_MATCHING_PRECISION value.
        """
        return 0.0005    # Approx 50 meters

    def fetch_route_status(self) -> List[LiveTrafficData]:
        """
        Fetch the live traffic data from the Scene Intelligence API.

        Returns:
            list[LiveTrafficData]: List of traffic data for all intersections.
        """
        try:
            logger.info("Fetching live traffic data ...")
            # Construct the API URL

            config = read_config_json()
            api_endpoint = config.get("api_endpoint")
            api_responses: list[dict] = []
            
            if not api_endpoint:
                raise ValueError("API endpoint not found in configuration.")
            
            for api_host in config.get("api_hosts", []):
                host = api_host.get("host")
                if host:
                    # Make the API request
                    try:
                        logger.debug(f"Sending request to Intersection API: {host}{api_endpoint}")
                        response = requests.get(f"{host}{api_endpoint}")
                        response.raise_for_status()  # Raise an exception for HTTP errors
                        # Parse the response
                        api_responses.append(response.json())
                    except requests.RequestException as e:
                        logger.error(f"Error fetching data from intersection at {host}: {e}")

            # List to store the final response as list of LiveTrafficData
            intersection_traffic_data = []
            
            # Look for intersections that match our current coordinates
            for response in api_responses:
                # for intersection in response.get("data", {}):
                # Get the intersection's coordinates
                intersection_data = response.get("data", {})
                logger.info(f"Processing intersection data: {intersection_data.get('intersection_name', 'Unknown')}")
                intersection_lat = intersection_data.get("latitude")
                intersection_lon = intersection_data.get("longitude")

                traffic_density = intersection_data.get("total_density", 0)

                # Get traffic description if available
                traffic_description = None
                vlm_analysis = response.get("vlm_analysis", {})
                if vlm_analysis and "traffic_summary" in vlm_analysis:
                    traffic_description = vlm_analysis.get("traffic_summary")

                # Get intersection images if available (base64 encoded)
                intersection_images = {}
                camera_images = response.get("camera_images", {})
                for camera_id, image_data in camera_images.items():
                    intersection_images[camera_id] = image_data.get("image_base64")

                # Create and return the LiveTrafficData
                intersection_traffic_data.append(
                    LiveTrafficData(
                        location_coordinates=GeoCoordinates(
                            latitude=intersection_lat,
                            longitude=intersection_lon,
                        ),
                        intersection_name=intersection_data.get("intersection_name", "Unknown Intersection"),
                        timestamp=intersection_data.get("timestamp", ""),
                        traffic_density=traffic_density,
                        traffic_description=traffic_description,
                        intersection_images=intersection_images,
                    )
                )
                    
            return intersection_traffic_data

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Error fetching live traffic data: {e}")
            return []
