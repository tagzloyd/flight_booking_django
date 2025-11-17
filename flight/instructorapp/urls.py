from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.instructor_login, name='instructor_login'),
    path('register/', views.instructor_register, name='instructor_register'),
    path('logout/', views.logout_view, name='instructor_logout'),
    
    # Main views
    path('', views.instructor_home, name='instructor_home'),
    path('sections/', views.instructor_section, name='instructor_section'),
    path('activities/', views.instructor_activity, name='instructor_activity'),
    
    # Section management
    path('section/<int:section_id>/', views.section_detail, name='section_detail'),
    path('section/<int:section_id>/create-activity/', views.create_activity, name='create_activity'),
    
    # Activity management
    path('activity/<int:activity_id>/', views.activity_detail, name='activity_detail'),
    path('activity/<int:activity_id>/edit/', views.edit_activity, name='edit_activity'),
    path('activity/<int:activity_id>/delete/', views.delete_activity, name='delete_activity'),
    path('activity/<int:activity_id>/activate/', views.activate_activity, name='activate_activity'),
    path('activity/<int:activity_id>/submissions/', views.activity_submissions, name='activity_submissions'),


    path('debug/submissions/', views.debug_submissions, name='debug_submissions'),
    # in instructorapp/urls.py
    path('debug-session/', views.debug_session, name='debug_session'),


    # Student work view
    path('activity/<int:activity_id>/student-work/', views.index, name='index'),
    path('api/activity/<int:activity_id>/submissions/', views.activity_submissions_api, name='activity_submissions_api'),

]