# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
FastAPI application entry point for VDMS DataPrep microservice.

This module initializes the FastAPI application with all necessary middleware,
routers, and configuration for the Visual Data Management System (VDMS) based
data preparation microservice.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_vdms.vectorstores import VDMS_Utils

from src.common import logger, settings
from src.common.schema import DataPrepResponse, StatusEnum
from src.core.embedding import _client_cache
from src.endpoints import (
    check_health_router,
    delete_video_router,
    download_video_router,
    list_videos_router,
    process_document_router,
    process_minio_video_router,
    upload_and_process_video_router,
)

# Dump loaded settings, if in debug mode
logger.debug(f"Settings loaded: {settings.model_dump()}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """

    # Execute following during startup
    logger.info("Starting VDMS-Dataprep Service . . .")

    # Run the application
    yield

    # Execute following during shutdown
    if _client_cache:
        logger.info("Updating VDMS index before tearing down . . .")
        for client_key, client_wrapper in _client_cache.items():
            try:
                vdms_utils = VDMS_Utils(client_wrapper.client)
                query = vdms_utils.add_descriptor_set(
                    "FindDescriptorSet",
                    name=settings.DB_COLLECTION,
                    storeIndex=True,
                )

                res, _ = vdms_utils.run_vdms_query([query])
                if res and "FailedCommand" in res[0]:
                    raise ValueError(
                        f"Failed to update VDMS index for collection {settings.DB_COLLECTION}."
                    )

                logger.info(f"VDMS client '{client_key}' index updated successfully.")
            except Exception as e:
                logger.error(f"Error updating index for VDMS client '{client_key}': {e}")

    logger.info("Tearing down VDMS-Dataprep Service . . .")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_DISPLAY_NAME,
    description=settings.APP_DESC,
    root_path="/v1/dataprep",
    lifespan=lifespan,  # Handle startup, shutdown and lifespan of application
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=settings.ALLOW_METHODS.split(","),
    allow_headers=settings.ALLOW_HEADERS.split(","),
)


# Startup event handler for SDK mode initialization
@app.on_event("startup")
async def startup_event():
    """Initialize SDK client and object detection models during app startup if in SDK mode.
    
    This function preloads both the SDK client and object detection models when the 
    application starts up in SDK mode, which improves the response time for the first 
    API requests. If preloading fails, the application still starts normally but may 
    have slower first requests.
    """
    if settings.EMBEDDING_PROCESSING_MODE.lower() == "sdk":
        logger.info("App startup: Preloading SDK client and models for faster first requests...")
        try:
            # Import here to avoid circular imports
            from src.core.embedding.sdk_embedding_helper import preload_sdk_client, preload_object_detector
            from src.core.utils.config_utils import get_config
            
            # Preload and warmup the SDK client
            sdk_success = preload_sdk_client()
            
            if sdk_success:
                logger.info("SDK client preload completed - embedding generation will be fast!")
            else:
                logger.warning("SDK client preload had issues - first embedding request may be slower")
            
            # Get object detection configuration from config
            config = get_config()
            detection_config = config.get('object_detection', {})
            enable_detection = detection_config.get('enabled', True)
            detection_confidence = detection_config.get('confidence_threshold', 0.85)
            
            # Preload object detection model
            detection_success = preload_object_detector(
                enable_object_detection=enable_detection,
                detection_confidence=detection_confidence
            )
            
            if detection_success:
                if enable_detection:
                    logger.info("Object detection model preload completed - detection will be fast!")
                else:
                    logger.info("Object detection disabled - skipping model preload")
            else:
                logger.warning("Object detection preload had issues - first detection request may be slower")
            
            # Overall status
            if sdk_success and detection_success:
                logger.info("All models preloaded successfully - API requests will be optimally fast!")
            else:
                logger.warning("Some model preloads had issues - some API requests may be slower initially")
                
        except Exception as e:
            logger.error(f"Failed to preload models during startup: {e}")
            # Don't fail the app startup, just log the error
    else:
        logger.info(f"App startup: Embedding mode is '{settings.EMBEDDING_PROCESSING_MODE}', skipping model preload")


# Setting up custom error message format
@app.exception_handler(HTTPException)
async def custom_exception_handler(request, exc):
    """Custom exception handler for HTTP exceptions.
    
    Args:
        request: The incoming request object
        exc: The HTTPException that was raised
        
    Returns:
        JSONResponse: A standardized error response using DataPrepResponse format
    """
    error_res = DataPrepResponse(status=StatusEnum.error, message=exc.detail)
    return JSONResponse(content=error_res.model_dump(), status_code=exc.status_code)


# Include routers from endpoints modules

# Health endpoint
app.include_router(check_health_router)

# Document processing endpoint
app.include_router(process_document_router)

# Video processing endpoints
app.include_router(process_minio_video_router)
app.include_router(upload_and_process_video_router)

# Video management endpoints
app.include_router(list_videos_router)
app.include_router(download_video_router)
app.include_router(delete_video_router)

