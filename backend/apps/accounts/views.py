from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    AuthResponseSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeUpdateSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
    issue_tokens,
)

AUTH_THROTTLES = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]


class RegisterView(generics.GenericAPIView):
    """Create a FARMER or WHOLESALE_BUYER account and return the user and tokens."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = AUTH_THROTTLES
    throttle_scope = "auth"

    @extend_schema(auth=[], responses={201: AuthResponseSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        body = {"user": UserSerializer(user).data, "tokens": issue_tokens(user), "role": user.role}
        return Response(body, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """Email + password -> access/refresh JWT. ``role`` is in the token and the response."""

    serializer_class = LoginSerializer
    throttle_classes = AUTH_THROTTLES
    throttle_scope = "auth"

    @extend_schema(auth=[], responses={200: AuthResponseSerializer})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    """Exchange a refresh token for a new access token (and a rotated refresh token)."""

    @extend_schema(auth=[])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """Blacklist the given refresh token so it can no longer be used."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
        except TokenError:
            raise ValidationError({"refresh": ["Token is invalid or expired."]})
        if str(token.get("user_id")) != str(request.user.pk):
            raise ValidationError({"refresh": ["This token does not belong to you."]})
        token.blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """Current user. PATCH may change ``display_name`` and ``phone_number`` only."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        return MeUpdateSerializer if self.request.method == "PATCH" else UserSerializer

    @extend_schema(request=MeUpdateSerializer, responses={200: UserSerializer})
    def patch(self, request, *args, **kwargs):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    """
    Change the password. All existing refresh tokens are revoked and a fresh
    token pair is returned.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = AUTH_THROTTLES
    throttle_scope = "auth"

    @extend_schema(request=ChangePasswordSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password", "updated_at"])
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        return Response(issue_tokens(user))
