from datetime import date

from rest_framework import serializers
from .models import Baptism, Bill, Church, DeathRegister, Designation, DheshaKuri, Diocese, Events, Grade, Priest, PriestChange, RegisterSetting, Relationship, TombFee, TombType, UpgradeRequest, VilichCholluKuri, Ward, Family, Member
from .services import can_add_member, generate_folio_number, generate_register_number
from rest_framework import serializers
from .models import Package
from .models import ChurchSubscription, Package
from django.utils import timezone

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


class ChurchDetailSerializer(serializers.ModelSerializer):

    class Meta:
        model = Church
        fields = "__all__"
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


class TombTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TombType
        fields = "__all__"
        read_only_fields = ("church",)

class TombFeeSerializer(serializers.ModelSerializer):

    class Meta:
        model = TombFee
        fields = "__all__"
        read_only_fields = ("church",)

    def validate(self, data):

        church = self.context["request"].user.church
        tomb_type = data.get("tomb_type")

        if tomb_type.church != church:
            raise serializers.ValidationError(
                "Invalid tomb type for this church."
            )

        return data

class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = "__all__"
        read_only_fields = ("church",)

class DioceseSerializer(serializers.ModelSerializer):

    class Meta:
        model = Diocese
        fields = "__all__"
        read_only_fields = ("church",)

    def validate_phone_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Phone number must contain digits only")

        if len(value) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits")

        return value

class PriestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Priest
        fields = "__all__"
        read_only_fields = ("church",)

class PriestChangeSerializer(serializers.ModelSerializer):

    class Meta:
        model = PriestChange
        fields = "__all__"
        read_only_fields = ("church",)

    def validate(self, data):

        request = self.context["request"]
        church = request.user.church

        # Handle both create and update cases
        priest = data.get("priest", getattr(self.instance, "priest", None))
        designation = data.get("designation", getattr(self.instance, "designation", None))
        date_to = data.get("date_to", getattr(self.instance, "date_to", None))

        # ---------- Cross-church validation ----------
        if priest and priest.church != church:
            raise serializers.ValidationError(
                "Invalid priest selected for this church."
            )

        if designation and designation.church != church:
            raise serializers.ValidationError(
                "Invalid designation selected for this church."
            )

        # ---------- Only one active designation ----------
        if date_to is None and designation:

            existing = PriestChange.objects.filter(
                church=church,
                designation=designation,
                date_to__isnull=True
            )

            # Exclude current instance when updating
            if self.instance:
                existing = existing.exclude(id=self.instance.id)

            if existing.exists():
                raise serializers.ValidationError(
                    f"There is already an active priest for the designation '{designation.designation_name}'."
                )

        return data


