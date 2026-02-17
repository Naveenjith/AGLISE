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
            "family_name",
            "history",
            "origin",
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
        church = self.context["church"]
        allowed, reason = can_add_member(church)
        if not allowed:
            raise serializers.ValidationError(reason)

        # -----------------------------
        # CREATE LOGIC
        # -----------------------------
        if not self.instance:

            # 🔥 Block head creation here
            if data.get("is_family_head"):
                raise serializers.ValidationError(
                    "Use family head API to create family head."
                )

            family = data.get("family")
            house_name = data.get("house_name")

            if not family:
                raise serializers.ValidationError({
                    "family": "Family is required."
                })

            if not house_name:
                raise serializers.ValidationError({
                    "house_name": "House name is required."
                })

            # 🔥 Block manual ward assignment
            if data.get("ward"):
                raise serializers.ValidationError({
                    "ward": "Ward should not be assigned manually."
                })

            # 🔥 Block image upload
            if data.get("family_image"):
                raise serializers.ValidationError({
                    "family_image": "Family image can only be uploaded for family head."
                })

            # 🔥 Ensure house has active head
            head = Member.objects.filter(
                family=family,
                house_name__iexact=house_name.strip(),
                is_family_head=True,
                is_active=True
            ).first()

            if not head:
                raise serializers.ValidationError(
                    "Cannot add member. No active head for this house."
                )

        # -----------------------------
        # UPDATE LOGIC
        # -----------------------------
        else:
            instance = self.instance

            # 🔥 Block promoting head
            if data.get("is_family_head"):
                raise serializers.ValidationError(
                    "Use family head API to assign family head."
                )

            # 🔥 Only head can update image
            if "family_image" in data and not instance.is_family_head:
                raise serializers.ValidationError({
                    "family_image": "Only family head can have family image."
                })

            # 🔥 Block manual ward change
            if "ward" in data:
                raise serializers.ValidationError({
                    "ward": "Ward cannot be modified here."
                })

        return data

    # -----------------------------
    # AUTO ASSIGN WARD ON CREATE
    # -----------------------------
    def create(self, validated_data):
        family = validated_data.get("family")
        house_name = validated_data.get("house_name")

        head = Member.objects.filter(
            family=family,
            house_name__iexact=house_name.strip(),
            is_family_head=True,
            is_active=True
        ).first()

        if not head:
            raise serializers.ValidationError(
                "Cannot add member. No active head for this house."
            )

        # 🔥 Inherit ward from head
        validated_data["ward"] = head.ward

        # 🔥 Attach church
        validated_data["church"] = self.context["church"]

        return super().create(validated_data)




class RelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Relationship
        fields = "__all__"
        read_only_fields = ("church",)
        
    def validate_name(self, value):
        return value.strip().title()



class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = "__all__"
        read_only_fields = ("church",)

    def create(self, validated_data):
        validated_data["church"] = self.context["church"]
        return super().create(validated_data)



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
    ward = serializers.SerializerMethodField()

    class Meta:
        model = Family
        fields = ["id", "family_name", "ward"]

    def get_ward(self, obj):
        head = obj.get_active_head()

        if head and head.ward:
            return {
                "id": head.ward.id,
                "ward_name": head.ward.ward_name,
                "ward_number": head.ward.ward_number,
                "place": head.ward.place,
            }
        return None




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
    house_name = serializers.SerializerMethodField()
    class Meta:
        model = Baptism
        fields = "__all__"

    def get_house_name(self, obj):
        if obj.member:
            return obj.member.house_name
        return None

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

        if category == "PARISH":
            if main_member and not main_member.is_family_head:
                raise serializers.ValidationError({
                    "main_member": "Main member must be a family head."
                })

        if category == "OTHER":
            if family or main_member or relation:
                raise serializers.ValidationError(
                    "Family, main member, and relationship must be empty for outsider baptism."
                )

        return data


class FamilyHeadCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Member
        fields = [
            "family",
            "house_name",   # 🔥 NEW
            "ward",
            "family_image",
            "name",
            "baptismal_name",
            "gender",
            "email",
            "marital_status",
            "spouse_name",
            "dob",
            "mobile_no",
            "phone_no",
            "blood_group",
            "father_name",
            "mother_name",
            "date_of_baptism",
            "parish_of_baptism",
            "educational_qualification",
            "sunday_school_qualification",
            "profession",
            "grade",
            "joining_date",
            "transferred_from",
            "address",
        ]

    def validate(self, data):
        church = self.context["church"]
        family = data.get("family")
        ward = data.get("ward")
        email = data.get("email")
        house_name = data.get("house_name")

        # 🔥 Ensure family belongs to church
        if family.church != church:
            raise serializers.ValidationError(
                "Invalid family selected."
            )

        # 🔥 house_name required
        if not house_name:
            raise serializers.ValidationError({
                "house_name": "House name is required."
            })

        # 🔥 Enforce ONE head per (family + house_name)
        existing_head = Member.objects.filter(
            family=family,
            house_name=house_name,
            is_family_head=True,
            is_active=True
        ).first()

        if existing_head:
            raise serializers.ValidationError(
                "This house already has an active head."
            )

        # 🔥 Ward required
        if not ward:
            raise serializers.ValidationError({
                "ward": "Ward is required for family head."
            })

        # 🔥 Email required
        if not email:
            raise serializers.ValidationError({
                "email": "Email is required for family head login."
            })

        return data

    def create(self, validated_data):
        validated_data["church"] = self.context["church"]
        validated_data["is_family_head"] = True
        validated_data["is_active"] = True

        return Member.objects.create(**validated_data)

class FamilyMemberSerializer(serializers.ModelSerializer):
    relationship = serializers.SerializerMethodField()
    grade_name = serializers.SerializerMethodField()
    family_name = serializers.SerializerMethodField()
    house_name = serializers.SerializerMethodField()
    family_image = serializers.SerializerMethodField()

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
            "family_image",
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
        return obj.house_name  # ✅ FIXED

    def get_family_image(self, obj):
        if obj.is_family_head and obj.family_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.family_image.url)

        # fallback: get from head
        head = Member.objects.filter(
            family=obj.family,
            house_name=obj.house_name,
            is_family_head=True,
            is_active=True
        ).first()

        if head and head.family_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(head.family_image.url)

        return None

#mobile Directory apis
class WardWithFamilyCountSerializer(serializers.ModelSerializer):
    family_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ward
        fields = ["id", "ward_name","place", "family_count","ward_number"]


class MobileFamilyListSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    family_name = serializers.SerializerMethodField()
    family_image = serializers.SerializerMethodField()

    class Meta:
        model = Member  # IMPORTANT
        fields = [
            "id",
            "family_name",
            "house_name",
            "family_image",
            "name",  # head name
            "member_count",
        ]

    def get_family_name(self, obj):
        return obj.family.family_name

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

class MobileFamilyDetailSerializer(serializers.Serializer):
    family_name = serializers.CharField()
    house_name = serializers.CharField()
    family_image = serializers.CharField()
    members = serializers.ListField()


    def get_members(self, obj):
        members = obj.members.filter(
            is_active=True,
            expired=False
        ).order_by("-is_family_head", "name")

        return MobileFamilyMemberSerializer(
            members,
            many=True
        ).data

class MobileFamilyBaptismSerializer(serializers.ModelSerializer):
    gender = serializers.CharField(source="member.gender", read_only=True)

    class Meta:
        model = Baptism
        fields = [
            "id",
            "name",
            "baptismal_name",
            "gender",
            "date_of_baptism",
            "register_number",
        ]


#marriage register
from rest_framework import serializers
from django.db import transaction
from django.db.models import Q
from .models import Marriage, Member


