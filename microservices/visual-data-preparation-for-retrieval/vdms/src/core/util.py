# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import io
import json
import pathlib
import uuid
from typing import Dict, List, Optional, Tuple, NamedTuple

import cv2
import yaml
import shutil
import torch
from tzlocal import get_localzone
from decord import VideoReader, cpu
from PIL import Image, ImageFile
from torchvision.transforms import ToPILImage

# Allow loading truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

from src.common import DataPrepException, Strings, logger, settings
from src.core.minio_client import MinioClient

# Initialize torchvision transform
toPIL = ToPILImage()


def sanitize_input(input: str) -> str | None:
    """Takes an string input and strips whitespaces. Returns None if
    string is empty else returns the string.
    """
    input = str.strip(input)
    if len(input) == 0:
        return None

    return input


def read_config(config_file: str | pathlib.Path, type: str = "yaml") -> dict | None:
    """Takes a yaml/json file path as input. Parses and returns
    the file content as dictionary.
    """
    path = pathlib.Path(config_file)
    config: dict = {}

    try:
        with open(path.absolute(), "r") as f:
            if type == "yaml" or path.suffix.lower() == "yaml":
                config = yaml.safe_load(f)
            elif type == "json" or path.suffix.lower() == "json":
                config = json.load(f)

    except Exception as ex:
        logger.error(f"Error while reading config file: {ex}")
        config = None

    return config


def save_video_to_temp(data: io.BytesIO, filename: str, temp_dir: str) -> pathlib.Path:
    """Save the video data to a temporary directory.

    Args:
        data (io.BytesIO): The video data
        filename (str): The filename to use
        temp_dir (str): The directory path string where videofile needs to be temporarily saved

    Returns:
        pathlib.Path: Path to the saved file
    """
    temp_file = pathlib.Path(temp_dir) / filename
    temp_file.parent.mkdir(parents=True, exist_ok=True)

    with open(temp_file, "wb") as file:
        file.write(data.read())

    return temp_file


