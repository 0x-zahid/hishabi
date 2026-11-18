"""AI Bangla entry endpoints.

Owner: Zahid. Module 3.
Complies with PROJECT_RULES.md.

Permissions:
- Owner and staff may use AI entry: both work the counter.

The endpoints only ever produce a **proposal**. Nothing is written to
``sales`` or ``payments`` until the user confirms, and the confirmation goes
through the existing sale service (R12, R13).

Every failure uses the project's error shape:
``{"error": {"code": ..., "message": ...}}``.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai import (
    AIConfirmRequest,
    AIParseRequest,
    AIParseResponse,
    AIRequestMessageOut,
    AIRequestOut,
    AIUsageOut,
)
from app.schemas.common import ErrorResponse
from app.schemas.sale import SaleOut
from app.services import ai_service, sale_service

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

require_owner_or_staff = require_roles("owner", "staff")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/parse",
    response_model=AIParseResponse,
    summary="Parse a Bangla sentence into a sale proposal",
    responses={
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def parse_sale(
    body: AIParseRequest,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Turn one Bangla sentence into a proposal the user can edit.

    The answer is never saved as a sale. It is a proposal with the matched
    customer and products, the closest candidates for anything that did not
    match, and the flags on the fields the user still has to fix.
    """
    row, proposal, warnings, remaining = ai_service.parse_sale_sentence(
        db, current_user.id, body.text, _client_ip(request)
    )
    return {
        "request_id": row.id,
        "status": row.status,
        "proposal": proposal,
        "warnings": warnings,
        "remaining_requests_today": remaining,
    }


@router.get(
    "/requests/today",
    response_model=AIUsageOut,
    summary="Show how many AI requests are left today",
)
def today_usage(
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Return the caller's own usage of the daily AI limit."""
    return ai_service.get_usage(db, current_user.id)


@router.get(
    "/requests/{request_id}",
    response_model=AIRequestOut,
    summary="Get one of the caller's own AI requests",
    responses={404: {"model": ErrorResponse}},
)
def get_request(
    request_id: int,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Return a stored request with the proposal it produced.

    A request that belongs to another user is reported as missing.
    """
    row = ai_service.get_request(db, current_user.id, request_id)
    proposal, warnings = ai_service.stored_proposal(row)
    return {
        "request_id": row.id,
        "status": row.status,
        "input_text": row.input_text,
        "proposal": proposal,
        "warnings": warnings,
        "confirmed": row.confirmed,
        "created_at": row.created_at,
    }


@router.post(
    "/requests/{request_id}/confirm",
    status_code=status.HTTP_201_CREATED,
    response_model=SaleOut,
    summary="Confirm a proposal and record the sale",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def confirm_request(
    request_id: int,
    body: AIConfirmRequest,
    request: Request,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Record the sale behind a proposal the user has edited and accepted.

    The edited proposal is re-validated on the server and the sale is created
    through the existing sale service, so the stock check, the stock ledger
    and the audit row behave exactly as they do for a sale recorded by hand.
    """
    sale = ai_service.confirm_request(
        db, current_user.id, request_id, body, _client_ip(request)
    )
    return sale_service.to_detail(sale)


@router.post(
    "/requests/{request_id}/reject",
    response_model=AIRequestMessageOut,
    summary="Discard a proposal without saving anything",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def reject_request(
    request_id: int,
    current_user: User = Depends(require_owner_or_staff),
    db: Session = Depends(get_db),
):
    """Throw a proposal away. No sale is created and nothing else changes."""
    message = ai_service.reject_request(db, current_user.id, request_id)
    return {"message": message}
