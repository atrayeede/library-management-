# library/urls.py - Updated with additional routes
from django.urls import path
from . import views

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    
    # Authentication
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Profile
    path('profile/', views.profile_view, name='profile'),
    
    # Books
    path('books/', views.book_list, name='book_list'),
    path('book/<int:book_id>/', views.book_detail, name='book_detail'),
    
    # Loan Management
    path('borrow/<int:book_id>/', views.borrow_book, name='borrow_book'),
    path('return/<int:loan_id>/', views.return_book, name='return_book'),
    path('my-loans/', views.my_loans, name='my_loans'),
    
    # Reservations
    path('reserve/<int:book_id>/', views.reserve_book, name='reserve_book'),
    path('cancel-reservation/<int:reservation_id>/', views.cancel_reservation, name='cancel_reservation'),
    path('my-reservations/', views.my_reservations, name='my_reservations'),
    
    # Reviews
    path('book/<int:book_id>/review/', views.add_review, name='add_review'),
    path('review/<int:review_id>/edit/', views.edit_review, name='edit_review'),
    path('review/<int:review_id>/delete/', views.delete_review, name='delete_review'),
    
    # Fines
    path('my-fines/', views.my_fines, name='my_fines'),
    
    # AJAX endpoints
    path('api/book/<int:book_id>/availability/', views.check_book_availability, name='check_book_availability'),
    path('api/book/<int:book_id>/queue-position/', views.get_reservation_queue_position, name='get_queue_position'),
]