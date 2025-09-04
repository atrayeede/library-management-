# library/models.py - Updated with additional fields and methods
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15, blank=True, help_text="Contact phone number")
    address = models.TextField(blank=True, help_text="Home address")
    date_of_birth = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    membership_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    # Additional fields for enhanced functionality
    notification_preferences = models.CharField(
        max_length=20,
        choices=[
            ('email', 'Email Only'),
            ('sms', 'SMS Only'),
            ('both', 'Email and SMS'),
            ('none', 'No Notifications')
        ],
        default='email'
    )
    loan_limit = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])

    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username
    
    @property
    def active_loans_count(self):
        return self.user.loan_set.filter(status='active').count()
    
    @property
    def total_fines(self):
        return sum(fine.amount for fine in self.user.fine_set.filter(status='pending'))

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name
    
    @property
    def book_count(self):
        return self.book_set.count()

class Author(models.Model):
    name = models.CharField(max_length=200)
    bio = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='authors/', blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
    
    @property
    def book_count(self):
        return self.book_set.count()
    
    @property
    def is_alive(self):
        return self.death_date is None

class Book(models.Model):
    title = models.CharField(max_length=300)
    authors = models.ManyToManyField(Author, related_name='book_set')
    isbn = models.CharField(max_length=13, unique=True, help_text="13-digit ISBN")
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='book_set')
    publication_date = models.DateField()
    publisher = models.CharField(max_length=200)
    pages = models.IntegerField(default=0, validators=[MinValueValidator(1)])
    language = models.CharField(max_length=50, default='English')
    edition = models.CharField(max_length=50, blank=True)
    # Inventory management
    total_copies = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    available_copies = models.IntegerField(default=1, validators=[MinValueValidator(0)])
    # Media
    book_cover = models.ImageField(upload_to='book_covers/', blank=True, null=True)
    # Metadata
    added_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Tracking fields
    view_count = models.PositiveIntegerField(default=0)
    like_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-added_date']

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('book_detail', kwargs={'book_id': self.id})

    @property
    def average_rating(self):
        reviews = self.review_set.filter(is_approved=True)
        if reviews.exists():
            return reviews.aggregate(models.Avg('rating'))['rating__avg']
        return 0

    @property
    def review_count(self):
        return self.review_set.filter(is_approved=True).count()

    def is_available(self):
        return self.available_copies > 0
    
    @property
    def copies_on_loan(self):
        return self.total_copies - self.available_copies
    
    @property
    def reservation_queue_length(self):
        return self.reservation_set.filter(status='pending').count()
    
    def can_be_borrowed_by(self, user):
        """Check if a user can borrow this book"""
        if not self.is_available():
            return False, "Book is not available"
        
        # Check if user already has this book
        if self.loan_set.filter(user=user, status='active').exists():
            return False, "You already have this book on loan"
        
        # Check user's loan limit
        if user.loan_set.filter(status='active').count() >= user.userprofile.loan_limit:
            return False, "You have reached your loan limit"
        
        # Check for pending fines
        if user.fine_set.filter(status='pending').exists():
            return False, "Please pay pending fines first"
        
        return True, "Can borrow"

