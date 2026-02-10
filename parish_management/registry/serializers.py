from rest_framework import serializers
from .models import Baptism, Bill, Church, Grade, Relationship, UpgradeRequest, Ward, Family, Member
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
        fields =  [
            "id",
            "church",
            "ward",
            "family_name",
            "history",
            "origin",
            "family_image",
        ]
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
        fields = ["id", "family_name","ward"]


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
    
#Baptism
class BaptismSerializer(serializers.ModelSerializer):
    class Meta:
        model = Baptism
        fields = "__all__"

    def validate(self, data):
        instance = self.instance

        category = data.get(
            "baptism_category",
            instance.baptism_category if instance else None
        )

        family = data.get(
            "family",
            instance.family if instance else None
        )

        main_member = data.get(
            "main_member",
            instance.main_member if instance else None
        )

        relation = data.get(
            "relation_with_main_member",
            instance.relation_with_main_member if instance else None
        )

        if category == "PARISH":
            if not family:
                raise serializers.ValidationError({
                    "family": "Family is required for parish baptism."
                })
            if not main_member:
                raise serializers.ValidationError({
                    "main_member": "Main member is required for parish baptism."
                })
            if not relation:
                raise serializers.ValidationError({
                    "relation_with_main_member": "Relationship is required for parish baptism."
                })

        if category == "OTHER":
            if family or main_member or relation:
                raise serializers.ValidationError(
                    "Family, main member, and relationship must be empty for outsider baptism."
                )

        return data


class FamilyMemberSerializer(serializers.ModelSerializer):
    relationship = serializers.SerializerMethodField()
    grade_name = serializers.SerializerMethodField()
    family_name = serializers.SerializerMethodField()
    house_name = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = [
            "id",
            "name",
            "gender",
            "dob",
            "mobile_no",
            "phone_no",
            "address",
            "profession",
            "marital_status",
            "blood_group",
            "is_family_head",
            "relationship",
            "grade_name",
            "family_name",
            "house_name",
        ]

    def get_relationship(self, obj):
        if obj.is_family_head:
            return None
        return obj.relationship.name if obj.relationship else None

    def get_grade_name(self, obj):
        return obj.grade.name if obj.grade else None

    def get_family_name(self, obj):
        return obj.family.family_name if obj.family else None

    def get_house_name(self, obj):
        return obj.family.house_name if obj.family else None



#mobile Directory apis
class WardWithFamilyCountSerializer(serializers.ModelSerializer):
    family_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ward
        fields = ["id", "ward_name","place", "family_count"]


class MobileFamilyListSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    head_name = serializers.SerializerMethodField()
    family_image = serializers.SerializerMethodField()
    class Meta:
        model = Family
        fields = [
            "id",
            "family_name",
            "family_image",
            "head_name",
            "member_count",
        ]

    def get_head_name(self, obj):
        head = obj.members.filter(
            is_family_head=True,
            is_active=True,
            expired=False
        ).first()
        return head.name if head else None
    def get_family_image(self, obj):
        request = self.context.get("request")
        if obj.family_image and request:
            return request.build_absolute_uri(obj.family_image.url)
        return None
    
class MobileFamilyMemberSerializer(serializers.ModelSerializer):
    relationship_name = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = [
            "id",
            "name",
            "gender",
            "dob",
            "age",
            "mobile_no",
            "is_family_head",
            "relationship_name",
        ]

    def get_relationship_name(self, obj):
        if obj.is_family_head:
            return "HEAD"
        return obj.relationship.name if obj.relationship else None

class MobileFamilyDetailSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    class Meta:
        model = Family
        fields = [
            "id",
            "family_name",
            "house_name",
            "family_image",
            "members",
        ]

    def get_members(self, obj):
        members = obj.members.filter(
            is_active=True,
            expired=False
        ).order_by("-is_family_head", "name")

        return MobileFamilyMemberSerializer(
            members,
            many=True
        ).data
