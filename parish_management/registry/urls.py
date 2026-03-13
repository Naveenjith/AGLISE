from django.urls import path
from .views import (
    BaptismAPIView,
    BaptismCertificateAPIView,
    BaptismDetailAPIView,
    ChurchBaptismCertificateAPIView,
    ChurchBillDetailAPIView,
    ChurchBillListAPIView,
    ChurchDashboardAPIView,
    ChurchMembersAPIView,
    DeathRegisterFinalizeView,
    DeathRegisterUpdateAPIView,
    DesignationDetailView,
    DesignationListCreateView,
    DheshaKuriAPIView,
    DioceseDetailView,
    DioceseListCreateView,
    FamilyBaptismsMobileAPIView,
    FamilyDetailMobileAPIView,
    FamilyHeadCreateAPIView,
    FamilyHeadUpdateAPIView,
    FamilyMarriagesMobileAPIView,
    FamilyMembersAPIView,
    InactiveMembersAPIView,
    MarriageCertificateAPIView,
    MarriageCertificateMobileAPIView,
    MarriageDetailAPIView,
    MarriageListCreateAPIView,
    MemberProfileAPIView,
    MyChurchAPIView,
    PackageListAPIView,
    PriestChangeDetailView,
    PriestChangeListCreateView,
    PriestDetailView,
    PriestDropdownAPIView,
    PriestListCreateView,
    PromoteFamilyHeadAPIView,
    RegisterSettingCreateAPIView,
    RegisterSettingListAPIView,
    RegisterSettingUpdateAPIView,
    RelationshipListCreateAPIView,
    SubscribeAPIView,
    SubscriptionExpiryAPIView,
    TombFeeDetailView,
    TombFeeListCreateView,
    TombTypeDetailView,
    TombTypeListCreateView,
    UpgradeAPIView,
    UpgradeRequestAPIView,
    UserDheshaKuriAPIView,
    UserVilichCholluKuriAPIView,
    VilichCholluKuriCreateAPIView,
    VilichCholluKuriDetailAPIView,
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
    path("mobile/families/<int:family_id>/<str:house_name>/",FamilyDetailMobileAPIView.as_view(),name="mobile-family-detail"),

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
    path("members/create-head/",FamilyHeadCreateAPIView.as_view(),name="create-family-head"),
    path("members/", MemberListCreateAPIView.as_view()),
    path("members/<int:pk>/", MemberDetailAPIView.as_view()),
    path("member/profile/", MemberProfileAPIView.as_view()),
    #member list by families
    path("families/<int:family_id>/<str:house_name>/members/",FamilyMembersAPIView.as_view(),name="family-members"),

    #Packages
    path("packages/", PackageListAPIView.as_view()),
    path("church/subscribe/", SubscribeAPIView.as_view()),
    path("church/upgrade/", UpgradeAPIView.as_view()),
    path("church/dashboard/", ChurchDashboardAPIView.as_view()),
    path("my-church/",MyChurchAPIView.as_view(),name="my-church"),

    path('churches/',ChurchList.as_view()),
    path("bills/",ChurchBillListAPIView.as_view(),name="church-bill-list"),
    path("bills/<int:pk>/",ChurchBillDetailAPIView.as_view(),name="church-bill-detail"),

    path("subscription/expiry/",SubscriptionExpiryAPIView.as_view(),name="subscription-expiry"),
    path("families/change-head/",ChangeFamilyHeadAPIView.as_view(),name="change-family-head"),
    path("subscriptions/upgrade-request/",UpgradeRequestAPIView.as_view(),name="upgrade-request"),

    #baptism
    path("baptisms/",BaptismAPIView.as_view(),name="baptism-list-create"),
    path("baptisms/<int:pk>/",BaptismDetailAPIView.as_view(),name="baptism-detail"),
    path("mobile/families/baptisms/",FamilyBaptismsMobileAPIView.as_view(),name="mobile-family-baptisms"),
    path("baptisms/<int:pk>/certificate/",BaptismCertificateAPIView.as_view(),name="baptism-certificate"),
    path("church/baptism-certificate/<int:pk>/",ChurchBaptismCertificateAPIView.as_view(),name="church-baptism-certificate"),

    #marriage
    path("marriages/vilich-chollu-kuri/",VilichCholluKuriCreateAPIView.as_view()),
    path("marriages/vilich-chollu-kuri/<int:pk>/detail/",VilichCholluKuriDetailAPIView.as_view()),
    path("marriages/",MarriageListCreateAPIView.as_view(),name="marriage-list-create"),
    path("marriages/<int:pk>/",MarriageDetailAPIView.as_view(),name="marriage-detail"),
    path("marriages/<int:pk>/certificate/", MarriageCertificateAPIView.as_view()),
    path("marriages/<int:pk>/dhesha-kuri/", DheshaKuriAPIView.as_view()),
    path("mobile/families/marriages/",FamilyMarriagesMobileAPIView.as_view(),name="mobile-family-marriages"),
    path("mobile/marriages/<int:pk>/certificate/",MarriageCertificateMobileAPIView.as_view(),name="mobile-marriage-certificate"),
    path("mobile/marriage/vilich-chollu-kuri/", UserVilichCholluKuriAPIView.as_view()),
    path("mobile/marriage/dhesha-kuri/", UserDheshaKuriAPIView.as_view()),

    #inactive members 
    path("members/inactive/",InactiveMembersAPIView.as_view(),name="inactive-members"),

    path("finalize/death/",DeathRegisterFinalizeView.as_view(),name="death-register-finalize"),
    path("death-registers/<int:pk>/",DeathRegisterUpdateAPIView.as_view(),name="death-register-update"),
    path("members/promote-head/<int:pk>/",PromoteFamilyHeadAPIView.as_view(),name="promote-family-head"),

    path("family-head/<int:pk>/",FamilyHeadUpdateAPIView.as_view(),name="family-head-edit"),
    path("church-members/",ChurchMembersAPIView.as_view(),name="church-members"),

    #tomb
    path("tomb-types/",TombTypeListCreateView.as_view(),name="tombtype-list-create"),
    path("tomb-types/<int:pk>/",TombTypeDetailView.as_view(),name="tombtype-detail"),
    path("tomb-fees/",TombFeeListCreateView.as_view(),name="tombfee-list-create"),
    path("tomb-fees/<int:pk>/",TombFeeDetailView.as_view(),name="tombfee-detail"),
    #designation
    path("designations/",DesignationListCreateView.as_view(),name="designation-list-create"),
    path("designations/<int:pk>/",DesignationDetailView.as_view(),name="designation-detail"),
    #dioces
    path("diocese/",DioceseListCreateView.as_view(),name="diocese-list-create"),
    path("diocese/<int:pk>/",DioceseDetailView.as_view(),name="diocese-detail"),

    #priest master
    path("priests/",PriestListCreateView.as_view(),name="priest-list-create"),
    path("priests/<int:pk>/",PriestDetailView.as_view(),name="priest-detail"),

    #priest change
    path("priest-changes/",PriestChangeListCreateView.as_view(),name="priestchange-list-create"),
    path("priest-changes/<int:pk>/",PriestChangeDetailView.as_view(),name="priestchange-detail"),

    #settingsregister
    path("register-settings/",RegisterSettingListAPIView.as_view(),name="register-settings-list"),
    path("register-settings/create/",RegisterSettingCreateAPIView.as_view(),name="register-settings-create"),
    path("register-settings/<str:register_type>/",RegisterSettingUpdateAPIView.as_view(),name="register-settings-update"),
    path("priests/dropdown/",PriestDropdownAPIView.as_view(),name="priests-dropdown")
]
