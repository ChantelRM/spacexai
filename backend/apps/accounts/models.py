from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Role(models.TextChoices):
    FARMER = "FARMER", "Farmer"
    WHOLESALE_BUYER = "WHOLESALE_BUYER", "Wholesale buyer"


def normalize_email_address(email: str) -> str:
    return (email or "").strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        if not extra_fields.get("role"):
            raise ValueError("A role is required.")
        if extra_fields["role"] not in Role.values:
            raise ValueError(f"Invalid role: {extra_fields['role']}")
        user = self.model(email=normalize_email_address(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=normalize_email_address(email))


class User(AbstractUser):
    """
    Platform user. Logs in with email. Every user is exactly one of the two
    account types in ``Role``; the role is set at registration and cannot be
    changed through the API.

    Other apps should link to this model with
    ``models.ForeignKey(settings.AUTH_USER_MODEL, ...)`` and never duplicate
    its fields.
    """

    username = None
    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    display_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name", "role"]

    objects = UserManager()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.display_name} <{self.email}> ({self.role})"

    def save(self, *args, **kwargs):
        self.email = normalize_email_address(self.email)
        super().save(*args, **kwargs)

    @property
    def is_farmer(self) -> bool:
        return self.role == Role.FARMER

    @property
    def is_wholesale_buyer(self) -> bool:
        return self.role == Role.WHOLESALE_BUYER
