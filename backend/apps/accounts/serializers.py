from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Role, normalize_email_address

User = get_user_model()


def issue_tokens(user) -> dict:
    """Create a refresh/access pair. Both carry the user's ``role`` claim."""
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "role", "display_name", "phone_number", "created_at", "updated_at"]
        read_only_fields = ["id", "email", "role", "created_at", "updated_at"]


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class AuthResponseSerializer(serializers.Serializer):
    """Shape returned by register and login."""

    user = UserSerializer()
    tokens = TokenPairSerializer()
    role = serializers.ChoiceField(choices=Role.choices)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    role = serializers.ChoiceField(choices=Role.choices)

    class Meta:
        model = User
        fields = ["email", "password", "role", "display_name", "phone_number"]
        extra_kwargs = {
            "display_name": {"required": True, "allow_blank": False},
            "phone_number": {"required": False},
        }

    def validate_email(self, value):
        email = normalize_email_address(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs):
        candidate = User(email=attrs.get("email"), display_name=attrs.get("display_name", ""))
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """Email + password -> JWT pair, with ``role`` in the claims and response."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs):
        attrs[self.username_field] = normalize_email_address(attrs.get(self.username_field))
        data = super().validate(attrs)
        return {
            "user": UserSerializer(self.user).data,
            "tokens": {"access": data["access"], "refresh": data["refresh"]},
            "role": self.user.role,
        }


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class MeUpdateSerializer(serializers.ModelSerializer):
    """
    PATCH /auth/me/. ``role`` and ``email`` are accepted in the payload only if
    unchanged (so clients can send the whole object back); any change is
    rejected with a validation error.
    """

    role = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)

    class Meta:
        model = User
        fields = ["display_name", "phone_number", "role", "email"]
        extra_kwargs = {"display_name": {"allow_blank": False}}

    def validate_role(self, value):
        if value != self.instance.role:
            raise serializers.ValidationError("Your account type cannot be changed.")
        return value

    def validate_email(self, value):
        if normalize_email_address(value) != self.instance.email:
            raise serializers.ValidationError("Your email address cannot be changed here.")
        return value

    def update(self, instance, validated_data):
        validated_data.pop("role", None)
        validated_data.pop("email", None)
        return super().update(instance, validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate(self, attrs):
        validate_password(attrs["new_password"], user=self.context["request"].user)
        return attrs
