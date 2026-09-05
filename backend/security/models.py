from typing import Optional, List
from pydantic import BaseModel, Field

class UserRegister(BaseModel):
    """Pydantic schema for user registration requests."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    department_id: Optional[int] = None

class UserLogin(BaseModel):
    """Pydantic schema for credentials validation requests."""
    username: str
    password: str

class UserResponse(BaseModel):
    """Pydantic schema for safe outbound user details (no passwords/hashes)."""
    id: int
    username: str
    role: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
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
    department_id: Optional[int] = None

class UserStatusRequest(BaseModel):
    is_active: bool

class UserRoleRequest(BaseModel):
    role: str

class UserDepartmentUpdateRequest(BaseModel):
    department_id: int

class PasswordResetRequest(BaseModel):
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

# Department Schemas
class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    description: Optional[str] = Field(default="", max_length=255)

class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None

class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    is_active: bool = True
    user_count: int = 0
    document_count: int = 0
    created_at: str
    updated_at: str

# Document Permissions / Sharing Schemas
class DocumentShareRequest(BaseModel):
    user_id: Optional[int] = None
    department_id: Optional[int] = None
    permission: str = Field(default="READ")  # READ, DOWNLOAD, USE_IN_RAG, EDIT, DELETE, SHARE, ALL

class DocumentPermissionResponse(BaseModel):
    id: int
    document_id: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    permission: str
    granted_by: Optional[int] = None
    created_at: str
