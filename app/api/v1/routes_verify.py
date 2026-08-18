import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app.core.msgpack_response import MsgPackResponse
from app.core.security import rate_limiter, verify_api_key
from app.domain.verification_service import verification_service
from app.infra.redis_client import redis_manager

router = APIRouter(prefix="/v1", tags=["Verification"])


EMAIL_SYNTAX_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class EmailVerifyRequest(BaseModel):
    email: str = Field(
        ...,
        max_length=254,
        description="RFC 5322 compliant email address to verify",
        examples=["user@example.com"],
    )

    @field_validator("email")
    @classmethod
    def validate_email_syntax(cls, v: str) -> str:
        clean_v = v.strip()
        if not EMAIL_SYNTAX_REGEX.match(clean_v):
            raise ValueError("Invalid email address syntax")
        return clean_v


class EmailVerifyResponse(BaseModel):
    disposable: bool = Field(description="True if email belongs to a disposable email provider")
    confidence: Literal["high", "medium", "low"] = Field(description="Confidence rating of classification")
    reason: Literal["known_provider", "no_mx", "heuristic", "clean"] = Field(
        description="Specific verification tier reason"
    )
    risk_score: int = Field(default=0, ge=0, le=100, description="Numerical risk score from 0 (safe) to 100 (disposable)")
    mx_provider: str | None = Field(default=None, description="Identified infrastructure MX provider")
    did_you_mean: str | None = Field(default=None, description="Suggested legitimate domain typo fix if detected")
    request_id: str = Field(description="Unique request tracing UUID")


class EmailBatchVerifyRequest(BaseModel):
    emails: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Batch of RFC 5322 compliant emails to verify (max 100 per request)",
        examples=[["user1@example.com", "user2@mailinator.com"]],
    )


class EmailBatchVerifyResponse(BaseModel):
    total_processed: int = Field(description="Total emails processed in batch")
    results: list[EmailVerifyResponse] = Field(description="List of verification responses")
    request_id: str = Field(description="Unique batch request tracing UUID")


@router.post(
    "/verify-email",
    response_model=EmailVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify if an email belongs to a disposable provider",
    description=(
        "Analyzes email domain across Bloom filter, Redis MX cache, DNS MX queries, "
        "and heuristics. Strictly complies with Privacy by Design: email is NEVER returned "
        "in the response body or logged. Supports Accept: application/x-msgpack for binary response."
    ),
)
async def verify_email(
    payload: EmailVerifyRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    accept: str | None = Header(default=None, alias="Accept"),
) -> Any:
    # 1. Apply sliding window rate limit
    await rate_limiter.check_rate_limit(
        request=request,
        redis_client=redis_manager.client,
    )

    req_id = x_request_id or str(uuid.uuid4())

    # 2. Execute verification pipeline
    result = await verification_service.verify_email_domain(
        email_str=payload.email,
        request_id=req_id,
    )

    response_data = EmailVerifyResponse(
        disposable=result.disposable,
        confidence=result.confidence,
        reason=result.reason,
        risk_score=result.risk_score,
        mx_provider=result.mx_provider,
        did_you_mean=result.did_you_mean,
        request_id=result.request_id,
    )

    # 3. Handle MessagePack binary response if requested
    if accept and "application/x-msgpack" in accept.lower():
        return MsgPackResponse(response_data.model_dump())

    return response_data


@router.post(
    "/verify-batch",
    response_model=EmailBatchVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch verify multiple email addresses concurrently",
    description=(
        "Processes up to 100 emails concurrently with bounded parallelism. "
        "Leverages L1/L2 multi-tier caching for sub-millisecond execution times. "
        "Supports Accept: application/x-msgpack for binary response."
    ),
)
async def verify_email_batch(
    payload: EmailBatchVerifyRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    accept: str | None = Header(default=None, alias="Accept"),
) -> Any:
    if len(payload.emails) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch limit exceeded. Maximum 100 emails per request.",
        )

    await rate_limiter.check_rate_limit(
        request=request,
        redis_client=redis_manager.client,
    )

    req_id = x_request_id or str(uuid.uuid4())

    results = await verification_service.verify_email_batch(payload.emails)

    batch_responses = [
        EmailVerifyResponse(
            disposable=r.disposable,
            confidence=r.confidence,
            reason=r.reason,
            risk_score=r.risk_score,
            mx_provider=r.mx_provider,
            did_you_mean=r.did_you_mean,
            request_id=r.request_id,
        )
        for r in results
    ]

    response_data = EmailBatchVerifyResponse(
        total_processed=len(batch_responses),
        results=batch_responses,
        request_id=req_id,
    )

    if accept and "application/x-msgpack" in accept.lower():
        return MsgPackResponse(response_data.model_dump())

    return response_data
