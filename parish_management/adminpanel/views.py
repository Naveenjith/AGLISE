from pyexpat.errors import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.shortcuts import render, redirect
from django.db import transaction, IntegrityError
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404
from adminpanel.decorators import admin_required
from adminpanel.forms import PackageForm, ChurchForm, ChurchSubscriptionForm
from registry.models import Bill, Church, Package, ChurchSubscription, UpgradeRequest
from accounts.utils import generate_password
from django.contrib.auth import logout
from datetime import date, timedelta, timezone
from dateutil.relativedelta import relativedelta
from registry.services import calculate_package_pricing, calculate_prorated_upgrade_amount,get_next_subscription_action
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import json
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.contrib import messages

User = get_user_model()


def admin_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user and user.role == "ADMIN":
            login(request, user)
            return redirect("adminpanel:dashboard")

        return render(request, "adminpanel/login.html", {
            "error": "Invalid credentials or not an admin"
        })

    return render(request, "adminpanel/login.html")


def admin_logout(request):
    logout(request)
    return redirect("adminpanel:login")


@admin_required
def dashboard(request):
    church_count = Church.objects.count()
    package_count = Package.objects.count()

    upgrade_request_count = UpgradeRequest.objects.filter(
        status="PENDING"
    ).count()

    expiring_count = ChurchSubscription.objects.filter(
        payment_status="PAID",
        end_date__lte=now().date() + timedelta(days=7),
        end_date__gte=now().date()
    ).count()

    return render(request, "adminpanel/dashboard.html", {
        "church_count": church_count,
        "package_count": package_count,
        "upgrade_request_count": upgrade_request_count,
        "expiring_count": expiring_count,
    })

#-------------package section---------#

@admin_required
def package_create(request):
    form = PackageForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect("adminpanel:package_list")

    return render(request, "adminpanel/package/package_create.html", {
        "form": form
    })

@admin_required
def package_list(request):
    packages = Package.objects.all()
    return render(request, "adminpanel/package/package_list.html", {
        "packages": packages
    })



@admin_required
def package_update(request, pk):
    package = get_object_or_404(Package, pk=pk)
    form = PackageForm(request.POST or None, instance=package)

    if form.is_valid():
        form.save()
        return redirect("adminpanel:package_list")

    return render(request, "adminpanel/package/package_update.html", {
        "form": form,
        "package": package
    })

@admin_required
def package_delete(request, pk):
    package = get_object_or_404(Package, pk=pk)

    # SAFETY CHECK: package in use?
    if ChurchSubscription.objects.filter(package=package).exists():
        return render(request, "adminpanel/package/package_delete.html", {
            "package": package,
            "error": "This package is already assigned to a church and cannot be deleted."
        })

    if request.method == "POST":
        package.delete()
        return redirect("adminpanel:package_list")

    return render(request, "adminpanel/package/package_delete.html", {
        "package": package
    })

#-----------------------------------------------------------------------------------------------------------#

from decimal import Decimal

