from rest_framework import serializers
from .models import Bill, Church, Grade, Relationship, UpgradeRequest, Ward, Family, Member
from .services import can_add_member
from rest_framework import serializers
from .models import Package
from .models import ChurchSubscription, Package


class ChurchListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Church
        fields = [
            "id",
            "name",
            "city",
            "diocese_name",
            "email",
            "phone_number",
            "is_active",
            "created_at",
        ]

class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = [
            "id",
            "name",
            "member_limit",
            "rate_per_member_monthly",
            "rate_per_member_yearly",
            "upgrade_rate_monthly",
            "upgrade_rate_yearly",
            "is_custom",
        ]


class SubscribeSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    billing_cycle = serializers.ChoiceField(
        choices=("MONTHLY", "YEARLY")
    )

    def validate(self, data):
        church = self.context["church"]

        if hasattr(church, "churchsubscription"):
            raise serializers.ValidationError(
                "Subscription already exists. Use upgrade."
            )

        try:
            package = Package.objects.get(id=data["package_id"])
        except Package.DoesNotExist:
            raise serializers.ValidationError("Invalid package")

        data["package"] = package
        return data


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = "__all__"
        read_only_fields = ("church",)

    def create(self, validated_data):
        validated_data["church"] = self.context["church"]
        return super().create(validated_data)


class FamilySerializer(serializers.ModelSerializer):
    class Meta:
        model = Family
        fields = "__all__"
        read_only_fields = ("church",)

    def create(self, validated_data):
        validated_data["church"] = self.context["church"]
        return super().create(validated_data)


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = "__all__"
        read_only_fields = ("church", "age")

    def validate(self, data):
        allowed, reason = can_add_member(self.context["church"])
        if not allowed:
            raise serializers.ValidationError(reason)
        return data

    def create(self, validated_data):
        validated_data["church"] = self.context["church"]
        return super().create(validated_data)


class RelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Relationship
        fields = "__all__"

class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model= Grade
        fields= "__all__"


class SubscribeSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    billing_cycle = serializers.ChoiceField(
        choices=("MONTHLY", "YEARLY")
    )

    def validate(self, data):
        church = self.context["church"]

        if hasattr(church, "churchsubscription"):
            raise serializers.ValidationError(
                "Subscription already exists. Use upgrade."
            )

        try:
            package = Package.objects.get(id=data["package_id"])
        except Package.DoesNotExist:
            raise serializers.ValidationError("Invalid package")

        data["package"] = package
        return data


#upgrade package serializer
class UpgradeSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()

    def validate(self, data):
        church = self.context["church"]

        subscription = getattr(church, "churchsubscription", None)
        if not subscription or not subscription.is_active:
            raise serializers.ValidationError("No active subscription")

        try:
            new_package = Package.objects.get(id=data["package_id"])
        except Package.DoesNotExist:
            raise serializers.ValidationError("Invalid package")

        if (
            not new_package.is_custom and
            not subscription.package.is_custom and
            new_package.member_limit <= subscription.package.member_limit
        ):
            raise serializers.ValidationError(
                "Upgrade must be to higher package"
            )

        data["subscription"] = subscription
        data["new_package"] = new_package
        return data

#for knowing member count
class ChurchDashboardSerializer(serializers.Serializer):
    church = serializers.DictField()
    subscription = serializers.DictField(allow_null=True)
    members = serializers.DictField()
    upgrade_required = serializers.BooleanField()


class WardMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = ["id", "ward_name", "ward_number", "place"]


class FamilyMiniSerializer(serializers.ModelSerializer):
    ward = WardMiniSerializer()

    class Meta:
        model = Family
        fields = ["id", "family_name", "house_name", "ward"]


class ChurchMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Church
        fields = ["id", "name", "city", "diocese_name"]


class MemberProfileSerializer(serializers.ModelSerializer):
    family = FamilyMiniSerializer()
    church = ChurchMiniSerializer()

    class Meta:
        model = Member
        fields = [
            "id",
            "name",
            "baptismal_name",
            "gender",
            "marital_status",
            "mobile_no",
            "blood_group",
            "dob",
            "age",
            "family",
            "church",
        ]


class BillListSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(
        source="subscription.package.name",
        read_only=True
    )

    class Meta:
        model = Bill
        fields = [
            "id",
            "bill_type",
            "package_name",
            "billing_cycle",
            "duration_months",
            "amount",
            "status",
            "created_at",
            "breakdown",
        ]

class BillDetailSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(
        source="subscription.package.name",
        read_only=True
    )
    church_name = serializers.CharField(
        source="church.name",
        read_only=True
    )

    class Meta:
        model = Bill
        fields = [
            "id",
            "church_name",
            "package_name",
            "bill_type",
            "billing_cycle",
            "duration_months",
            "amount",
            "status",
            "created_at",
            "paid_at",
            "breakdown",
        ]

#expire
class SubscriptionExpirySerializer(serializers.Serializer):
    package = serializers.CharField()
    billing_cycle = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    days_remaining = serializers.IntegerField()
    status = serializers.CharField()

#upgrade request
class UpgradeRequestSerializer(serializers.ModelSerializer):
    requested_package = serializers.PrimaryKeyRelatedField(
        queryset=Package.objects.filter(is_trial=False)
    )

    class Meta:
        model = UpgradeRequest
        fields = [
            "id",
            "requested_package",
            "requested_capacity",
            "reason",
            "status",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
        ]

    def validate(self, attrs):
        package = attrs.get("requested_package")
        capacity = attrs.get("requested_capacity")

        # 🔒 Custom package requires capacity
        if package.is_custom and not capacity:
            raise serializers.ValidationError(
                {"requested_capacity": "Capacity is required for custom package"}
            )

        # 🔒 Non-custom should not send capacity
        if not package.is_custom and capacity:
            raise serializers.ValidationError(
                {"requested_capacity": "Capacity allowed only for custom package"}
            )

        return attrs