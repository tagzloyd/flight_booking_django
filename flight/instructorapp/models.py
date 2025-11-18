# instructorapp/models.py
from django.db import models
from django.utils import timezone
import random
import string
from flightapp.models import Student, User, AddOn, BookingDetail
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class Section(models.Model):
    section_name = models.CharField(max_length=200)
    section_code = models.CharField(max_length=50, unique=True)
    semester = models.CharField(max_length=50)
    academic_year = models.CharField(max_length=20)
    schedule = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sections')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.section_code} - {self.section_name}"

    def enrolled_students_count(self):
        return self.enrollments.filter(is_active=True).count()

class SectionEnrollment(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='section_enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['section', 'student']

    def __str__(self):
        return f"{self.student.student_number} - {self.section.section_code}"

class ActivityAddOn(models.Model):
    """Model to store add-on requirements for activities"""
    activity = models.ForeignKey('Activity', on_delete=models.CASCADE, related_name='activity_addons')
    addon = models.ForeignKey(AddOn, on_delete=models.CASCADE, related_name='activity_requirements')
    passenger = models.ForeignKey('ActivityPassenger', on_delete=models.CASCADE, null=True, blank=True, related_name='passenger_addons')
    is_required = models.BooleanField(default=False, help_text="Whether this add-on is mandatory for the activity")
    quantity_per_passenger = models.PositiveIntegerField(default=1, help_text="How many of this add-on each passenger should have")
    points_value = models.DecimalField(max_digits=6, decimal_places=2, default=10.00, help_text="Points awarded for including this add-on")
    notes = models.TextField(blank=True, null=True, help_text="Additional instructions for this add-on")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['activity', 'addon', 'passenger']
        verbose_name_plural = "Activity Add-ons"

    def __str__(self):
        status = "Required" if self.is_required else "Optional"
        passenger_info = f" - {self.passenger.first_name} {self.passenger.last_name}" if self.passenger else " - All Passengers"
        return f"{self.addon.name} - {self.activity.title}{passenger_info} ({status})"

class Activity(models.Model):
    # Basic Information
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    activity_type = models.CharField(max_length=50, default='Flight Booking')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='activities')
    
    # Flight Booking Requirements (based on flightapp models)
    required_trip_type = models.CharField(
        max_length=20,
        choices=[
            ("one_way", "One Way"),
            ("round_trip", "Round Trip"), 
            ("multi_city", "Multi City")
        ],
        default='one_way'
    )
    required_origin = models.CharField(max_length=100, blank=True)
    required_destination = models.CharField(max_length=100, blank=True)
    required_departure_date = models.DateField(null=True, blank=True)
    required_return_date = models.DateField(null=True, blank=True)
    required_travel_class = models.CharField(
        max_length=20,
        choices=[
            ('economy', 'Economy'),
            ('premium_economy', 'Premium Economy'),
            ('business', 'Business'),
            ('first', 'First Class'),
        ],
        default='economy'
    )
    
    # Passenger Requirements
    required_passengers = models.PositiveIntegerField(default=1)  # Adults
    required_children = models.PositiveIntegerField(default=0)    # Children (2-11 years)
    required_infants = models.PositiveIntegerField(default=0)     # Infants (under 2 years)
    
    # Passenger Information Requirements
    require_passenger_details = models.BooleanField(default=True)
    
    # REMOVED: required_max_price field
    
    # Instructions & Timing
    instructions = models.TextField()
    total_points = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    due_date = models.DateTimeField()
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    
    # Add-on Grading Settings
    addon_grading_enabled = models.BooleanField(default=True, help_text="Enable grading for add-ons")
    required_addon_points = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="Minimum points required from add-ons")
    
    # Code System
    activity_code = models.CharField(max_length=8, unique=True, blank=True, null=True)
    is_code_active = models.BooleanField(default=False)
    code_generated_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Activities"
        ordering = ['-created_at']

    def generate_activity_code(self):
        """Generate a unique 6-character alphanumeric code"""
        while True:
            characters = string.ascii_uppercase + string.digits
            code = ''.join(random.choice(characters) for _ in range(6))
            if not Activity.objects.filter(activity_code=code).exists():
                return code

    def activate_code(self):
        """Activate the activity code - code expires at due_date"""
        if not self.activity_code:
            self.activity_code = self.generate_activity_code()
        
        self.is_code_active = True
        self.code_generated_at = timezone.now()
        self.status = 'published'
        self.save()

    def get_total_passengers(self):
        """Get total number of passengers including adults, children, and infants"""
        return self.required_passengers + self.required_children + self.required_infants

    @property
    def required_addons(self):
        """Property to access add-ons through the ActivityAddOn model"""
        return self.activity_addons.all()

    @property
    def total_addon_points(self):
        """Calculate total possible points from all add-ons"""
        return sum(addon.points_value for addon in self.activity_addons.all())

    @property
    def required_addons_list(self):
        """Get list of required add-ons"""
        return self.activity_addons.filter(is_required=True)

    @property
    def optional_addons_list(self):
        """Get list of optional add-ons"""
        return self.activity_addons.filter(is_required=False)

    @property
    def is_code_expired(self):
        """Check if the activity code has expired (same as due date passed)"""
        return self.is_due_date_passed

    @property
    def is_code_valid(self):
        """Check if code is both active and not expired"""
        return self.is_code_active and not self.is_due_date_passed

    @property
    def is_due_date_passed(self):
        """Check if due date has passed"""
        return timezone.now() > self.due_date

    @property
    def time_until_due(self):
        """Get time remaining until due date (and code expiration)"""
        remaining = self.due_date - timezone.now()
        if remaining.total_seconds() <= 0:
            return None
        return remaining

    @property
    def submission_status(self):
        """Get overall submission status"""
        if self.is_due_date_passed:
            return 'expired'
        elif self.is_code_active:
            return 'active'
        else:
            return 'inactive'

    def can_submit(self):
        """Check if submissions are currently allowed"""
        return self.is_code_valid and not self.is_due_date_passed

    def __str__(self):
        return f"{self.title} - {self.section.section_code}"