@admin_required
@transaction.atomic
def church_create(request):
    church_form = ChurchForm(request.POST or None, request.FILES or None)
    sub_form = ChurchSubscriptionForm(request.POST or None)

    package_pricing = json.dumps( {
        str(pkg.id): {
            "is_custom": pkg.is_custom,
            "is_trial": pkg.is_trial,
            "member_limit": pkg.member_limit,
            "rate_monthly": float(pkg.rate_per_member_monthly or 0),
            "rate_yearly": float(pkg.rate_per_member_yearly or 0),
        }
        for pkg in Package.objects.all()
    })

    if request.method == "POST":
        if church_form.is_valid() and sub_form.is_valid():

            # 1️⃣ Create Church (inactive by default)
            church = church_form.save(commit=False)
            church.is_active = False
            church.save()

            # 2️⃣ Create Church User
            password = generate_password()
            User.objects.create_user(
                username=church.email,
                email=church.email,
                password=password,
                role="CHURCH",
                church=church
            )

            # 3️⃣ Subscription + Billing
            package = sub_form.cleaned_data.get("package")
            billing_cycle = sub_form.cleaned_data.get("billing_cycle")
            custom_capacity = sub_form.cleaned_data.get("custom_capacity")

            bill_created = False

            if package:

                # 🟡 TRIAL PACKAGE
                if package.is_trial:
                    ChurchSubscription.objects.create(
                        church=church,
                        package=package,
                        payment_status="PAID",
                        is_active=True,
                        billing_cycle="TRIAL",
                        duration_months=0
                    )

                    church.is_active = True
                    church.save(update_fields=["is_active"])

                # 🟢 PAID PACKAGE (NORMAL + CUSTOM)
                else:
                    duration_months = 1 if billing_cycle == "MONTHLY" else 12

                    capacity = (
                        custom_capacity
                        if package.is_custom
                        else package.member_limit
                    )

                    subscription = ChurchSubscription.objects.create(
                        church=church,
                        package=package,
                        billing_cycle=billing_cycle,
                        duration_months=duration_months,
                        payment_status="UNPAID",
                        is_active=False,
                        custom_capacity=custom_capacity if package.is_custom else None
                    )

                    rate = (
                        package.rate_per_member_monthly
                        if billing_cycle == "MONTHLY"
                        else package.rate_per_member_yearly
                    )

                    amount = (
                        Decimal(rate) *
                        Decimal(capacity) *
                        Decimal(duration_months)
                    )

                    Bill.objects.create(
                        church=church,
                        subscription=subscription,
                        bill_type="NEW",
                        billing_cycle=billing_cycle,
                        duration_months=duration_months,
                        amount=amount,
                        breakdown={
                            "line_items": [{
                                "type": "NEW",
                                "members": int(capacity),          # 🔥 bill-time snapshot
            "rate": float(rate),               # 🔥 bill-time snapshot
            "months": int(duration_months),    # 🔥 bill-time snapshot
            "calculation": f"{rate} × {capacity} × {duration_months}",
            "total": float(amount),
        }],
        "grand_total": float(amount),
                        }
                    )

                    bill_created = True

            # 4️⃣ Email (send only after everything succeeds)
            frontend_login_url = settings.FRONTEND_LOGIN_URL

            if package and package.is_trial:
                message = (
                    f"Your church account has been created successfully.\n\n"
                    f"Email: {church.email}\n"
                    f"Password: {password}\n\n"
                    f"Login here:\n{frontend_login_url}\n\n"
                    f"You are on a TRIAL plan."
                )
            elif bill_created:
                message = (
                    f"Your church account has been created successfully.\n\n"
                    f"Email: {church.email}\n"
                    f"Password: {password}\n\n"
                    f"Login here:\n{frontend_login_url}\n\n"
                    f"A package has been assigned.\n"
                    f"Your account will be activated after payment confirmation."
                )
            else:
                message = (
                    f"Your church account has been created successfully.\n\n"
                    f"Email: {church.email}\n"
                    f"Password: {password}\n\n"
                    f"Login here:\n{frontend_login_url}\n\n"
                    f"Please purchase a package to activate your account."
                )

            send_mail(
                subject="EGLISE Church Login Details",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[church.email],
                fail_silently=False,
            )

            return redirect("adminpanel:church_list")

    return render(
        request,
        "adminpanel/church/church_create.html",
        {
            "church_form": church_form,
            "sub_form": sub_form,
            "package_pricing": package_pricing,
        }
    )


@admin_required
def church_list(request):
    churches = (
        Church.objects
        .select_related("churchsubscription", "churchsubscription__package")
        .all()
    )
    return render(
        request,
        "adminpanel/church/church_list.html",
        {"churches": churches}
    )


@admin_required
def church_detail(request, pk):
    church = get_object_or_404(Church, pk=pk)
    subscription = getattr(church, "churchsubscription", None)

    pricing = None
    next_action = None

    if subscription:
        pricing = calculate_package_pricing(
            subscription.package,
            subscription.billing_cycle
        )
        next_action = get_next_subscription_action(church)

    bills = (
        Bill.objects
        .filter(church=church)
        .order_by("-created_at")
    )

    return render(
        request,
        "adminpanel/church/church_detail.html",
        {
            "church": church,
            "subscription": subscription,
            "pricing": pricing,
            "next_action": next_action,
            "bills": bills,   # ✅ ADD THIS
        }
    )




