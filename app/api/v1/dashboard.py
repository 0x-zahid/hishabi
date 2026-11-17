"""Owner dashboard endpoints.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md:
- Owner only: Staff or Viewer receive 403.
- Four aggregated sections in one response.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_owner
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.dashboard import DashboardSummaryOut
from app.services import dashboard_service

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


@router.get(
    "/summary",
    response_model=DashboardSummaryOut,
    summary="Get Owner dashboard summary metrics (Owner only)",
)
def get_dashboard_summary(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return today's sales, customer dues, low-stock alerts, and 10 recent transactions."""
    return dashboard_service.get_dashboard_summary(db)