class ActivityPassenger(models.Model):
    """Model to store passenger details for activities"""
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='passengers')
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    date_of_birth = models.DateField()
    nationality = models.CharField(max_length=100)
    
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.activity.title}"
    
    def get_passenger_type(self):
        """Determine passenger type based on age (simplified)"""
        if self.is_primary:
            return "Adult (Primary)"
        return "Adult"

class ActivitySubmission(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='activity_submissions')
    booking = models.ForeignKey('flightapp.Booking', on_delete=models.CASCADE, related_name='activity_submissions', null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True, null=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('submitted', 'Submitted'),
            ('graded', 'Graded'),
            ('late', 'Late Submission'),
        ],
        default='submitted'
    )

    # Activity requirements (copied for grading reference)
    required_origin_airport = models.ForeignKey(
        'flightapp.Airport', 
        on_delete=models.CASCADE, 
        related_name='activity_origins',
        null=True, 
        blank=True
    )
    required_destination_airport = models.ForeignKey(
        'flightapp.Airport', 
        on_delete=models.CASCADE, 
        related_name='activity_destinations',
        null=True, 
        blank=True
    )
    
    required_trip_type = models.CharField(
        max_length=20,
        choices=[
            ("one_way", "One Way"),
            ("round_trip", "Round Trip"), 
        ],
        default='one_way'
    )
    required_travel_class = models.CharField(
        max_length=20,
        choices=[
            ('economy', 'Economy'),
            ('premium_economy', 'Premium Economy'),
            ('business', 'Business'),
            ('first', 'First Class'),
        ],
        default='economy'
    )
    required_passengers = models.PositiveIntegerField(default=1)
    required_children = models.PositiveIntegerField(default=0)
    required_infants = models.PositiveIntegerField(default=0)
    require_passenger_details = models.BooleanField(default=True)
    # REMOVED: required_max_price field

    # Add-on grading fields
    addon_score = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="Points earned from add-ons")
    max_addon_points = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="Maximum possible points from add-ons")
    addon_feedback = models.TextField(blank=True, help_text="Feedback specific to add-on selection")

    class Meta:
        unique_together = ['activity', 'student']

    def __str__(self):
        return f"{self.student.student_number} - {self.activity.title}"

    @property
    def is_late_submission(self):
        """Check if submission was made after due date"""
        if not self.submitted_at or not self.activity.due_date:
            return False
        return self.submitted_at > self.activity.due_date

    @property
    def base_score(self):
        """Calculate base score without add-ons"""
        if self.score is None:
            return 0
        return self.score - self.addon_score

    @property
    def total_score_with_addons(self):
        """Calculate total score including add-ons"""
        base = self.score or 0
        return base + self.addon_score

    @property
    def addon_completion_percentage(self):
        """Calculate percentage of add-on points achieved"""
        if self.max_addon_points == 0:
            return 0
        return (self.addon_score / self.max_addon_points) * 100

    def get_student_selected_addons(self):
        """Get all add-ons selected by the student for this submission"""
        if not self.booking:
            return AddOn.objects.none()
        
        # Get all booking details for this booking
        booking_details = self.booking.details.all()
        
        # Get all add-ons from all booking details
        selected_addons = AddOn.objects.none()
        for detail in booking_details:
            selected_addons = selected_addons.union(detail.addons.all())
        
        return selected_addons

    def calculate_addon_score(self):
        """
        Calculate add-on score based on student's selected add-ons
        This method should be called during grading
        """
        if not self.activity.addon_grading_enabled:
            return 0, 0

        total_points = 0
        max_possible_points = 0
        
        # Get all activity add-on requirements
        activity_addons = self.activity.activity_addons.all()
        
        # Get student's selected add-ons
        student_addons = self.get_student_selected_addons()
        
        for activity_addon in activity_addons:
            max_possible_points += activity_addon.points_value
            
            # Check if this add-on was selected by the student
            student_has_addon = student_addons.filter(
                id=activity_addon.addon.id
            ).exists()
            
            if student_has_addon:
                total_points += activity_addon.points_value
        
        return total_points, max_possible_points

    def save(self, *args, **kwargs):
        """Automatically set status to late if submitted after due date"""
        if self.submitted_at and self.activity.due_date and self.submitted_at > self.activity.due_date:
            self.status = 'late'
        super().save(*args, **kwargs)