@admin_required
@transaction.atomic
def church_edit(request, pk):
    church = get_object_or_404(Church, pk=pk)
    subscription = getattr(church, "churchsubscription", None)

    church_form = ChurchForm(
        request.POST or None,
        request.FILES or None,
        instance=church
    )

    sub_form = ChurchSubscriptionForm(
        request.POST or None,
        initial={
            "package": subscription.package if subscription else None,
            "billing_cycle": subscription.billing_cycle if subscription else None,
            "custom_capacity": subscription.custom_capacity if subscription else None,
        }
    )

    packages = Package.objects.all()
    package_pricing = {
        str(p.id): {
            "is_trial": p.is_trial,
            "is_custom": p.is_custom,
            "member_limit": p.member_limit,
            "rate_monthly": float(p.rate_per_member_monthly or 0),
            "rate_yearly": float(p.rate_per_member_yearly or 0),
            "upgrade_rate_monthly": float(p.upgrade_rate_monthly or 0),
            "upgrade_rate_yearly": float(p.upgrade_rate_yearly or 0),
        }
        for p in packages
    }

    if request.method == "POST" and church_form.is_valid() and sub_form.is_valid():
        church = church_form.save(commit=False)

        # 🔥 CRITICAL FIX: persist church updates (image + fields)
        church.save()

        package = sub_form.cleaned_data["package"]
        billing_cycle = sub_form.cleaned_data["billing_cycle"]
        custom_capacity = sub_form.cleaned_data.get("custom_capacity")

        duration_months = 1 if billing_cycle == "MONTHLY" else 12

        # -------------------------------------------------
        # REMOVE SUBSCRIPTION
        # -------------------------------------------------
        if not package:
            if subscription:
                subscription.delete()
            church.is_active = False
            church.save()
            return redirect("adminpanel:church_detail", pk=church.pk)

        # -------------------------------------------------
        # TRIAL PACKAGE
        # -------------------------------------------------
        if package.is_trial:
            if subscription:
                subscription.package = package
                subscription.billing_cycle = None
                subscription.duration_months = None
                subscription.custom_capacity = None
                subscription.payment_status = "PAID"
                subscription.is_active = True
                subscription.save()
            else:
                ChurchSubscription.objects.create(
                    church=church,
                    package=package,
                    payment_status="PAID",
                    is_active=True
                )

            church.is_active = True
            church.save()
            return redirect("adminpanel:church_detail", pk=church.pk)

        # -------------------------------------------------
        # BLOCK DUPLICATE UNPAID BILLS
        # -------------------------------------------------
        if subscription and Bill.objects.filter(
            subscription=subscription,
            status="UNPAID"
        ).exists():
            messages.error(request, "Please clear the pending bill first.")
            return redirect("adminpanel:church_detail", pk=church.pk)

        # -------------------------------------------------
        # BLOCK SAME-DAY MULTIPLE CHANGES
        # -------------------------------------------------
        today = now().date()
        if subscription and Bill.objects.filter(
            subscription=subscription,
            created_at__date=today
        ).exists():
            messages.error(
                request,
                "Subscription was already modified today. "
                "Please try again tomorrow."
            )
            return redirect("adminpanel:church_detail", pk=church.pk)

        # -------------------------------------------------
        # CAPACITY VALIDATION
        # -------------------------------------------------
        if package.is_custom:
            if not custom_capacity:
                sub_form.add_error(
                    "custom_capacity",
                    "Custom capacity is required."
                )
                return render(
                    request,
                    "adminpanel/church/church_edit.html",
                    {
                        "church_form": church_form,
                        "sub_form": sub_form,
                        "church": church,
                        "package_pricing": json.dumps(
                            package_pricing,
                            cls=DjangoJSONEncoder
                        ),
                    }
                )
            capacity = Decimal(custom_capacity)
        else:
            capacity = Decimal(package.member_limit)

        bill_items = []
        total_amount = Decimal("0.00")
        credit_generated = Decimal("0.00")

        # -------------------------------------------------
        # NEW SUBSCRIPTION
        # -------------------------------------------------
        if not subscription or subscription.package.is_trial:
            subscription = ChurchSubscription.objects.create(
                church=church,
                package=package,
                billing_cycle=billing_cycle,
                duration_months=duration_months,
                custom_capacity=custom_capacity if package.is_custom else None,
                payment_status="UNPAID",
                is_active=False,
                credit_balance=Decimal("0.00"),
            )

            rate = (
                Decimal(package.rate_per_member_monthly)
                if billing_cycle == "MONTHLY"
                else Decimal(package.rate_per_member_yearly)
            )

            total_amount = rate * capacity * duration_months

            bill_items.append({
                "type": "NEW",
    "members": int(capacity),          # 🔥 bill-time snapshot
    "rate": float(rate),               # 🔥 bill-time snapshot
    "months": int(duration_months),    # 🔥 bill-time snapshot
    "calculation": f"{rate} × {capacity} × {duration_months}",
    "total": float(total_amount),
            })

            bill_type = "NEW"

        # -------------------------------------------------
        # DETERMINE IF THIS IS A REAL UPGRADE
        # -------------------------------------------------
        else:
            is_upgrade = (
                subscription
                and package.id != subscription.package.id
                and package.member_limit > subscription.package.member_limit
            )

            if is_upgrade:
                result = calculate_prorated_upgrade_amount(
                    subscription=subscription,
                    target_package=package,
                    target_billing_cycle=billing_cycle,
                    target_capacity=custom_capacity,
                )

                total_amount = result["amount"]
                credit_generated = result["credit"]

                if credit_generated > 0:
                    subscription.credit_balance += credit_generated
                    subscription.save(update_fields=["credit_balance"])

                if result["breakdown"]:
                    bill_items.append(result["breakdown"])

                bill_type = "UPGRADE"

                if (
                    result.get("breakdown")
                    and "remaining_months" in result["breakdown"]
                ):
                    duration_months = result["breakdown"]["remaining_months"]

            else:
                subscription.billing_cycle = billing_cycle
                subscription.custom_capacity = (
                    custom_capacity if package.is_custom else None
                )
                subscription.save(
                    update_fields=["billing_cycle", "custom_capacity"]
                )
                return redirect("adminpanel:church_detail", pk=church.pk)

        # -------------------------------------------------
        # CREATE BILL
        # -------------------------------------------------
        if total_amount > 0:
            Bill.objects.create(
                church=church,
                subscription=subscription,
                bill_type=bill_type,
                billing_cycle=billing_cycle,
                duration_months=duration_months,
                amount=total_amount,
                breakdown={
                     "line_items": bill_items,
    "grand_total": float(total_amount),
    "credit_generated": float(credit_generated),
    "apply": {
        "package_id": package.id,
        "billing_cycle": billing_cycle,
        "duration_months": duration_months,
        "custom_capacity": (
            int(custom_capacity)
            if package.is_custom else None
                        ),
                    },
                }
            )

        church.is_active = False
        church.save()

        return redirect("adminpanel:church_detail", pk=church.pk)

    return render(
        request,
        "adminpanel/church/church_edit.html",
        {
            "church_form": church_form,
            "sub_form": sub_form,
            "church": church,
            "package_pricing": json.dumps(
                package_pricing,
                cls=DjangoJSONEncoder
            ),
        }
    )

