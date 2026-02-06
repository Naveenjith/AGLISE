from datetime import date
from decimal import Decimal
from .models import Package
from django.db import transaction

# =====================================================
# CONSTANTS
# =====================================================

MONTHLY = "MONTHLY"
YEARLY = "YEARLY"


# =====================================================
# HELPERS
# =====================================================

def get_cycle_months(billing_cycle: str) -> int:
    """
    MONTHLY  → 1 month
    YEARLY   → 12 months
    """
    return 1 if billing_cycle == MONTHLY else 12


def get_rate(package, billing_cycle, *, upgrade=False):
    if billing_cycle == MONTHLY:
        rate = (
            package.upgrade_rate_monthly
            if upgrade else
            package.rate_per_member_monthly
        )
    else:
        rate = (
            package.upgrade_rate_yearly
            if upgrade else
            package.rate_per_member_yearly
        )

    if rate is None:
        return None

    return Decimal(rate)



def get_capacity(subscription_or_package, custom_capacity=None) -> Decimal:
    """
    Resolves member capacity safely
    """
    if hasattr(subscription_or_package, "is_custom"):
        # Package
        if subscription_or_package.is_custom:
            if not custom_capacity:
                raise ValueError("custom_capacity required for custom package")
            return Decimal(custom_capacity)
        return Decimal(subscription_or_package.member_limit)

    # Subscription
    if subscription_or_package.package.is_custom:
        return Decimal(subscription_or_package.custom_capacity)

    return Decimal(subscription_or_package.package.member_limit)


# =====================================================
# NEW / RENEW BILL
# =====================================================

def calculate_new_bill_amount(package, billing_cycle, capacity) -> Decimal:
    """
    Used for NEW or RENEW bills only
    """
    if package.is_trial:
        return Decimal("0.00")

    months = get_cycle_months(billing_cycle)
    rate = get_rate(package, billing_cycle)

    return rate * capacity * Decimal(months)


# =====================================================
# PRORATED UPGRADE
# =====================================================
from decimal import Decimal
from datetime import date


def calculate_prorated_upgrade_amount(
    subscription,
    target_package,
    target_billing_cycle,
    target_capacity=None,
):
    """
    SaaS upgrade calculation (MONTH-BASED)

    FINAL RULES (LOCKED):
    - Month-based proration only
    - Any started calendar month counts as consumed
    - OLD plan value:
        • BASE rate if pricing_origin == BASE
        • UPGRADE rate if pricing_origin == UPGRADE
    - NEW plan value: TARGET package upgrade rate
    """

    ZERO = Decimal("0.00")

    # -------------------------------------------------
    # BLOCK INVALID STATES
    # -------------------------------------------------
    if not subscription or subscription.package.is_trial:
        return {"amount": ZERO, "credit": ZERO, "breakdown": None}

    if not subscription.start_date:
        return {"amount": ZERO, "credit": ZERO, "breakdown": None}

    today = date.today()

    # -------------------------------------------------
    # TOTAL MONTHS IN CURRENT PLAN
    # -------------------------------------------------
    total_months = get_cycle_months(subscription.billing_cycle)

    # -------------------------------------------------
    # MONTHS USED (CALENDAR-BASED)
    # -------------------------------------------------
    start = subscription.start_date
    months_used = (
        (today.year - start.year) * 12
        + (today.month - start.month)
        + 1
    )
    months_used = max(min(months_used, total_months), 1)

    remaining_months = max(total_months - months_used, 0)

    # -------------------------------------------------
    # OLD PLAN RATE (DEPENDS ON PRICING ORIGIN)
    # -------------------------------------------------
    if subscription.pricing_origin == "BASE":
        old_rate = get_rate(
            subscription.package,
            subscription.billing_cycle,
            upgrade=False,   # BASE rate
        )
    else:
        old_rate = get_rate(
            subscription.package,
            subscription.billing_cycle,
            upgrade=True,    # UPGRADE rate
        )

    if old_rate is None:
        raise ValueError(
            f"Rate not configured for current package {subscription.package}"
        )

    old_capacity = get_capacity(subscription)

    old_remaining_value = (
        old_rate * old_capacity * Decimal(remaining_months)
    ).quantize(Decimal("0.01"))

    # -------------------------------------------------
    # TARGET UPGRADE RATE (MANDATORY)
    # -------------------------------------------------
    upgrade_rate = get_rate(
        target_package,
        target_billing_cycle,
        upgrade=True,
    )

    if upgrade_rate is None:
        raise ValueError(
            f"Upgrade rate not configured for target package {target_package}"
        )

    new_capacity = get_capacity(target_package, target_capacity)

    # -----------------------------
    # MONTHLY TARGET
    # -----------------------------
    if target_billing_cycle == MONTHLY:
        monthly_amount = (
            upgrade_rate * new_capacity
        ).quantize(Decimal("0.01"))

        return {
            "amount": monthly_amount,
            "credit": old_remaining_value,
            "breakdown": {
                "type": "UPGRADE",
                "mode": "MONTH_BASED",
                "months_used": months_used,
                "members": int(new_capacity), 
                "remaining_months": remaining_months,
                "old_rate": float(old_rate),
                "upgrade_rate": float(upgrade_rate),
                "old_remaining_value": float(old_remaining_value),
                "monthly_amount": float(monthly_amount),
                "explanation": (
                    f"₹{upgrade_rate} × {new_capacity} members for 1 month"
                ),
            },
        }

    # -----------------------------
    # YEARLY TARGET
    # -----------------------------
    new_remaining_value = (
        upgrade_rate * new_capacity * Decimal(remaining_months)
    ).quantize(Decimal("0.01"))

    amount_to_pay = (new_remaining_value - old_remaining_value).quantize(
        Decimal("0.01")
    )
    amount_to_pay = max(amount_to_pay, ZERO)

    return {
        "amount": amount_to_pay,
        "credit": ZERO,
        "breakdown": {
            "type": "UPGRADE",
            "mode": "MONTH_BASED",
            "months_used": months_used,
            "members": int(new_capacity), 
            "remaining_months": remaining_months,
            "old_rate": float(old_rate),
            "upgrade_rate": float(upgrade_rate),
            "old_remaining_value": float(old_remaining_value),
            "new_remaining_value": float(new_remaining_value),
            "upgrade_amount": float(amount_to_pay),
            "explanation": (
                f"(₹{upgrade_rate} × {new_capacity} × {remaining_months}) "
                f"− (₹{old_rate} × {old_capacity} × {remaining_months})"
            ),
        },
    }




