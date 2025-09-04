# library/views.py - Updated with additional functionality
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Count
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from datetime import timedelta
from .models import Book, UserProfile, Loan, Reservation, Review, Fine, Category, Author
from .forms import (CustomUserCreationForm, CustomAuthenticationForm, 
                   UserProfileForm, BookSearchForm, ReviewForm, ReservationForm)

def home(request):
    """Home page with featured books and statistics"""
    featured_books = Book.objects.filter(available_copies__gt=0).annotate(
        avg_rating=Avg('review__rating')
    ).order_by('-added_date')[:6]
    
    total_books = Book.objects.count()
    total_users = UserProfile.objects.count()
    active_loans = Loan.objects.filter(status='active').count()
    
    context = {
        'featured_books': featured_books,
        'total_books': total_books,
        'total_users': total_users,
        'active_loans': active_loans,
    }
    return render(request, 'library/home.html', context)

def register_view(request):
    """User registration"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! Welcome to our library community.')
            login(request, user)
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'library/register.html', {'form': form})

def login_view(request):
    """User login"""
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                
                # Check for pending notifications
                pending_reservations = Reservation.objects.filter(
                    user=user, status='available'
                ).count()
                
                if pending_reservations > 0:
                    messages.info(request, f'You have {pending_reservations} book(s) ready for pickup!')
                
                return redirect(request.GET.get('next', 'home'))
    else:
        form = CustomAuthenticationForm()
    return render(request, 'library/login.html', {'form': form})

def logout_view(request):
    """User logout"""
    logout(request)
    messages.info(request, 'You have been logged out. Thank you for using our library!')
    return redirect('home')

@login_required
def profile_view(request):
    """View and edit user profile"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            # Update user fields
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.email = form.cleaned_data['email']
            request.user.save()
            
            # Update profile
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile, user=request.user)
    
    # Get user's activity
    user_loans = Loan.objects.filter(user=request.user).order_by('-loan_date')[:5]
    user_reservations = Reservation.objects.filter(user=request.user).order_by('-reservation_date')[:5]
    user_reviews = Review.objects.filter(user=request.user).order_by('-created_date')[:5]
    pending_fines = Fine.objects.filter(user=request.user, status='pending')
    
    context = {
        'form': form,
        'profile': profile,
        'user_loans': user_loans,
        'user_reservations': user_reservations,
        'user_reviews': user_reviews,
        'pending_fines': pending_fines,
    }
    return render(request, 'library/profile.html', context)

def book_list(request):
    """List all books with search and filtering"""
    form = BookSearchForm(request.GET)
    books = Book.objects.all().annotate(
        avg_rating=Avg('review__rating'),
        num_reviews=Count('review', distinct=True)
    ).select_related('category').prefetch_related('authors')
    
    if form.is_valid():
        query = form.cleaned_data.get('query')
        category = form.cleaned_data.get('category')
        
        if query:
            books = books.filter(
                Q(title__icontains=query) |
                Q(authors__name__icontains=query) |
                Q(isbn__icontains=query) |
                Q(description__icontains=query) |
                Q(publisher__icontains=query)
            ).distinct()
        
        if category:
            books = books.filter(category=category)
    
    # Pagination
    paginator = Paginator(books, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'page_obj': page_obj,
        'books': page_obj,
    }
    return render(request, 'library/book_list.html', context)

def book_detail(request, book_id):
    """Book details with reviews and reservation"""
    book = get_object_or_404(Book, id=book_id)
    reviews = Review.objects.filter(book=book, is_approved=True).select_related('user').order_by('-created_date')
    user_review = None
    user_reservation = None
    user_loan = None
    related_books = []
    can_review = False 
    
    if request.user.is_authenticated:
        try:
            user_review = Review.objects.get(book=book, user=request.user)
        except Review.DoesNotExist:
            pass
        
        try:
            user_reservation = Reservation.objects.get(
                book=book, user=request.user, 
                status__in=['pending', 'available']
            )
        except Reservation.DoesNotExist:
            pass
            
        try:
            user_loan = Loan.objects.get(
                book=book, user=request.user, status='active'
            )
        except Loan.DoesNotExist:
            pass

        if user_loan and not user_review:
            can_review = True
    
    # Get related books (same category or authors)
    if book.category:
        related_books = Book.objects.filter(
            category=book.category
        ).exclude(id=book.id).annotate(
            avg_rating=Avg('review__rating')
        )[:4]
    
    if not related_books.exists():
        # Get books by same authors
        author_ids = book.authors.values_list('id', flat=True)
        related_books = Book.objects.filter(
            authors__id__in=author_ids
        ).exclude(id=book.id).distinct().annotate(
            avg_rating=Avg('review__rating')
        )[:4]
    
    context = {
        'book': book,
        'reviews': reviews,
        'user_review': user_review,
        'user_reservation': user_reservation,
        'user_loan': user_loan,
        'related_books': related_books,
        'can_reserve': book.available_copies == 0 and not user_reservation and not user_loan,
        'can_borrow': book.available_copies > 0 and not user_loan,
        'can_review': can_review,
    }
    return render(request, 'library/book_detail.html', context)