def get_minio_client() -> MinioClient:
    """Get a configured Minio client instance.

    Returns:
        MinioClient: A configured Minio client

    Raises:
        Exception: If Minio client configuration is missing
    """
    if (
        not settings.MINIO_ENDPOINT
        or not settings.MINIO_ACCESS_KEY
        or not settings.MINIO_SECRET_KEY
    ):
        logger.error("Minio configuration is incomplete")
        raise Exception(Strings.minio_conn_error)

    try:
        return MinioClient(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    except Exception as ex:
        logger.error(f"Failed to initialize Minio client: {ex}")
        raise DataPrepException(status_code=500, msg=Strings.minio_conn_error)


def get_video_from_minio(
    bucket_name: str, video_id: str, video_name: Optional[str] = None
) -> Tuple[io.BytesIO, str]:
    """Get video data from Minio storage.

    Args:
        bucket_name (str): The bucket containing the video
        video_id (str): The directory (video_id) containing the video
        video_name (Optional[str], optional): Specific video filename. If None, first video found is used.

    Returns:
        Tuple[io.BytesIO, str]: Tuple containing the video data and the video filename

    Raises:
        DataPrepException: If video not found or other Minio error occurs
    """
    try:
        minio_client = get_minio_client()

        # Determine the object name
        object_name = None
        if video_name:
            # If video_name is provided, use it directly
            object_name = f"{video_id}/{video_name}"
        else:
            # Otherwise, find the first video in the directory
            object_name = minio_client.get_video_in_directory(bucket_name, video_id)

        if not object_name:
            logger.error(f"No video found in directory {video_id}")
            raise DataPrepException(status_code=404, msg=Strings.video_id_not_found)

        # Get the video data
        data = minio_client.download_video_stream(bucket_name, object_name)
        if not data:
            logger.error(f"Failed to download video {object_name}")
            raise DataPrepException(status_code=404, msg=Strings.minio_file_not_found)

        # Extract just the filename part
        filename = pathlib.Path(object_name).name

        return data, filename
    except DataPrepException as ex:
        # Re-raise DataPrepException directly
        raise ex
    except Exception as ex:
        logger.error(f"Error getting video from Minio: {ex}")
        raise DataPrepException(status_code=500, msg=Strings.minio_error)


def get_video_fps_and_frames(video_local_path: pathlib.Path) -> tuple[float, int]:
    """
    Open the video file and get fps and total frames in video

    Args:
        video_local_path (Path) : Path of the video file

    Returns:
        fps, frames (tuple) : A tuple containing float fps and total num of frames (int)
            in the video.
    """
    cap = cv2.VideoCapture(str(video_local_path))
    if not cap.isOpened():
        raise Exception(Strings.video_open_error)

    fps: float = cap.get(cv2.CAP_PROP_FPS)
    total_frames: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    return fps, total_frames


def save_metadata_at_temp(metadata_temp_path: str, metadata: dict) -> pathlib.Path:
    """
    Dumps the metadata dictionary in json format in a temporary file.

    Args:
        metadata_temp_path (str) : Temporary path where metadata json needs to be saved
        metadata (dict) :  the metadata content as python dict

    Returns:
        metadata_file (Path) : Path of the metadata file location
    """
    metadata_path = pathlib.Path(metadata_temp_path)
    metadata_path.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_path / settings.METADATA_FILENAME

    logger.info("Saving video metadata to a temporary file...")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    logger.info("Metadata saved!")
    return metadata_file


# Frame extraction data structures
class FrameInfo(NamedTuple):
    """Information about an extracted frame."""

    frame_number: int
    timestamp: float
    image_path: str
    frame_type: str  # "full_frame" or "detected_crop"
    crop_index: Optional[int] = None
    detection_confidence: Optional[float] = None
    crop_bbox: Optional[Tuple[int, int, int, int]] = None
    detected_label: Optional[str] = None


def create_temp_directory(base_path: str = None) -> str:
    """
    Create a unique temporary directory for frame extraction.
    
    Args:
        base_path: Base path for temporary directories. If None, uses config default.
        
    Returns:
        Path to the created temporary directory
    """
    if base_path is None:
        config = get_config()
        base_path = config.get("frames_temp_dir", "/tmp/dataprep/vdms_frames")
    
    unique_id = uuid.uuid4().hex
    temp_dir = pathlib.Path(base_path) / f"frames_{unique_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


def process_video_with_frame_extraction(
    video_path: str,
    frame_interval: int = None,
    enable_object_detection: bool = None,
    detection_confidence: float = None,
    temp_dir: Optional[str] = None,
    detector=None
) -> Tuple[List[FrameInfo], str]:
    """
    Extract frames from video using frame interval approach.
    This is the core function for the new frame-based processing strategy.
    
    Args:
        video_path: Path to the video file
        frame_interval: Extract every Nth frame. If None, uses config default.
        enable_object_detection: Whether to detect and crop objects. If None, uses config default.
        detection_confidence: Confidence threshold for object detection. If None, uses config default.
        temp_dir: Optional temporary directory path
        detector: Optional YOLOXDetector instance for object detection
        
    Returns:
        Tuple of (frame_info_list, manifest_path)
        
    Raises:
        Exception: If video processing fails
    """
    try:
        # Get config defaults if parameters not provided
        config = get_config()
        
        if frame_interval is None:
            frame_interval = config.get("frame_interval", 15)
        if enable_object_detection is None:
            enable_object_detection = config.get("enable_object_detection", True)
        if detection_confidence is None:
            detection_confidence = config.get("detection_confidence", 0.85)
        
        logger.info(f"Processing video with frame extraction: {video_path}")
        logger.debug(f"Frame interval: {frame_interval}, Object detection: {enable_object_detection}")
        
        # Create temporary directory if not provided
        if temp_dir is None:
            temp_dir = create_temp_directory()
        
        # Use decord for video processing (same as embedding service)
        vr = VideoReader(video_path, ctx=cpu(0))
        fps = vr.get_avg_fps()
        total_frames = len(vr)
        
        logger.debug(f"Video FPS: {fps}, Total frames: {total_frames}")
        
        # Calculate frame indices (every Nth frame)
        frame_indices = list(range(0, total_frames, frame_interval))
        logger.debug(f"Extracting {len(frame_indices)} frames with interval {frame_interval}")
        
        frame_info_list = []
        
        # Process frames one by one using seek and next_frame approach  
        for i, frame_idx in enumerate(frame_indices):
            try:
                # Seek to frame and get it
                vr.seek(frame_idx)
                frame_tensor = vr.next()
                logger.debug(f"Processing frame {i}: frame_idx={frame_idx}, tensor_shape={frame_tensor.shape}")
            except Exception as e:
                logger.error(f"Failed to extract frame {frame_idx}: {e}")
                continue
            timestamp = frame_idx / fps
            
            # Handle different tensor types from decord VideoReader
            try:
                if hasattr(frame_tensor, 'asnumpy'):
                    # It's a decord NDArray - convert to numpy first
                    frame_numpy = frame_tensor.asnumpy()
                    frame_torch = torch.from_numpy(frame_numpy)
                elif hasattr(frame_tensor, 'numpy'):
                    # It's a PyTorch tensor - convert to numpy first
                    frame_numpy = frame_tensor.numpy()
                    frame_torch = torch.from_numpy(frame_numpy)
                elif hasattr(frame_tensor, 'detach'):
                    # It's a PyTorch tensor with gradients - detach first
                    frame_torch = frame_tensor.detach()
                else:
                    # Assume it's already a PyTorch tensor or numpy array
                    if isinstance(frame_tensor, torch.Tensor):
                        frame_torch = frame_tensor
                    else:
                        frame_torch = torch.from_numpy(frame_tensor)
                
                # Convert to PIL Image (ensure correct dimension order: H,W,C -> C,H,W)
                if len(frame_torch.shape) == 3 and frame_torch.shape[-1] == 3:
                    # Format is H,W,C (height, width, channels) - need to permute to C,H,W
                    frame_pil = toPIL(frame_torch.permute(2, 0, 1))
                else:
                    # Assume it's already in correct format
                    frame_pil = toPIL(frame_torch)
                    
            except Exception as tensor_error:
                logger.error(f"Failed to convert frame tensor for frame {frame_idx}: {tensor_error}")
                logger.error(f"Frame tensor type: {type(frame_tensor)}, shape: {getattr(frame_tensor, 'shape', 'unknown')}")
                continue
            
            # Save full frame
            full_frame_filename = f"frame_{frame_idx:06d}.jpg"
            full_frame_path = pathlib.Path(temp_dir) / full_frame_filename
            frame_pil.save(full_frame_path, quality=90, optimize=True)
            
            # Object detection and crop extraction
            if enable_object_detection and detector is not None:
                try:
                    # Get detected crops
                    crops = detector.extract_crops(frame_pil)
                    detection_metadata = detector.get_detection_metadata(frame_pil)
                    
                    logger.debug(f"Frame {frame_idx}: {len(crops)} objects detected")
                    
                    if len(crops) > 0:
                        # If objects are detected, only add crop entries (not full frame)
                        for j, (crop, det_meta) in enumerate(zip(crops, detection_metadata)):
                            crop_filename = f"frame_{frame_idx:06d}_crop_{j:03d}.jpg"
                            crop_path = pathlib.Path(temp_dir) / crop_filename
                            crop.save(crop_path, quality=90, optimize=True)
                            
                            crop_info = FrameInfo(
                                frame_number=frame_idx,
                                timestamp=timestamp,
                                image_path=str(crop_path),
                                frame_type="detected_crop",
                                crop_index=j,
                                detection_confidence=det_meta['confidence'],
                                crop_bbox=tuple(det_meta['bbox']),
                                detected_label=det_meta.get('class_name')
                            )
                            frame_info_list.append(crop_info)
                    else:
                        # No objects detected, add full frame
                        frame_info = FrameInfo(
                            frame_number=frame_idx,
                            timestamp=timestamp,
                            image_path=str(full_frame_path),
                            frame_type="full_frame"
                        )
                        frame_info_list.append(frame_info)
                        
                except Exception as e:
                    logger.warning(f"Object detection failed for frame {frame_idx}: {e}")
                    # Fallback: add full frame when detection fails
                    frame_info = FrameInfo(
                        frame_number=frame_idx,
                        timestamp=timestamp,
                        image_path=str(full_frame_path),
                        frame_type="full_frame"
                    )
                    frame_info_list.append(frame_info)
            else:
                # Object detection not enabled, add full frame
                frame_info = FrameInfo(
                    frame_number=frame_idx,
                    timestamp=timestamp,
                    image_path=str(full_frame_path),
                    frame_type="full_frame"
                )
                frame_info_list.append(frame_info)
            
        # Create frames manifest
        manifest_path = create_frames_manifest(frame_info_list, temp_dir)
        
        logger.info(f"Frame extraction complete: {len(frame_info_list)} frames extracted")
        return frame_info_list, manifest_path
        
    except Exception as e:
        logger.error(f"Error in frame extraction: {e}")
        raise Exception(f"Failed to extract frames from video: {e}")


def create_frames_manifest(frame_info_list: List[FrameInfo], temp_dir: str, video_path: str = None) -> str:
    """
    Create a JSON manifest file for the extracted frames.
    This manifest will be used by the embedding service for batch processing.
    
    Args:
        frame_info_list: List of frame information
        temp_dir: Directory to save the manifest
        video_path: Path to the video file (for batch processing)
        
    Returns:
        Path to the created manifest file
    """
    try:
        # Convert FrameInfo namedtuples to dictionaries
        frames_data = []
        for frame_info in frame_info_list:
            frame_dict = {
                "frame_number": frame_info.frame_number,
                "timestamp": frame_info.timestamp,
                "image_path": frame_info.image_path,
                "type": frame_info.frame_type
            }
            
            # Add optional fields if present
            if frame_info.crop_index is not None:
                frame_dict["crop_index"] = frame_info.crop_index
            if frame_info.detection_confidence is not None:
                frame_dict["detection_confidence"] = frame_info.detection_confidence
            if frame_info.crop_bbox is not None:
                frame_dict["crop_bbox"] = list(frame_info.crop_bbox)
            if frame_info.detected_label is not None:
                frame_dict["detected_label"] = frame_info.detected_label
            
            frames_data.append(frame_dict)
        
        # For video-based processing, optimize frame extraction to avoid duplicates
        if video_path:
            # Extract unique frame numbers and create mapping
            unique_frames_data = []
            frame_to_metadata_map = {}
            seen_frame_numbers = set()
            
            for frame_info in frame_info_list:
                frame_num = frame_info.frame_number
                
                # Create frame dictionary
                frame_dict = {
                    "frame_number": frame_info.frame_number,
                    "timestamp": frame_info.timestamp,
                    "image_path": frame_info.image_path,
                    "type": frame_info.frame_type
                }
                
                # Add optional fields if present
                if frame_info.crop_index is not None:
                    frame_dict["crop_index"] = frame_info.crop_index
                if frame_info.detection_confidence is not None:
                    frame_dict["detection_confidence"] = frame_info.detection_confidence
                if frame_info.crop_bbox is not None:
                    frame_dict["crop_bbox"] = list(frame_info.crop_bbox)
                if frame_info.detected_label is not None:
                    frame_dict["detected_label"] = frame_info.detected_label
                
                frames_data.append(frame_dict)
                
                # For unique frame extraction, only add each frame number once
                if frame_num not in seen_frame_numbers:
                    # Add only the base frame info for video extraction (no crop-specific data)
                    unique_frame_dict = {
                        "frame_number": frame_info.frame_number,
                        "timestamp": frame_info.timestamp,
                        "image_path": frame_info.image_path,
                        "type": "full_frame"  # Always use full_frame for video extraction
                    }
                    unique_frames_data.append(unique_frame_dict)
                    seen_frame_numbers.add(frame_num)
                    frame_to_metadata_map[frame_num] = []
                
                # Add metadata for this frame/crop
                frame_to_metadata_map[frame_num].append(frame_dict)
            
            # Create optimized manifest structure
            # Use unique_frames_data for the main "frames" array that multimodal service will use
            manifest = {
                "frames": unique_frames_data,  # Deduplicated frames for video extraction
                "all_frame_metadata": frames_data,  # Complete metadata for all frames/crops
                "frame_metadata_map": frame_to_metadata_map,  # Map frames to their metadata
                "total_frames": len(unique_frames_data),  # Number of frames to extract
                "total_metadata_entries": len(frames_data),  # Total metadata entries (including crops)
                "extraction_timestamp": datetime.datetime.now().isoformat(),
                "video_path": video_path
            }
            
            logger.info(f"Added video_path to manifest: {video_path}")
            logger.info(f"Video processing optimization: {len(frames_data)} total entries, {len(unique_frames_data)} unique frames to extract")
        else:
            # Create traditional manifest structure for image-based processing
            manifest = {
                "frames": frames_data,
                "total_frames": len(frames_data),
                "extraction_timestamp": datetime.datetime.now().isoformat()
            }
        
        # Save manifest file
        manifest_path = pathlib.Path(temp_dir) / "frames_manifest.json"
        logger.info(f"Creating manifest at: {manifest_path}")
        
        # Ensure directory exists
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Frames manifest created successfully: {manifest_path}")
        
        # Verify file was created
        if manifest_path.exists():
            file_size = manifest_path.stat().st_size
            logger.info(f"Manifest file size: {file_size} bytes")
        else:
            logger.error(f"Manifest file was not created at {manifest_path}")
            raise Exception(f"Failed to create manifest file at {manifest_path}")
            
        return str(manifest_path)
        
    except Exception as e:
        logger.error(f"Error creating frames manifest: {e}")
        raise Exception(f"Failed to create frames manifest: {e}")


def create_enhanced_frame_metadata(
    video_metadata: dict,
    frame_info: FrameInfo,
    frame_interval: int,
    enable_object_detection: bool
) -> dict:
    """
    Create enhanced metadata for a single frame that preserves all video context
    while adding frame-specific information.
    
    Args:
        video_metadata: Original video metadata dictionary
        frame_info: Frame-specific information
        frame_interval: Frame extraction interval used
        enable_object_detection: Whether object detection was enabled
        
    Returns:
        Enhanced metadata dictionary for the frame
    """
    # Start with all original video metadata
    enhanced_metadata = video_metadata.copy()
    
    # Add frame-specific metadata
    enhanced_metadata.update({
        "frame_number": frame_info.frame_number,
        "timestamp": frame_info.timestamp,
        "frame_interval": frame_interval,
        "embedding_type": "frame",
        "is_detected_crop": frame_info.frame_type == "detected_crop",
        "enable_object_detection": enable_object_detection,
        "processing_timestamp": datetime.datetime.now().isoformat()
    })
    
    # Add detection-specific metadata if applicable
    if frame_info.frame_type == "detected_crop":
        enhanced_metadata.update({
            "crop_index": frame_info.crop_index,
            "detection_confidence": frame_info.detection_confidence,
            "crop_bbox": list(frame_info.crop_bbox) if frame_info.crop_bbox else None
        })
    else:
        enhanced_metadata.update({
            "crop_index": None,
            "detection_confidence": None,
            "crop_bbox": None
        })
    
    return enhanced_metadata


def cleanup_temp_directory(temp_dir: str) -> None:
    """
    Clean up temporary directory and all its contents.
    
    Args:
        temp_dir: Path to the temporary directory to clean up
    """
    try:
        temp_path = pathlib.Path(temp_dir)
        if temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temporary directory {temp_dir}: {e}")


# Configuration management for frame-based processing
def _load_base_config() -> dict:
    """Load base configuration from file once and cache it"""
    if not hasattr(_load_base_config, "_cache"):
        try:
            config = read_config(settings.CONFIG_FILEPATH, type="yaml")
            if not config:
                logger.warning("Could not load config file, using empty config")
                config = {}
            _load_base_config._cache = config
        except Exception as e:
            logger.error(f"Error loading base config file: {e}")
            _load_base_config._cache = {}
    
    return _load_base_config._cache


def _get_config_value(setting_name: str, config_path: list):
    """
    Get configuration value with precedence: env_var > config_file
    
    Args:
        setting_name: Name of the setting in environment/settings
        config_path: Path in config dict (e.g., ["frame_processing", "frame_interval"])
    """
    # First try environment/settings
    env_value = getattr(settings, setting_name, None)
    if env_value is not None:
        return env_value
    
    # Then try config file
    config = _load_base_config()
    config_value = config
    for key in config_path:
        if isinstance(config_value, dict) and key in config_value:
            config_value = config_value[key]
        else:
            config_value = None
            break
    
    return config_value


def get_config() -> dict:
    """
    Get complete configuration with validation.
    Combines processing config with object detection configuration.
    Environment variables override config file settings.
    
    Returns:
        Dictionary containing complete validated configuration
    """
    try:
        config = _load_base_config()
        
        # Build processing configuration
        processing_config = {
            "frame_interval": _get_config_value("FRAME_INTERVAL", ["frame_processing", "frame_interval"]) or 15,
            "enable_object_detection": _get_config_value("ENABLE_OBJECT_DETECTION", ["frame_processing", "enable_object_detection"]),
            "detection_confidence": _get_config_value("DETECTION_CONFIDENCE", ["frame_processing", "detection_confidence"]) or 0.85,
            "frames_temp_dir": _get_config_value("FRAMES_TEMP_DIR", ["frame_processing", "shared_volume", "frames_temp_dir"]) or "/tmp/dataprep/vdms_frames",
            "frames_bucket": _get_config_value("effective_bucket_name", ["frame_processing", "object_storage", "frames_bucket"]) or settings.effective_bucket_name,
            "fallback_order": _get_config_value("STRATEGY_FALLBACK_ORDER", ["frame_processing", "fallback_order"]) or ["shared_volume", "object_storage", "base64_transfer"]
        }
        
        # Build object detection configuration
        object_detection_config = {
            "enabled": processing_config["enable_object_detection"] if processing_config["enable_object_detection"] is not None else False,
            "device": _get_config_value("DETECTION_DEVICE", ["object_detection", "device"]) or "CPU",
            "confidence_threshold": processing_config["detection_confidence"],
            "nms_threshold": _get_config_value("NMS_THRESHOLD", ["object_detection", "nms_threshold"]) or 0.45,
            "input_size": _get_config_value("DETECTION_INPUT_SIZE", ["object_detection", "input_size"]) or [640, 640],
            "model_dir": settings.DETECTION_MODEL_DIR,  # Environment variable takes highest priority
            "model_name": _get_config_value("DETECTION_MODEL_NAME", ["object_detection", "model_name"])  # No default - must be explicitly set
        }
        
        # Validate configuration
        validated_config = _validate_config(processing_config, object_detection_config)
        
        logger.debug(f"Complete configuration loaded and validated: {validated_config}")
        return validated_config
        
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise ValueError(f"Failed to load configuration: {e}")


def _validate_config(processing_config: dict, object_detection_config: dict) -> dict:
    """
    Validate and sanitize configuration parameters.
    
    Args:
        processing_config: Processing configuration dictionary
        object_detection_config: Object detection configuration dictionary
        
    Returns:
        Validated configuration dictionary
        
    Raises:
        ValueError: If configuration is invalid
    """
    validated_config = processing_config.copy()
    
    # Validate frame_interval
    frame_interval = validated_config.get("frame_interval", 15)
    if not isinstance(frame_interval, int) or frame_interval < 1:
        raise ValueError(f"frame_interval must be a positive integer, got: {frame_interval}")
    validated_config["frame_interval"] = frame_interval
    
    # Validate detection_confidence
    detection_confidence = validated_config.get("detection_confidence", 0.85)
    if not isinstance(detection_confidence, (int, float)) or not 0.0 <= detection_confidence <= 1.0:
        raise ValueError(f"detection_confidence must be between 0.0 and 1.0, got: {detection_confidence}")
    validated_config["detection_confidence"] = float(detection_confidence)
    
    # Validate boolean settings
    bool_settings = ["enable_object_detection"]
    for setting in bool_settings:
        if setting in validated_config and validated_config[setting] is not None:
            validated_config[setting] = bool(validated_config[setting])
    
    # Add object detection config
    validated_config["object_detection"] = object_detection_config
    
    logger.debug("Configuration validation successful")
    return validated_config

def clear_config_cache():
    """Clear the configuration cache to force reload from file."""
    if hasattr(_load_base_config, "_cache"):
        delattr(_load_base_config, "_cache")
        logger.debug("Configuration cache cleared")


def create_detector_instance(config: Optional[dict] = None, enable_object_detection: Optional[bool] = None, detection_confidence: Optional[float] = None):
    """
    Create a detector instance based on configuration with API parameter override.
    
    Args:
        config: Configuration dictionary. If None, loads from effective config.
        enable_object_detection: Override for object detection enabled state from API
        detection_confidence: Override for detection confidence from API
        
    Returns:
        YOLOXDetector instance or None if detection is disabled or unavailable
    """
    try:
        # Import detector here to avoid circular imports and handle missing dependencies
        from src.core.object_detection import create_detector
        
        logger.info("Attempting to create detector instance...")
        logger.debug(f"Detector config passed: {config}")
        logger.debug(f"API overrides: enable_object_detection={enable_object_detection}, detection_confidence={detection_confidence}")
        
        # Get effective config to check object detection settings
        effective_config = get_config()
        detection_config = effective_config.get('object_detection', {}).copy()
        
        # Override with API parameters if provided
        if enable_object_detection is not None:
            detection_config['enabled'] = enable_object_detection
            logger.info(f"Overriding object detection enabled with API value: {enable_object_detection}")
        
        if detection_confidence is not None:
            detection_config['confidence_threshold'] = detection_confidence
            logger.info(f"Overriding detection confidence with API value: {detection_confidence}")
        
        # Use the same device as processing components for consistency across all components
        from src.common import settings
        sdk_device = settings.DEVICE
        detection_config['device'] = sdk_device
        logger.info(f"Using processing device for object detection: {sdk_device}")
        
        logger.info(f"Object detection configuration: enabled={detection_config.get('enabled', False)}, "
                   f"device={detection_config.get('device', 'CPU')}, "
                   f"confidence_threshold={detection_config.get('confidence_threshold', 0.5)}")
        
        # Create custom config with overrides
        detector_config = {
            'object_detection': detection_config
        }
        
        detector = create_detector(detector_config)
        
        if detector is None:
            logger.error("create_detector returned None - object detection is likely disabled in configuration")
            return None
            
        logger.info("Detector instance created successfully")
        return detector
        
    except ImportError as e:
        logger.error(f"Detector module not available - ImportError: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create detector instance: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def process_video_with_enhanced_detection(
    video_path: pathlib.Path,
    frame_interval: int = None,
    object_detection_config = None
) -> List[FrameInfo]:
    """
    Enhanced video processing with frame-based extraction and optional object detection.
    
    Args:
        video_path: Path to the video file
        frame_interval: Number of frames between extractions. If None, uses config default.
        object_detection_config: Configuration for object detection
        
    Returns:
        List of FrameInfo objects containing frame metadata
        
    Raises:
        Exception: If video processing fails
    """
    try:
        # Get config defaults if parameters not provided
        config = get_config()
        
        if frame_interval is None:
            frame_interval = config.get("frame_interval", 15)
        
        # Create detector if object detection is enabled
        detector = None
        enable_object_detection = object_detection_config and object_detection_config.enabled
        detection_confidence = (
            object_detection_config.confidence_threshold
            if object_detection_config and hasattr(object_detection_config, "confidence_threshold")
            else config.get("detection_confidence", 0.85)
        )
        
        logger.info(f"Object detection configuration: enabled={enable_object_detection}, "
                   f"confidence_threshold={detection_confidence}")
        
        if enable_object_detection:
            logger.info("Object detection is enabled - attempting to create detector...")
            # Pass None to use the effective config instead of a minimal config
            detector = create_detector_instance(None)
            
            if detector is None:
                error_msg = (
                    "Object detection is REQUIRED but detector is unavailable! "
                    "This could be due to: "
                    "1) Object detection disabled in configuration, "
                    "2) Missing OpenVINO dependencies, "
                    "3) Model download/extraction failure, "
                    "4) Virtual environment not properly activated. "
                    "Check the logs above for specific error details."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                logger.info("Object detector successfully created and ready")
        else:
            logger.info("Object detection is disabled - proceeding with frame-only extraction")
        
        # Process video with frame extraction and optional object detection
        frame_info_list, _ = process_video_with_frame_extraction(
            video_path=str(video_path),
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
            detector=detector
        )
        
        logger.info(f"Enhanced video processing complete: {len(frame_info_list)} items extracted")
        
        return frame_info_list
        
    except Exception as e:
        logger.error(f"Enhanced video processing failed: {e}")
        raise Exception(f"Failed to process video with enhanced detection: {e}")


def store_enhanced_video_metadata(
    bucket_name: str,
    video_id: str,
    video_filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: str,
    frame_interval: int = None,
    enable_object_detection: bool = None,
    detection_confidence: float = None,
    tags: List[str] | str = [],
) -> pathlib.Path:
    """
    Store enhanced video metadata with frame-based processing and object detection support

    Args:
        bucket_name (str): Bucket name where the video is stored
        video_id (str): Directory containing the video
        video_filename (str): Video filename
        temp_video_path (pathlib.Path): Temporary path to the video file
        metadata_temp_path (str): Path to store metadata
        frame_interval (int): Number of frames between extractions. If None, uses config default.
        enable_object_detection (bool): Whether to enable object detection. If None, uses config default.
        detection_confidence (float): Confidence threshold for object detection. If None, uses config default.
        tags (List[str] | str): Tags for the video

    Returns:
        metadata_file_path (Path): Path of the metadata file location
    """
    # Get config defaults if parameters not provided
    config = get_config()
    
    if frame_interval is None:
        frame_interval = config.get("frame_interval", 15)
    if enable_object_detection is None:
        enable_object_detection = config.get("enable_object_detection", True)
    if detection_confidence is None:
        detection_confidence = config.get("detection_confidence", 0.85)
    
    metadata: dict = extract_enhanced_video_metadata(
        temp_video_path=temp_video_path,
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=video_filename,
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
        tags=tags,
    )
    metadata_file_path: pathlib.Path = save_metadata_at_temp(metadata_temp_path, metadata)

    return metadata_file_path


def extract_enhanced_video_metadata(
    temp_video_path: pathlib.Path,
    bucket_name: str,
    video_id: str,
    video_filename: str,
    frame_interval: int = None,
    enable_object_detection: bool = None,
    detection_confidence: float = None,
    tags: List[str] | str = [],
) -> Dict:
    """
    Generates enhanced metadata for a video with frame-based processing and optional object detection.

    Args:
        temp_video_path (pathlib.Path): Path to the video file on disk
        bucket_name (str): Bucket name where the video is stored
        video_id (str): Directory (video_id) containing the video
        video_filename (str): Name of the video file
        frame_interval (int): Number of frames between extractions. If None, uses config default.
        enable_object_detection (bool): Whether to enable object detection. If None, uses config default.
        detection_confidence (float): Confidence threshold for object detection. If None, uses config default.
        tags (List[str] | str): Tags for the video

    Returns:
        metadata (dict): The generated metadata as a python dict
    """
    from src.common.schema import FrameExtractionModeEnum
    
    # Get config defaults if parameters not provided
    config = get_config()
    
    if frame_interval is None:
        frame_interval = config.get("frame_interval", 15)
    if enable_object_detection is None:
        enable_object_detection = config.get("enable_object_detection", True)
    if detection_confidence is None:
        detection_confidence = config.get("detection_confidence", 0.85)
    
    metadata = {}
    logger.info("Extracting enhanced video metadata with frame-based processing...")

    # Generate clean timestamp once 
    date_time = datetime.datetime.now()
    local_timezone = get_localzone()
    current_time_local = date_time.replace(tzinfo=datetime.timezone.utc).astimezone(local_timezone)
    iso_date_time = current_time_local.isoformat()

    # Construct the path to the video in Minio
    video_minio_path = f"{video_id}/{video_filename}"
    video_rel_url = f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
    video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"

    fps, total_frames = get_video_fps_and_frames(temp_video_path)

    # If tags is a list, convert it to a comma-separated string
    if isinstance(tags, List):
        tags: str = ",".join(tags) if tags else ""

    # Process video with frame-based extraction
    if enable_object_detection:
        logger.info("Processing video with enhanced frame extraction and object detection")
        
        # Create object detection config for the enhanced detection pipeline
        from src.common.schema import ObjectDetectionConfig
        object_detection_config = ObjectDetectionConfig(
            enabled=settings.ENABLE_OBJECT_DETECTION,
            confidence_threshold=detection_confidence,
            extraction_mode=FrameExtractionModeEnum.object_detection
        )
        
        # Use the enhanced detection pipeline
        frame_info_list = process_video_with_enhanced_detection(
            temp_video_path,
            frame_interval=frame_interval,
            object_detection_config=object_detection_config,
        )
        
        # Generate metadata for each extracted frame/crop
        for idx, frame_info in enumerate(frame_info_list):
            keyname = f"{video_id}_{idx}"
            
            # Calculate interval info based on frame number
            interval_num = frame_info.frame_number // frame_interval
            start_time = frame_info.timestamp
            
            metadata[keyname] = {
                "timestamp": start_time,
                "video_id": video_id,
                "video": video_filename,
                "interval_num": interval_num,
                "frame_number": frame_info.frame_number,
                "frame_type": frame_info.frame_type,
                "image_path": frame_info.image_path,
                "created_at": iso_date_time,
                "fps": int(fps),
                "total_frames": total_frames,
                "video_temp_path": str(temp_video_path),
                "video_remote_path": video_minio_path,
                "bucket_name": bucket_name,
                "video_url": video_url,
                "video_rel_url": video_rel_url,
                "tags": tags,
                "object_detection_enabled": True,
                "extraction_mode": object_detection_config.extraction_mode.value,
                "frame_interval": frame_interval,
            }
            
            # Add object detection specific metadata if this is a crop
            if frame_info.frame_type == "detected_crop":
                metadata[keyname].update({
                    "crop_index": frame_info.crop_index,
                    "detection_confidence": frame_info.detection_confidence,
                    "crop_bbox": frame_info.crop_bbox,
                })
        
        # Create frames manifest using the dedicated function
        manifest_path = create_frames_manifest(frame_info_list, str(temp_video_path.parent), str(temp_video_path))
        
        # Add manifest path to the first metadata entry for reference
        if metadata:
            first_key = next(iter(metadata))
            metadata[first_key]["frames_manifest_path"] = str(manifest_path)
            
    else:
        # Process with basic frame-based extraction (no object detection)
        logger.info("Processing video with basic frame-based extraction")
        
        # Create frame info list for batch processing
        frame_info_list = []
        
        # Calculate frame extraction points based on frame_interval
        frame_count = 0
        for frame_number in range(0, total_frames, frame_interval):
            keyname = f"{video_id}_{frame_count}"
            timestamp = frame_number / fps
            
            # Create FrameInfo for this frame (for batch processing)
            frame_info = FrameInfo(
                frame_number=frame_number,
                timestamp=timestamp,
                image_path=None,  # No individual frame images for video-based processing
                frame_type="full_frame",  # API expects 'full_frame' or 'detected_crop'
                crop_index=None,
                detection_confidence=None,
                crop_bbox=None
            )
            frame_info_list.append(frame_info)
            
            metadata[keyname] = {
                "timestamp": timestamp,
                "video_id": video_id,
                "video": video_filename,
                "interval_num": frame_count,
                "frame_number": frame_number,
                "frame_type": "full_frame",  # API expects 'full_frame' or 'detected_crop'
                "created_at": iso_date_time,
                "fps": int(fps),
                "total_frames": total_frames,
                "video_temp_path": str(temp_video_path),
                "video_remote_path": video_minio_path,
                "bucket_name": bucket_name,
                "video_url": video_url,
                "video_rel_url": video_rel_url,
                "tags": tags,
                "object_detection_enabled": False,
                "extraction_mode": "frame_based",
                "frame_interval": frame_interval,
            }

            frame_count += 1

        # Create frames manifest for batch processing (even without object detection)
        logger.info(f"Creating frames manifest for {len(frame_info_list)} frames...")
        manifest_path = create_frames_manifest(frame_info_list, str(temp_video_path.parent), str(temp_video_path))
        
        # Add manifest path to the first metadata entry for reference
        if metadata:
            first_key = next(iter(metadata))
            metadata[first_key]["frames_manifest_path"] = str(manifest_path)
            logger.info(f"Frames manifest created at: {manifest_path}")

    return metadata