class MemberSerializer(serializers.ModelSerializer):

    class Meta:
        model = Member
        fields = "__all__"
        read_only_fields = ("church", "age","ward", "address", "family_image")

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

            if data.get("address"):
                raise serializers.ValidationError({
                    "address": "Address should not be assigned manually."
                         })

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
            relationship = data.get("relationship", instance.relationship)
            family = instance.family

            # 🔥 🚨 BLOCK DIRECT EXPIRE
            if "expired" in data:
                raise serializers.ValidationError(
                    "Use mark-dead API to mark a member as deceased."
                )

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

            # -----------------------------
            # RELATIONSHIP VALIDATION
            # -----------------------------

            # Get active head
            head = Member.objects.filter(
                family=family,
                house_name=instance.house_name,
                is_family_head=True,
                is_active=True
            ).first()

            # 1️⃣ Head cannot have relationship
            if instance.is_family_head:
                if relationship:
                    raise serializers.ValidationError({
                        "relationship": "Family head cannot have a relationship."
                    })

            if relationship:
                rel_name = relationship.name

                # 2️⃣ Only one Father / Mother per family
                if rel_name in ["Father", "Mother"]:
                    existing = Member.objects.filter(
                        family=family,
                        relationship__name=rel_name,
                        expired=False
                    ).exclude(pk=instance.pk)

                    if existing.exists():
                        raise serializers.ValidationError({
                            "relationship": f"{rel_name} already exists in this family."
                        })

                # 3️⃣ Son / Daughter must be younger than head
                if rel_name in ["Son", "Daughter"]:
                    if not head:
                        raise serializers.ValidationError(
                            "Cannot assign child relationship without active head."
                        )

                    if not instance.dob or not head.dob:
                        raise serializers.ValidationError(
                            "DOB required to validate child relationship."
                        )

                    if instance.dob <= head.dob:
                        raise serializers.ValidationError({
                            "relationship": "Child must be younger than family head."
                        })

                # 4️⃣ In-law must have spouse
                if rel_name in ["Son_In_Low", "Daughter_In_Low"]:
                    if not instance.spouse:
                        raise serializers.ValidationError({
                            "relationship": "In-law must have spouse assigned."
                        })

        return data

    # -----------------------------
    # CREATE LOGIC
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

        # 🔥 Inherit image from head
        validated_data["family_image"] = head.family_image
        validated_data["address"] = head.address

        return super().create(validated_data)

    # -----------------------------
    # UPDATE LOGIC (CLEANED)
    # -----------------------------
    def update(self, instance, validated_data):
        # 🔥 NO DEATH LOGIC HERE ANYMORE
        return super().update(instance, validated_data)

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
    family_name = serializers.CharField(source="family.family_name", read_only=True)

    class Meta:
        model = Baptism
        fields = "__all__"
        read_only_fields = ("register_number", "church")

    # ---------------------------------
    # HOUSE NAME
    # ---------------------------------
    def get_house_name(self, obj):
        if obj.member:
            return obj.member.house_name
        return None

    # ---------------------------------
    # VALIDATION
    # ---------------------------------
    def validate(self, data):

        instance = self.instance
        request = self.context.get("request")

        church = request.user.church if request else None

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

        priest_name = data.get(
            "priest_name",
            instance.priest_name if instance else None
        )

        panchayath = data.get(
            "panchayath",
            instance.panchayath if instance else None
        )

        # -------------------------
        # Required fields
        # -------------------------
        if not priest_name:
            raise serializers.ValidationError({
                "priest_name": "Priest name is required."
            })

        if not panchayath:
            raise serializers.ValidationError({
                "panchayath": "Panchayath name is required."
            })

        # -------------------------
        # Parish baptism validation
        # -------------------------
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

            # main_member must be head
            if main_member and not main_member.is_family_head:
                raise serializers.ValidationError({
                    "main_member": "Main member must be a family head."
                })

            # ensure family belongs to church
            if church and family and family.church != church:
                raise serializers.ValidationError({
                    "family": "Selected family does not belong to this church."
                })

        # -------------------------
        # Outsider baptism validation
        # -------------------------
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
            "house_name",
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

        # ----------------------------
        # Ensure family belongs to church
        # ----------------------------
        if family.church != church:
            raise serializers.ValidationError(
                "Invalid family selected."
            )

        # ----------------------------
        # house_name required
        # ----------------------------
        if not house_name:
            raise serializers.ValidationError({
                "house_name": "House name is required."
            })

        # ----------------------------
        # Only one active head per house
        # ----------------------------
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

        # ----------------------------
        # Ward required
        # ----------------------------
        if not ward:
            raise serializers.ValidationError({
                "ward": "Ward is required for family head."
            })

        # ----------------------------
        # Email required
        # ----------------------------
        if not email:
            raise serializers.ValidationError({
                "email": "Email is required for family head login."
            })

        return data


    def create(self, validated_data):

        church = self.context["church"]

        with transaction.atomic():

            # Generate formatted register number
            register_no = generate_register_number(
                church,
                "HEAD"
            )

            # Generate formatted folio number
            folio_no = generate_folio_number(
            church
            )

            validated_data["church"] = church
            validated_data["is_family_head"] = True
            validated_data["is_active"] = True
            validated_data["register_number"] = register_no
            validated_data["folio_number"] = folio_no

            head = Member.objects.create(**validated_data)

        return head

