import secrets
import string

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))



from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings

User = get_user_model()


def create_family_head_user(member):
    # Safety checks
    if not member.is_family_head:
        return None

    if not member.email:
        raise ValueError("Family head must have an email address.")

    if hasattr(member, "user"):
        return member.user  # already exists

    password = get_random_string(10)

    user = User.objects.create_user(
        username=member.email,
        email=member.email,
        password=password,
        role="USER",
        member=member,
        church=member.church,
    )

    # Send email
    send_mail(
        subject="Your Parish Account Login Details",
        message=(
            f"Dear {member.name},\n\n"
            f"Your parish account has been created.\n\n"
            f"Login Email: {member.email}\n"
            f"Password: {password}\n\n"
            f"Please change your password after login.\n\n"
            f"Regards,\n"
            f"{member.church.name}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[member.email],
        fail_silently=False,
    )

    return user

# accounts/utils.py

import random
import hashlib

def generate_otp():
    return f"{random.randint(100000, 999999)}"

def hash_otp(otp):
    return hashlib.sha256(otp.encode()).hexdigest()


