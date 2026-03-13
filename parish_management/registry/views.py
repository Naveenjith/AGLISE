from datetime import date
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    UpdateAPIView,
)
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import IsChurchAuthenticated,IsChurchUser, IsMemberUser
from accounts.utils import create_family_head_user
from registry.services import calculate_new_bill_amount, calculate_prorated_upgrade_amount, get_next_subscription_action, register_death
from .models import Baptism, Bill, Church, DeathRegister, Designation, DheshaKuri, Diocese, Grade, Marriage, Priest, PriestChange, RegisterSetting, Relationship, TombFee, TombType, UpgradeRequest, VilichCholluKuri, Ward, Family, Member,Package
from .serializers import BaptismSerializer, BillDetailSerializer, BillListSerializer, ChurchDetailSerializer, ChurchListSerializer, DeathRegisterSerializer, DesignationSerializer, DheshaKuriSerializer, DioceseSerializer, FamilyHeadCreateSerializer, FamilyHeadUpdateSerializer, FamilyMemberSerializer, GradeSerializer, InactiveMemberSerializer, MarriageCertificateSerializer, MarriageSerializer, MemberProfileSerializer, MobileFamilyBaptismSerializer, MobileFamilyDetailSerializer, MobileFamilyListSerializer, MobileFamilyMemberSerializer, PriestChangeSerializer, PriestNameSerializer,PriestSerializer, RegisterSettingSerializer, RelationshipSerializer, SubscriptionExpirySerializer, TombFeeSerializer, TombTypeSerializer, UpgradeSerializer, VilichCholluKuriSerializer, WardSerializer, FamilySerializer, MemberSerializer,PackageSerializer, WardWithFamilyCountSerializer
from rest_framework.generics import ListAPIView
from .models import ChurchSubscription
from .serializers import SubscribeSerializer,UpgradeRequestSerializer
from rest_framework.views import APIView
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.db.models import Count,Sum
from django.db.models import Q,F

class ChurchContextMixin:

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["church"] = self.request.user.church
        return context

    def get_queryset(self):
        if not hasattr(self.model, "church"):
            raise Exception(
                f"{self.model.__name__} must have a church field."
            )

        return self.model.objects.filter(
            church=self.request.user.church
        )


class ChurchList(ListAPIView):
    permission_classes=[IsAuthenticated]
    serializer_class = ChurchListSerializer
    queryset = Church.objects.all().order_by("-created_at")

class MyChurchAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        church = request.user.church
        serializer = ChurchDetailSerializer(church)
        return Response(serializer.data)



class WardListCreateAPIView(ChurchContextMixin,ListCreateAPIView):
    model = Ward
    serializer_class = WardSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]


class WardDetailAPIView(ChurchContextMixin,RetrieveUpdateDestroyAPIView):
    model = Ward
    serializer_class = WardSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

class FamilyListCreateAPIView(ChurchContextMixin,ListCreateAPIView):
    model = Family
    serializer_class = FamilySerializer
    permission_classes = [IsAuthenticated, IsChurchUser]
    
class RelationshipListCreateAPIView(ChurchContextMixin,ListCreateAPIView):
    model = Relationship
    serializer_class = RelationshipSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)

class RelationshipdetailView(ChurchContextMixin,RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated,IsChurchUser]
    model=Relationship
    serializer_class=RelationshipSerializer

    

class GradeListCreateview(ChurchContextMixin,ListCreateAPIView):
    model=Grade
    serializer_class=GradeSerializer
    permission_classes=[IsAuthenticated,IsChurchUser]

class GradeDetailview(ChurchContextMixin,RetrieveUpdateDestroyAPIView):
    model=Grade
    serializer_class=GradeSerializer
    permission_classes=[IsAuthenticated,IsChurchUser]