class FamilyMemberSerializer(serializers.ModelSerializer):
    relationship = serializers.SerializerMethodField()
    grade_name = serializers.SerializerMethodField()
    family_name = serializers.SerializerMethodField()
    house_name = serializers.SerializerMethodField()
    family_image = serializers.SerializerMethodField()
    spouse_name=serializers.SerializerMethodField()

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
            'spouse_name',
            "blood_group",
            "is_family_head",
            "relationship",
            "grade_name",
            "family_name",
            "family_image",
            "house_name",
            "register_number",
            "folio_number"
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
        return obj.house_name  
    
    def get_spouse_name(self, obj):
        if obj.spouse:
         return obj.spouse.name
        return obj.spouse_name or None
    
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
    family_id = serializers.IntegerField(source="family.id", read_only=True)

    class Meta:
        model = Member  # IMPORTANT
        fields = [
            "id",
            "family_name",
            "family_id",
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

class VilichCholluKuriSerializer(serializers.ModelSerializer):

    marriage_completed = serializers.SerializerMethodField()

    class Meta:
        model = VilichCholluKuri
        fields = "__all__"
        read_only_fields = ("church", "marriage", "created_at")

    def get_marriage_completed(self, obj):
        return obj.marriage is not None

    def validate(self, data):

        church = self.context["request"].user.church

        groom_name = data.get("groom_name", getattr(self.instance, "groom_name", None))
        bride_name = data.get("bride_name", getattr(self.instance, "bride_name", None))
        marriage_date = data.get("marriage_date", getattr(self.instance, "marriage_date", None))

        qs = VilichCholluKuri.objects.filter(
            church=church,
            groom_name=groom_name,
            bride_name=bride_name,
            marriage_date=marriage_date
        )

        # 🔹 exclude current object when editing
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
            "Pre-announcement already exists for this couple on this date."
            )

        return data

#marriage register
from rest_framework import serializers
from django.db import transaction
from .models import Marriage, Member

class MarriageMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ["id", "name", "dob", "house_name", "marital_status","is_active",]

