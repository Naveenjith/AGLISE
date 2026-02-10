from django.db import models
from datetime import date
from datetime import timedelta
from django.forms import ValidationError
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.utils.timezone import now
from accounts.utils import create_family_head_user

class Church(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    city = models.CharField(max_length=100)

    vicar = models.CharField(max_length=150)
    asst_vicar1 = models.CharField(max_length=150, blank=True)
    asst_vicar2 = models.CharField(max_length=150, blank=True)
    asst_vicar3 = models.CharField(max_length=150, blank=True)

    diocese_name = models.CharField(max_length=150)

    logo = models.ImageField(
        upload_to="church_logos/",
        null=True,
        blank=True
    )

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)  # 🔥 NEW
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name
    

class Package(models.Model):
    name = models.CharField(max_length=100)
    member_limit = models.PositiveIntegerField(null=True, blank=True)
    is_trial = models.BooleanField(default=False)
    trial_member_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=5,
        help_text="Max members allowed for trial package"
    )
    rate_per_member_monthly = models.DecimalField(max_digits=8, decimal_places=2)
    rate_per_member_yearly = models.DecimalField(max_digits=8, decimal_places=2)

    upgrade_rate_monthly = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    upgrade_rate_yearly = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    is_custom = models.BooleanField(default=False)  # Contact Sales

    def clean(self):
        # Trial package rules
        if self.is_trial:
            if self.trial_member_limit is None:
                raise ValidationError(
                    "Trial package must have trial_member_limit"
                )

            # Trial must not have pricing
            if (
                self.rate_per_member_monthly or
                self.rate_per_member_yearly or
                self.upgrade_rate_monthly or
                self.upgrade_rate_yearly
            ):
                raise ValidationError(
                    "Trial package must not have pricing or upgrade rates"
                )

        # Custom package rules
        if self.is_custom and self.is_trial:
            raise ValidationError(
                "Package cannot be both trial and custom"
            )

    def can_upgrade(self):
        # Trial packages are never upgradable
        if self.is_trial:
            return False

        return (
            self.upgrade_rate_monthly is not None or
            self.upgrade_rate_yearly is not None
        )

    def __str__(self):
        return self.name


class ChurchSubscription(models.Model):
    church = models.OneToOneField(Church, on_delete=models.CASCADE)
    package = models.ForeignKey(Package, on_delete=models.PROTECT)

    billing_cycle = models.CharField(
        max_length=10,
        choices=(("MONTHLY", "Monthly"), ("YEARLY", "Yearly"))
    )
    payment_status = models.CharField(
        max_length=10,
        choices=(("PAID", "Paid"), ("UNPAID", "Unpaid")),
        default="UNPAID"
    )
    duration_months = models.PositiveIntegerField(
        help_text="Number of months purchased (e.g. 3, 5, 12)"
    )
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    custom_capacity = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    credit_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    PRICING_ORIGIN_CHOICES = (
        ("BASE", "Base Purchase"),
        ("UPGRADE", "Upgrade Purchase"),
    )

    pricing_origin = models.CharField(
        max_length=10,
        choices=PRICING_ORIGIN_CHOICES,
        default="BASE",
        help_text="How this subscription tier was acquired"
    )

    # -----------------------------
    # AUTO-CALCULATE END DATE
    # -----------------------------
    def save(self, *args, **kwargs):
        if self.start_date and self.duration_months:
            self.end_date = self.start_date + relativedelta(
                months=self.duration_months
            )
        super().save(*args, **kwargs)

    # -----------------------------
    # EXPIRY CHECK
    # -----------------------------
    def is_expired(self):
        if not self.end_date:
            return False
        return self.end_date < date.today()

    def expires_in_days(self):
        if not self.end_date:
            return None
        return (self.end_date - date.today()).days

    def __str__(self):
        return f"{self.church.name} - {self.package.name}"



class Ward(models.Model):
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="wards"
    )
    ward_name = models.CharField(max_length=100)
    ward_number = models.PositiveIntegerField()
    place = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.ward_name} ({self.church.name})"


class Family(models.Model):
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="families"
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="families"
    )

    family_name = models.CharField(max_length=150)
    house_name = models.CharField(max_length=150,blank=True,null=True)
    history = models.TextField(blank=True)
    origin = models.CharField(max_length=150, blank=True)
    family_image = models.ImageField(
        upload_to="family_images/",
        null=True,
        blank=True
    )
    def get_active_head(self):
        return self.members.filter(
            is_family_head=True,
            expired=False,
            is_active=True
        ).first()

    def __str__(self):
        return self.family_name