class MarriageSerializer(serializers.ModelSerializer):

    class Meta:
        model = Marriage
        fields = "__all__"

    # ---------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------
    def validate(self, data):
        marriage_type = data.get("marriage_type")

        groom_member = data.get("groom_member")
        groom_name = data.get("groom_name")

        bride_member = data.get("bride_member")
        bride_name = data.get("bride_name")

        transfer_to = data.get("transfer_to")

        # -----------------------------
        # COMMON VALIDATIONS
        # -----------------------------
        if not marriage_type:
            raise serializers.ValidationError("Marriage type is required.")

        # Prevent same person marrying themselves
        if groom_member and bride_member and groom_member == bride_member:
            raise serializers.ValidationError(
                "Groom and bride cannot be the same member."
            )

        # Prevent multiple marriages
        if groom_member and groom_member.marital_status == "MARRIED":
            raise serializers.ValidationError(
                {"groom_member": "Groom is already married."}
            )

        if bride_member and bride_member.marital_status == "MARRIED":
            raise serializers.ValidationError(
                {"bride_member": "Bride is already married."}
            )

        # -----------------------------
        # ADD_BRIDE RULES
        # -----------------------------
        if marriage_type == "ADD_BRIDE":

            if not groom_member:
                raise serializers.ValidationError({
                    "groom_member": "Groom must be a parish member."
                })

            if groom_name:
                raise serializers.ValidationError({
                    "groom_name": "Do not provide groom_name when groom_member is selected."
                })

            if bride_member:
                raise serializers.ValidationError({
                    "bride_member": "Bride must not already be a parish member for ADD_BRIDE."
                })

            if not bride_name:
                raise serializers.ValidationError({
                    "bride_name": "Bride name is required."
                })

            if not data.get("relation_of_bride_with_main_member"):
                raise serializers.ValidationError({
                    "relation_of_bride_with_main_member": "Relationship of bride with main member is required."
                })

        # -----------------------------
        # TRANSFER_BRIDE RULES
        # -----------------------------
        if marriage_type == "TRANSFER_BRIDE":

            if not bride_member:
                raise serializers.ValidationError({
                    "bride_member": "Bride must be an existing parish member."
                })

            if bride_name:
                raise serializers.ValidationError({
                    "bride_name": "Do not provide bride_name when bride_member is selected."
                })

            if not transfer_to:
                raise serializers.ValidationError({
                    "transfer_to": "Transfer destination is required."
                })

        return data

    # ---------------------------------------------------
    # CREATE LOGIC
    # ---------------------------------------------------
    def create(self, validated_data):
        marriage_type = validated_data.get("marriage_type")

        groom_member = validated_data.get("groom_member")
        bride_member = validated_data.get("bride_member")
        bride_name = validated_data.get("bride_name")

        family = validated_data.get("family")
        church = validated_data.get("church")

        relation_bride = validated_data.get("relation_of_bride_with_main_member")

        with transaction.atomic():

            # Create marriage record first
            marriage = Marriage.objects.create(**validated_data)

            # -------------------------------------------------
            # ADD_BRIDE FLOW
            # -------------------------------------------------
            if marriage_type == "ADD_BRIDE":

                # Create bride as new member
                new_bride = Member.objects.create(
                    church=church,
                    family=family,
                    name=bride_name,
                    gender="FEMALE",
                    marital_status="MARRIED",
                    relationship=relation_bride,
                    father_name=validated_data.get("bride_father"),
                    mother_name=validated_data.get("bride_mother"),
                    is_active=True
                )

                # Link bride to marriage
                marriage.bride_member = new_bride
                marriage.save(update_fields=["bride_member"])

                # Update groom marital status
                groom_member.marital_status = "MARRIED"
                groom_member.save(update_fields=["marital_status"])

            # -------------------------------------------------
            # TRANSFER_BRIDE FLOW
            # -------------------------------------------------
            if marriage_type == "TRANSFER_BRIDE":

                # Deactivate bride
                bride_member.marital_status = "MARRIED"
                bride_member.is_active = False
                bride_member.save(update_fields=["marital_status", "is_active"])

                # If groom exists internally, update status
                if groom_member:
                    groom_member.marital_status = "MARRIED"
                    groom_member.save(update_fields=["marital_status"])

            return marriage
