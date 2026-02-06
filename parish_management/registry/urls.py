from django.urls import path
from .views import (
    ChurchBillDetailAPIView,
    ChurchBillListAPIView,
    ChurchDashboardAPIView,
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
    RelationshipdetailView,GradeListCreateview,GradeDetailview
)

urlpatterns = [
    # Wards
    path("wards/", WardListCreateAPIView.as_view()),
    path("wards/<int:pk>/", WardDetailAPIView.as_view()),
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
]