class MarriageSerializer(serializers.ModelSerializer):

    groom = MarriageMemberSerializer(
        source="groom_member",
        read_only=True
    )

    bride = MarriageMemberSerializer(
        source="bride_member",
        read_only=True
    )

    vilich_chollu_kuri = serializers.PrimaryKeyRelatedField(
        queryset=VilichCholluKuri.objects.none(),
        required=False,
        allow_null=True
    )

    groom_confession_date = serializers.DateField(
        required=False,
        allow_null=True,
        write_only=True
    )

    bride_confession_date = serializers.DateField(
        required=False,
        allow_null=True,
        write_only=True
    )

    groom_dob = serializers.DateField(required=False, allow_null=True, write_only=True)
    groom_house_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    groom_family_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    groom_place = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Marriage
        fields = "__all__"
        read_only_fields = ("church", "register_number")

    # ---------------------------------------------------
    # LIMIT VILICH TO SAME CHURCH
    # ---------------------------------------------------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        church = self.context.get("church")

        if church:
            self.fields["vilich_chollu_kuri"].queryset = VilichCholluKuri.objects.filter(
                church=church
            )

    # ---------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------
    def validate(self, data):

        church = self.context["church"]

        groom_member = data.get("groom_member")
        bride_member = data.get("bride_member")
        relation_bride = data.get("relation_of_bride_with_main_member")
        family = data.get("family")
        marriage_type = data.get("marriage_type")
        vilich = data.get("vilich_chollu_kuri")

        if family and family.church != church:
            raise serializers.ValidationError(
                {"family": "Family does not belong to this church."}
            )

        if groom_member and groom_member.church != church:
            raise serializers.ValidationError(
                {"groom_member": "Groom does not belong to this church."}
            )

        if bride_member and bride_member.church != church:
            raise serializers.ValidationError(
                {"bride_member": "Bride does not belong to this church."}
            )

        if relation_bride and relation_bride.church != church:
            raise serializers.ValidationError(
                {"relation_of_bride_with_main_member": "Invalid bride relationship for this church."}
            )

        if not marriage_type:
            raise serializers.ValidationError(
                {"marriage_type": "Marriage type is required."}
            )

        if groom_member and bride_member and groom_member == bride_member:
            raise serializers.ValidationError(
                "Groom and bride cannot be the same member."
            )

        if groom_member and groom_member.spouse:
            raise serializers.ValidationError(
                {"groom_member": "Groom already has a spouse linked."}
            )

        if bride_member and bride_member.spouse:
            raise serializers.ValidationError(
                {"bride_member": "Bride already has a spouse linked."}
            )

        if groom_member and family and groom_member.family != family:
            raise serializers.ValidationError(
                {"family": "Groom must belong to the selected family."}
            )

        # -------------------------
        # VILICH VALIDATION
        # -------------------------
        if vilich:

            if vilich.church != church:
                raise serializers.ValidationError(
                    {"vilich_chollu_kuri": "Invalid pre-announcement for this church."}
                )

            if vilich.marriage:
                raise serializers.ValidationError(
                    {"vilich_chollu_kuri": "This pre-announcement already has a marriage."}
                )

        return data

    # ---------------------------------------------------
    # CREATE LOGIC
    # ---------------------------------------------------
    def create(self, validated_data):

        marriage_type = validated_data.get("marriage_type")
        groom_member = validated_data.get("groom_member")
        bride_member = validated_data.get("bride_member")

        groom_dob = validated_data.pop("groom_dob", None)
        groom_house_name = validated_data.pop("groom_house_name", "")
        groom_family_name = validated_data.pop("groom_family_name", "")
        groom_place = validated_data.pop("groom_place", "")

        church = validated_data.get("church")
        relation_bride = validated_data.get("relation_of_bride_with_main_member")

        groom_confession_date = validated_data.pop("groom_confession_date", None)
        bride_confession_date = validated_data.pop("bride_confession_date", None)

        vilich = validated_data.pop("vilich_chollu_kuri", None)

        # ---------------------------------------------------
        # AUTO FILL FROM PRE ANNOUNCEMENT
        # ---------------------------------------------------
        if vilich:

            validated_data.setdefault("groom_name", vilich.groom_name)
            validated_data.setdefault("groom_dob", vilich.groom_dob)
            validated_data.setdefault("groom_house_name", vilich.groom_house_name)
            validated_data.setdefault("groom_family_name", vilich.groom_family_name)
            validated_data.setdefault("groom_address", vilich.groom_place)

            validated_data.setdefault("groom_father", vilich.groom_father)
            validated_data.setdefault("groom_mother", vilich.groom_mother)

            validated_data.setdefault("bride_name", vilich.bride_name)
            validated_data.setdefault("bride_dob", vilich.bride_dob)
            validated_data.setdefault("bride_address", vilich.bride_place)

            validated_data.setdefault("bride_father", vilich.bride_father)
            validated_data.setdefault("bride_mother", vilich.bride_mother)

        with transaction.atomic():

            # -------------------------
            # LOCK GROOM
            # -------------------------
            if groom_member:
                groom_member = Member.objects.select_for_update().get(id=groom_member.id)

                if groom_member.spouse:
                    raise serializers.ValidationError(
                        {"groom_member": "Groom already married."}
                    )

            # -------------------------
            # LOCK BRIDE
            # -------------------------
            if bride_member:
                bride_member = Member.objects.select_for_update().get(id=bride_member.id)

                if bride_member.spouse:
                    raise serializers.ValidationError(
                        {"bride_member": "Bride already married."}
                    )

            # -------------------------
            # STORE GROOM SNAPSHOT
            # -------------------------
            if not groom_member:
                validated_data["groom_dob"] = groom_dob
                validated_data["groom_house_name"] = groom_house_name
                validated_data["groom_family_name"] = groom_family_name
                validated_data["groom_address"] = groom_place

            # -------------------------
            # STORE BRIDE SNAPSHOT
            # -------------------------
            if bride_member:
                validated_data["bride_name"] = bride_member.name
                validated_data["bride_dob"] = bride_member.dob
                validated_data["bride_address"] = bride_member.address

            marriage = Marriage.objects.create(**validated_data)

            if vilich:
                vilich.marriage = marriage
                vilich.save(update_fields=["marriage"])

            # =================================================
            # ADD_BRIDE
            # =================================================
            if marriage_type == "ADD_BRIDE":

                family = groom_member.family
                house_name = groom_member.house_name

                if bride_member:

                    bride_member.is_active = False
                    bride_member.inactive_reason = "MARRIED_MOVED_TO_HUSBAND_FAMILY"
                    bride_member.inactive_date = timezone.now().date()
                    bride_member.save(update_fields=[
                        "is_active",
                        "inactive_reason",
                        "inactive_date"
                    ])

                    new_bride = Member.objects.create(
                        church=church,
                        family=family,
                        house_name=house_name,
                        name=bride_member.name,
                        gender=bride_member.gender,
                        dob=bride_member.dob,
                        email=bride_member.email,
                        mobile_no=bride_member.mobile_no,
                        phone_no=bride_member.phone_no,
                        blood_group=bride_member.blood_group,
                        profession=bride_member.profession,
                        address=validated_data.get("bride_address") or groom_member.address,
                        grade=bride_member.grade,
                        sunday_school=bride_member.sunday_school,
                        educational_qualification=bride_member.educational_qualification,
                        relationship=relation_bride,
                        father_name=bride_member.father_name,
                        mother_name=bride_member.mother_name,
                        marital_status="MARRIED",
                        is_active=True,
                    )

                else:

                    bride_name = validated_data.get("bride_name")

                    if not bride_name:
                        raise serializers.ValidationError(
                            {"bride_name": "Bride name is required for external bride."}
                        )

                    new_bride = Member.objects.create(
                        church=church,
                        family=family,
                        house_name=house_name,
                        name=bride_name,
                        gender="FEMALE",
                        dob=validated_data.get("bride_dob"),
                        father_name=validated_data.get("bride_father"),
                        mother_name=validated_data.get("bride_mother"),
                        relationship=relation_bride,
                        marital_status="MARRIED",
                        address=validated_data.get("bride_address") or groom_member.address,
                        is_active=True,
                    )

                groom_member.spouse = new_bride
                new_bride.spouse = groom_member

                groom_member.marital_status = "MARRIED"
                new_bride.marital_status = "MARRIED"

                groom_member.spouse_name = new_bride.name
                new_bride.spouse_name = groom_member.name

                groom_member.save(update_fields=["spouse", "marital_status", "spouse_name"])
                new_bride.save(update_fields=["spouse", "marital_status", "spouse_name"])

                marriage.bride_member = new_bride
                marriage.family = family
                marriage.save(update_fields=["bride_member", "family"])

            # =================================================
            # TRANSFER_BRIDE
            # =================================================
            if marriage_type == "TRANSFER_BRIDE":

                bride_member.marital_status = "MARRIED"
                bride_member.is_active = False
                bride_member.inactive_reason = "TRANSFERRED_AFTER_MARRIAGE"
                bride_member.inactive_date = timezone.now().date()
                bride_member.save(update_fields=[
                    "marital_status",
                    "is_active",
                    "inactive_reason",
                    "inactive_date"
                ])

                if groom_member:
                    groom_member.marital_status = "MARRIED"
                    groom_member.save(update_fields=["marital_status"])

                groom_age = None
                if not groom_member and groom_dob:
                    today = date.today()
                    groom_age = today.year - groom_dob.year - (
                        (today.month, today.day) < (groom_dob.month, groom_dob.day)
                    )

                DheshaKuri.objects.create(
                    church=church,
                    marriage=marriage,
                    groom_confession_date=groom_confession_date,
                    bride_confession_date=bride_confession_date,
                    groom_name=groom_member.name if groom_member else validated_data.get("groom_name"),
                    groom_dob=groom_member.dob if groom_member else groom_dob,
                    groom_age=groom_member.age if groom_member else groom_age,
                    groom_house_name=groom_member.house_name if groom_member else groom_house_name,
                    groom_family_name=groom_member.family.family_name if groom_member else groom_family_name,
                    groom_place=groom_member.address if groom_member else groom_place,
                    groom_father=validated_data.get("groom_father"),
                    groom_mother=validated_data.get("groom_mother"),
                    bride_name=bride_member.name,
                    bride_dob=bride_member.dob,
                    bride_age=bride_member.age,
                    bride_house_name=bride_member.house_name,
                    bride_family_name=bride_member.family.family_name,
                    bride_father=validated_data.get("bride_father"),
                    bride_mother=validated_data.get("bride_mother"),
                    bride_place=bride_member.address,
                    transfer_to=validated_data.get("transfer_to"),
                )

            return marriage

    # ---------------------------------------------------
    # CLEAN RESPONSE
    # ---------------------------------------------------
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("bride_member", None)
        data.pop("groom_member", None)
        return data #mrg certificate for church
