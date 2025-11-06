"""
DRF serializers for Marketplace app models: Category, Listing, MessageThread, Message,
Transaction, and Report. These serializers normalize model fields for RESTful
endpoints while keeping relationships explicit and avoiding deep nesting by default.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, Listing, MessageThread, Message, Transaction, Report

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    """Lightweight user serializer exposing id and username only."""

    class Meta:
        model = User
        fields = ["id", "username"]


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