@admin_required
@transaction.atomic
def church_delete(request, pk):
    church = get_object_or_404(Church, pk=pk, is_deleted=False)
    subscription = getattr(church, "churchsubscription", None)

    if subscription and subscription.payment_status == "PAID":
        return render(
            request,
            "adminpanel/church/church_delete.html",
            {
                "church": church,
                "error": (
                    "This church has a PAID subscription. "
                    "Mark payment UNPAID or suspend before deleting."
                )
            }
        )

    if request.method == "POST":
        church.is_active = False
        church.is_deleted = True
        church.deleted_at = timezone.now()
        church.save(update_fields=["is_active", "is_deleted", "deleted_at"])
        return redirect("adminpanel:church_list")

    return render(
        request,
        "adminpanel/church/church_delete.html",
        {
            "church": church,
            "hard_delete": False
        }
    )



@admin_required
def bill_list(request):
    bills = Bill.objects.select_related(
        "church", "subscription"
    ).order_by("-created_at")

    church_id = request.GET.get("church")
    if church_id:
        bills = bills.filter(church_id=church_id)

    return render(
        request,
        "adminpanel/bill/bill_list.html",
        {"bills": bills}
    )


@admin_required
@transaction.atomic
def bill_detail(request, pk):
    bill = get_object_or_404(
        Bill.objects.select_related(
            "church",
            "subscription",
            "subscription__package"
        ),
        pk=pk
    )

    subscription = bill.subscription
    church = bill.church

    # =================================================
    # 🔥 DERIVED BILL DETAILS (DISPLAY ONLY)
    # =================================================
    members = None
    rate = None

    breakdown = bill.breakdown or {}
    items = breakdown.get("items", [])

    if items:
        item = items[0]  # single-item billing system

        # MEMBERS
        if "capacity" in item:
            members = item["capacity"]
        elif subscription.package.is_custom:
            members = subscription.custom_capacity
        else:
            members = subscription.package.member_limit

        # RATE
        if bill.bill_type == "UPGRADE":
            rate = item.get("upgrade_rate")
        else:
            rate = item.get("rate")

    # =================================================
    # POST: MARK BILL AS PAID
    # =================================================
    if request.method == "POST":

        if bill.status == "PAID":
            return redirect("adminpanel:church_detail", pk=church.pk)

        if subscription.package.is_trial:
            return redirect("adminpanel:church_detail", pk=church.pk)

        # 1️⃣ Mark bill PAID
        bill.status = "PAID"
        bill.paid_at = timezone.now()
        bill.save(update_fields=["status", "paid_at"])

        # 2️⃣ APPLY BILL EFFECTS
        apply_data = (bill.breakdown or {}).get("apply")

        if apply_data:
            subscription.package_id = apply_data["package_id"]
            subscription.billing_cycle = apply_data["billing_cycle"]
            subscription.custom_capacity = apply_data.get("custom_capacity")

            today = timezone.now().date()

            if bill.bill_type == "NEW":
                duration_months = apply_data["duration_months"]

                subscription.start_date = today
                subscription.end_date = today + relativedelta(
                    months=duration_months
                )
                subscription.duration_months = duration_months

                # 🔥 CRITICAL
                subscription.pricing_origin = "BASE"

            elif bill.bill_type == "UPGRADE":
                remaining_months = 0

                if items and "remaining_months" in items[0]:
                    remaining_months = items[0]["remaining_months"]

                subscription.start_date = today
                subscription.end_date = today + relativedelta(
                    months=remaining_months
                )
                subscription.duration_months = remaining_months

                # 🔥 CRITICAL
                subscription.pricing_origin = "UPGRADE"

        subscription.payment_status = "PAID"
        subscription.is_active = True
        subscription.save()

        church.is_active = True
        church.save(update_fields=["is_active"])

        return redirect("adminpanel:church_detail", pk=church.pk)

    # =================================================
    # GET: RENDER PAGE
    # =================================================
    return render(
        request,
        "adminpanel/bill/bill_detail.html",
        {
            "bill": bill,
            "subscription": subscription,
            "church": church,
            "members": members,
            "rate": rate,
        }
    )



