from django.urls import path
from adminpanel import views

app_name = "adminpanel"

urlpatterns = [
    path("login/", views.admin_login, name="login"),
    path("logout/", views.admin_logout, name="logout"),
    path("", views.dashboard, name="dashboard"),

    path("churches/", views.church_list, name="church_list"),
    path("churches/create/", views.church_create, name="church_create"),
    path("churches/<int:pk>/", views.church_detail, name="church_detail"),
    path("churches/<int:pk>/edit/", views.church_edit, name="church_edit"),
    path("churches/<int:pk>/delete/", views.church_delete, name="church_delete"),
    path("church/<int:pk>/activate/", views.church_activate, name="church_activate"),
    path("church/<int:pk>/hard-delete/",views.church_hard_delete,name="church_hard_delete"),
    path("church/<int:pk>/restore/",views.church_restore,name="church_restore"),


    #path("subscriptions/<int:pk>/mark-paid/",views.mark_payment_paid,name="mark_payment_paid"),
    path("subscription/<int:pk>/mark-unpaid/",views.mark_payment_unpaid,name="mark_payment_unpaid"),
    path("church/<int:pk>/suspend/",views.church_suspend,name='church_suspend'),


    path("packages/", views.package_list, name="package_list"),
    path("packages/create/", views.package_create, name="package_create"),
    path("packages/<int:pk>/edit/", views.package_update, name="package_update"),
    path("packages/<int:pk>/delete/", views.package_delete, name="package_delete"),
    path("bills/",views.bill_list,name="bill_list"),
    path("bills/<int:pk>/",views.bill_detail,name="bill_detail"),

    path("upgrade-requests/",views.upgrade_request_list,name="upgrade_request_list"),
    path("upgrade-requests/<int:pk>/",views.upgrade_request_detail,name="upgrade_request_detail"),
    path("churches/expiring/",views.expiring_churches,name="expiring_churches"),

]
