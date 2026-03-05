import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .schemas import UserCreate, UserResponse, LoginRequest, Token, RefreshTokenRequest
from .services import (
    create_user, authenticate_user,
    get_user_by_username, get_user_by_email, get_user_by_id,
    create_access_token, create_refresh_token,
    store_refresh_token, get_refresh_token, revoke_refresh_token,
    decode_access_token,
)

router = APIRouter()
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


# ── dependency ────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
):
    if credentials is None:
        logger.warning("No Authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated – provide a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_access_token(credentials.credentials)
    if token_data is None or token_data.user_id is None:
        logger.warning("Invalid or expired access token received")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials – token invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(session, token_data.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "healthy", "service": "auth-service"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, session: AsyncSession = Depends(get_session)):
    if await get_user_by_username(session, user_data.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    if await get_user_by_email(session, user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return await create_user(session, user_data)


@router.post("/login", response_model=Token)
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await authenticate_user(session, data.username, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token = create_access_token({"sub": str(user.id), "username": user.username})
    refresh_token = create_refresh_token()
    await store_refresh_token(session, user.id, refresh_token)

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh(data: RefreshTokenRequest, session: AsyncSession = Depends(get_session)):
    db_token = await get_refresh_token(session, data.refresh_token)
    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user = await get_user_by_id(session, db_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # rotate tokens
    access_token = create_access_token({"sub": str(user.id), "username": user.username})
    new_refresh = create_refresh_token()
    await revoke_refresh_token(session, data.refresh_token)
    await store_refresh_token(session, user.id, new_refresh)

    return Token(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout")
async def logout(
    data: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    await revoke_refresh_token(session, data.refresh_token)
    logger.info("User %s logged out", current_user.username)
    return {"message": "Successfully logged out"}


@router.get("/verify", response_model=UserResponse)
async def verify(current_user=Depends(get_current_user)):
    """
    Verify a Bearer token and return the user payload.
    Other HTTP services call this to validate tokens without
    needing access to SECRET_KEY or the DB directly.
    """
    return current_user