# UPDATED MODEL: StudentSelectedAddOn without BookingAddOn reference
class StudentSelectedAddOn(models.Model):
    """Track which add-ons students selected for their activity submission"""
    submission = models.ForeignKey(ActivitySubmission, on_delete=models.CASCADE, related_name='selected_addons')
    activity_addon = models.ForeignKey(ActivityAddOn, on_delete=models.CASCADE, related_name='student_selections')
    addon = models.ForeignKey(AddOn, on_delete=models.CASCADE, related_name='student_selections')
    booking_detail = models.ForeignKey('flightapp.BookingDetail', on_delete=models.CASCADE, null=True, blank=True, related_name='selected_addons')
    quantity_selected = models.PositiveIntegerField(default=1)
    points_earned = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['submission', 'activity_addon', 'addon']

    def __str__(self):
        return f"{self.submission.student.student_number} - {self.addon.name}"

    def save(self, *args, **kwargs):
        """Automatically calculate points earned"""
        self.points_earned = self.activity_addon.points_value * self.quantity_selected
        super().save(*args, **kwargs)

@receiver(post_save, sender=ActivitySubmission)
def log_activity_submission(sender, instance, created, **kwargs):
    if created:
        logger.info(f"NEW ACTIVITY SUBMISSION CREATED: "
                   f"ID: {instance.id}, "
                   f"Activity: {instance.activity.title}, "
                   f"Student: {instance.student.first_name} {instance.student.last_name}, "
                   f"Booking: {instance.booking.id if instance.booking else 'None'}")
        print(f"✅ AUTOMATIC LOG: ActivitySubmission {instance.id} created!")

class PracticeBooking(models.Model):
    """Model for practice bookings that are not graded activities"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='practice_bookings')
    booking = models.ForeignKey('flightapp.Booking', on_delete=models.CASCADE, related_name='practice_booking')
    created_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    
    # Practice booking details (for analysis/feedback)
    practice_type = models.CharField(
        max_length=20,
        choices=[
            ('free_practice', 'Free Practice'),
            ('guided_practice', 'Guided Practice'),
        ],
        default='free_practice'
    )
    
    # Optional: Practice scenario description
    scenario_description = models.TextField(blank=True, null=True)
    
    # Optional: Practice requirements (for guided practice)
    practice_requirements = models.JSONField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Practice Booking - {self.student.first_name} {self.student.last_name} - {self.created_at.strftime('%Y-%m-%d')}"