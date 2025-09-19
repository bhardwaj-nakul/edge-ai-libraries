"""MQTT service for traffic intelligence camera data subscription."""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from queue import Queue
import threading

import paho.mqtt.client as mqtt
import structlog

from models import CameraDataMessage, CameraImage


logger = structlog.get_logger(__name__)


class MQTTService:
    """
    MQTT service for subscribing to camera data topics.
    
    Subscribes to scenescape/data/camera/camera<1,2,3,4> topics and processes
    incoming camera data for traffic intelligence analysis.
    """
    
    def __init__(self, config_service, data_aggregator):
        """
        Initialize MQTT service.
        
        Args:
            config_service: Configuration service instance
            data_aggregator: Data aggregator service for processing messages
        """
        self.config = config_service
        self.data_aggregator = data_aggregator
        self.mqtt_config = config_service.get_mqtt_config()
        
        # MQTT connection settings - use config or fallback to localhost
        self.host = self.mqtt_config.get("host", "localhost")
        self.port = self.mqtt_config.get("port", 1883)
        self.use_tls = self.mqtt_config.get("use_tls", False)
        self.ca_cert_path = self.mqtt_config.get("ca_cert_path", "../secrets/certs/scenescape-ca.pem")
        self.cert_required = self.mqtt_config.get("cert_required", True)
        self.verify_hostname = self.mqtt_config.get("verify_hostname", False)
        self.username = self.mqtt_config.get("username")
        self.password = self.mqtt_config.get("password")
        
        # Camera topics
        self.camera_topics = config_service.get_camera_topics()
        self.image_topics = config_service.get_image_topics()
        
        # MQTT client and connection state
        self.client = None
        self.connected = False
        self.loop = None
        
        # Message processing
        self.shutdown_event = asyncio.Event()
        
        # Rate limiting - process data every 1 second per camera
        self.last_processed_time = {}  # camera_number -> timestamp
        self.rate_limit_seconds = self.mqtt_config.get("rate_limit_seconds", 10.0)
        
        # Topic patterns for camera data and images
        # Pattern: scenescape/data/camera/camera{1,2,3,4}
        self.camera_data_pattern = re.compile(r'scenescape/data/camera/camera(\d+)')
        # Pattern: scenescape/image/camera/camera{1,2,3,4}
        self.camera_image_pattern = re.compile(r'scenescape/image/camera/camera(\d+)')
        
        logger.info("MQTT service initialized", 
                   host=self.host, 
                   port=self.port, 
                   use_tls=self.use_tls,
                   has_auth=bool(self.username),
                   cert_required=self.cert_required,
                   verify_hostname=self.verify_hostname,
                   ca_cert_path=self.ca_cert_path,
                   camera_topics=self.camera_topics,
                   image_topics=self.image_topics)
    
    async def initialize(self) -> None:
        """Initialize MQTT client."""
        try:
            self.client = mqtt.Client()
            
            # Configure authentication
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
                logger.info("MQTT username/password authentication configured", username=self.username)
            
            # Configure TLS
            if self.use_tls:
                logger.info("Configuring MQTT TLS", 
                           ca_cert=self.ca_cert_path,
                           cert_required=self.cert_required,
                           verify_hostname=self.verify_hostname)
                
                try:
                    import ssl
                    
                    # Resolve certificate paths relative to the script location
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    
                    def resolve_cert_path(cert_path):
                        if os.path.isabs(cert_path):
                            return cert_path
                        return os.path.join(script_dir, cert_path)
                    
                    ca_cert_full_path = resolve_cert_path(self.ca_cert_path)
                    
                    logger.info("Certificate path resolved",
                               ca_cert=ca_cert_full_path)
                    
                    if self.cert_required:
                        # Check if CA certificate file exists
                        if not os.path.exists(ca_cert_full_path):
                            logger.error("Missing CA certificate file", ca_cert=ca_cert_full_path)
                            raise FileNotFoundError(f"Missing CA certificate file: {ca_cert_full_path}")
                        
                        # Use CA certificate only for server verification
                        self.client.tls_set(ca_certs=ca_cert_full_path, 
                                          certfile=None, 
                                          keyfile=None,
                                          cert_reqs=ssl.CERT_REQUIRED,
                                          tls_version=ssl.PROTOCOL_TLS)
                        
                        # Set hostname verification based on config
                        if not self.verify_hostname:
                            self.client.tls_insecure_set(True)
                            logger.info("TLS configured with CA certificate (hostname verification disabled)")
                        else:
                            logger.info("TLS configured with CA certificate (full verification)")
                            
                    else:
                        # TLS without certificate verification (insecure but matches some UI settings)
                        try:
                            # First try with CA cert only
                            if os.path.exists(ca_cert_full_path):
                                self.client.tls_set(ca_certs=ca_cert_full_path, 
                                                  certfile=None, 
                                                  keyfile=None,
                                                  cert_reqs=ssl.CERT_NONE,
                                                  tls_version=ssl.PROTOCOL_TLS)
                                logger.info("TLS with CA cert but no verification")
                            else:
                                # No certificates, just TLS
                                self.client.tls_set(ca_certs=None, 
                                                  certfile=None, 
                                                  keyfile=None,
                                                  cert_reqs=ssl.CERT_NONE,
                                                  tls_version=ssl.PROTOCOL_TLS)
                                logger.info("TLS without certificates")
                            
                            self.client.tls_insecure_set(True)
                            
                        except Exception as e:
                            logger.warning("Advanced TLS failed, trying basic TLS", error=str(e))
                            # Fallback to most basic TLS
                            self.client.tls_set()
                            self.client.tls_insecure_set(True)
                            logger.info("Basic TLS enabled")
                            
                except Exception as e:
                    logger.error("Failed to configure TLS", error=str(e))
                    raise
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            logger.info("MQTT client initialized")
            
        except Exception as e:
            logger.error("Failed to initialize MQTT client", error=str(e))
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            self.connected = True
            logger.info("MQTT connected successfully")
            
            # Subscribe to camera data topics
            for topic in self.camera_topics:
                client.subscribe(topic, qos=1)
                logger.info("Subscribed to camera topic", topic=topic)
            for topic in self.image_topics:
                client.subscribe(topic, qos=1)
                logger.info("Subscribed to image topic", topic=topic)
            
            # Automatically trigger getimage commands once connected and subscribed
            if self.loop:
                asyncio.run_coroutine_threadsafe(
                    self._trigger_initial_getimage_commands(),
                    self.loop
                )
            else:
                logger.warning("No event loop set, cannot trigger initial getimage commands")
                
        else:
            self.connected = False
            logger.error("MQTT connection failed", return_code=rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback."""
        self.connected = False
        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly", return_code=rc)
        else:
            logger.info("MQTT disconnected")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback - process messages directly with rate limiting."""
        try:
            # Parse message payload
            try:
                payload = json.loads(msg.payload.decode())
                # print('----------------------------------------')
                # print(f"Topic: {msg.topic}")
                # print(payload)
                # print('----------------------------------------')

            except json.JSONDecodeError:
                logger.error("Failed to parse MQTT message payload", 
                           topic=msg.topic, payload=msg.payload.decode()[:100])
                return

            # Check if this is a camera data topic
            camera_data_match = self.camera_data_pattern.match(msg.topic)
            camera_image_match = self.camera_image_pattern.match(msg.topic)
            
            if camera_data_match:
                # Handle camera data message
                camera_number = camera_data_match.group(1)
                timestamp = datetime.now(timezone.utc)
                
                # Schedule async processing for camera data
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self._process_camera_data_message(
                            camera_number=camera_number,
                            payload=payload,
                            timestamp=timestamp,
                            topic=msg.topic
                        ),
                        self.loop
                    )
                else:
                    logger.warning("No event loop set, cannot process camera data message")
                    
            elif camera_image_match:
                # Handle camera image message
                camera_number = camera_image_match.group(1)
                timestamp = datetime.now(timezone.utc)
                
                # Schedule async processing for camera image
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self._process_camera_image_message(
                            camera_number=camera_number,
                            payload=payload,
                            timestamp=timestamp,
                            topic=msg.topic
                        ),
                        self.loop
                    )
                else:
                    logger.warning("No event loop set, cannot process camera image message")
                    
            else:
                logger.debug("Ignoring unrecognized topic", topic=msg.topic)
        
        except Exception as e:
            logger.error("Error processing MQTT message", error=str(e), topic=msg.topic)
    
    async def start(self) -> None:
        """Start MQTT service."""
        try:
            if not self.client:
                await self.initialize()
            
            logger.info("Starting MQTT connection", host=self.host, port=self.port, use_tls=self.use_tls)
            
            try:
                self.client.connect(self.host, self.port, 60)
            except Exception as e:
                error_str = str(e).lower()
                if "ssl" in error_str or "tls" in error_str:
                    logger.error("SSL/TLS connection failed", error=str(e), host=self.host, port=self.port)
                    
                    # Provide specific suggestions based on the error
                    if "wrong version number" in error_str:
                        logger.error("SSL version mismatch detected.")
                    elif "certificate" in error_str:
                        logger.error("Certificate validation failed. Try: MQTT_CERT_REQUIRED=false")
                    
                    # If TLS is enabled and we get SSL errors, suggest trying without TLS
                    if self.use_tls:
                        logger.error("Consider trying connection without TLS first to test basic connectivity")
                        
                else:
                    logger.error("MQTT connection failed", error=str(e), host=self.host, port=self.port)
                raise
            
            # Start the network loop in a separate thread
            self.client.loop_start()
            
            # Wait for connection to establish
            await asyncio.sleep(2)
            
            logger.info("MQTT service started successfully")
            
            # Keep the service running
            while not self.shutdown_event.is_set():
                await asyncio.sleep(1)
        
        except Exception as e:
            logger.error("Failed to start MQTT service", error=str(e))
            raise
    
    async def stop(self) -> None:
        """Stop MQTT service."""
        try:
            # Signal the shutdown event
            self.shutdown_event.set()
            
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT service stopped")
        
        except Exception as e:
            logger.error("Error stopping MQTT service", error=str(e))
    
    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self.connected
    
    def set_event_loop(self, loop):
        """Set the event loop reference for async task scheduling."""
        self.loop = loop
        logger.info("Event loop reference set for MQTT service")

    async def send_getimage_commands(self) -> bool:
        """Send 'getimage' command to all cameras."""
        if not self.connected:
            logger.warning("MQTT Publisher not connected, cannot send commands")
            return False
        
        try:
            camera_ids = ["camera1", "camera2", "camera3", "camera4"]
            
            if not camera_ids:
                logger.warning("No camera IDs found")
                return False
            
            success_count = 0
            for camera_id in camera_ids:
                try:
                    topic = f"scenescape/cmd/camera/{camera_id}"
                    message = "getimage"
                    
                    result = self.client.publish(topic, message)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        success_count += 1
                        logger.debug("Sent getimage command", camera_id=camera_id, topic=topic)
                    else:
                        logger.warning("Failed to send getimage command", 
                                     camera_id=camera_id, 
                                     result_code=result.rc)
                    
                    # Small delay between commands to avoid overwhelming the broker
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error("Error sending getimage command", 
                               camera_id=camera_id, 
                               error=str(e))
            
            logger.info("Sent getimage commands", 
                       total_cameras=len(camera_ids), 
                       successful=success_count)
            
            return success_count > 0
            
        except Exception as e:
            logger.error("Failed to send getimage commands", error=str(e))
            return False

    async def _trigger_initial_getimage_commands(self) -> None:
        """
        Trigger initial getimage commands after MQTT connection is established.
        
        This method is called automatically when the MQTT connection is established
        to request initial images from all cameras.
        """
        try:
            # Small delay to ensure subscriptions are fully established
            await asyncio.sleep(1.0)
            
            logger.info("Triggering initial getimage commands for all cameras")
            success = await self.send_getimage_commands()
            
            if success:
                logger.info("Initial getimage commands sent successfully")
            else:
                logger.warning("Failed to send initial getimage commands")
                
        except Exception as e:
            logger.error("Error triggering initial getimage commands", error=str(e))
        
    async def _process_camera_image_message(self,
                                           camera_number: str,
                                           payload: Dict[str, Any],
                                           timestamp: datetime,
                                           topic: str) -> None:
        """
        Process camera image message from MQTT.
        
        Args:
            camera_number: Camera number (1, 2, 3, 4)
            payload: Message payload with image data
            timestamp: Message timestamp
            topic: MQTT topic
        """
        try:
            # Rate limiting check for image messages
            current_time = timestamp.timestamp()
            last_time = self.last_processed_time.get(f"image_{camera_number}", 0)
            
            if current_time - last_time < self.rate_limit_seconds:
                return
            
            # Update last processed time
            self.last_processed_time[f"image_{camera_number}"] = current_time
            
            # Extract data from payload
            camera_id = payload.get('id', f'camera{camera_number}')
            image_data = payload.get('image')  # Base64 encoded image
            image_timestamp_str = payload.get('timestamp')
            
            if not image_data:
                logger.warning("No image data in image message", camera_id=camera_id, topic=topic)
                return
            
            # Parse image timestamp
            image_timestamp = timestamp
            if image_timestamp_str:
                try:
                    image_timestamp = datetime.fromisoformat(image_timestamp_str.replace('Z', '+00:00'))
                except:
                    pass
            
            # Map camera number to direction (configurable mapping)
            direction_mapping = {
                '1': 'north',
                '2': 'south', 
                '3': 'east',
                '4': 'west',
            }
            direction = direction_mapping.get(camera_number, f'camera{camera_number}')
            
            # Create camera image
            camera_image = CameraImage(
                camera_id=camera_id,
                direction=direction,
                timestamp=image_timestamp,
                image_base64=image_data,
                image_size_bytes=len(image_data) * 3 // 4 if image_data else None  # Approximate base64 decode size
            )
            
            # Send to data aggregator for processing (image only)
            await self.data_aggregator.process_camera_image(camera_image)
            
            
            logger.debug("Camera image processed successfully", 
                       camera_id=camera_id,
                       direction=direction,
                       image_size=len(image_data))
        except Exception as e:
            logger.error("Failed to process camera image message", 
                        error=str(e), 
                        camera_number=camera_number, 
                        topic=topic)

    async def _process_camera_data_message(self, 
                                         camera_number: str,
                                         payload: Dict[str, Any],
                                         timestamp: datetime,
                                         topic: str) -> None:
        """
        Process camera data message from MQTT.
        
        Args:
            camera_number: Camera number (1, 2, 3, 4)
            payload: Message payload
            timestamp: Message timestamp
            topic: MQTT topic
        """
        try:
            # Rate limiting check for data messages
            current_time = timestamp.timestamp()
            last_time = self.last_processed_time.get(f"data_{camera_number}", 0)
            
            if current_time - last_time < self.rate_limit_seconds:
                return
            
            # Update last processed time
            self.last_processed_time[f"data_{camera_number}"] = current_time
            
            # Extract data from payload
            camera_id = payload.get('id', f'camera{camera_number}')
            intersection_id = self.config.get_intersection_id()
            
            # Map camera number to direction (configurable mapping)
            direction_mapping = {
                '1': 'north',
                '2': 'south', 
                '3': 'east',
                '4': 'west',
                # Add camera 4 for west if available
            }
            direction = direction_mapping.get(camera_number, f'camera{camera_number}')
            
            # Extract traffic counts from objects array
            objects = payload.get('objects', {})
            vehicle_count = len(objects.get('vehicle', []))
            pedestrian_count = len(objects.get('pedestrian', []))
            
            # Extract image data if available
            image_data = payload.get('image_data')  # Base64 encoded image
            image_timestamp_str = payload.get('timestamp')
            
            # Parse image timestamp
            image_timestamp = timestamp
            if image_timestamp_str:
                try:
                    image_timestamp = datetime.fromisoformat(image_timestamp_str.replace('Z', '+00:00'))
                except:
                    pass
            
            # Create camera data message
            camera_message = CameraDataMessage(
                camera_id=camera_id,
                intersection_id=intersection_id,
                direction=direction,
                vehicle_count=vehicle_count,
                pedestrian_count=pedestrian_count,
                timestamp=image_timestamp,
                image_data=image_data
            )
            

            # Print detailed object information
            if objects:
                if 'vehicle' in objects:
                    for i, vehicle in enumerate(objects['vehicle']):
                        conf = vehicle.get('confidence', 0)
                        bbox = vehicle.get('bounding_box_px', {})
                        print(f"  Vehicle {i+1}: confidence={conf:.3f}, bbox=({bbox.get('x',0)},{bbox.get('y',0)},{bbox.get('width',0)},{bbox.get('height',0)})")
                if 'pedestrian' in objects:
                    for i, pedestrian in enumerate(objects['pedestrian']):
                        conf = pedestrian.get('confidence', 0)
                        bbox = pedestrian.get('bounding_box_px', {})
                        print(f"  Pedestrian {i+1}: confidence={conf:.3f}, bbox=({bbox.get('x',0)},{bbox.get('y',0)},{bbox.get('width',0)},{bbox.get('height',0)})")
                       
            # Send to data aggregator for processing
            await self.data_aggregator.process_camera_data(camera_message)
            
            logger.debug("Camera data processed successfully", 
                       camera_id=camera_id,
                       direction=direction,
                       vehicle_count=vehicle_count,
                       has_image=bool(image_data))
                    
        except Exception as e:
            logger.error("Failed to process camera data message", 
                        error=str(e), 
                        camera_number=camera_number, 
                        topic=topic)
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get MQTT connection status information."""
        return {
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "use_tls": self.use_tls,
            "has_authentication": bool(self.username),
            "cert_required": self.cert_required,
            "subscribed_topics": self.camera_topics,
            "rate_limit_seconds": self.rate_limit_seconds,
            "cameras_being_tracked": list(self.last_processed_time.keys())
        }