@admin_required
@transaction.atomic
def mark_payment_unpaid(request, pk):
    subscription = get_object_or_404(ChurchSubscription, pk=pk)

    if subscription.package.is_trial:
        return redirect("adminpanel:church_detail", pk=subscription.church.id)

    # ❗ DO NOT MODIFY BILL HISTORY
    subscription.payment_status = "UNPAID"
    subscription.is_active = False
    subscription.save(update_fields=["payment_status", "is_active"])

    church = subscription.church
    church.is_active = False
    church.save(update_fields=["is_active"])

    return redirect("adminpanel:church_detail", pk=church.id)


@admin_required
def church_suspend(request, pk):
    church = get_object_or_404(Church, pk=pk)

    church.is_active = False
    church.save(update_fields=["is_active"])

    subscription = getattr(church, "churchsubscription", None)
    if subscription:
        subscription.is_active = False
        subscription.save(update_fields=["is_active"])

    return redirect("adminpanel:church_detail", pk=pk)


@admin_required
@transaction.atomic
def church_activate(request, pk):
    church = get_object_or_404(
        Church,
        pk=pk,
        is_deleted=False
    )

    subscription = getattr(church, "churchsubscription", None)

    # 🚫 Block activation if no subscription or unpaid
    if not subscription or subscription.payment_status != "PAID":
        messages.error(
            request,
            "Church cannot be activated until payment is completed."
        )
        return redirect("adminpanel:church_detail", pk=pk)

    # ✅ Activate church + subscription
    church.is_active = True
    church.save(update_fields=["is_active"])

    subscription.is_active = True
    subscription.save(update_fields=["is_active"])

    messages.success(
        request,
        "Church activated successfully."
    )

    return redirect("adminpanel:church_detail", pk=pk)


