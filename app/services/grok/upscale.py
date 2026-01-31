"""Video upscale manager"""

from urllib.parse import urlparse
from typing import Dict, Any, Optional
from curl_cffi.requests import AsyncSession

from app.services.grok.statsig import get_dynamic_headers
from app.services.grok.cache import video_cache_service
from app.core.exception import GrokApiException
from app.core.config import setting
from app.core.logger import logger

# Constant definitions
UPSCALE_ENDPOINT = "https://grok.com/rest/media/video/upscale"
REQUEST_TIMEOUT = 180
IMPERSONATE_BROWSER = "chrome133a"


class VideoUpscaleManager:
    """
    Grok video upscale manager
    
    Provides video upscaling functionality
    """

    @staticmethod
    async def upscale(video_id: str, auth_token: str) -> Optional[Dict[str, Any]]:
        """
        Upscale video to HD
        
        Args:
            video_id: The ID of the video to upscale
            auth_token: Authentication token
            
        Returns:
            Upscale result including hdMediaUrl
        """
        try:
            # Validate parameters
            if not video_id:
                raise GrokApiException("Video ID missing", "INVALID_PARAMS")

            if not auth_token:
                raise GrokApiException("Authentication token missing", "NO_AUTH_TOKEN")

            # Build payload
            payload = {
                "videoId": video_id
            }

            # Get authentication token and cookie
            cf_clearance = setting.grok_config.get("cf_clearance", "")
            cookie = f"{auth_token};{cf_clearance}" if cf_clearance else auth_token

            # Get proxy configuration
            proxy_url = setting.grok_config.get("proxy_url", "")
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

            # Send async request
            async with AsyncSession() as session:
                response = await session.post(
                    UPSCALE_ENDPOINT,
                    headers={
                        **get_dynamic_headers("/rest/media/video/upscale"),
                        "Cookie": cookie,
                    },
                    json=payload,
                    impersonate=IMPERSONATE_BROWSER,
                    timeout=REQUEST_TIMEOUT,
                    proxies=proxies,
                )

                # Check response
                if response.status_code == 200:
                    result = response.json()
                    hd_url = result.get("hdMediaUrl", "")
                    logger.debug(f"[VideoUpscale] Video upscale successful, HD URL: {hd_url}")

                    # Cache video
                    if hd_url:
                        try:
                            # Extract path from URL
                            parsed_url = urlparse(hd_url)
                            video_path = parsed_url.path
                            
                            # Download and cache
                            cache_path = await video_cache_service.download_video(video_path, auth_token)
                            
                            if cache_path:
                                # Generate local URL
                                safe_path = video_path.lstrip('/').replace('/', '-')
                                base_url = setting.global_config.get("base_url", "")
                                local_video_url = f"{base_url}/images/{safe_path}" if base_url else f"/images/{safe_path}"
                                logger.debug(f"[VideoUpscale] Video cached successfully, local URL: {local_video_url}")
                                hd_url = local_video_url
                        except Exception as e:
                            logger.warning(f"[VideoUpscale] Failed to cache video: {e}")

                    return {
                        "hd_media_url": hd_url,
                        "success": True,
                        "data": result
                    }
                else:
                    error_msg = f"Status code: {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = f"{error_msg}, Details: {error_data}"
                    except:
                        error_msg = f"{error_msg}, Details: {response.text[:200]}"

                    logger.error(f"[VideoUpscale] Video upscale failed: {error_msg}")
                    raise GrokApiException(f"Video upscale failed: {error_msg}", "UPSCALE_ERROR")

        except GrokApiException:
            raise
        except Exception as e:
            logger.error(f"[VideoUpscale] Video upscale exception: {e}")
            raise GrokApiException(f"Video upscale exception: {e}", "UPSCALE_ERROR") from e
