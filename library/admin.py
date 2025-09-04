# library/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import UserProfile, Category, Author, Book, Loan, Reservation, Review, Fine

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'membership_date', 'is_active']
    list_filter = ['membership_date', 'is_active']
    search_fields = ['user__username', 'user__email', 'phone']
    readonly_fields = ['membership_date']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['name', 'nationality', 'birth_date']
    list_filter = ['nationality']
    search_fields = ['name', 'nationality']

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'get_authors', 'isbn', 'category', 'total_copies', 'available_copies', 'average_rating']
    list_filter = ['category', 'publication_date', 'language', 'added_date']
    search_fields = ['title', 'isbn', 'authors__name']
    filter_horizontal = ['authors']
    readonly_fields = ['added_date', 'average_rating']
    
    def get_authors(self, obj):
        return ", ".join([author.name for author in obj.authors.all()])
    get_authors.short_description = 'Authors'
    
    def average_rating(self, obj):
        return f"{obj.average_rating:.1f}" if obj.average_rating else "No ratings"
    average_rating.short_description = 'Avg Rating'

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['user', 'book', 'loan_date', 'due_date', 'return_date', 'status', 'fine_amount', 'is_overdue']
    list_filter = ['status', 'loan_date', 'due_date']
    search_fields = ['user__username', 'book__title']
    readonly_fields = ['loan_date']
    actions = ['mark_as_returned', 'calculate_fines']
    
    def is_overdue(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red;">Yes</span>')
        return format_html('<span style="color: green;">No</span>')
    is_overdue.short_description = 'Overdue'
    
    def mark_as_returned(self, request, queryset):
        for loan in queryset:
            if loan.status == 'active':
                loan.status = 'returned'
                loan.return_date = timezone.now()
                loan.book.available_copies += 1
                loan.book.save()
                loan.save()
        self.message_user(request, f"{queryset.count()} loans marked as returned.")
    mark_as_returned.short_description = "Mark selected loans as returned"
    
    def calculate_fines(self, request, queryset):
        for loan in queryset:
            fine_amount = loan.calculate_fine()
            if fine_amount > 0:
                Fine.objects.get_or_create(
                    user=loan.user,
                    loan=loan,
                    defaults={'amount': fine_amount, 'reason': f'Late return of "{loan.book.title}"'}
                )
        self.message_user(request, "Fines calculated for overdue loans.")
    calculate_fines.short_description = "Calculate fines for overdue loans"

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['user', 'book', 'reservation_date', 'expiry_date', 'status']
    list_filter = ['status', 'reservation_date']
    search_fields = ['user__username', 'book__title']
    actions = ['mark_as_available', 'mark_as_expired']
    
    def mark_as_available(self, request, queryset):
        queryset.update(status='available')
        self.message_user(request, f"{queryset.count()} reservations marked as available.")
    mark_as_available.short_description = "Mark selected reservations as available"
    
    def mark_as_expired(self, request, queryset):
        queryset.update(status='expired')
        self.message_user(request, f"{queryset.count()} reservations marked as expired.")
    mark_as_expired.short_description = "Mark selected reservations as expired"

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'book', 'rating', 'title', 'created_date', 'is_approved']
    list_filter = ['rating', 'is_approved', 'created_date']
    search_fields = ['user__username', 'book__title', 'title']
    actions = ['approve_reviews', 'disapprove_reviews']
    
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, f"{queryset.count()} reviews approved.")
    approve_reviews.short_description = "Approve selected reviews"
    
    def disapprove_reviews(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, f"{queryset.count()} reviews disapproved.")
    disapprove_reviews.short_description = "Disapprove selected reviews"

@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'reason', 'status', 'created_date', 'paid_date']
    list_filter = ['status', 'created_date']
    search_fields = ['user__username', 'reason']
    actions = ['mark_as_paid', 'waive_fines']
    
    def mark_as_paid(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='paid', paid_date=timezone.now())
        self.message_user(request, f"{queryset.count()} fines marked as paid.")
    mark_as_paid.short_description = "Mark selected fines as paid"
    
    def waive_fines(self, request, queryset):
        queryset.update(status='waived')
        self.message_user(request, f"{queryset.count()} fines waived.")
    waive_fines.short_description = "Waive selected fines"