class MarriageCertificateSerializer(serializers.ModelSerializer):

    church_name = serializers.CharField(source="church.name")
    family_name = serializers.CharField(source="family.family_name")

    groom_full_name = serializers.SerializerMethodField()
    bride_full_name = serializers.SerializerMethodField()

    groom_dob = serializers.SerializerMethodField()
    bride_dob = serializers.SerializerMethodField()

    groom_age = serializers.SerializerMethodField()
    bride_age = serializers.SerializerMethodField()

    groom_occupation = serializers.SerializerMethodField()
    bride_occupation = serializers.SerializerMethodField()

    groom_address = serializers.SerializerMethodField()
    bride_address = serializers.SerializerMethodField()

    class Meta:
        model = Marriage
        fields = [
            "id",
            "register_number",
            "date",
            "church_name",
            "family_name",

            "groom_full_name",
            "groom_dob",
            "groom_age",
            "groom_occupation",
            "groom_address",

            "bride_full_name",
            "bride_dob",
            "bride_age",
            "bride_occupation",
            "bride_address",

            "groom_father",
            "groom_mother",
            "bride_father",
            "bride_mother",

            "nationality_of_groom",
            "nationality_of_bride",

            "witness_bride_side",
            "witness_groom_side",

            "minister_of_marriage",
            "other_priests",
            "remarks",
        ]

    # -------------------------
    # NAMES
    # -------------------------
    def get_groom_full_name(self, obj):
        return obj.groom_member.name if obj.groom_member else obj.groom_name

    def get_bride_full_name(self, obj):
        return obj.bride_member.name if obj.bride_member else obj.bride_name

    # -------------------------
    # DOB
    # -------------------------
    def get_groom_dob(self, obj):
        if obj.groom_member:
            return obj.groom_member.dob
        return obj.groom_dob

    def get_bride_dob(self, obj):
        if obj.bride_member:
            return obj.bride_member.dob
        return obj.bride_dob  # fallback for ADD_BRIDE case

    # -------------------------
    # AGE
    # -------------------------
    def get_groom_age(self, obj):
        if obj.groom_member:
            return obj.groom_member.age
        if obj.groom_dob:
            today = date.today()
            return today.year - obj.groom_dob.year - (
            (today.month, today.day) < (obj.groom_dob.month, obj.groom_dob.day)
            )
        return None
    
    def get_bride_age(self, obj):
        if obj.bride_member:
            return obj.bride_member.age
        if obj.bride_dob:
            today = date.today()
            return today.year - obj.bride_dob.year - (
                (today.month, today.day) < (obj.bride_dob.month, obj.bride_dob.day)
            )
        return None

    # -------------------------
    # OCCUPATION
    # -------------------------
    def get_groom_occupation(self, obj):
        return obj.groom_member.profession if obj.groom_member else None

    def get_bride_occupation(self, obj):
        return obj.bride_member.profession if obj.bride_member else None

    # -------------------------
    # ADDRESS
    # -------------------------
    def get_groom_address(self, obj):
        if obj.groom_member:
            return obj.groom_member.address
        return obj.groom_address

    def get_bride_address(self, obj):
        if obj.bride_member:
            return obj.bride_member.address
        return obj.bride_address
    
