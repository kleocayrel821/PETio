"""
DRF serializers for Marketplace app models: Category, Listing, MessageThread, Message,
Transaction, and Report. These serializers normalize model fields for RESTful
endpoints while keeping relationships explicit and avoiding deep nesting by default.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, Listing, MessageThread, Message, Transaction, Report

User = get_user_model()


13→class UserSummarySerializer(serializers.ModelSerializer):
14→    display_name = serializers.SerializerMethodField()
15→    avatar_url = serializers.SerializerMethodField()
16→
17→    def get_display_name(self, obj):
18→        try:
19→            profile = getattr(obj, "profile", None)
20→            if profile and getattr(profile, "display_name", ""):
21→                return profile.display_name
22→        except Exception:
23→            pass
24→        return ""
25→
26→    def get_avatar_url(self, obj):
27→        try:
28→            profile = getattr(obj, "profile", None)
29→            avatar = getattr(profile, "avatar", None) if profile is not None else None
30→            if avatar:
31→                request = self.context.get("request") if hasattr(self, "context") else None
32→                url = avatar.url
33→                if request is not None:
34→                    try:
35→                        return request.build_absolute_uri(url)
36→                    except Exception:
37→                        return url
38→                return url
39→        except Exception:
40→            pass
41→        return ""
42→
43→    class Meta:
44→        model = User
45→        fields = ["id", "username", "display_name", "avatar_url"]


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for marketplace categories."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ListingSerializer(serializers.ModelSerializer):
    """Serializer for listings with seller summary and category id."""

    seller = UserSummarySerializer(read_only=True)
    seller_id = serializers.PrimaryKeyRelatedField(
        source="seller", queryset=User.objects.all(), write_only=True
    )
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), required=False, allow_null=True
    )
    # Expose full category details read-only to simplify UI rendering (e.g., admin quick view)
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Listing
        fields = [
            "id",
            "seller",
            "seller_id",
            "category_id",
            "category",
            "title",
            "description",
            "price",
            "quantity",
            "main_image",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for individual messages within a thread."""

    sender = UserSummarySerializer(read_only=True)
    sender_id = serializers.PrimaryKeyRelatedField(
        source="sender", queryset=User.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = Message
        fields = [
            "id",
            "thread",
            "sender",
            "sender_id",
            "content",
            "created_at",
            "read_at",
        ]
        read_only_fields = ["id", "created_at", "sender", "read_at"]


class MessageThreadSerializer(serializers.ModelSerializer):
    """Serializer for message threads with buyer/seller summaries."""

    listing_id = serializers.PrimaryKeyRelatedField(source="listing", queryset=Listing.objects.all())
    buyer = UserSummarySerializer(read_only=True)
    buyer_id = serializers.PrimaryKeyRelatedField(
        source="buyer", queryset=User.objects.all(), write_only=True, required=False
    )
    seller = UserSummarySerializer(read_only=True)
    seller_id = serializers.PrimaryKeyRelatedField(
        source="seller", queryset=User.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = MessageThread
        fields = [
            "id",
            "listing_id",
            "buyer",
            "buyer_id",
            "seller",
            "seller_id",
            "status",
            "last_message_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_message_at", "buyer", "seller"]


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for transactions with party summaries."""

    listing_id = serializers.PrimaryKeyRelatedField(source="listing", queryset=Listing.objects.all())
    buyer = UserSummarySerializer(read_only=True)
    buyer_id = serializers.PrimaryKeyRelatedField(
        source="buyer", queryset=User.objects.all(), write_only=True
    )
    seller = UserSummarySerializer(read_only=True)
    seller_id = serializers.PrimaryKeyRelatedField(
        source="seller", queryset=User.objects.all(), write_only=True
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "listing_id",
            "buyer",
            "buyer_id",
            "seller",
            "seller_id",
            "status",
            "payment_method",
            "amount_paid",
            "payment_proof",
            "meetup_time",
            "meetup_place",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "buyer", "seller"]


class ReportSerializer(serializers.ModelSerializer):
    """Serializer for listing reports."""

    reporter = UserSummarySerializer(read_only=True)
    reporter_id = serializers.PrimaryKeyRelatedField(
        source="reporter", queryset=User.objects.all(), write_only=True, required=False
    )
    listing_id = serializers.PrimaryKeyRelatedField(source="listing", queryset=Listing.objects.all())

    class Meta:
        model = Report
        fields = [
            "id",
            "reporter",
            "reporter_id",
            "listing_id",
            "reason",
            "details",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "reporter"]
