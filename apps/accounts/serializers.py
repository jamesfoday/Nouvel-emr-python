from rest_framework import serializers
from .models import User

class CurrentUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "display_name", "is_staff", "roles")

    def get_roles(self, obj):
        # I expose role names so the client can drive UI guards.
        return list(
            obj.role_bindings.select_related("role").values_list("role__name", flat=True)
        )
