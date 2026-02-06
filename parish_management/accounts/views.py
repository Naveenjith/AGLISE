from accounts.models import PasswordResetOTP, User
from accounts.utils import generate_otp, hash_otp
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.serializers import ChangePasswordSerializer, LoginSerializer
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import IsChurchUser
from accounts.serializers import ChurchProfileSerializer
from django.core.mail import send_mail
from rest_framework.decorators import api_view,permission_classes
from django.contrib.auth.hashers import make_password

class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        response = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": user.role,
            "user_id": user.id,
            "email": user.email,
            "church_name": user.church.name if user.church else None,
            
        }

        if user.role == "CHURCH":
            response.update({
                "church_id": user.church.id,
                "church_active": user.church.is_active,
            })

        if user.role == "USER":
            response.update({
                "member_id": user.member.id,
                "family_id": user.member.family.id,
                "church_id": user.member.church.id,
            })

        return Response(response)



class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"detail": "Logged out successfully"},
                status=status.HTTP_200_OK
            )
        except Exception:
            return Response(
                {"detail": "Invalid token"},
                status=status.HTTP_400_BAD_REQUEST
            )

class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        # ----------------------------
        # VERIFY OLD PASSWORD
        # ----------------------------
        if not user.check_password(old_password):
            return Response(
                {"detail": "Old password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------
        # SET NEW PASSWORD
        # ----------------------------
        user.set_password(new_password)
        user.save()

        return Response(
            {"detail": "Password changed successfully"},
            status=status.HTTP_200_OK
        )    

class ChurchProfileAPIView(APIView):
    permission_classes = [IsAuthenticated, IsChurchUser]

    def get(self, request):
        serializer = ChurchProfileSerializer(request.user.church)
        return Response(serializer.data)

    def put(self, request):
        serializer = ChurchProfileSerializer(
            request.user.church,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    

#forgot password
@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    email = request.data.get("email")

    if not email:
        return Response({"error": "Email required"}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # ❗ SECURITY: don’t reveal user existence
        return Response(
            {"message": "If the email exists, OTP has been sent"},
            status=200
        )

    # Invalidate old OTPs
    PasswordResetOTP.objects.filter(
        user=user,
        is_used=False
    ).update(is_used=True)

    otp = generate_otp()
    otp_hash = hash_otp(otp)

    PasswordResetOTP.objects.create(
        user=user,
        otp_hash=otp_hash
    )

    send_mail(
        subject="Password Reset OTP",
        message=f"Your OTP is {otp}. It is valid for 10 minutes.",
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )

    return Response(
        {"message": "OTP sent to email"},
        status=200
    )


#reset password
@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password(request):
    email = request.data.get("email")
    otp = request.data.get("otp")
    new_password = request.data.get("new_password")

    if not all([email, otp, new_password]):
        return Response(
            {"error": "All fields are required"},
            status=400
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid OTP"}, status=400)

    otp_hash = hash_otp(otp)

    try:
        otp_obj = PasswordResetOTP.objects.get(
            user=user,
            otp_hash=otp_hash,
            is_used=False
        )
    except PasswordResetOTP.DoesNotExist:
        return Response({"error": "Invalid or expired OTP"}, status=400)

    if otp_obj.is_expired():
        return Response({"error": "OTP expired"}, status=400)

    # Reset password
    user.password = make_password(new_password)
    user.save(update_fields=["password"])

    otp_obj.is_used = True
    otp_obj.save(update_fields=["is_used"])

    return Response({"message": "Password reset successful"}, status=200)