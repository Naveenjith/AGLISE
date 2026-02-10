from django.urls import path
from .views import (
    BaptismAPIView,
    BaptismCertificateAPIView,
    BaptismDetailAPIView,
    ChurchBillDetailAPIView,
    ChurchBillListAPIView,
    ChurchDashboardAPIView,
    FamilyDetailMobileAPIView,
    FamilyMembersAPIView,
    MemberProfileAPIView,
    PackageListAPIView,
    RelationshipListCreateAPIView,
    SubscribeAPIView,
    SubscriptionExpiryAPIView,
    UpgradeAPIView,
    UpgradeRequestAPIView,
    WardListCreateAPIView,
    WardDetailAPIView,
    FamilyListCreateAPIView,
    FamilyDetailAPIView,
    MemberListCreateAPIView,
    MemberDetailAPIView,
    ChurchList,
    ChangeFamilyHeadAPIView,
    RelationshipdetailView,GradeListCreateview,GradeDetailview,WardListWithFamilyCountAPIView,WardFamiliesMobileAPIView
)

urlpatterns = [
    # Wards
    path("wards/", WardListCreateAPIView.as_view()),
    path("wards/<int:pk>/", WardDetailAPIView.as_view()),
    path("mobile/wards/", WardListWithFamilyCountAPIView.as_view()),
    path("mobile/<ward_id>/families/", WardFamiliesMobileAPIView.as_view()),
    path("mobile/families/<int:family_id>/",FamilyDetailMobileAPIView.as_view(),name="mobile-family-detail"),

    #Grade
    path("grade/",GradeListCreateview.as_view(),name='grade_create'),
    path("grade/<int:pk>/",GradeDetailview.as_view(),name='grade-update-delete'),

    # Relationship
    path("relationships/",RelationshipListCreateAPIView.as_view(),name="relationship-list-create"),
    path("relationships/<int:pk>/",RelationshipdetailView.as_view(),name="relationship-detail"),
    # Families
    path("families/", FamilyListCreateAPIView.as_view()),
    path("families/<int:pk>/", FamilyDetailAPIView.as_view()),

    # Members
    path("members/", MemberListCreateAPIView.as_view()),
    path("members/<int:pk>/", MemberDetailAPIView.as_view()),
    path("member/profile/", MemberProfileAPIView.as_view()),
    #member list by families
    path("families/<int:family_id>/members/",FamilyMembersAPIView.as_view(),name="family-members"),

    #Packages
    path("packages/", PackageListAPIView.as_view()),
    path("church/subscribe/", SubscribeAPIView.as_view()),
    path("church/upgrade/", UpgradeAPIView.as_view()),
    path("church/dashboard/", ChurchDashboardAPIView.as_view()),

    path('churches/',ChurchList.as_view()),
    path("bills/",ChurchBillListAPIView.as_view(),name="church-bill-list"),
    path("bills/<int:pk>/",ChurchBillDetailAPIView.as_view(),name="church-bill-detail"),

    path("subscription/expiry/",SubscriptionExpiryAPIView.as_view(),name="subscription-expiry"),
    path("families/change-head/",ChangeFamilyHeadAPIView.as_view(),name="change-family-head"),
    path("subscriptions/upgrade-request/",UpgradeRequestAPIView.as_view(),name="upgrade-request"),

    #baptism
    path("baptisms/",BaptismAPIView.as_view(),name="baptism-list-create"),
    path("baptisms/<int:pk>/",BaptismDetailAPIView.as_view(),name="baptism-detail"),
    path("baptisms/<int:pk>/certificate/",BaptismCertificateAPIView.as_view(),name="baptism-certificate"),
]
