import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .grpc_client import validate_token, refresh_token as grpc_refresh, get_user
from .schemas import ProfileResponse, ProfileUpdate, TokenRefreshRequest, TokenResponse, UserPayload
from .services import get_or_create_profile, update_profile

router = APIRouter()
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


# ── dependency: validate token via gRPC → Auth service ────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserPayload:
    if credentials is None:
        logger.warning("No Authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated – provide a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = await validate_token(credentials.credentials)

    if not response.valid:
        logger.warning("Token validation failed: %s", response.error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalid: {response.error}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    u = response.user
    return UserPayload(
        id=u.id,
        username=u.username,
        email=u.email,
        full_name=u.full_name,
        is_active=u.is_active,
        is_superuser=u.is_superuser,
    )


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "healthy", "service": "user-service"}


@router.get("/me", response_model=ProfileResponse)
async def get_me(
    current_user: UserPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get the current user's full profile (auth data + local profile data)."""
    profile = await get_or_create_profile(session, current_user.id)
    return ProfileResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.patch("/me", response_model=ProfileResponse)
async def update_me(
    data: ProfileUpdate,
    current_user: UserPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update the current user's local profile (bio, avatar)."""
    profile = await update_profile(session, current_user.id, data.bio, data.avatar_url)
    return ProfileResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: TokenRefreshRequest):
    """
    Delegate token refresh to Auth service via gRPC.
    User service never holds the SECRET_KEY.
    """
    resp = await grpc_refresh(data.refresh_token)
    if resp.error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=resp.error,
        )
    return TokenResponse(access_token=resp.access_token, refresh_token=resp.refresh_token)


@router.get("/users/{user_id}", response_model=ProfileResponse)
async def get_user_by_id(
    user_id: int,
    current_user: UserPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Fetch any user's profile by id.
    Auth data is fetched from Auth service via gRPC.
    Profile data is from this service's local DB.
    """
    try:
        auth_user = await get_user(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await get_or_create_profile(session, user_id)
    return ProfileResponse(
        id=auth_user.id,
        username=auth_user.username,
        email=auth_user.email,
        full_name=auth_user.full_name,
        is_active=auth_user.is_active,
        is_superuser=auth_user.is_superuser,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )

