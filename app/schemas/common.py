"""Shared response models.

Owner: Zahid. The error model is defined once here and imported everywhere,
so every failure in the project returns the same JSON shape
(PROJECT_RULES.md, "API Response and Error Format").

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Only 2 kg of চাল is in stock."
  }
}
```
"""

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """The inner object of an error body."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ErrorResponse(BaseModel):
    """The full error body returned by every failing endpoint."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
