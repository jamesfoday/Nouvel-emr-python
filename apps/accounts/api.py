from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .serializers import CurrentUserSerializer

class WhoAmIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Session-authenticated request; returns the current user + roles.
        return Response(CurrentUserSerializer(request.user).data)