@login_required
def borrow_book(request, book_id):
    """Borrow a book"""
    book = get_object_or_404(Book, id=book_id)
    
    if book.available_copies <= 0:
        messages.error(request, 'This book is currently not available.')
        return redirect('book_detail', book_id=book.id)
    
    # Check if user already has this book
    existing_loan = Loan.objects.filter(
        book=book, user=request.user, status='active'
    ).exists()
    
    if existing_loan:
        messages.error(request, 'You have already borrowed this book.')
        return redirect('book_detail', book_id=book.id)
    
    # Check for pending fines
    pending_fines = Fine.objects.filter(user=request.user, status='pending').exists()
    if pending_fines:
        messages.error(request, 'Please pay your pending fines before borrowing new books.')
        return redirect('my_fines')
    
    # Check loan limit (e.g., max 5 active loans)
    active_loans_count = Loan.objects.filter(user=request.user, status='active').count()
    if active_loans_count >= 5:
        messages.error(request, 'You have reached the maximum number of active loans (5).')
        return redirect('my_loans')
    
    # Create loan
    loan = Loan.objects.create(
        book=book,
        user=request.user,
        due_date=timezone.now() + timedelta(days=14)
    )
    
    # Update available copies
    book.available_copies -= 1
    book.save()
    
    # Check if user had a reservation
    try:
        reservation = Reservation.objects.get(
            book=book, user=request.user, status__in=['pending', 'available']
        )
        reservation.status = 'fulfilled'
        reservation.save()
        messages.success(request, f'Great! You have successfully borrowed "{book.title}" (was reserved). Due date: {loan.due_date.strftime("%B %d, %Y")}')
    except Reservation.DoesNotExist:
        messages.success(request, f'You have successfully borrowed "{book.title}". Due date: {loan.due_date.strftime("%B %d, %Y")}')
    
    # Check if this book had pending reservations and notify next user
    next_reservation = Reservation.objects.filter(
        book=book, status='pending'
    ).order_by('reservation_date').first()
    
    if next_reservation and book.available_copies > 0:
        next_reservation.status = 'available'
        next_reservation.save()
        # Here you could send an email notification
    
    return redirect('my_loans')

@login_required
def return_book(request, loan_id):
    """Return a borrowed book"""
    loan = get_object_or_404(Loan, id=loan_id, user=request.user, status='active')
    
    loan.return_date = timezone.now()
    loan.status = 'returned'
    
    # Calculate fine if overdue
    fine_amount = 0
    if loan.is_overdue():
        fine_amount = loan.calculate_fine()
        if fine_amount > 0:
            Fine.objects.create(
                user=request.user,
                loan=loan,
                amount=fine_amount,
                reason=f'Late return of "{loan.book.title}"'
            )
            messages.warning(request, f'Book returned with a late fee of ${fine_amount}. Please pay the fine to continue borrowing.')
    
    loan.save()
    
    # Update available copies
    loan.book.available_copies += 1
    loan.book.save()
    
    # Check for pending reservations
    next_reservation = Reservation.objects.filter(
        book=loan.book, status='pending'
    ).order_by('reservation_date').first()
    
    if next_reservation:
        next_reservation.status = 'available'
        next_reservation.expiry_date = timezone.now() + timedelta(days=7)
        next_reservation.save()
        # Here you could send an email notification to the user
        messages.info(request, f'"{loan.book.title}" has been made available to the next person in the reservation queue.')
    
    if fine_amount == 0:
        messages.success(request, f'Successfully returned "{loan.book.title}". Thank you for returning on time!')
    
    return redirect('my_loans')

@login_required
def reserve_book(request, book_id):
    """Reserve a book"""
    book = get_object_or_404(Book, id=book_id)
    
    # Check if book is available
    if book.available_copies > 0:
        messages.error(request, 'This book is currently available for borrowing.')
        return redirect('book_detail', book_id=book.id)
    
    # Check if user already has a reservation
    existing_reservation = Reservation.objects.filter(
        book=book, user=request.user, status__in=['pending', 'available']
    ).exists()
    
    if existing_reservation:
        messages.error(request, 'You already have a reservation for this book.')
        return redirect('book_detail', book_id=book.id)
    
    # Check if user already has this book on loan
    existing_loan = Loan.objects.filter(
        book=book, user=request.user, status='active'
    ).exists()
    
    if existing_loan:
        messages.error(request, 'You currently have this book on loan.')
        return redirect('book_detail', book_id=book.id)
    
    # Create reservation
    reservation = Reservation.objects.create(
        book=book,
        user=request.user,
        expiry_date=timezone.now() + timedelta(days=7)
    )
    
    # Calculate queue position
    queue_position = Reservation.objects.filter(
        book=book, status='pending', reservation_date__lt=reservation.reservation_date
    ).count() + 1
    
    messages.success(request, f'Successfully reserved "{book.title}". You are #{queue_position} in the queue. You will be notified when it becomes available.')
    return redirect('my_reservations')

