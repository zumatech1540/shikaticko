from django.urls import path

from . import views


app_name = "payments"


urlpatterns = [
    path(
        "mpesa/initiate/<str:order_reference>/",
        views.initiate_mpesa_payment,
        name="mpesa_initiate",
    ),

    path(
        "mpesa/callback/",
        views.mpesa_callback,
        name="mpesa_callback",
    ),

    path(
        "status/<str:order_reference>/",
        views.payment_status,
        name="payment_status",
    ),
]