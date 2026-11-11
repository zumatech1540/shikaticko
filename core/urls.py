from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),

    path('about/', views.about, name='about'),

    path(
        'competitions/',
        views.competitions,
        name='competitions'
    ),

    path(
        'contact/',
        views.contact,
        name='contact'
    ),

    path(
        'faq/',
        views.faq,
        name='faq'
    ),
]