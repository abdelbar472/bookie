from datetime import datetime, timedelta
from typing import Optional
import secrets
import logging

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .models import User, RefreshToken
from .schemas import UserCreate, TokenData
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)


# ── passwords ─────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ── tokens ────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def decode_access_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str = payload.get("sub")
        username: str = payload.get("username")
        token_type: str = payload.get("type")

        if sub is None or token_type != "access":
            return None

        return TokenData(user_id=int(sub), username=username)
    except (JWTError, ValueError, TypeError) as exc:
        logger.warning("Token decode error: %s", exc)
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────

async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, user_data: UserCreate) -> User:
    db_user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
    )
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> Optional[User]:
    logger.info("Authenticating user: %s", username)
    user = await get_user_by_username(session, username)
    if not user or not verify_password(password, user.hashed_password):
        logger.warning("Authentication failed for: %s", username)
        return None
    logger.info("Authentication successful: %s", username)
    return user


async def store_refresh_token(
    session: AsyncSession, user_id: int, token: str
) -> RefreshToken:
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db_token = RefreshToken(token=token, user_id=user_id, expires_at=expires_at)
    session.add(db_token)
    await session.commit()
    await session.refresh(db_token)
    return db_token


async def get_refresh_token(session: AsyncSession, token: str) -> Optional[RefreshToken]:
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.is_revoked == False,  # noqa: E712
            RefreshToken.expires_at > datetime.utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(session: AsyncSession, token: str) -> bool:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    db_token = result.scalar_one_or_none()
    if db_token:
        db_token.is_revoked = True
        await session.commit()
        return True
    return False