@admin_required
@transaction.atomic
def church_restore(request, pk):
    church = get_object_or_404(
        Church,
        pk=pk,
        is_deleted=True
    )

    church.is_deleted = False
    church.deleted_at = None
    church.is_active = False  # stays inactive until admin decides
    church.save(update_fields=["is_deleted", "deleted_at", "is_active"])

    return redirect("adminpanel:church_list")


@admin_required
@transaction.atomic
def church_hard_delete(request, pk):
    church = get_object_or_404(Church, pk=pk, is_deleted=True)

    if request.method == "POST":
        User.objects.filter(church=church).delete()
        church.delete()  # 🔥 REAL DELETE
        return redirect("adminpanel:church_list")

    return render(
        request,
        "adminpanel/church/church_delete.html",
        {
            "church": church,
            "hard_delete": True
        }
    )


#upgrade request
@admin_required
def upgrade_request_list(request):
    requests = (
        UpgradeRequest.objects
        .select_related(
            "church",
            "current_package",
            "requested_package"
        )
        .order_by("-created_at")
    )

    status = request.GET.get("status")
    if status:
        requests = requests.filter(status=status)

    return render(
        request,
        "adminpanel/upgrade_request/upgrade_request_list.html",
        {
            "requests": requests,
            "status": status,
        }
    )


@admin_required
@transaction.atomic
def upgrade_request_detail(request, pk):
    upgrade_request = get_object_or_404(
        UpgradeRequest.objects.select_related(
            "church",
            "current_package",
            "requested_package"
        ),
        pk=pk
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if upgrade_request.status != "PENDING":
            messages.error(request, "Request already processed.")
            return redirect(
                "adminpanel:upgrade_request_detail",
                pk=pk
            )

        if action == "approve":
            upgrade_request.status = "APPROVED"
            upgrade_request.reviewed_at = timezone.now()
            upgrade_request.save(update_fields=["status", "reviewed_at"])

            messages.success(
                request,
                "Upgrade request approved. Church can proceed with upgrade."
            )

        elif action == "reject":
            upgrade_request.status = "REJECTED"
            upgrade_request.reviewed_at = timezone.now()
            upgrade_request.save(update_fields=["status", "reviewed_at"])

            messages.warning(request, "Upgrade request rejected.")

        return redirect(
            "adminpanel:upgrade_request_detail",
            pk=pk
        )

    return render(
        request,
        "adminpanel/upgrade_request/upgrade_request_detail.html",
        {
            "req": upgrade_request
        }
    )


@admin_required
def expiring_churches(request):
    churches = Church.objects.filter(
        churchsubscription__payment_status="PAID",
        churchsubscription__end_date__lte=now().date() + timedelta(days=7),
        churchsubscription__end_date__gte=now().date()
    ).select_related("churchsubscription", "churchsubscription__package")

    return render(
        request,
        "adminpanel/church/expiring_churches.html",
        {
            "churches": churches,
        }
    )