class DheshaKuriSerializer(serializers.ModelSerializer):

    church_name = serializers.CharField(source="church.name")

    class Meta:
        model = DheshaKuri
        fields = [
            "id",
            "church_name",
            "created_at",

            # Marriage info
            "transfer_to",

            # Groom snapshot
            "groom_name",
            "groom_dob",
            "groom_age",
            "groom_house_name",
            "groom_family_name",
            "groom_father",
            "groom_mother",
            "groom_place",
            "groom_confession_date",

            # Bride snapshot
            "bride_name",
            "bride_dob",
            "bride_age",
            "bride_house_name",
            "bride_family_name",
            "bride_father",
            "bride_mother",
            "bride_place",
            "bride_confession_date",
        ]

#inactive users
class InactiveMemberSerializer(serializers.ModelSerializer):
    family_name = serializers.CharField(source="family.family_name", read_only=True)

    class Meta:
        model = Member
        fields = [
            "id",
            "name",
            "gender",
            "dob",
            "marital_status",
            "house_name",
            "family_name",
            "is_active",
            "inactive_reason",
            "inactive_date",
        ]

#Death Register
class DeathRegisterSerializer(serializers.ModelSerializer):

    member = serializers.PrimaryKeyRelatedField(read_only=True)
    member_name = serializers.CharField(source="member.name", read_only=True)
    family_name = serializers.CharField(
        source="member.family.family_name",
        read_only=True
    )

    house_name = serializers.CharField(
        source="member.house_name",
        read_only=True
    )

    class Meta:
        model = DeathRegister
        fields = "__all__"
        read_only_fields = ("reg_no", "church", "member", "status")

    def validate(self, data):
        instance = self.instance
        member = instance.member if instance else None

        if not member:
            raise serializers.ValidationError("Member is required.")

        # 🔥 Member must already be expired (safety check)
        if not member.expired:
            raise serializers.ValidationError(
                "Member must be marked expired first."
            )

        # 🔥 Merge existing + incoming values for validation
        died_on = data.get("died_on", instance.died_on)
        funeral_on = data.get("funeral_on", instance.funeral_on)
        tomb_type = data.get("tomb_type", instance.tomb_type)
        tomb_charge = data.get("tomb_charge", instance.tomb_charge)
        reason_of_death=data.get("reason_of_death",instance.reason_of_death)

        # 🔥 Required validations for completion readiness
        if not died_on:
            raise serializers.ValidationError({
                "died_on": "Date of death is required."
            })

        if not funeral_on:
            raise serializers.ValidationError({
                "funeral_on": "Funeral date is required."
            })

        if not tomb_type:
            raise serializers.ValidationError({
                "tomb_type": "Tomb type is required."
            })

        if tomb_charge is None:
            raise serializers.ValidationError({
                "tomb_charge": "Tomb charge must be provided."
            })
        
        if not reason_of_death or not reason_of_death.strip():
            raise serializers.ValidationError({
            "reason_of_death": "Reason of death is required."
            })
        return data

