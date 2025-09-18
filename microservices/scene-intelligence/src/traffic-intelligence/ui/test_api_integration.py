#!/usr/bin/env python3
"""
Test script to verify the API integration and camera image parsing
"""

import json
import requests
from data_loader import load_monitoring_data_from_api

def test_api_data_structure():
    """Test the API data structure and camera image parsing"""
    print("Testing API integration...")
    
    # Test API endpoint directly
    try:
        response = requests.get("http://10.223.23.199:8081/api/v1/traffic/current", timeout=10)
        response.raise_for_status()
        raw_data = response.json()
        
        print("✓ API endpoint is accessible")
        print(f"Camera images keys: {list(raw_data.get('camera_images', {}).keys())}")
        
        # Check camera images structure
        camera_images = raw_data.get("camera_images", {})
        for camera_key, camera_data in camera_images.items():
            print(f"\nCamera: {camera_key}")
            print(f"  Direction: {camera_data.get('direction')}")
            print(f"  Camera ID: {camera_data.get('camera_id')}")
            print(f"  Has image: {'Yes' if camera_data.get('image_base64') else 'No'}")
            if camera_data.get('image_base64'):
                image_length = len(camera_data.get('image_base64', ''))
                print(f"  Image size: {image_length} characters")
        
    except Exception as e:
        print(f"✗ Error accessing API: {e}")
        return False
    
    # Test data parsing
    try:
        monitoring_data = load_monitoring_data_from_api()
        
        if monitoring_data:
            print(f"\n✓ Data parsing successful")
            print(f"Intersection: {monitoring_data.data.intersection_name}")
            print(f"Total density: {monitoring_data.data.total_density}")
            print(f"Camera images available: {len(monitoring_data.camera_images)}")
            
            for camera_key, camera_data in monitoring_data.camera_images.items():
                print(f"  {camera_key}: {type(camera_data)}")
                if isinstance(camera_data, dict):
                    print(f"    Direction: {camera_data.get('direction')}")
                    print(f"    Has image: {'Yes' if camera_data.get('image_base64') else 'No'}")
                else:
                    print(f"    Direction: {camera_data.direction}")
                    print(f"    Has image: {'Yes' if camera_data.image_base64 else 'No'}")
                    
            return True
        else:
            print("✗ Data parsing failed")
            return False
            
    except Exception as e:
        print(f"✗ Error parsing data: {e}")
        return False

if __name__ == "__main__":
    success = test_api_data_structure()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")