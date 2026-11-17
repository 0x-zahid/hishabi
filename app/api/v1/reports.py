"""Reports and export endpoints.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md:
- Owner only: Staff or Viewer receive 403.
- In-memory streaming export for PDF and Excel (zero disk writes).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_owner
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.report import (
    DailySalesReportOut,
    DueReportOut,
    MonthlySalesReportOut,
    ProfitReportOut,
)
from app.services import export_service, report_service

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["reports"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


@router.get(
    "/daily",
    response_model=DailySalesReportOut,
    summary="Get daily sales and profit report (Owner only)",
)
def get_daily_report(
    date: date = Query(..., description="Target report date (YYYY-MM-DD)"),
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return daily sales count, total amount, profit, and cash vs credit split."""
    return report_service.get_daily_sales_report(db, date)


@router.get(
    "/monthly",
    response_model=MonthlySalesReportOut,
    summary="Get monthly sales and profit report (Owner only)",
)
def get_monthly_report(
    year: int = Query(..., ge=2000, le=2100, description="Report year (YYYY)"),
    month: int = Query(..., ge=1, le=12, description="Report month (1-12)"),
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return monthly aggregated sales, profit, and day-by-day summary."""
    return report_service.get_monthly_sales_report(db, year, month)


@router.get(
    "/dues",
    response_model=DueReportOut,
    summary="Get customer dues report (Owner only)",
)
def get_due_report(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return total outstanding dues and individual customer breakdown."""
    return report_service.get_due_report(db)


@router.get(
    "/profit",
    response_model=ProfitReportOut,
    summary="Get profit report for a date range (Owner only)",
)
def get_profit_report(
    start: date = Query(..., description="Start date (inclusive)"),
    end: date = Query(..., description="End date (inclusive)"),
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Return revenue, cost of goods sold, and gross profit."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DATE_RANGE", "message": "start must be on or before end."},
        )
    return report_service.get_profit_report(db, start, end)


@router.get(
    "/{report_type}/export",
    summary="Export report as in-memory PDF or Excel (Owner only)",
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
            },
            "description": "Downloadable file stream.",
        },
        400: {"model": ErrorResponse},
    },
)
def export_report(
    report_type: str,
    format: str = Query("pdf", description="Export format ('pdf' or 'xlsx')"),
    # Parameters for the various reports
    date: date | None = Query(None, description="Date for daily report"),
    year: int | None = Query(None, description="Year for monthly report"),
    month: int | None = Query(None, description="Month for monthly report"),
    start: date | None = Query(None, description="Start date for profit report"),
    end: date | None = Query(None, description="End date for profit report"),
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Stream an in-memory PDF or Excel report without writing to disk."""
    report_type = report_type.lower()
    format = format.lower()

    if report_type not in ("daily", "monthly", "dues", "profit"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REPORT_TYPE",
                "message": f"Report type '{report_type}' is invalid. Must be daily, monthly, dues, or profit.",
            },
        )

    if format not in ("pdf", "xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_FORMAT",
                "message": f"Format '{format}' is invalid. Must be 'pdf' or 'xlsx'.",
            },
        )

    if report_type == "daily":
        target_date = date or date.today()
        data = report_service.get_daily_sales_report(db, target_date).model_dump()
        content, filename, media_type = export_service.export_daily_report(data, format)
    elif report_type == "monthly":
        now = date.today()
        y = year or now.year
        m = month or now.month
        data = report_service.get_monthly_sales_report(db, y, m).model_dump()
        content, filename, media_type = export_service.export_monthly_report(data, format)
    elif report_type == "dues":
        data = report_service.get_due_report(db).model_dump()
        content, filename, media_type = export_service.export_due_report(data, format)
    else:  # profit
        now = date.today()
        s = start or now.replace(day=1)
        e = end or now
        if s > e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_DATE_RANGE", "message": "start must be on or before end."},
            )
        data = report_service.get_profit_report(db, s, e).model_dump()
        content, filename, media_type = export_service.export_profit_report(data, format)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
