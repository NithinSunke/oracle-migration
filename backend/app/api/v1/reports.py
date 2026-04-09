from fastapi import APIRouter, HTTPException, Response, status

from backend.app.schemas.report import RecommendationReport
from backend.app.services.report_service import report_service

router = APIRouter()


@router.get("/{request_id}", response_model=RecommendationReport)
async def get_report(request_id: str) -> RecommendationReport:
    report = report_service.get(request_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for '{request_id}' was not found.",
        )
    return report


@router.post("/{request_id}", response_class=Response)
async def download_report(request_id: str) -> Response:
    report_json = report_service.render_json(request_id)
    if report_json is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for '{request_id}' was not found.",
        )

    headers = {
        "Content-Disposition": f'attachment; filename="{request_id}-report.json"',
    }
    return Response(content=report_json, media_type="application/json", headers=headers)