def calculate_package_pricing(package, billing_cycle):
    """
    Used ONLY for display (church_detail page).
    Not used for billing.
    """

    if not package or package.is_trial:
        return None

    months = get_cycle_months(billing_cycle)

    rate = get_rate(
        package,
        billing_cycle,
        upgrade=False
    )

    capacity = (
        package.member_limit
        if not package.is_custom
        else None
    )

    monthly_amount = rate * (capacity or 1)

    return {
        "billing_cycle": billing_cycle,
        "months": months,
        "rate": float(rate),
        "capacity": capacity,
        "monthly": float(monthly_amount),
        "total": float(monthly_amount * Decimal(months)),
    }



# =====================================================
# SUBSCRIPTION CHECKS
# =====================================================

def can_add_member(church):
    subscription = getattr(church, "churchsubscription", None)

    if not subscription or not subscription.is_active:
        return False, "No active subscription."

    package = subscription.package
    current_count = church.members.filter(
        is_active=True,
        expired=False
    ).count()

    # Trial
    if package.is_trial:
        if current_count >= package.trial_member_limit:
            return False, "Trial limit reached."
        return True, None

    # Custom
    if package.is_custom:
        if not subscription.custom_capacity:
            return False, "Custom capacity not set."

        if current_count >= subscription.custom_capacity:
            return False, "Custom member limit reached."
        return True, None

    # Standard
    if current_count >= package.member_limit:
        return False, "Member limit exceeded."

    return True, None


# =====================================================
# UPGRADE SUGGESTIONS
# =====================================================

def get_next_subscription_action(church):
    subscription = getattr(church, "churchsubscription", None)

    if not subscription or not subscription.is_active:
        return None

    package = subscription.package
    members = church.members.filter(
        is_active=True,
        expired=False
    ).count()

    if package.is_trial:
        if members >= package.trial_member_limit:
            return {
                "type": "TRIAL_EXPIRED",
                "message": "Trial limit reached.",
            }
        return None

    if package.is_custom:
        return None

    if members <= package.member_limit:
        return None

    next_package = (
        Package.objects
        .filter(
            is_trial=False,
            is_custom=False,
            member_limit__gt=package.member_limit
        )
        .order_by("member_limit")
        .first()
    )

    if not next_package:
        return None

    return {
        "type": "UPGRADE_REQUIRED",
        "current_package": package,
        "current_members": members,
        "suggested_package": next_package,
    }






@transaction.atomic
def handle_member_death(member, *, new_head_id=None):
    """
    Handles member death safely:
    - Marks member as expired & inactive
    - Removes head-of-family flag
    - Optionally assigns a new family head
    """

    if member.expired:
        return  # idempotent

    family = member.family

    # 1️⃣ Mark member as deceased
    member.expired = True
    member.is_active = False
    member.is_family_head = False
    member.save(
        update_fields=["expired", "is_active", "is_family_head"]
    )

    # 2️⃣ Assign new family head (if provided)
    if new_head_id:
        new_head = (
            family.members
            .filter(id=new_head_id, expired=False, is_active=True)
            .first()
        )

        if not new_head:
            raise ValueError("Invalid new family head")

        new_head.is_family_head = True
        new_head.save(update_fields=["is_family_head"])