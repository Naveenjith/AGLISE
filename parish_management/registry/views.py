from datetime import date
from django.shortcuts import get_object_or_404
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import IsChurchAuthenticated,IsChurchUser, IsMemberUser
from registry.services import calculate_new_bill_amount, calculate_prorated_upgrade_amount, get_next_subscription_action
from .models import Baptism, Bill, Church, Grade, Relationship, UpgradeRequest, Ward, Family, Member,Package
from .serializers import BaptismSerializer, BillDetailSerializer, BillListSerializer, ChurchListSerializer, FamilyMemberSerializer, GradeSerializer, MemberProfileSerializer, MobileFamilyDetailSerializer, MobileFamilyListSerializer, RelationshipSerializer, SubscriptionExpirySerializer, UpgradeSerializer, WardSerializer, FamilySerializer, MemberSerializer,PackageSerializer, WardWithFamilyCountSerializer
from rest_framework.generics import ListAPIView
from .models import ChurchSubscription
from .serializers import SubscribeSerializer,UpgradeRequestSerializer
from rest_framework.views import APIView
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.db.models import Count,Sum

class ChurchContextMixin:
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Only add church to context if the user has one
        if hasattr(self.request.user, 'church'):
            context["church"] = self.request.user.church
        return context

    def get_queryset(self):
        # 1. Start with all objects
        queryset = self.model.objects.all()
        
        # 2. Check if the model has a field named 'church'
        has_church_field = any(f.name == 'church' for f in self.model._meta.get_fields())
        
        # 3. Only filter if the field exists
        if has_church_field:
            return queryset.filter(church=self.request.user.church)
        
        # 4. Otherwise, return all (for global models like Grade/Relationship)
        return queryset

class ChurchList(ListAPIView):
    permission_classes=[IsAuthenticated]
    serializer_class = ChurchListSerializer
    queryset = Church.objects.all().order_by("-created_at")



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



class MemberListCreateAPIView(ChurchContextMixin,ListCreateAPIView):
    model = Member
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]


class MemberDetailAPIView(
    ChurchContextMixin,
    RetrieveUpdateDestroyAPIView
):
    model = Member
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, IsChurchUser]

    def destroy(self, request, *args, **kwargs):
        member = self.get_object()

        if member.is_family_head:
            other_members = Member.objects.filter(
                family=member.family,
                is_active=True
            ).exclude(pk=member.pk)

            if other_members.exists():
                return Response(
                    {
                        "detail": (
                            "Cannot delete family head while "
                            "other members exist."
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

        # --------------------
        # Church basic details
        # --------------------
        church_data = {
            "id": church.id,
            "name": church.name,
            "city": church.city,
            "diocese": church.diocese_name,
            "email": church.email,
            "phone": church.phone_number,
            "is_active": church.is_active,
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
            baptism = serializer.save()

            if (
                baptism.baptism_category == "PARISH"
                and baptism.member is None
            ):
                member = Member.objects.create(
                    church=baptism.church,
                    family=baptism.family,
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
        baptism = get_object_or_404(
            Baptism,
            pk=pk,
            church=request.user.church
        )

        data = {
            "certificate_type": (
                "PARISH" if baptism.baptism_category == "PARISH" else "OTHER"
            ),

            # -------------------------
            # CHURCH INFO
            # -------------------------
            "church": {
                "name": baptism.church.name,
                "address": baptism.church.address,
            },

            # -------------------------
            # BAPTISM DETAILS
            # -------------------------
            "register_number": baptism.register_number,
            "date_of_baptism": baptism.date_of_baptism,
            "parish_of_baptism": baptism.parish_of_baptism,

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
            # PARISH MEMBER DETAILS
            # -------------------------
            "parish_member_details": None,
        }

        if baptism.baptism_category == "PARISH":
            data["parish_member_details"] = {
                "family_name": baptism.family.family_name,
                "house_name": baptism.family.house_name,
                "main_member_name": (
                    baptism.main_member.name if baptism.main_member else None
                ),
                "relationship": (
                    baptism.relation_with_main_member.name
                    if baptism.relation_with_main_member
                    else None
                ),
                "member_id": baptism.member.id if baptism.member else None,
            }

        return Response(data, status=status.HTTP_200_OK)



class FamilyMembersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, family_id):
        family = get_object_or_404(
            Family,
            id=family_id,
            church=request.user.church
        )

        members = Member.objects.filter(
            family=family
        ).order_by("-is_family_head", "name")  # ✅ correct field

        serializer = FamilyMemberSerializer(members, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


#mobile directory apis
class WardListWithFamilyCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wards = (
            Ward.objects
            .filter(church=request.user.church)
            .annotate(family_count=Count("families"))
            .order_by("ward_name")
        )

        serializer = WardWithFamilyCountSerializer(wards, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class WardFamiliesMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ward_id):
        # Ensure ward belongs to church
        get_object_or_404(
            Ward,
            id=ward_id,
            church=request.user.church
        )

        families_qs = (
            Family.objects
            .filter(
                ward_id=ward_id,
                church=request.user.church
            )
            .annotate(member_count=Count("members"))
            .order_by("family_name")
        )

        total_families = families_qs.count()
        total_members = families_qs.aggregate(
            total=Sum("member_count")
        )["total"] or 0

        serializer = MobileFamilyListSerializer(
            families_qs,
            many=True,
            context={"request": request}
        )

        return Response(
            {
                "total_families": total_families,
                "total_members": total_members,
                "families": serializer.data,
            }
        )
    
class FamilyDetailMobileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, family_id):
        family = get_object_or_404(
            Family,
            id=family_id,
            church=request.user.church
        )

        serializer = MobileFamilyDetailSerializer(family)
        return Response(serializer.data, status=status.HTTP_200_OK)
