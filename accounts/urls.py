
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [

    # Customer registration
    path(
        'register/',
        views.register,
        name='register'
    ),

    # Organizer registration
    path(
        'organizer/register/',
        views.organizer_register,
        name='organizer_register'
    ),

    # User login
    path(
        'login/',
        views.user_login,
        name='login'
    ),

    # User logout
    path(
        'logout/',
        views.user_logout,
        name='logout'
    ),

    # Administrator dashboard
    path(
        'admin/dashboard/',
        views.admin_dashboard,
        name='admin_dashboard'
    ),

    # Organizer dashboard
    path(
        'organizer/dashboard/',
        views.organizer_dashboard,
        name='organizer_dashboard'
    ),

]
