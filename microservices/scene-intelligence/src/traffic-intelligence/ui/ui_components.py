"""
UI Components for the RSU Monitoring System
"""
import base64
import io
from PIL import Image
from typing import Optional, List, Tuple
from datetime import datetime

from models import MonitoringData
from config import Config


class UIComponents:
    """UI component generator class"""

    @staticmethod
    def _render_markdown(md_text: str) -> str:
        """Render markdown text to HTML. Falls back to simple replacements if markdown package not installed."""
        if md_text is None:
            return ""

        try:
            import markdown  # type: ignore
            return markdown.markdown(md_text, extensions=["extra", "sane_lists", "tables"])  # type: ignore
        except Exception:
            pass    
    @staticmethod
    def create_header(monitoring_data: Optional[MonitoringData] = None) -> str:
        """Create the header section with system title and status"""
        if not monitoring_data:
            return """
            <div style="text-align: center; background: linear-gradient(135deg, #1e3a8a, #3b82f6); 
                        padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <p style="color: white; margin: 0; font-size: 24px;">🚦 Traffic MONITORING SYSTEM</p>
                <p style="color: #fbbf24; margin: 5px 0 0 0;">⚠️ DATA UNAVAILABLE</p>
            </div>
            """
        
        return f"""
        <div style="text-align: center; background: linear-gradient(135deg, #1e3a8a, #3b82f6); 
                    padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <p style="color: white; margin: 0; font-size: 24px;">🚦 {Config.APP_TITLE} | {monitoring_data.data.intersection_name}</p> 
        </div>
        """

    @staticmethod
    def create_traffic_summary(monitoring_data: Optional[MonitoringData]) -> str:
        """Create traffic summary cards"""
        if not monitoring_data:
            return "<p style='text-align: center; color: #ef4444;'>No traffic data available</p>"
        
        data = monitoring_data.data
        
        return f"""
        <div style="background: #1f2937; border-radius: 12px; padding: 15px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
            <h3 style="color: #f3f4f6; margin: 0 0 15px 0; text-align: center;">🚦 TRAFFIC SUMMARY</h3>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 15px 0;">
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 2em; color: #60a5fa;">{data.northbound_density}</div>
                    <div style="color: #d1d5db;">↑ NORTH</div>
                </div>
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 2em; color: #60a5fa;">{data.southbound_density}</div>
                    <div style="color: #d1d5db;">↓ SOUTH</div>
                </div>
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 2em; color: #60a5fa;">{data.eastbound_density}</div>
                    <div style="color: #d1d5db;">→ EAST</div>
                </div>
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 2em; color: #60a5fa;">{data.westbound_density}</div>
                    <div style="color: #d1d5db;">← WEST</div>
                </div>
            </div>
            
            <div style="text-align: center; background: #065f46; padding: 15px; border-radius: 8px; margin-top: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                <div style="font-size: 2.5em; color: #60a5fa; font-weight: bold;">{data.total_density}</div>
                <div style="color: #d1fae5; font-weight: 500;">TOTAL VEHICLES</div>
            </div>
            </div>  
        </div>
        """

    @staticmethod
    def create_environmental_panel(monitoring_data: Optional[MonitoringData]) -> str:
        """Create environmental data panel"""
        if not monitoring_data:
            return "<p style='text-align: center; color: #ef4444;'>No environmental data available</p>"
        
        weather = monitoring_data.weather_data
        
        # Determine air quality status (simulated)
        temp = weather.temperature_celsius
        humidity = weather.humidity_percent
        
        if temp < 0 or temp > 35 or humidity > 80:
            air_quality = "POOR"
            air_color = "#ef4444"
        elif temp < 10 or temp > 30 or humidity > 60:
            air_quality = "MODERATE"
            air_color = "#f59e0b"
        else:
            air_quality = "GOOD"
            air_color = "#10b981"
        
        # Wind direction
        wind_dir = weather.wind_direction_degrees
        if wind_dir < 45 or wind_dir >= 315:
            wind_text = "N"
        elif wind_dir < 135:
            wind_text = "E"
        elif wind_dir < 225:
            wind_text = "S"
        else:
            wind_text = "W"
        
        return f"""
        <div style="background: #1f2937; border-radius: 12px; padding: 15px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
            <h3 style="color: #f3f4f6; margin: 0 0 15px 0; text-align: center;">🌡️ ENVIRONMENTAL DATA</h3>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 2em; color: #fbbf24;">{weather.temperature_celsius}°C</div>
                    <div style="color: #d1d5db;">TEMPERATURE</div>
                </div>
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 2em; color: #60a5fa;">{weather.humidity_percent}%</div>
                    <div style="color: #d1d5db;">HUMIDITY</div>
                </div>
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 1.5em; color: #a78bfa;">{weather.wind_speed_kph} km/h {wind_text}</div>
                    <div style="color: #d1d5db;">WIND</div>
                </div>
                <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 1.5em; color: #34d399;">{weather.precipitation_mm} mm</div>
                    <div style="color: #d1d5db;">RAINFALL</div>
                </div>
            </div>
            
            <div style="text-align: center; background: #374151; padding: 15px; border-radius: 8px; margin-top: 15px;">
                <div style="font-size: 1.5em; color: {air_color}; font-weight: bold;">{air_quality}</div>
                <div style="color: #d1d5db;">AIR QUALITY</div>
            </div>
            
            <div style="margin-top: 15px; text-align: center;">
                <p style="color: #9ca3af; margin: 5px 0;">Conditions: {weather.conditions}</p>
            </div>
        </div>
        """

    @staticmethod
    def create_alerts_panel(monitoring_data: Optional[MonitoringData]) -> str:
        """Create alerts panel with structured alerts and recommendations"""
        if not monitoring_data:
            return "<p style='text-align: center; color: #ef4444;'>No alerts data available</p>"
        
        alerts = monitoring_data.vlm_analysis.alerts
        recommendations = monitoring_data.vlm_analysis.recommendations or []
        
        if not alerts and not recommendations:
            return """
            <div style="background: #1f2937; border-radius: 12px; padding: 15px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
                <h3 style="color: #f3f4f6; margin: 0 0 15px 0; text-align: left;">🚨 Traffic Status and Alerts</h3>
                <div style="text-align: center; background: #065f46; padding: 20px; border-radius: 8px;">
                    <div style="font-size: 1.5em; color: #10b981;">✅ ALL SYSTEMS OPERATIONAL</div>
                    <div style="color: #d1fae5; margin-top: 10px;">No active alerts or recommendations</div>
                </div>
            </div>
            """
        
        # Process alerts with new structured format
        alerts_html = ""
        for alert in alerts:
            if isinstance(alert, dict):
                # New structured alert format
                alert_type = alert.get("alert_type", "general")
                level = alert.get("level", "info")
                description = alert.get("description", "")
                weather_related = alert.get("weather_related", False)
                
                # Determine styling based on level
                if level.lower() == "critical":
                    bg_color = "#7f1d1d"  # Dark red
                    text_color = "#fecaca"
                    icon = "🚨"
                    border_color = "#dc2626"
                elif level.lower() == "warning":
                    bg_color = "#92400e"  # Dark orange
                    text_color = "#fed7aa"
                    icon = "⚠️"
                    border_color = "#f59e0b"
                elif level.lower() == "advisory":
                    bg_color = "#1e40af"  # Dark blue
                    text_color = "#bfdbfe"
                    icon = "ℹ️"
                    border_color = "#3b82f6"
                else:
                    bg_color = "#374151"
                    text_color = "#d1d5db"
                    icon = "ℹ️"
                    border_color = "#6b7280"
                
                # Add weather icon if weather-related
                if weather_related:
                    icon = "🌦️"
                
                alerts_html += f"""
                <div style="background: {bg_color}; color: {text_color}; padding: 15px; 
                            border-radius: 8px; margin: 10px 0; border-left: 4px solid {border_color};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                        <strong>{icon} {level.upper()} ALERT</strong>
                        <span style="font-size: 0.8em; opacity: 0.8;">{alert_type.replace('_', ' ').title()}</span>
                    </div>
                    <div style="font-size: 0.95em; line-height: 1.4;">{description}</div>
                </div>
                """
            else:
                # Fallback for string format (legacy)
                alerts_html += f"""
                <div style="background: #374151; color: #d1d5db; padding: 15px; 
                            border-radius: 8px; margin: 10px 0; border-left: 4px solid #6b7280;">
                    <strong>ℹ️ INFO:</strong> {alert}
                </div>
                """
        
        # Process recommendations
        recommendations_html = ""
        if recommendations:
            for idx, recommendation in enumerate(recommendations, 1):
                recommendations_html += f"""
                <div style="background: #065f46; color: #d1fae5; padding: 12px; 
                            border-radius: 6px; margin: 8px 0; border-left: 3px solid #10b981;">
                    <div style="font-size: 0.9em; line-height: 1.4;">
                        <strong>💡 Recommendation {idx}:</strong> {recommendation}
                    </div>
                </div>
                """
        
        analysis_html = UIComponents._render_markdown(monitoring_data.vlm_analysis.analysis)
        
        return f"""
        <div style="background: #1f2937; border-radius: 12px; padding: 15px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
            <h3 style="color: #f3f4f6; margin: 0 0 15px 0; text-align: left;">🚨 Traffic Status and Alerts</h3>
            
            {alerts_html}
            
            {f'''
            <div style="margin-top: 15px;">
                <h4 style="color: #f3f4f6; margin: 10px 0 8px 0; font-size: 1em;">💡 Recommendations</h4>
                {recommendations_html}
            </div>
            ''' if recommendations_html else ''}
            
            <div style="margin-top: 15px; padding: 15px; background: #374151; border-radius: 8px;">
                <h4 style="color: #f3f4f6; margin-top: 0;">Analysis Summary:</h4>
                <div style="color: #d1d5db; margin: 5px 0; font-size: 0.95em; line-height: 1.4;">{analysis_html}</div>
                <p style="color: #9ca3af; margin: 5px 0; font-size: 0.9em;">
                    Age: {monitoring_data.vlm_analysis.analysis_age_minutes} min
                </p>
            </div>
        </div>
        """

    @staticmethod
    def create_camera_images(monitoring_data: Optional[MonitoringData]) -> List[Tuple[str, str]]:
        """Create camera images for display in Gradio Gallery"""
        if not monitoring_data or not monitoring_data.camera_images:
            return []
        
        image_list = []
        
        for camera_name, camera_data in monitoring_data.camera_images.items():
            # Handle both CameraData objects and dict structures from API
            if hasattr(camera_data, 'image_base64'):
                # CameraData object
                image_base64 = camera_data.image_base64
                direction = camera_data.direction
                camera_id = camera_data.camera_id
            elif isinstance(camera_data, dict):
                # Dict from API
                image_base64 = camera_data.get('image_base64')
                direction = camera_data.get('direction', 'unknown')
                camera_id = camera_data.get('camera_id', 'unknown')
            else:
                continue
                
            if image_base64:
                try:
                    # Decode base64 image
                    image_bytes = base64.b64decode(image_base64)
                    
                    # Create PIL Image from bytes
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    # Create a caption with camera info
                    caption = f"{direction.upper()} - {camera_id}"
                    
                    # For Gradio Gallery, we need to save the image temporarily or use base64
                    # We'll return the image object and caption
                    image_list.append((image, caption))
                    
                except Exception as e:
                    print(f"Error processing image for {camera_name}: {e}")
                    continue
        
        return image_list

    @staticmethod
    def create_camera_grid_html(monitoring_data: Optional[MonitoringData]) -> str:
        """Create an HTML grid display of camera images"""
        if not monitoring_data or not monitoring_data.camera_images:
            return "<p style='text-align: center; color: #ef4444;'>No camera images available</p>"
        
        cameras_html = ""
        
        # Define camera order for consistent layout - updated for new API format
        camera_order = ["north_camera", "east_camera", "south_camera", "west_camera"]
        
        # If the expected camera keys don't exist, use whatever keys are available
        available_cameras = list(monitoring_data.camera_images.keys())
        cameras_to_display = [cam for cam in camera_order if cam in available_cameras] or available_cameras
        
        for camera_key in cameras_to_display:
            if camera_key in monitoring_data.camera_images:
                camera_data = monitoring_data.camera_images[camera_key]
                
                # Handle both CameraData objects and dict structures from API
                if hasattr(camera_data, 'image_base64'):
                    # CameraData object
                    image_base64 = camera_data.image_base64
                    direction = camera_data.direction
                    camera_id = camera_data.camera_id
                elif isinstance(camera_data, dict):
                    # Dict from API
                    image_base64 = camera_data.get('image_base64')
                    direction = camera_data.get('direction', 'unknown')
                    camera_id = camera_data.get('camera_id', 'unknown')
                else:
                    continue
                
                if image_base64:
                    # Create data URL for image
                    image_src = f"data:image/jpeg;base64,{image_base64}"
                    
                    cameras_html += f"""
                    <div style="background: #374151; border-radius: 8px; padding: 12px; text-align: center; 
                                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
                        <h4 style="color: #f3f4f6; margin: 0 0 8px 0; font-size: 0.9em;">
                            {direction.upper()} VIEW - {camera_id}
                        </h4>
                        <div style="position: relative; display: inline-block; width: 100%;">
                            <img src="{image_src}" 
                                 style="width: 100%; max-width: 350px; height: 200px; object-fit: cover; 
                                        border-radius: 6px; border: 2px solid #6b7280; 
                                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);" 
                                 alt="{direction} view">
                            <div style="position: absolute; top: 6px; right: 6px; 
                                        background: rgba(220,38,38,0.9); color: white; 
                                        padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: bold;">
                                ● LIVE
                            </div>
                        </div>
                    </div>
                    """
                else:
                    cameras_html += f"""
                    <div style="background: #374151; border-radius: 8px; padding: 12px; text-align: center;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
                        <h4 style="color: #f3f4f6; margin: 0 0 8px 0; font-size: 0.9em;">
                            {direction.upper()} VIEW - {camera_id}
                        </h4>
                        <div style="background: #4b5563; border-radius: 6px; padding: 30px; color: #9ca3af; 
                                    height: 200px; display: flex; flex-direction: column; justify-content: center; 
                                    align-items: center; border: 2px solid #6b7280;">
                            <div style="font-size: 36px; margin-bottom: 8px;">📷</div>
                            <div style="font-size: 12px;">No image available</div>
                        </div>
                    </div>
                    """
        
        return f"""
        <div style="background: #1f2937; border-radius: 12px; padding: 15px; margin: 10px 0;">
            <h3 style="color: #f3f4f6; margin: 0 0 15px 0; text-align: center;">📹 Camera Feeds</h3>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                {cameras_html}
            </div>
        </div>
        """
    
    @staticmethod
    def create_system_info(monitoring_data: Optional[MonitoringData] = None) -> str:
        """Create system information footer with current status"""
        import datetime
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Get system status information
        last_update = "N/A"
        system_status = "OFFLINE"
        
        if monitoring_data:
            last_update = monitoring_data.timestamp or current_time
            system_status = "ONLINE"
        
        return f"""
        <div style="
            background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid #4b5563;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        ">
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 15px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 12px;
            ">
                <div>
                    <strong style="color: #60a5fa;">System Status:</strong>
                    <span style="color: {'#10b981' if system_status == 'ONLINE' else '#ef4444'};">
                        {'🟢' if system_status == 'ONLINE' else '🔴'} {system_status}
                    </span>
                </div>
                <div>
                    <strong style="color: #60a5fa;">Last Update:</strong>
                    <span style="color: #d1d5db;">{last_update}</span>
                </div>
                <div>
                    <strong style="color: #60a5fa;">Current Time:</strong>
                    <span style="color: #d1d5db;">{current_time}</span>
                </div>
                <div>
                    <strong style="color: #60a5fa;">Dashboard:</strong>
                    <span style="color: #10b981;">RSU Monitor v1.0</span>
                </div>
            </div>
        </div>
        """