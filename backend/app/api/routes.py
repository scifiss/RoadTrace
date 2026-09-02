import asyncio

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.domain import AnalysisRequest, AnalysisResult, AnalysisSummary, HealthResponse
from app.ingestion.repository import RepositoryAcquisitionError, RepositoryInputError

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.post("/analyses", response_model=AnalysisResult, status_code=status.HTTP_201_CREATED)
async def create_analysis(payload: AnalysisRequest, request: Request) -> AnalysisResult:
    try:
        return await asyncio.to_thread(
            request.app.state.analysis_service.analyze_url, payload.repository_url
        )
    except RepositoryInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RepositoryAcquisitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The public repository could not be obtained: {exc}",
        ) from exc


@router.get("/analyses", response_model=list[AnalysisSummary])
async def list_analyses(
    request: Request, limit: int = Query(default=20, ge=1, le=100)
) -> list[AnalysisSummary]:
    return request.app.state.analysis_store.list_recent(limit)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResult)
async def get_analysis(analysis_id: str, request: Request) -> AnalysisResult:
    result = request.app.state.analysis_store.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return result
