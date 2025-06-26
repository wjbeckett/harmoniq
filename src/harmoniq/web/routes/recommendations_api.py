"""
Album Recommendations API Endpoints
Provides REST API for the Album Recommendations page
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from ...recommendation_storage import AlbumRecommendationManager, RecommendationStatus
from ...discovery_library_grower import AlbumDiscoveryEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recommendations", tags=["recommendations"])


# Pydantic models for request/response
class RecommendationResponse(BaseModel):
    id: str
    title: str
    artist: str
    year: Optional[int]
    mbid: Optional[str]
    status: str
    discovered_date: str
    similarity_score: float
    cover_art_url: Optional[str]
    external_ratings: Dict[str, Any]
    tags: List[str]
    user_notes: str
    relative_time: str


class BulkUpdateRequest(BaseModel):
    album_ids: List[str]
    status: str
    user_notes: Optional[str] = ""


class DiscoveryRequest(BaseModel):
    force_refresh: bool = False


def get_recommendation_manager(request: Request) -> AlbumRecommendationManager:
    """Get recommendation manager from app state."""
    manager = getattr(request.app.state, "recommendation_manager", None)
    if not manager:
        raise HTTPException(
            status_code=500, detail="Recommendation manager not initialized"
        )
    return manager


def get_discovery_engine(request: Request) -> AlbumDiscoveryEngine:
    """Get discovery engine from app state."""
    engine = getattr(request.app.state, "discovery_engine", None)
    if not engine:
        raise HTTPException(status_code=500, detail="Discovery engine not initialized")
    return engine


@router.get("/pending", response_model=List[RecommendationResponse])
async def get_pending_recommendations(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, min_length=1),
) -> List[Dict[str, Any]]:
    """Get pending recommendations for user review."""
    try:
        recommendation_manager = get_recommendation_manager(request)

        if search:
            recommendations = recommendation_manager.search_recommendations(
                search, RecommendationStatus.PENDING
            )[:limit]
        else:
            recommendations = recommendation_manager.get_pending_recommendations(limit)

        # Add relative time for each recommendation
        for rec in recommendations:
            rec["relative_time"] = _calculate_relative_time(rec["discovered_date"])

        return recommendations

    except Exception as e:
        logger.error(f"Error fetching pending recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recommendations")


@router.get("/all")
async def get_all_recommendations(
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """Get all recommendations with optional filtering."""
    try:
        recommendation_manager = get_recommendation_manager(request)

        # Parse status if provided
        status_filter = None
        if status:
            try:
                status_filter = RecommendationStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        if search:
            recommendations = recommendation_manager.search_recommendations(
                search, status_filter
            )[:limit]
        else:
            recommendations = recommendation_manager.get_recommendations_by_status(
                status_filter, limit
            )

        # Add relative time
        for rec in recommendations:
            rec["relative_time"] = _calculate_relative_time(rec["discovered_date"])

        return recommendations

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recommendations")


@router.post("/update-status/{album_id}")
async def update_recommendation_status(
    request: Request, album_id: str, status: str, user_notes: Optional[str] = ""
) -> Dict[str, Any]:
    """Update the status of a single recommendation."""
    try:
        recommendation_manager = get_recommendation_manager(request)

        # Validate status
        try:
            status_enum = RecommendationStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        success = recommendation_manager.update_recommendation_status(
            album_id, status_enum, user_notes
        )

        if not success:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        return {
            "success": True,
            "message": f"Recommendation status updated to {status}",
            "album_id": album_id,
            "new_status": status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating recommendation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update recommendation")


@router.post("/bulk-update")
async def bulk_update_recommendations(
    request: Request, bulk_request: BulkUpdateRequest
) -> Dict[str, Any]:
    """Update multiple recommendations at once."""
    recommendation_manager = get_recommendation_manager(request)

    # Validate status
    try:
        status_enum = RecommendationStatus(bulk_request.status)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid status: {bulk_request.status}"
        )

    user_notes = bulk_request.user_notes if bulk_request.user_notes is not None else ""
    results = recommendation_manager.bulk_update_status(
        bulk_request.album_ids, status_enum, user_notes
    )

    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful

    return {
        "success": True,
        "message": f"Updated {successful} recommendations, {failed} failed",
        "total_processed": len(bulk_request.album_ids),
        "successful": successful,
        "failed": failed,
        "results": results,
    }


@router.post("/discover")
async def trigger_discovery(
    request: Request, discovery_request: DiscoveryRequest
) -> Dict[str, Any]:
    """Trigger album discovery process."""
    try:
        discovery_engine = get_discovery_engine(request)

        logger.info("Manual discovery triggered via API")
        results = await discovery_engine.run_discovery_cycle()

        return {
            "success": True,
            "message": f"Discovery complete: {results['new_recommendations']} new recommendations",
            "results": results,
        }
    except Exception as e:
        logger.error(f"Error triggering discovery: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger discovery")


@router.post("/process-approved")
async def process_approved_recommendations(request: Request) -> Dict[str, Any]:
    """Process approved recommendations by adding them to Lidarr."""
    try:
        discovery_engine = get_discovery_engine(request)

        logger.info("Processing approved recommendations via API")
        results = await discovery_engine.process_approved_recommendations()

        return {
            "success": True,
            "message": f"Processed {results['processed']} recommendations: {results['successful']} successful, {results['failed']} failed",
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error processing approved recommendations: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to process approved recommendations"
        )


@router.get("/statistics")
async def get_recommendation_statistics(request: Request) -> Dict[str, Any]:
    """Get recommendation statistics and analytics."""
    try:
        recommendation_manager = get_recommendation_manager(request)

        stats = recommendation_manager.get_statistics()

        # Add some calculated metrics
        total_decisions = stats.get("total_approved", 0) + stats.get("total_denied", 0)
        approval_rate = (
            (stats.get("total_approved", 0) / total_decisions * 100)
            if total_decisions > 0
            else 0
        )

        stats["total_decisions"] = total_decisions
        stats["approval_rate"] = round(approval_rate, 1)
        stats["pending_count"] = stats.get("pending", 0)
        stats["ready_to_process"] = stats.get("approved", 0)

        return stats

    except Exception as e:
        logger.error(f"Error fetching recommendation statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


@router.delete("/cleanup")
async def cleanup_old_recommendations(
    request: Request, days_old: int = Query(30, ge=1, le=365)
) -> Dict[str, Any]:
    """Clean up old denied/failed recommendations."""
    try:
        recommendation_manager = get_recommendation_manager(request)

        removed_count = recommendation_manager.cleanup_old_recommendations(days_old)

        return {
            "success": True,
            "message": f"Cleaned up {removed_count} old recommendations",
            "removed_count": removed_count,
            "days_old": days_old,
        }

    except Exception as e:
        logger.error(f"Error cleaning up recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup recommendations")


@router.get("/preview/{album_id}")
async def get_album_preview(album_id: str, request: Request) -> Dict[str, Any]:
    """Get enhanced preview data for an album."""
    try:
        recommendation_manager = get_recommendation_manager(request)

        # Get the recommendation
        recommendations = recommendation_manager.recommendations["recommendations"]
        if album_id not in recommendations:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        recommendation = recommendations[album_id]

        # TODO: Add more preview data (YouTube links, Spotify previews, etc.)
        preview_data = {
            "album": recommendation,
            "youtube_search_url": f"https://www.youtube.com/results?search_query={recommendation['artist']}+{recommendation['title']}+full+album",
            "spotify_search_url": f"https://open.spotify.com/search/{recommendation['artist']}%20{recommendation['title']}",
            "lastfm_url": f"https://www.last.fm/music/{recommendation['artist'].replace(' ', '+')}/_/{recommendation['title'].replace(' ', '+')}",
            "musicbrainz_url": (
                f"https://musicbrainz.org/release/{recommendation['mbid']}"
                if recommendation.get("mbid")
                else None
            ),
        }

        return preview_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching album preview: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch album preview")


@router.get("/debug")
async def debug_manager(request: Request):
    """Debug endpoint to check manager state."""
    manager = getattr(request.app.state, "recommendation_manager", None)

    if not manager:
        return {"error": "No manager found"}

    import os

    return {
        "manager_exists": manager is not None,
        "file_path": manager.recommendations_file,
        "file_exists": os.path.exists(manager.recommendations_file),
        "file_readable": os.access(manager.recommendations_file, os.R_OK),
        "file_size": (
            os.path.getsize(manager.recommendations_file)
            if os.path.exists(manager.recommendations_file)
            else 0
        ),
        "manager_stats": manager.get_statistics(),
        "pending_count": len(manager.get_pending_recommendations()),
    }


def _calculate_relative_time(iso_date_string: str) -> str:
    """Calculate relative time from ISO date string."""
    try:
        from datetime import datetime

        date = datetime.fromisoformat(iso_date_string)
        now = datetime.now()
        diff = now - date

        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "Just discovered"
    except Exception:
        return "Recently"
