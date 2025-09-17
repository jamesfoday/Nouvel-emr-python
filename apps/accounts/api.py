# apps/accounts/api.py
from typing import Any, Dict, List

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator

from rest_framework import status, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.types import OpenApiTypes


class LoginRequestSerializer(serializers.Serializer):
    # I accept username OR email here; I’ll resolve emails to usernames internally.
    username = serializers.CharField()
    password = serializers.CharField()


class WhoAmISerializer(serializers.Serializer):
    is_authenticated = serializers.BooleanField()
    user_id = serializers.IntegerField(required=False)
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    display_name = serializers.CharField(required=False, allow_blank=True)
    roles = serializers.ListField(child=serializers.CharField(), required=False)


@extend_schema(
    summary="Get CSRF token (and set cookie)",
    description=(
        "I set the `csrftoken` cookie and also return the token in JSON so clients "
        "can send it back in the `X-CSRFToken` header for POST/PUT/PATCH/DELETE."
    ),
    responses={200: OpenApiTypes.OBJECT},
)
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        token = get_token(request)
        return Response({"csrfToken": token})


@extend_schema(
    summary="Session login",
    description=(
        "I authenticate with Django sessions. Requires CSRF token. "
        "You can pass username **or** email in the `username` field."
    ),
    request=LoginRequestSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Login body",
            value={"username": "admin", "password": "adminpass"},
        )
    ],
)
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = authenticate(request, username=username, password=password)
        if not user and "@" in username:
            # I resolve email → username fallback.
            U = get_user_model()
            found = U.objects.filter(email__iexact=username).first()
            if found:
                user = authenticate(request, username=found.username, password=password)

        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        login(request, user)
        return Response({"detail": "OK"})


@extend_schema(
    summary="Session logout",
    description="I log out the current session. Requires CSRF token.",
    responses={200: OpenApiTypes.OBJECT},
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"detail": "OK"})


@extend_schema(
    summary="Who am I",
    description=(
        "I return current user info and bound roles. If anonymous, I return `is_authenticated=false`."
    ),
    responses={200: WhoAmISerializer},
)
class WhoAmIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"is_authenticated": False})

        # I pull role names from rbac bindings if present.
        roles = []
        try:
            roles = list(
                request.user.role_bindings.select_related("role").values_list("role__name", flat=True)
            )
        except Exception:
            roles = []

        # I’m defensive about optional fields like display_name on custom user models.
        payload: Dict[str, Any] = {
            "is_authenticated": True,
            "user_id": request.user.id,
            "username": getattr(request.user, "username", ""),
            "email": getattr(request.user, "email", ""),
            "display_name": getattr(request.user, "display_name", getattr(request.user, "first_name", "")),
            "roles": roles,
        }
        return Response(payload)
