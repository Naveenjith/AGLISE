import secrets
import string

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


# accounts/utils.py

import random
import hashlib

def generate_otp():
    return f"{random.randint(100000, 999999)}"

def hash_otp(otp):
    return hashlib.sha256(otp.encode()).hexdigest()
