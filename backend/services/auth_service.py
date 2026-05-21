from core.security import create_access_token, verify_password
from repositories.interfaces.user import UserRepositoryProtocol
from services.exceptions import AccountDisabledError, AuthenticationError


class AuthService:
    def __init__(self, repo: UserRepositoryProtocol) -> None:
        self._repo = repo

    def authenticate(self, email: str, password: str) -> str:
        """Validate credentials and return a signed JWT. Raises on any failure."""
        user = self._repo.get_by_email(email)
        # Deliberately check both conditions before raising — don't leak whether the email exists.
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")
        if not user.is_active:
            raise AccountDisabledError("Account disabled")
        return create_access_token(subject=user.email, role=user.role)
