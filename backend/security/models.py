from pydantic import BaseModel, Field

class UserRegister(BaseModel):
    """Pydantic schema for user registration requests."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    """Pydantic schema for credentials validation requests."""
    username: str
    password: str

class UserResponse(BaseModel):
    """Pydantic schema for safe outbound user details (no passwords/hashes)."""
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool = False
    created_at: str

class TokenResponse(BaseModel):
    """Pydantic schema representing successful authentication payload."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class UserProvisionRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: str = "user"

class UserStatusRequest(BaseModel):
    is_active: bool

class UserRoleRequest(BaseModel):
    role: str

class PasswordResetRequest(BaseModel):
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