class FamilyDetailAPIView(
    ChurchContextMixin,
    RetrieveUpdateDestroyAPIView
):
    model = Family
    serializer_class = FamilySerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def destroy(self, request, *args, **kwargs):
        family = self.get_object()

        members = family.members.filter(is_active=True)

        # ❌ More than one member → block delete
        if members.count() > 1:
            return Response(
                {
                    "detail": (
                        "Family cannot be deleted because "
                        "it has more than one active member."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ❌ Single member but not head → block delete
        if members.exists() and not members.first().is_family_head:
            return Response(
                {
                    "detail": (
                        "Family cannot be deleted because "
                        "the remaining member is not the family head."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ Safe to delete
        return super().destroy(request, *args, **kwargs)


class FamilyHeadCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def post(self, request):
        serializer = FamilyHeadCreateSerializer(
            data=request.data,
            context={"church": request.user.church}
        )

        serializer.is_valid(raise_exception=True)
        head = serializer.save()

        return Response(
            {
                "message": "Family head created successfully.",
                "member_id": head.id,
                "family_id": head.family.id,
            },
            status=status.HTTP_201_CREATED
        )


class MemberListCreateAPIView(ChurchContextMixin, ListCreateAPIView):
    model = Member
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["church"] = self.request.user.church
        return context

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)





class MemberDetailAPIView(
    ChurchContextMixin,
    RetrieveUpdateDestroyAPIView
):
    model = Member
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["church"] = self.request.user.church
        return context

    def perform_update(self, serializer):
        instance = self.get_object()
        validated_data = serializer.validated_data

        # 🔥 Prevent promoting to head here
        if (
            "is_family_head" in validated_data
            and validated_data["is_family_head"] is True
            and not instance.is_family_head
        ):
            raise ValidationError(
                "Use family head API to promote a member to head."
            )

     # 🔥 If member is NOT head → block ward & image
        if not instance.is_family_head:
            if "ward" in validated_data:
                raise ValidationError({
                "ward": "Only family head can have ward."
                })

            if "family_image" in validated_data:
                raise ValidationError({
                "family_image": "Only family head can have family image."
                })

        serializer.save()


    def destroy(self, request, *args, **kwargs):
        member = self.get_object()

        # 🔥 Prevent deleting head if dependents exist in SAME HOUSE
        if member.is_family_head:
            other_members = Member.objects.filter(
                family=member.family,
                house_name=member.house_name,
                is_active=True
            ).exclude(pk=member.pk)

            if other_members.exists():
                return Response(
                    {
                        "detail": (
                            "Cannot delete family head while "
                            "dependents exist in this house."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        return super().destroy(request, *args, **kwargs)




class PackageListAPIView(ListAPIView):
    permission_classes = [IsAuthenticated,IsChurchAuthenticated]
    queryset = Package.objects.all()
    serializer_class = PackageSerializer
    


class SubscribeAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchAuthenticated]

    @transaction.atomic
    def post(self, request):
        church = request.user.church

        if hasattr(church, "churchsubscription"):
            return Response(
                {"detail": "Subscription already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SubscribeSerializer(
            data=request.data,
            context={"church": church}
        )
        serializer.is_valid(raise_exception=True)

        package = serializer.validated_data["package"]
        billing_cycle = serializer.validated_data.get("billing_cycle")
        capacity = serializer.validated_data.get("capacity")

        # -------------------------
        # TRIAL
        # -------------------------
        if package.is_trial:
            ChurchSubscription.objects.create(
                church=church,
                package=package,
                payment_status="PAID",
                is_active=True,
            )
            church.is_active = True
            church.save(update_fields=["is_active"])

            return Response(
                {"detail": "Trial activated"},
                status=status.HTTP_201_CREATED
            )

        duration_months = 12 if billing_cycle == "YEARLY" else 1
        resolved_capacity = (
            capacity if package.is_custom else package.member_limit
        )

        # -------------------------
        # CREATE SUBSCRIPTION
        # -------------------------
        subscription = ChurchSubscription.objects.create(
            church=church,
            package=package,
            billing_cycle=billing_cycle,
            duration_months=duration_months,
            custom_capacity=capacity if package.is_custom else None,
            payment_status="UNPAID",
            is_active=False,
        )

        amount = calculate_new_bill_amount(
            package=package,
            billing_cycle=billing_cycle,
            capacity=resolved_capacity,
        )

        bill = Bill.objects.create(
            church=church,
            subscription=subscription,
            bill_type="NEW",
            billing_cycle=billing_cycle,
            duration_months=duration_months,
            amount=amount,
            breakdown={
                "items": [{
                    "type": "NEW",
                    "calculation": (
                        f"{resolved_capacity} × "
                        f"{package.rate_per_member_yearly if billing_cycle == 'YEARLY' else package.rate_per_member_monthly} × "
                        f"{duration_months}"
                    ),
                    "total": float(amount),
                }],
                "grand_total": float(amount),
                "credit_generated": 0,
                "apply": {
                    "package_id": package.id,
                    "billing_cycle": billing_cycle,
                    "duration_months": duration_months,
                    "custom_capacity": capacity,
                }
            }
        )

        return Response(
            {
                "detail": "Subscription created. Awaiting payment.",
                "bill_id": bill.id,
                "amount": bill.amount,
            },
            status=status.HTTP_201_CREATED
        )



    
class UpgradeAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    @transaction.atomic
    def post(self, request):
        church = request.user.church
        subscription = getattr(church, "churchsubscription", None)

        # -------------------------------------------------
        # BASIC GUARDS
        # -------------------------------------------------
        if not subscription or not subscription.is_active:
            return Response(
                {"detail": "No active subscription"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if Bill.objects.filter(
            subscription=subscription,
            status="UNPAID"
        ).exists():
            return Response(
                {"detail": "Please clear pending bill first"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # INPUT
        # -------------------------------------------------
        package_id = request.data.get("package_id")
        billing_cycle = request.data.get("billing_cycle")
        capacity = request.data.get("capacity")

        if not package_id or not billing_cycle:
            return Response(
                {"detail": "package_id and billing_cycle are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_package = get_object_or_404(Package, id=package_id)

        # -------------------------------------------------
        # CUSTOM VALIDATION
        # -------------------------------------------------
        if target_package.is_custom:
            if not capacity:
                return Response(
                    {"detail": "capacity is required for custom package"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            capacity = int(capacity)
        else:
            if capacity:
                return Response(
                    {
                        "detail":
                        "capacity is allowed only for custom packages"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        # -------------------------------------------------
        # CALCULATE UPGRADE (SERVICE IS SOURCE OF TRUTH)
        # -------------------------------------------------
        result = calculate_prorated_upgrade_amount(
            subscription=subscription,
            target_package=target_package,
            target_billing_cycle=billing_cycle,
            target_capacity=capacity,
        )

        if result["amount"] <= 0:
            return Response(
                {"detail": "No payable upgrade amount"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # CREATE BILL
        # -------------------------------------------------
        bill = Bill.objects.create(
            church=church,
            subscription=subscription,
            bill_type="UPGRADE",
            billing_cycle=billing_cycle,
            duration_months=subscription.duration_months,
            amount=result["amount"],
            breakdown={
                "items": [result["breakdown"]],
                "grand_total": float(result["amount"]),
                "credit_generated": float(result["credit"]),
                "apply": {
                    "package_id": target_package.id,
                    "billing_cycle": billing_cycle,
                    "duration_months": subscription.duration_months,
                    "custom_capacity": capacity,
                },
            }
        )

        return Response(
            {
                "detail": "Upgrade bill generated",
                "bill_id": bill.id,
                "amount": bill.amount,
                "payment_status": bill.status,
            },
            status=status.HTTP_201_CREATED
        )


class ChurchDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchAuthenticated]

    def get(self, request):
        church = request.user.church

        # Build full logo URL
        logo_url = None
        if church.logo:
            logo_url = request.build_absolute_uri(church.logo.url)

        # --------------------
        # Church basic details
        # --------------------
        church_data = {
            "id": church.id,
            "name": church.name,
            "city": church.city,
            "diocese": church.diocese_name,
            "vicar":church.vicar,
            "asst_vicar":church.asst_vicar1,
            "asst_vicar2":church.asst_vicar2,
            "email": church.email,
            "email": church.email,
            "phone": church.phone_number,
            "is_active": church.is_active,
            "logo": logo_url,
        }

        # --------------------
        # Subscription details
        # --------------------
        subscription = getattr(church, "churchsubscription", None)

        if subscription:
            package = subscription.package
            subscription_data = {
                "package": package.name,
                "member_limit": package.member_limit,
                "billing_cycle": subscription.billing_cycle,
                "is_custom": package.is_custom,
                "start_date": subscription.start_date,
            }
        else:
            subscription_data = None

        # --------------------
        # Member counts
        # --------------------
        current_count = church.members.filter(
            is_active=True,
            expired=False
        ).count()

        allowed_limit = (
            subscription.package.member_limit
            if subscription and subscription.package.member_limit
            else None
        )

        members_data = {
            "current_count": current_count,
            "allowed_limit": allowed_limit,
            "remaining": (
                allowed_limit - current_count
                if allowed_limit is not None
                else None
            ),
        }

        # --------------------
        # Upgrade required?
        # --------------------
        upgrade_required = False
        if subscription and allowed_limit is not None:
            upgrade_required = current_count > allowed_limit

        return Response({
            "church": church_data,
            "subscription": subscription_data,
            "members": members_data,
            "upgrade_required": upgrade_required,
        })

#member
class MemberProfileAPIView(APIView):
    permission_classes = [IsAuthenticated, IsMemberUser]

    def get(self, request):
        member = request.user.member
        serializer = MemberProfileSerializer(member)
        return Response(serializer.data)
    
#Bill
class ChurchBillListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request):
        church = request.user.church

        bills = (
            Bill.objects
            .filter(church=church)
            .select_related("subscription", "subscription__package")
            .order_by("-created_at")
        )

        # Optional filter
        bill_status = request.query_params.get("status")
        if bill_status in ["PAID", "UNPAID"]:
            bills = bills.filter(status=bill_status)

        serializer = BillListSerializer(bills, many=True)

        return Response(
            {
                "count": bills.count(),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK
        )
    
class ChurchBillDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request, pk):
        church = request.user.church

        bill = get_object_or_404(
            Bill.objects.select_related(
                "church",
                "subscription",
                "subscription__package",
            ),
            pk=pk,
            church=church,  # 🔒 critical security check
        )

        serializer = BillDetailSerializer(bill)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
    
#expire
class SubscriptionExpiryAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request):
        church = request.user.church
        subscription = getattr(church, "churchsubscription", None)

        if not subscription or not subscription.end_date:
            return Response(
                {"detail": "No active subscription"},
                status=status.HTTP_404_NOT_FOUND
            )

        today = date.today()
        days_remaining = (subscription.end_date - today).days

        if days_remaining < 0:
            expiry_status = "EXPIRED"
        elif days_remaining <= 7:
            expiry_status = "EXPIRING_SOON"
        else:
            expiry_status = "ACTIVE"

        data = {
            "package": subscription.package.name,
            "billing_cycle": subscription.billing_cycle,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date,
            "days_remaining": max(days_remaining, 0),
            "status": expiry_status,
        }

        serializer = SubscriptionExpirySerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)



class UpgradeRequestAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def post(self, request):
        church = request.user.church
        subscription = getattr(church, "churchsubscription", None)

        if not subscription or not subscription.is_active:
            return Response(
                {"detail": "No active subscription"},
                status=400
            )

        serializer = UpgradeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        UpgradeRequest.objects.create(
            church=church,
            current_package=subscription.package,
            requested_package=serializer.validated_data["requested_package"],
            requested_capacity=serializer.validated_data.get("requested_capacity"),
            reason=serializer.validated_data.get("reason", ""),
        )

        return Response(
            {"detail": "Upgrade request sent to admin"},
            status=201
        )


#change family head
class ChangeFamilyHeadAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    @transaction.atomic
    def post(self, request):
        family_id = request.data.get("family_id")
        new_head_id = request.data.get("member_id")

        if not family_id or not new_head_id:
            return Response(
                {"detail": "family_id and member_id are required"},
                status=400
            )

        church = request.user.church

        family = get_object_or_404(
            Family,
            id=family_id,
            church=church
        )

        new_head = get_object_or_404(
            Member,
            id=new_head_id,
            family=family,
            church=church,
            expired=False,
            is_active=True
        )

        # Remove existing head
        family.members.filter(
            is_family_head=True
        ).update(is_family_head=False)

        # Set new head
        new_head.is_family_head = True
        new_head.save(update_fields=["is_family_head"])

        return Response(
            {"detail": "Family head updated successfully"},
            status=200
        )   
#baptism
class BaptismAPIView(APIView):
    permission_classes = [IsChurchUser]

    def get(self, request):
        """
        List baptisms with optional category filter
        ?category=PARISH | OTHER
        """
        category = request.query_params.get("category")

        baptisms = Baptism.objects.filter(
            church=request.user.church
        )

        if category:
            category = category.upper()
            if category not in ["PARISH", "OTHER"]:
                return Response(
                    {"detail": "Invalid category. Use PARISH or OTHER."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            baptisms = baptisms.filter(baptism_category=category)

        baptisms = baptisms.select_related(
            "family",
            "main_member",
            "relation_with_main_member",
            "member"
        ).order_by("-created_at")

        serializer = BaptismSerializer(baptisms, many=True)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )



    def post(self, request):
        data = request.data.copy()
        data["church"] = request.user.church.id

        serializer = BaptismSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            baptism = serializer.save(
            church=request.user.church
             )

            member=None
            # AUTO CREATE MEMBER ONLY FOR PARISH
            if (
                baptism.baptism_category == "PARISH"
                and baptism.member is None
            ):
                main_member = baptism.main_member

                # 🔥 STRICT VALIDATION
                if not main_member.is_family_head:
                    raise ValidationError(
                    "Main member must be a family head."
                    )

                if main_member.family != baptism.family:
                    raise ValidationError(
                        "Main member does not belong to selected family."
                )

                member = Member.objects.create(
                    church=baptism.church,
                    family=baptism.family,
                    house_name=main_member.house_name,  # ✅ CRITICAL
                    ward=main_member.ward,              # ✅ CRITICAL
                    name=baptism.name,
                    baptismal_name=baptism.baptismal_name,
                    gender=baptism.gender,
                    dob=baptism.dob,
                    address=baptism.address,
                    relationship=baptism.relation_with_main_member,
                    father_name=baptism.father_name,
                    mother_name=baptism.mother_name,
                    date_of_baptism=baptism.date_of_baptism,
                    parish_of_baptism=baptism.parish_of_baptism,
                    is_family_head=False,
                    is_active=True
                )

            if member:
                baptism.member = member
                baptism.save(update_fields=["member"])

        return Response(
            BaptismSerializer(baptism).data,
            status=status.HTTP_201_CREATED
        )




class BaptismDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        """
        Ensure baptism belongs to the logged-in user's church
        """
        return get_object_or_404(
            Baptism,
            pk=pk,
            church=request.user.church
        )

    # -------------------------
    # INTERNAL SAFETY CHECK
    # -------------------------
    def _block_if_member_exists(self, baptism, data):
        """
        Prevent dangerous updates once a Member is created
        """
        if baptism.member:
            blocked_fields = {
                "baptism_category",
                "family",
                "main_member",
                "relation_with_main_member",
            }

            attempted = blocked_fields.intersection(data.keys())
            if attempted:
                raise ValidationError(
                    f"Cannot modify {', '.join(attempted)} after member creation."
                )

    # -------------------------
    # FULL UPDATE
    # -------------------------
    def put(self, request, pk):
        baptism = self.get_object(request, pk)

        data = request.data.copy()
        data["church"] = request.user.church.id

        self._block_if_member_exists(baptism, data)

        serializer = BaptismSerializer(
            baptism,
            data=data
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    # -------------------------
    # PARTIAL UPDATE
    # -------------------------
    def patch(self, request, pk):
        baptism = self.get_object(request, pk)

        data = request.data.copy()
        data["church"] = request.user.church.id

        self._block_if_member_exists(baptism, data)

        serializer = BaptismSerializer(
            baptism,
            data=data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    # -------------------------
    # DELETE
    # -------------------------
    def delete(self, request, pk):
        baptism = self.get_object(request, pk)

        if baptism.member:
            raise ValidationError(
                "Cannot delete baptism record after member creation."
            )

        baptism.delete()
        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class BaptismCertificateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        # 🔒 Ensure logged-in user is a family head
        member = getattr(request.user, "member", None)

        if not member or not member.is_family_head:
            return Response(
                {"detail": "Only family head can access certificates."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 🔒 Fetch baptism only inside same family + house
        baptism = get_object_or_404(
            Baptism.objects.select_related(
                "church",
                "family",
                "main_member",
                "relation_with_main_member",
                "member",
            ),
            pk=pk,
            baptism_category="PARISH",
            family=member.family,
            member__house_name=member.house_name,
            member__is_active=True,
            member__expired=False,
        )

        baptism_member = baptism.member
        main_member = baptism.main_member

        data = {
            "certificate_type": "PARISH",

            # -------------------------
            # CHURCH INFO
            # -------------------------
            "church": {
                "name": baptism.church.name,
                "address": baptism.church.address,
                "city": baptism.church.city,
                "email": baptism.church.email,
                "phone": baptism.church.phone_number,
            },

            # -------------------------
            # BAPTISM DETAILS
            # -------------------------
            "register_number": baptism.register_number,
            "date_of_baptism": baptism.date_of_baptism,
            "parish_of_baptism": baptism.parish_of_baptism,
            "panchayath": baptism.panchayath,
            "priest_name": baptism.priest_name,

            # -------------------------
            # PERSON DETAILS
            # -------------------------
            "name": baptism.name,
            "baptismal_name": baptism.baptismal_name,
            "gender": baptism.gender,
            "date_of_birth": baptism.dob,
            "place_of_birth": baptism.place_of_birth,
            "address": baptism.address,

            # -------------------------
            # PARENTS
            # -------------------------
            "father_name": baptism.father_name,
            "mother_name": baptism.mother_name,

            # -------------------------
            # GODPARENTS
            # -------------------------
            "god_father": baptism.god_father,
            "god_mother": baptism.god_mother,

            # -------------------------
            # PARISH DETAILS
            # -------------------------
            "parish_member_details": {
                "family_name": member.family.family_name,
                "house_name": member.house_name,
                "main_member_name": (
                    main_member.name if main_member else None
                ),
                "relationship": (
                    baptism.relation_with_main_member.name
                    if baptism.relation_with_main_member
                    else None
                ),
                "member_id": (
                    str(baptism_member.id) if baptism_member else None
                ),
            },
        }

        return Response(data, status=status.HTTP_200_OK)
#baptims certificate for church
class ChurchBaptismCertificateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request, pk):

        baptism = get_object_or_404(
            Baptism.objects.select_related(
                "church",
                "family",
                "main_member",
                "relation_with_main_member",
                "member",
            ),
            pk=pk,
            church=request.user.church
        )

        baptism_member = baptism.member
        main_member = baptism.main_member

        data = {
            "certificate_type": baptism.baptism_category,

            # -------------------------
            # CHURCH INFO
            # -------------------------
            "church": {
                "name": baptism.church.name,
                "address": baptism.church.address,
                "city": baptism.church.city,
                "email": baptism.church.email,
                "phone": baptism.church.phone_number,
            },

            # -------------------------
            # BAPTISM DETAILS
            # -------------------------
            "register_number": baptism.register_number,
            "date_of_baptism": baptism.date_of_baptism,
            "parish_of_baptism": baptism.parish_of_baptism,
            "panchayath": baptism.panchayath,
            "priest_name": baptism.priest_name,

            # -------------------------
            # PERSON DETAILS
            # -------------------------
            "name": baptism.name,
            "baptismal_name": baptism.baptismal_name,
            "gender": baptism.gender,
            "date_of_birth": baptism.dob,
            "place_of_birth": baptism.place_of_birth,
            "address": baptism.address,

            # -------------------------
            # PARENTS
            # -------------------------
            "father_name": baptism.father_name,
            "mother_name": baptism.mother_name,

            # -------------------------
            # GODPARENTS
            # -------------------------
            "god_father": baptism.god_father,
            "god_mother": baptism.god_mother,

            # -------------------------
            # PARISH DETAILS
            # -------------------------
            "parish_member_details": {
                "family_name": (
                    baptism.family.family_name if baptism.family else None
                ),
                "house_name": (
                    baptism_member.house_name if baptism_member else None
                ),
                "main_member_name": (
                    main_member.name if main_member else None
                ),
                "relationship": (
                    baptism.relation_with_main_member.name
                    if baptism.relation_with_main_member else None
                ),
                "member_id": (
                    str(baptism_member.id) if baptism_member else None
                ),
            },
        }

        return Response(data, status=status.HTTP_200_OK)




class FamilyMembersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, family_id, house_name):
        family = get_object_or_404(
            Family,
            id=family_id,
            church=request.user.church
        )

        members = Member.objects.filter(
            family=family,
            house_name=house_name,
            is_active=True,
            expired=False
        ).order_by("-is_family_head", "name")

        serializer = FamilyMemberSerializer(
            members,
            many=True,
            context={"request": request}
        )

        return Response(serializer.data, status=status.HTTP_200_OK)



#mobile directory apis
class WardListWithFamilyCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wards = Ward.objects.filter(
            church=request.user.church
        ).annotate(
            family_count=Count(
                "members",
                filter=Q(
                    members__is_family_head=True,
                    members__is_active=True,
                    members__expired=False
                )
            )
        ).order_by("ward_name")

        serializer = WardWithFamilyCountSerializer(wards, many=True)
        return Response(serializer.data)

    
class WardFamiliesMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ward_id):
        ward = get_object_or_404(
            Ward,
            id=ward_id,
            church=request.user.church
        )

        heads = (
            Member.objects
            .filter(
                ward=ward,
                is_family_head=True,
                is_active=True,
                expired=False
            )
            .annotate(
                member_count=Count(
                    "family__members",
                    filter=Q(
                        family__members__house_name=F("house_name"),
                        family__members__is_active=True,
                        family__members__expired=False
                    )
                )
            )
            .order_by("family__family_name")
        )

        serializer = MobileFamilyListSerializer(
            heads,
            many=True,
            context={"request": request}
        )

        return Response({
            "total_families": heads.count(),
            "total_members": sum([h.member_count for h in heads]),
            "families": serializer.data
        })

    
class FamilyDetailMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, family_id, house_name):
        family = get_object_or_404(
            Family,
            id=family_id,
            church=request.user.church
        )

        members = Member.objects.filter(
            family=family,
            house_name=house_name,
            is_active=True,
            expired=False
        ).order_by("-is_family_head", "name")

        head = members.filter(is_family_head=True).first()

        return Response({
            "family_name": family.family_name,
            "house_name": house_name,
            "member_count": members.count(),
            "family_image": (
                request.build_absolute_uri(head.family_image.url)
                if head and head.family_image else None
            ),
            "members": MobileFamilyMemberSerializer(
                members,
                many=True
            ).data
        })



class FamilyBaptismsMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # 🔒 Must be family head
        if request.user.role != "USER":
            return Response(
                {"detail": "Only family members allowed."},
                status=403
            )

        member = request.user.member

        if not member or not member.is_family_head:
            return Response(
                {"detail": "Only family head can access this."},
                status=403
            )

        family = member.family
        house_name = member.house_name

        baptisms = (
            Baptism.objects
            .select_related("member")
            .filter(
                family=family,
                baptism_category="PARISH",
                member__house_name=house_name,
                member__is_active=True,
                member__expired=False
            )
            .order_by("-date_of_baptism")
        )

        serializer = MobileFamilyBaptismSerializer(
            baptisms,
            many=True
        )

        return Response({
            "family_name": family.family_name,
            "house_name": house_name,
            "baptism_count": baptisms.count(),
            "baptisms": serializer.data
        })

#pre announcement
class VilichCholluKuriCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def post(self, request):

        serializer = VilichCholluKuriSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(
            church=request.user.church
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

class VilichCholluKuriDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request, pk):

        vilich = get_object_or_404(
            VilichCholluKuri,
            pk=pk,
            church=request.user.church
        )

        serializer = VilichCholluKuriSerializer(vilich)
        return Response(serializer.data)

#marriage register
class MarriageListCreateAPIView(
    ChurchContextMixin,
    ListCreateAPIView
):
    model = Marriage
    serializer_class = MarriageSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_queryset(self):
        return Marriage.objects.filter(
        church=self.request.user.church
        ).select_related(
        "groom_member",
        "bride_member",
        "family"
        )

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class MarriageDetailAPIView(
    ChurchContextMixin,
    RetrieveUpdateDestroyAPIView
):
    model = Marriage
    serializer_class = MarriageSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

#certificate vilich chollu GET
class MarriageCertificateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request, pk):
        marriage = get_object_or_404(
            Marriage,
            pk=pk,
            church=request.user.church
        )

        serializer = MarriageCertificateSerializer(marriage)
        return Response(serializer.data)
    
class DheshaKuriAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request, pk):

        dhesha = get_object_or_404(
            DheshaKuri.objects.select_related("church", "marriage"),
            marriage__id=pk,
            church=request.user.church
        )

        serializer = DheshaKuriSerializer(dhesha)
        return Response(serializer.data)
    
#marriage list for mobile 
class FamilyMarriagesMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        member = getattr(request.user, "member", None)

        if not member or not member.is_family_head:
            return Response(
                {"detail": "Only family head can access this."},
                status=status.HTTP_403_FORBIDDEN
            )

        marriages = (
            Marriage.objects
            .select_related("groom_member", "bride_member")
            .filter(
            church=member.church,
            family=member.family,
            marriage_type="ADD_BRIDE" 
            )
        .filter(
            Q(bride_member__house_name=member.house_name) |
            Q(groom_member__house_name=member.house_name)
        )
            .order_by("-date")
)

        data = []

        for marriage in marriages:
            data.append({
                "id": marriage.id,
                "marriage_type": marriage.marriage_type,
                "register_number": marriage.register_number,
                "date": marriage.date,
                "groom_name": (
                    marriage.groom_member.name
                    if marriage.groom_member
                    else marriage.groom_name
                ),
                "bride_name": (
                    marriage.bride_member.name
                    if marriage.bride_member
                    else marriage.bride_name
                ),
            })

        return Response({
            "family_name": member.family.family_name,
            "house_name": member.house_name,
            "marriage_count": marriages.count(),
            "marriages": data
        })
#mobile get
class MarriageCertificateMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        member = getattr(request.user, "member", None)

        if not member or not member.is_family_head:
            return Response(
                {"detail": "Only family head can access certificates."},
                status=status.HTTP_403_FORBIDDEN
            )

        marriage = get_object_or_404(
            Marriage.objects.select_related(
                "church",
                "family",
                "groom_member",
                "bride_member",
            ),
            pk=pk,
            family=member.family,
            church=member.church,
        )

        # 🔥 BLOCK TRANSFER_BRIDE
        if marriage.marriage_type != "ADD_BRIDE":
            return Response(
                {"detail": "Marriage certificate available only for ADD_BRIDE."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🔐 HOUSE LEVEL SECURITY
        if not (
            (marriage.bride_member and marriage.bride_member.house_name == member.house_name) or
            (marriage.groom_member and marriage.groom_member.house_name == member.house_name)
        ):
            return Response(
                {"detail": "You do not have permission to access this marriage."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = MarriageCertificateSerializer(marriage)

        return Response(serializer.data)
    
class UserVilichCholluKuriAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        member = getattr(request.user, "member", None)

        if not member or not member.is_family_head:
            return Response(
                {"detail": "Only family head can access this."},
                status=403
            )

        vilich = (
            VilichCholluKuri.objects
            .select_related("marriage")
            .filter(
                church=member.church,
                marriage__family=member.family
            )
            .order_by("-created_at")
            .first()
        )

        if not vilich:
            return Response(
                {"detail": "Pre-announcement not found."},
                status=404
            )

        serializer = VilichCholluKuriSerializer(vilich)
        return Response(serializer.data)
class UserDheshaKuriAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        member = request.user.member

        if not member or not member.is_family_head:
            return Response(
                {"detail": "Only family head can access this."},
                status=403
            )

        dhesha = (
            DheshaKuri.objects
            .select_related("church", "marriage")
            .filter(
                church=member.church,
                marriage__family=member.family,
                marriage__marriage_type="TRANSFER_BRIDE"
            )
            .order_by("-created_at")
            .first()
        )

        if not dhesha:
            return Response(
                {"detail": "Dhesha Kuri not found."},
                status=404
            )

        serializer = DheshaKuriSerializer(dhesha)
        return Response(serializer.data)


#inactive users LIST
class InactiveMembersAPIView(ChurchContextMixin, ListAPIView):
    model = Member
    serializer_class = InactiveMemberSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            is_active=False,
            expired=False
        ).order_by("family__family_name", "house_name", "name")
    

#Death Register
class DeathRegisterFinalizeView(APIView):
    permission_classes=[IsAuthenticated, IsChurchUser]

    def post(self, request):
        serializer = DeathRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        member = serializer.validated_data["member"]

        try:
            death = DeathRegister.objects.get(
                member=member,
                status="PENDING"
            )
        except DeathRegister.DoesNotExist:
            return Response(
                {"error": "No pending death request found for this member."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():

            # Update the pending record
            death.died_on = serializer.validated_data.get("died_on")
            death.funeral_on = serializer.validated_data.get("funeral_on")
            death.tomb_type = serializer.validated_data.get("tomb_type")
            death.tomb_charge = serializer.validated_data.get("tomb_charge")
            death.tomb_idn = serializer.validated_data.get("tomb_idn")
            death.reason_of_death = serializer.validated_data.get("reason_of_death")
            death.remarks = serializer.validated_data.get("remarks")
            death.status = "COMPLETED"
            death.save()

            # 🔥 Spouse widow logic
            if member.spouse:
                member.spouse.marital_status = "WIDOWED"
                member.spouse.save(update_fields=["marital_status"])

        return Response(
            DeathRegisterSerializer(death).data,
            status=status.HTTP_200_OK
        )
    
#promote to head
class PromoteFamilyHeadAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def post(self, request, pk):

        try:
            member = Member.objects.get(
                pk=pk,
                church=request.user.church
            )
        except Member.DoesNotExist:
            return Response(
                {"error": "Member not found."},
                status=404
            )

        if member.expired:
            return Response(
                {"error": "Cannot promote expired member as head."},
                status=400
            )

        if member.is_family_head:
            return Response(
                {"error": "Member is already head."},
                status=400
            )

        if not member.email:
            return Response(
                {"error": "Member must have an email to become family head."},
                status=400
            )

        with transaction.atomic():

            # Get old head
            old_head = Member.objects.filter(
                family=member.family,
                house_name=member.house_name,
                is_family_head=True
            ).first()

            # Remove old head
            Member.objects.filter(
                family=member.family,
                house_name=member.house_name,
                is_family_head=True
            ).update(is_family_head=False)

            # Disable old head login
            if old_head and hasattr(old_head, "user"):
                old_head.user.is_active = False
                old_head.user.save(update_fields=["is_active"])

            # Promote new head
            member.is_family_head = True
            member.save(update_fields=["is_family_head"])

            # 🔹 Create login + send email
            create_family_head_user(member)

        return Response(
            {"message": "Member promoted as family head and credentials sent."},
            status=200
        )
class DeathRegisterUpdateAPIView(UpdateAPIView):
    serializer_class = DeathRegisterSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_queryset(self):
        return DeathRegister.objects.filter(
            church=self.request.user.church,
            status="PENDING"
        )

    def perform_update(self, serializer):

        death = serializer.save()

        # Required validations before completing
        if not death.died_on:
            raise ValidationError("Date of death is required.")

        if not death.funeral_on:
            raise ValidationError("Funeral date is required.")

        if not death.tomb_type:
            raise ValidationError("Tomb type is required.")

        if death.tomb_charge is None:
            raise ValidationError("Tomb charge must be provided.")

        # Mark register completed
        death.status = "COMPLETED"
        death.save()

        member = death.member

        # Widow logic
        if member.spouse:
            spouse = member.spouse

            spouse.marital_status = "WIDOWED"
            spouse.spouse = None
            spouse.save(update_fields=["marital_status", "spouse"])

            member.spouse = None
            member.save(update_fields=["spouse"])

#family head edit details
class FamilyHeadUpdateAPIView(UpdateAPIView):
    serializer_class = FamilyHeadUpdateSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_queryset(self):
        return Member.objects.filter(
            church=self.request.user.church,
            is_family_head=True,
            is_active=True
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["church"] = self.request.user.church
        return context

#members under a church
class ChurchMembersAPIView(ListAPIView):
    serializer_class = FamilyMemberSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_queryset(self):
        church = self.request.user.church

        return Member.objects.filter(
            church=church,
            is_active=True
        ).select_related(
            "family",
            "relationship",
            "grade",
            "spouse"
        ).order_by("name")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context
    
#new tables and crud
#tomb
class TombTypeListCreateView(generics.ListCreateAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = TombTypeSerializer
    def get_queryset(self):
        return TombType.objects.filter(
            church=self.request.user.church
        )

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class TombTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = TombTypeSerializer
    def get_queryset(self):
        return TombType.objects.filter(
            church=self.request.user.church
        )


class TombFeeListCreateView(generics.ListCreateAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = TombFeeSerializer
    def get_queryset(self):
        return TombFee.objects.filter(
            church=self.request.user.church
        ).select_related("tomb_type")

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class TombFeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = TombFeeSerializer
    def get_queryset(self):
        return TombFee.objects.filter(
            church=self.request.user.church
        ).select_related("tomb_type")


#designation
class DesignationListCreateView(generics.ListCreateAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = DesignationSerializer
    def get_queryset(self):
        return Designation.objects.filter(
            church=self.request.user.church
        ).order_by("designation_name")

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class DesignationDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = DesignationSerializer
    def get_queryset(self):
        return Designation.objects.filter(
            church=self.request.user.church
        ).order_by("designation_name")

#dioces
class DioceseListCreateView(generics.ListCreateAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = DioceseSerializer
    def get_queryset(self):
        return Diocese.objects.filter(
            church=self.request.user.church
        ).order_by("name")

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class DioceseDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = DioceseSerializer
    def get_queryset(self):
        return Diocese.objects.filter(
            church=self.request.user.church
        ).order_by("name")


#priest master
class PriestListCreateView(generics.ListCreateAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = PriestSerializer
    def get_queryset(self):
        return Priest.objects.filter(
            church=self.request.user.church
        ).order_by("name")

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class PriestDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = PriestSerializer
    def get_queryset(self):
        return Priest.objects.filter(
            church=self.request.user.church
        ).order_by("name")



#priest change 
class PriestChangeListCreateView(generics.ListCreateAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = PriestChangeSerializer
    def get_queryset(self):
        return PriestChange.objects.filter(
            church=self.request.user.church
        ).select_related("priest", "designation")

    def perform_create(self, serializer):
        serializer.save(church=self.request.user.church)


class PriestChangeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes=[IsAuthenticated, IsChurchUser]
    serializer_class = PriestChangeSerializer
    def get_queryset(self):
        return PriestChange.objects.filter(
            church=self.request.user.church
        ).select_related("priest", "designation")



#Registersettings
class RegisterSettingCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def post(self, request):

        church = request.user.church
        register_type = request.data.get("register_type")

        # prevent duplicate settings
        if RegisterSetting.objects.filter(
            church=church,
            register_type=register_type
        ).exists():
            return Response(
                {"error": "Settings already exist for this register type."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RegisterSettingSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        serializer.save(church=church)

        return Response(
            {
                "message": "Register settings created successfully.",
                "data": serializer.data
            },
            status=status.HTTP_201_CREATED
        )
    
class RegisterSettingListAPIView(ListAPIView):
    serializer_class = RegisterSettingSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get_queryset(self):
        return RegisterSetting.objects.filter(
            church=self.request.user.church
        )
    
class RegisterSettingUpdateAPIView(UpdateAPIView):
    serializer_class = RegisterSettingSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]
    lookup_field = "register_type"

    def get_queryset(self):
        return RegisterSetting.objects.filter(
            church=self.request.user.church
        )
#priest GET
class PriestDropdownAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request):

        church = request.user.church

        serializer = PriestNameSerializer(church)

        # Convert serializer data to list of names (remove empty ones)
        priests = [
            name for name in serializer.data.values()
            if name
        ]

        return Response(priests)