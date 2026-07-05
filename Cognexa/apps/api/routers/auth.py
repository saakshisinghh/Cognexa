from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import jwt
import bcrypt
import secrets
import logging

from apps.api.db import get_db
from apps.api.models import User, RefreshToken, PasswordResetToken, UserRole
from apps.api.schemas.auth import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    RefreshTokenRequest, PasswordChange, UserUpdate,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from apps.api.config import settings
from apps.api.services.audit import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ─── Dependencies ─────────────────────────────────────────────────────────────

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_role(*roles: UserRole):
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return dependency


require_admin = require_role(UserRole.admin)
require_engineer_or_admin = require_role(UserRole.admin, UserRole.engineer)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=UserResponse, status_code=201)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    # SECURITY FIX: role is intentionally NOT taken from the request body —
    # public self-service signup always creates a low-privilege Engineer
    # account. Promotion to Admin/Viewer must go through
    # PATCH /auth/users/{id}/role by an existing admin.
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.engineer,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"New user registered: {user.email}")
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    user = db.query(User).filter(User.email == payload.email, User.is_active == True).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        write_audit_log(
            db, action="login_failed", status="failure", user_email=payload.email,
            ip_address=ip, user_agent=ua, detail="Invalid credentials",
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(user.id, user.role.value)
    raw_refresh = create_refresh_token()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    rt = RefreshToken(token=raw_refresh, user_id=user.id, expires_at=expires)
    db.add(rt)
    user.last_login = datetime.now(timezone.utc)
    write_audit_log(
        db, action="login", status="success", user_id=user.id, user_email=user.email,
        role=user.role.value, ip_address=ip, user_agent=ua,
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(
        RefreshToken.token == payload.refresh_token,
        RefreshToken.revoked == False,
    ).first()
    if not rt:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        rt.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Rotate refresh token
    rt.revoked = True
    new_refresh = create_refresh_token()
    new_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    new_rt = RefreshToken(token=new_refresh, user_id=rt.user_id, expires_at=new_expires)
    db.add(new_rt)
    db.commit()

    user = db.query(User).filter(User.id == rt.user_id).first()
    access_token = create_access_token(user.id, user.role.value)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=204)
def logout(payload: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(RefreshToken.token == payload.refresh_token).first()
    if rt:
        rt.revoked = True
        user = db.query(User).filter(User.id == rt.user_id).first()
        write_audit_log(
            db, action="logout", status="success",
            user_id=rt.user_id, user_email=user.email if user else None,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_me(payload: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    # Role change only by admin
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=204)
def change_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()


@router.get("/users", response_model=list[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 50,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(User).offset(skip).limit(limit).all()


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Fixes issue #6 (Frontend Authentication UX — 'Forgot Password' missing).

    Always returns 202 regardless of whether the email exists, so this
    endpoint can't be used to enumerate registered accounts. If the user
    exists, a reset token is created and logged (in place of an email
    delivery integration, which isn't configured in this environment).
    """
    user = db.query(User).filter(User.email == payload.email, User.is_active == True).first()
    if user:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.add(PasswordResetToken(token=token, user_id=user.id, expires_at=expires))
        db.commit()
        # No SMTP/email provider is configured in this environment — log the
        # reset link so it can be picked up in dev/demo. Wire this to a real
        # mailer (SES/SendGrid/etc.) before using in production.
        logger.info(f"Password reset requested for {user.email}: token={token} (expires in 1h)")
    return {"detail": "If that email is registered, a password reset link has been sent."}


@router.post("/reset-password", status_code=204)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    rt = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == payload.token,
        PasswordResetToken.used == False,
    ).first()
    if not rt or rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(payload.new_password)
    rt.used = True
    # Revoke all existing refresh tokens so old sessions can't outlive the
    # password change.
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked == False).update(
        {"revoked": True}
    )
    db.commit()


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def change_user_role(
    user_id: str,
    role: UserRole,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = target.role.value
    target.role = role
    write_audit_log(
        db, action="role_change", status="success", user_id=admin.id, user_email=admin.email,
        role=admin.role.value, resource=f"user:{user_id}",
        old_value={"role": old_role}, new_value={"role": role.value},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(target)
    return target
