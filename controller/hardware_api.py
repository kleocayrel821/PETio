from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Hardware, ControllerSettings
from .serializers import HardwareSerializer, ControllerSettingsSerializer

User = get_user_model()

@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def validate_key(request):
    """Validate that a hardware unique_key exists and return basic info."""
    key = request.data.get("unique_key")
    if not key:
        return Response({"error": "unique_key is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        hw = Hardware.objects.get(unique_key=str(key))
    except Hardware.DoesNotExist:
        return Response({"valid": False, "error": "Hardware not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        "valid": True,
        "hardware_id": hw.id,
        "is_paired": hw.is_paired,
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pair_hardware(request):
    """Pair an existing unpaired hardware to the authenticated user."""
    key = request.data.get("unique_key")
    if not key:
        return Response({"error": "unique_key is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        hw = Hardware.objects.get(unique_key=str(key))
    except Hardware.DoesNotExist:
        return Response({"error": "Hardware not found"}, status=status.HTTP_404_NOT_FOUND)
    if hw.is_paired and hw.paired_user_id and hw.paired_user_id != request.user.id:
        return Response({"error": "Hardware already paired to another user"}, status=status.HTTP_409_CONFLICT)
    try:
        with transaction.atomic():
            hw.pair_to_user(request.user)
            # Ensure settings row exists; if previously created in no-account mode, retain it
            ControllerSettings.objects.get_or_create(hardware=hw)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(HardwareSerializer(hw).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_devices(request):
    """List all hardware paired to the authenticated user with settings summary."""
    items = Hardware.objects.filter(paired_user_id=request.user.id).order_by("-updated_at")
    data = []
    for hw in items:
        settings = ControllerSettings.objects.filter(hardware=hw).first()
        data.append({
            "hardware": HardwareSerializer(hw).data,
            "settings": ControllerSettingsSerializer(settings).data if settings else None,
        })
    return Response({"count": len(data), "results": data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def update_settings(request):
    """Create or update controller settings for a hardware device.
    - If hardware is unpaired: allow update with unique_key only (no auth).
    - If paired: require authenticated user to be the owner.
    """
    key = request.data.get("unique_key")
    if not key:
        return Response({"error": "unique_key is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        hw = Hardware.objects.get(unique_key=str(key))
    except Hardware.DoesNotExist:
        return Response({"error": "Hardware not found"}, status=status.HTTP_404_NOT_FOUND)
    if hw.is_paired:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        if hw.paired_user_id != user.id:
            return Response({"error": "Forbidden: hardware owned by another user"}, status=status.HTTP_403_FORBIDDEN)
    instance = ControllerSettings.objects.filter(hardware=hw).first()
    if instance:
        serializer = ControllerSettingsSerializer(instance, data=request.data, partial=True)
    else:
        payload = dict(request.data)
        payload["hardware"] = hw.id
        serializer = ControllerSettingsSerializer(data=payload)
    if serializer.is_valid():
        obj = serializer.save()
        return Response(ControllerSettingsSerializer(obj).data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