class Loan(models.Model):
    LOAN_STATUS_CHOICES = [
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
        ('lost', 'Lost'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    loan_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()
    return_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=LOAN_STATUS_CHOICES, default='active')
    renewal_count = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(3)])
    fine_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-loan_date']

    def __str__(self):
        return f"{self.user.username} - {self.book.title}"

    def save(self, *args, **kwargs):
        if not self.due_date:
            self.due_date = timezone.now() + timedelta(days=14)  # 14 days loan period
        super().save(*args, **kwargs)

    def is_overdue(self):
        if self.status == 'returned':
            return False
        return timezone.now() > self.due_date

    @property
    def days_overdue(self):
        if not self.is_overdue():
            return 0
        return (timezone.now().date() - self.due_date.date()).days

    def calculate_fine(self):
        if self.is_overdue() and self.status != 'returned':
            overdue_days = self.days_overdue
            fine_per_day = Decimal('1.00')  # $1 per day
            self.fine_amount = overdue_days * fine_per_day
            if self.status != 'overdue':
                self.status = 'overdue'
            return self.fine_amount
        return Decimal('0.00')
    
    @property
    def can_be_renewed(self):
        """Check if loan can be renewed"""
        if self.renewal_count >= 3:
            return False, "Maximum renewals reached"
        if self.is_overdue():
            return False, "Cannot renew overdue book"
        if self.book.reservation_set.filter(status='pending').exists():
            return False, "Book has pending reservations"
        return True, "Can be renewed"
    
    def renew(self):
        """Renew the loan for additional 14 days"""
        can_renew, message = self.can_be_renewed
        if can_renew:
            self.due_date = timezone.now() + timedelta(days=14)
            self.renewal_count += 1
            self.save()
            return True, "Loan renewed successfully"
        return False, message

class Reservation(models.Model):
    RESERVATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('available', 'Available'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reservation_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()
    status = models.CharField(max_length=10, choices=RESERVATION_STATUS_CHOICES, default='pending')
    notification_sent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['book', 'user']
        ordering = ['reservation_date']

    def __str__(self):
        return f"{self.user.username} reserved {self.book.title}"

    def save(self, *args, **kwargs):
        if not self.expiry_date:
            self.expiry_date = timezone.now() + timedelta(days=7)  # 7 days to pick up
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expiry_date and self.status not in ['fulfilled', 'cancelled']
    
    @property
    def queue_position(self):
        """Get position in reservation queue"""
        return Reservation.objects.filter(
            book=self.book,
            status='pending',
            reservation_date__lt=self.reservation_date
        ).count() + 1
    
    @property
    def days_until_expiry(self):
        if self.status != 'available':
            return None
        delta = self.expiry_date - timezone.now()
        return max(0, delta.days)

class Review(models.Model):
    RATING_CHOICES = [
        (1, '1 Star - Poor'),
        (2, '2 Stars - Fair'),
        (3, '3 Stars - Good'),
        (4, '4 Stars - Very Good'),
        (5, '5 Stars - Excellent'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=RATING_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200)
    comment = models.TextField()
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    is_approved = models.BooleanField(default=True)
    helpful_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['book', 'user']
        ordering = ['-created_date']

    def __str__(self):
        return f"{self.user.username} - {self.book.title} ({self.rating} stars)"
    
    @property
    def rating_display(self):
        return f"{self.rating}/5 stars"

class Fine(models.Model):
    FINE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('waived', 'Waived'),
        ('disputed', 'Disputed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True)
    paid_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=FINE_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f"Fine for {self.user.username} - ${self.amount}"
    
    def mark_as_paid(self, payment_method=''):
        """Mark fine as paid"""
        self.status = 'paid'
        self.paid_date = timezone.now()
        self.payment_method = payment_method
        self.save()
    
    @property
    def days_overdue_when_created(self):
        """Calculate how many days overdue the book was when fine was created"""
        if self.loan.due_date:
            return (self.created_date.date() - self.loan.due_date.date()).days
        return 0

# Additional utility model for system settings
class LibrarySettings(models.Model):
    loan_period_days = models.IntegerField(default=14)
    max_renewals = models.IntegerField(default=3)
    reservation_hold_days = models.IntegerField(default=7)
    fine_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)
    max_loan_limit = models.IntegerField(default=5)
    library_name = models.CharField(max_length=200, default="City Library")
    library_address = models.TextField(blank=True)
    library_phone = models.CharField(max_length=20, blank=True)
    library_email = models.EmailField(blank=True)
    
    class Meta:
        verbose_name = "Library Settings"
        verbose_name_plural = "Library Settings"
    
    def save(self, *args, **kwargs):
        # Ensure only one settings record exists
        if not self.pk and LibrarySettings.objects.exists():
            raise ValueError("Only one LibrarySettings instance allowed")
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        """Get or create library settings"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings