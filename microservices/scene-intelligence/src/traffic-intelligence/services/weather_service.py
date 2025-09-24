"""Weather service for traffic intelligence with caching and error handling."""

import asyncio
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import structlog

from models import WeatherData
from .config import ConfigService


logger = structlog.get_logger(__name__)


class WeatherService:
    """
    Weather service for traffic intelligence.
    
    Fetches weather data from National Weather Service API with caching
    and provides weather analysis for traffic correlation.
    """
    
    def __init__(self, config_service: ConfigService):
        """Initialize weather service with configuration."""
        self.config = config_service
        self.weather_config = config_service.get_weather_config()
        
        # Weather API configuration
        self.api_base_url = self.weather_config.get("api_base_url", "https://api.weather.gov")
        self.user_agent = self.weather_config.get("user_agent", "traffic-intelligence (admin@example.com)")
        self.cache_duration = timedelta(minutes=self.weather_config.get("cache_duration_minutes", 15))
        self.update_interval = timedelta(minutes=self.weather_config.get("update_interval_minutes", 10))
        
        # Caching
        self._cached_weather: Optional[WeatherData] = None
        self._cache_timestamp: Optional[datetime] = None
        
        # Periodic update task
        self._update_task: Optional[asyncio.Task] = None
        self._running = False
        self.is_mock = False
        
        logger.info("Weather service initialized", 
                   api_base_url=self.api_base_url,
                   cache_duration_minutes=self.cache_duration.total_seconds() / 60,
                   update_interval_minutes=self.update_interval.total_seconds() / 60)
    
    async def start(self):
        """Start the weather service with periodic updates."""
        if self._running:
            logger.warning("Weather service already running")
            return
        
        self._running = True
        
        logger.info("Weather service starting - fetching initial weather data")
        
        # Fetch initial weather data
        try:
            initial_weather = await self.get_current_weather(force_refresh=True)
            if initial_weather:
                logger.info("Initial weather data fetched successfully", 
                           temperature=initial_weather.temperature,
                           conditions=initial_weather.detailed_forecast)
            else:
                logger.warning("Failed to fetch initial weather data")
        except Exception as e:
            logger.error("Error fetching initial weather data", error=str(e))
        
        # Start periodic update task
        self._update_task = asyncio.create_task(self._periodic_update_loop())
        logger.info("Weather service started with periodic updates")
    
    async def stop(self):
        """Stop the weather service and cancel periodic updates."""
        self._running = False
        
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Weather service stopped")
    
    async def _periodic_update_loop(self):
        """Periodic update loop that fetches weather data at intervals."""
        logger.info("Starting periodic weather update loop", 
                   interval_minutes=self.update_interval.total_seconds() / 60)
        
        while self._running:
            try:
                await asyncio.sleep(self.update_interval.total_seconds())
                
                if self._running:  # Check again after sleep
                    logger.debug("Performing periodic weather update")
                    await self.get_current_weather(force_refresh=True)
                    
            except asyncio.CancelledError:
                logger.info("Periodic weather update loop cancelled")
                break
            except Exception as e:
                logger.error("Error in periodic weather update loop", error=str(e))
                # Continue loop on error, but wait a bit before retrying
                if self._running:
                    await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def get_current_weather(self, force_refresh: bool = False) -> Optional[WeatherData]:
        """
        Get current weather data with caching.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            WeatherData object or None if unavailable
        """
        logger.info("Getting current weather data", force_refresh=force_refresh, has_cached=self._cached_weather is not None)
        
        # Check cache first
        if not force_refresh and self._is_cache_valid():
            logger.debug("Returning cached weather data")
            return self._cached_weather
        
        # Get intersection coordinates
        lat, lon = self.config.get_intersection_coordinates()
        logger.info("Fetching weather for coordinates", lat=lat, lon=lon)
        
        try:
            weather_data = await self._fetch_weather_data(lat, lon)
            if weather_data:
                # Update cache
                self._cached_weather = weather_data
                self._cache_timestamp = datetime.now(timezone.utc)
                logger.info("Weather data updated", 
                           temperature=weather_data.temperature,
                           conditions=weather_data.detailed_forecast,
                           precipitation=weather_data.is_precipitation)
                return weather_data
            else:
                logger.warning("Failed to fetch weather data")
                return self._cached_weather  # Return cached data if available
                
        except Exception as e:
            logger.error("Error fetching weather data", error=str(e))
            return self._cached_weather  # Return cached data on error
    
    async def _fetch_weather_data(self, lat: float, lon: float) -> Optional[WeatherData]:
        """
        Fetch weather data from National Weather Service API using synchronous requests.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            WeatherData object or None if failed
        """
        logger.info("Starting weather data fetch", lat=lat, lon=lon, api_base_url=self.api_base_url)
        
        def _sync_fetch():
            """Synchronous fetch operation to run in thread pool."""
            try:
                # Step 1: Get the gridpoint endpoint for the given lat/long
                points_url = f"{self.api_base_url}/points/{lat},{lon}"
                logger.info("Making request to points API", url=points_url)
                
                points_resp = requests.get(points_url, headers={"User-Agent": self.user_agent})
                points_resp.raise_for_status()
                points_data = points_resp.json()
                
                logger.info("Points API response successful", status_code=points_resp.status_code)

                # Step 2: Get hourly forecast URL from the gridpoint response
                forecast_url = points_data["properties"]["forecastHourly"]
                logger.info("Making request to hourly forecast API", url=forecast_url)

                # Step 3: Fetch forecast data
                forecast_resp = requests.get(forecast_url, headers={"User-Agent": self.user_agent})
                forecast_resp.raise_for_status()
                forecast_data = forecast_resp.json()
                
                logger.info("Forecast API response successful", status_code=forecast_resp.status_code)

                # Step 4: Process the first forecast period (most current hour) and format according to specified structure
                first_period = forecast_data["properties"]["periods"][0]
                
                # Process weather data into WeatherData object
                weather_data = self._process_weather_data(first_period)
                
                logger.info("Weather data fetched successfully", 
                           conditions=weather_data.detailed_forecast,
                           temperature=weather_data.temperature,
                           precipitation=weather_data.is_precipitation)
                
                return weather_data
                
            except requests.exceptions.RequestException as e:
                logger.error("HTTP request error when fetching weather data", error=str(e))
                return self._get_mock_weather_data()
            except KeyError as e:
                logger.error("Missing key in weather API response", key=str(e))
                return self._get_mock_weather_data()
            except Exception as e:
                logger.error("Failed to fetch weather data", error=str(e))
                return self._get_mock_weather_data()
        
        # Run the synchronous operation in a thread pool to avoid blocking
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_fetch)
            return result
        except Exception as e:
            logger.error("Error in async weather fetch wrapper", error=str(e))
            return self._get_mock_weather_data()
        except KeyError as e:
            logger.error("Missing key in weather API response", key=str(e))
            return self._get_mock_weather_data()
        except Exception as e:
            logger.error("Failed to fetch weather data", error=str(e))
            return self._get_mock_weather_data()
    
    def _get_mock_weather_data(self) -> WeatherData:
        """Provide mock weather data when API is unavailable."""
        return WeatherData(
            name="Current Hour",
            temperature=85,
            temperature_unit="F",
            detailed_forecast="Mostly cloudy conditions with light winds. No precipitation expected.",
            fetched_at=datetime.now(timezone.utc),
            is_precipitation=False,
            is_mock=True,
            wind_speed="5 mph",
            wind_direction="S",
            short_forecast="Mostly Cloudy",
            wind_info="5mph/S",
            precipitation_prob=4.0,
            dewpoint=17.2,
            relative_humidity=47.0,
            is_daytime=False,
            start_time="2025-09-21T22:00:00-07:00",
            end_time="2025-09-21T23:00:00-07:00"
        )
    
    def get_default_weather(self) -> WeatherData:
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
    
    def _process_weather_data(self, forecast_period: Dict[str, Any]) -> WeatherData:
        """
        Process raw hourly forecast data into WeatherData object.
        
        Args:
            forecast_period: Raw forecast period from NWS hourly API
            
        Returns:
            WeatherData object with processed weather information
        """
        # Get temperature and keep in Fahrenheit (as expected by WeatherData)
        temp_f = forecast_period.get("temperature", 72)
        temp_unit = forecast_period.get("temperatureUnit", "F")
        
        # Get precipitation probability for road conditions
        precipitation_prob = forecast_period.get("probabilityOfPrecipitation", {})
        if isinstance(precipitation_prob, dict):
            prob_value = precipitation_prob.get("value", 0) or 0
        else:
            prob_value = 0
        
        # Determine precipitation status and road conditions
        is_precipitation = prob_value > 30  # Consider > 30% as likely precipitation
        
        # Get period name (hourly forecast usually doesn't have a name, so use a default)
        period_name = forecast_period.get("name", "Current Hour")
        
        # Get detailed forecast (for hourly, this might be empty)
        detailed_forecast = forecast_period.get("detailedForecast", 
                                               forecast_period.get("shortForecast", "Clear conditions"))
        
        # If detailed forecast is empty, create one from available data
        if not detailed_forecast.strip():
            short_forecast = forecast_period.get("shortForecast", "Clear")
            wind_speed = forecast_period.get("windSpeed", "0 mph")
            wind_direction = forecast_period.get("windDirection", "N")
            detailed_forecast = f"{short_forecast} conditions with {wind_speed} winds from the {wind_direction}."
            if prob_value > 0:
                detailed_forecast += f" {prob_value}% chance of precipitation."

        # Get short forecast
        short_forecast = forecast_period.get("shortForecast", "Clear")
        
        # Get wind speed and direction
        wind_speed = forecast_period.get("windSpeed", "0 mph")
        wind_direction = forecast_period.get("windDirection", "N")
        
        # Create wind_info field by combining speed and direction (e.g., "3mph/W")
        # Extract numeric speed from wind_speed string
        import re
        speed_match = re.search(r'(\d+)', wind_speed)
        speed_number = speed_match.group(1) if speed_match else "0"
        wind_info = f"{speed_number}mph/{wind_direction}"
        
        # Get dewpoint from hourly data
        dewpoint_data = forecast_period.get("dewpoint", {})
        dewpoint = None
        if isinstance(dewpoint_data, dict):
            dewpoint = dewpoint_data.get("value")
        
        # Get relative humidity from hourly data
        humidity_data = forecast_period.get("relativeHumidity", {})
        relative_humidity = None
        if isinstance(humidity_data, dict):
            relative_humidity = humidity_data.get("value")
        
        # Get daytime status
        is_daytime = forecast_period.get("isDaytime", None)
        
        # Get time periods
        start_time = forecast_period.get("startTime")
        end_time = forecast_period.get("endTime")

        return WeatherData(
            name=period_name,
            temperature=temp_f,
            temperature_unit=temp_unit,
            detailed_forecast=detailed_forecast,
            fetched_at=datetime.utcnow(),
            is_precipitation=is_precipitation,
            is_mock=False,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            short_forecast=short_forecast,
            wind_info=wind_info,
            precipitation_prob=float(prob_value),
            dewpoint=dewpoint,
            relative_humidity=relative_humidity,
            is_daytime=is_daytime,
            start_time=start_time,
            end_time=end_time
        )
   
    def _is_cache_valid(self) -> bool:
        """Check if cached weather data is still valid."""
        if not self._cached_weather or not self._cache_timestamp:
            return False
        
        age = datetime.now(timezone.utc) - self._cache_timestamp
        return age < self.cache_duration
    