from django.contrib.auth import get_user_model
User = get_user_model()
class FamilyHeadUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Member
        fields = [
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
            "ward",
            "grade",
            "family_image",
            "joining_date",
            "transferred_from",
            "address",
            "relationship"
        ]

    def validate(self, data):
        instance = self.instance

        if not instance.is_family_head:
            raise serializers.ValidationError(
                "This member is not a family head."
            )

        # Prevent duplicate email
        if "email" in data:
            email = data["email"]
            if Member.objects.filter(email=email).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({
                    "email": "Email already exists."
                })

        return data

    def update(self, instance, validated_data):
        new_email = validated_data.get("email", instance.email)

        with transaction.atomic():

            member = super().update(instance, validated_data)

            # Update linked user email if head email changed
            if instance.is_family_head and instance.user:
                user = instance.user

                if user.email != new_email:
                    user.email = new_email
                    user.username = new_email  # username used for login
                    user.save(update_fields=["email", "username"])

        return member
    

class RegisterSettingSerializer(serializers.ModelSerializer):

    class Meta:
        model = RegisterSetting
        fields = "__all__"
        read_only_fields = ("church",)

#priest master 
class PriestNameSerializer(serializers.ModelSerializer):

    class Meta:
        model = Church
        fields = ["vicar", "asst_vicar1", "asst_vicar2", "asst_vicar3"]



class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Events
        fields = '__all__'
        read_only_fields = ("church", "created_at")