class Relationship(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Grade(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name





class Member(models.Model):
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="members"
    )
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="members"
    )

    name = models.CharField(max_length=150)
    baptismal_name = models.CharField(max_length=150, blank=True)

    gender = models.CharField(
        max_length=10,
        choices=(("MALE", "Male"), ("FEMALE", "Female"))
    )
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True
    )
    marital_status = models.CharField(
        max_length=20,
        choices=(
            ("SINGLE", "Single"),
            ("MARRIED", "Married"),
            ("WIDOWED", "Widowed"),
        )
    )

    spouse_name = models.CharField(max_length=150, blank=True)

    dob = models.DateField()
    age = models.PositiveIntegerField(editable=False)

    mobile_no = models.CharField(max_length=15)
    phone_no = models.CharField(max_length=15, blank=True)

    blood_group = models.CharField(max_length=5, blank=True)
    expired = models.BooleanField(default=False)

    father_name = models.CharField(max_length=150, blank=True)
    mother_name = models.CharField(max_length=150, blank=True)

    date_of_baptism = models.DateField(null=True, blank=True)
    parish_of_baptism = models.CharField(max_length=150, blank=True)

    educational_qualification = models.CharField(max_length=150, blank=True)
    sunday_school_qualification = models.CharField(max_length=150, blank=True)

    profession = models.CharField(max_length=150, blank=True)

    relationship = models.ForeignKey(
        Relationship,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    joining_date = models.DateField(null=True, blank=True)
    transferred_from = models.CharField(max_length=150, blank=True)
    address = models.TextField(blank=True)
    is_family_head = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
    # Track previous head state (important)
        was_head = None
        if self.pk:
            was_head = Member.objects.filter(
                pk=self.pk
            ).values_list("is_family_head", flat=True).first()

    # 🔥 Enforce single family head
        if self.is_family_head:
            Member.objects.filter(
            family=self.family,
            is_family_head=True
            ).exclude(pk=self.pk).update(is_family_head=False)

    # 🔢 Age calculation
        if self.dob:
            today = date.today()
            self.age = today.year - self.dob.year - (
                (today.month, today.day) < (self.dob.month, self.dob.day)
            )

        super().save(*args, **kwargs)

    # 👤 AUTO-CREATE USER FOR FAMILY HEAD
        if self.is_family_head and self.is_active:
        # Only when becoming head (not every save)
            if was_head is False or was_head is None:
                if not self.email:
                    raise ValidationError(
                    "Family head must have an email address."
                    )

                create_family_head_user(self)


    def __str__(self):
        return self.name


class Bill(models.Model):
    BILL_TYPE_CHOICES = (
    ("NEW", "New Subscription"),
    ("UPGRADE", "Upgrade"),
    ("EXTENSION", "Extension"),
    ("RENEW", "Renewal"),
    )

    STATUS_CHOICES = (
        ("UNPAID", "Unpaid"),
        ("PAID", "Paid"),
        ("CANCELLED", "Cancelled"),
    )

    bill_number = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True
    )

    invoice_number = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True
    )

    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="bills"
    )
    subscription = models.ForeignKey(
        ChurchSubscription,
        on_delete=models.CASCADE,
        related_name="bills"
    )

    bill_type = models.CharField(
        max_length=20,
        choices=BILL_TYPE_CHOICES
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    billing_cycle = models.CharField(
        max_length=10,
        choices=(("MONTHLY", "Monthly"), ("YEARLY", "Yearly")),
        null=True,
        blank=True
    )

    duration_months = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="UNPAID"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    breakdown = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.bill_number:
            self.bill_number = f"EGLS-BILL-{timezone.now().year}-{self.pk or 'NEW'}"

        if not self.invoice_number:
            self.invoice_number = f"EGLS-INV-{timezone.now().year}-{self.pk or 'NEW'}"

        super().save(*args, **kwargs)

    # Fix NEW placeholder after first save
        if "NEW" in self.bill_number or "NEW" in self.invoice_number:
            self.bill_number = f"EGLS-BILL-{timezone.now().year}-{self.pk}"
            self.invoice_number = f"EGLS-INV-{timezone.now().year}-{self.pk}"
            super().save(update_fields=["bill_number", "invoice_number"])


    def __str__(self):
        return f"Bill #{self.id} - {self.church.name}"



class UpgradeRequest(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )

    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="upgrade_requests"
    )

    current_package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="+"
    )

    requested_package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="+"
    )

    requested_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Only for custom or higher member request"
    )

    reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.church.name} → {self.requested_package.name}"


#Baptism
class Baptism(models.Model):
    BAPTISM_CATEGORY_CHOICES = (
        ("PARISH", "Parish (Church Member)"),
        ("OTHER", "Other (Outsider)"),
    )

    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="baptisms"
    )

    baptism_category = models.CharField(
        max_length=10,
        choices=BAPTISM_CATEGORY_CHOICES
    )

    # ---------- COMMON FIELDS ----------
    date_of_baptism = models.DateField()
    register_number = models.CharField(max_length=50, unique=True)
    place_of_birth = models.CharField(max_length=150)

    name = models.CharField(max_length=150)
    baptismal_name = models.CharField(max_length=150)

    gender = models.CharField(
        max_length=10,
        choices=(("MALE", "Male"), ("FEMALE", "Female"))
    )

    dob = models.DateField(null=True, blank=True)
    address = models.TextField()

    parish_of_baptism = models.CharField(max_length=150)

    god_father = models.CharField(max_length=150)
    god_mother = models.CharField(max_length=150)

    father_name = models.CharField(max_length=150)
    mother_name = models.CharField(max_length=150)

    remarks = models.TextField(blank=True)

    # ---------- PARISH ONLY ----------
    family = models.ForeignKey(
        Family,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    main_member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="as_main_member_in_baptisms"
    )

    relation_with_main_member = models.ForeignKey(
        Relationship,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="baptism_record"
        )
    
    member = models.OneToOneField(
        Member,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="baptism"
        )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.register_number})"