@login_required
def cancel_reservation(request, reservation_id):
    """Cancel a reservation"""
    reservation = get_object_or_404(
        Reservation, id=reservation_id, user=request.user, 
        status__in=['pending', 'available']
    )
    
    book_title = reservation.book.title
    reservation.status = 'cancelled'
    reservation.save()
    
    messages.success(request, f'Reservation for "{book_title}" has been cancelled.')
    return redirect('my_reservations')

@login_required
def add_review(request, book_id):
    """Add a review for a book"""
    book = get_object_or_404(Book, id=book_id)
    
    # Check if user has borrowed this book
    has_borrowed = Loan.objects.filter(book=book, user=request.user).exists()
    if not has_borrowed:
        messages.error(request, 'You can only review books you have borrowed.')
        return redirect('book_detail', book_id=book.id)
    
    # Check if user already reviewed this book
    existing_review = Review.objects.filter(book=book, user=request.user).exists()
    if existing_review:
        messages.error(request, 'You have already reviewed this book.')
        return redirect('book_detail', book_id=book.id)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.book = book
            review.user = request.user
            review.save()
            messages.success(request, 'Your review has been added successfully! Thank you for sharing your thoughts.')
            return redirect('book_detail', book_id=book.id)
    else:
        form = ReviewForm()
    
    context = {
        'form': form,
        'book': book,
    }
    return render(request, 'library/add_review.html', context)

@login_required
def edit_review(request, review_id):
    """Edit a user's review"""
    review = get_object_or_404(Review, id=review_id, user=request.user)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your review has been updated successfully!')
            return redirect('book_detail', book_id=review.book.id)
    else:
        form = ReviewForm(instance=review)
    
    context = {
        'form': form,
        'book': review.book,
        'review': review,
    }
    return render(request, 'library/edit_review.html', context)

@login_required
def delete_review(request, review_id):
    """Delete a user's review"""
    review = get_object_or_404(Review, id=review_id, user=request.user)
    book_id = review.book.id
    book_title = review.book.title
    
    review.delete()
    messages.success(request, f'Your review for "{book_title}" has been deleted.')
    return redirect('book_detail', book_id=book_id)

@login_required
def my_loans(request):
    """User's loan history"""
    loans = Loan.objects.filter(user=request.user).select_related('book').order_by('-loan_date')
    
    # Update overdue status and calculate fines
    for loan in loans:
        if loan.status == 'active' and loan.is_overdue():
            fine_amount = loan.calculate_fine()
            if fine_amount > 0:
                # Create fine if it doesn't exist
                fine, created = Fine.objects.get_or_create(
                    user=request.user,
                    loan=loan,
                    defaults={
                        'amount': fine_amount,
                        'reason': f'Late return of "{loan.book.title}"'
                    }
                )
                if not created:
                    # Update existing fine amount
                    fine.amount = fine_amount
                    fine.save()
            loan.save()
    
    context = {
        'loans': loans,
    }
    return render(request, 'library/my_loans.html', context)

@login_required
def my_reservations(request):
    """User's reservations"""
    reservations = Reservation.objects.filter(user=request.user).select_related('book').order_by('-reservation_date')
    
    # Update expired reservations
    for reservation in reservations:
        if reservation.is_expired() and reservation.status in ['pending', 'available']:
            reservation.status = 'expired'
            reservation.save()
            
    available_reservation = reservations.filter(status='available').first()

    context = {
        'reservations': reservations,
        'available_reservation': available_reservation, 
    }
    return render(request, 'library/my_reservations.html', context)

@login_required
def my_fines(request):
    """User's fines"""
    fines = Fine.objects.filter(user=request.user).select_related('loan__book').order_by('-created_date')
    total_pending = sum(fine.amount for fine in fines if fine.status == 'pending')
    
    context = {
        'fines': fines,
        'total_pending': total_pending,
    }
    return render(request, 'library/my_fines.html', context)

# AJAX Views for dynamic functionality
@login_required
def check_book_availability(request, book_id):
    """AJAX view to check book availability"""
    book = get_object_or_404(Book, id=book_id)
    return JsonResponse({
        'available_copies': book.available_copies,
        'total_copies': book.total_copies,
        'is_available': book.available_copies > 0
    })

@login_required
def get_reservation_queue_position(request, book_id):
    """AJAX view to get user's position in reservation queue"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    try:
        reservation = Reservation.objects.get(
            book_id=book_id, user=request.user, status='pending'
        )
        position = Reservation.objects.filter(
            book_id=book_id, status='pending', 
            reservation_date__lt=reservation.reservation_date
        ).count() + 1
        
        return JsonResponse({
            'position': position,
            'status': reservation.status
        })
    except Reservation.DoesNotExist:
        return JsonResponse({'error': 'No reservation found'}, status=404)