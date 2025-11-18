# instructorapp/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Section, SectionEnrollment, Activity, ActivityPassenger, ActivitySubmission

class SectionEnrollmentInline(admin.TabularInline):
    model = SectionEnrollment
    extra = 0
    readonly_fields = ['enrolled_at']
    fields = ['student', 'is_active', 'enrolled_at']
    raw_id_fields = ['student']
    can_delete = True

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = [
        'section_code', 
        'section_name', 
        'semester', 
        'academic_year', 
        'instructor', 
        'enrolled_students_count',
        'created_at'
    ]
    list_filter = [
        'semester', 
        'academic_year', 
        'instructor',
        'created_at'
    ]
    search_fields = [
        'section_code', 
        'section_name', 
        'instructor__username',
        'instructor__first_name',
        'instructor__last_name'
    ]
    readonly_fields = ['created_at', 'updated_at', 'enrolled_students_count_display']
    fieldsets = [
        ('Basic Information', {
            'fields': [
                'section_name',
                'section_code',
                'semester',
                'academic_year',
                'instructor'
            ]
        }),
        ('Schedule & Description', {
            'fields': [
                'schedule',
                'description'
            ]
        }),
        ('Statistics', {
            'fields': [
                'enrolled_students_count_display'
            ]
        }),
        ('Timestamps', {
            'fields': [
                'created_at',
                'updated_at'
            ],
            'classes': ['collapse']
        })
    ]
    inlines = [SectionEnrollmentInline]
    
    def enrolled_students_count_display(self, obj):
        return obj.enrolled_students_count()
    enrolled_students_count_display.short_description = 'Enrolled Students'

@admin.register(SectionEnrollment)
class SectionEnrollmentAdmin(admin.ModelAdmin):
    list_display = [
        'section',
        'student',
        'is_active',
        'enrolled_at'
    ]
    list_filter = [
        'section__semester',
        'section__academic_year',
        'is_active',
        'enrolled_at'
    ]
    search_fields = [
        'section__section_code',
        'section__section_name',
        'student__student_number',
        'student__user__first_name',
        'student__user__last_name'
    ]
    readonly_fields = ['enrolled_at']
    list_editable = ['is_active']
    raw_id_fields = ['section', 'student']

class ActivityPassengerInline(admin.TabularInline):
    model = ActivityPassenger
    extra = 0
    fields = [
        'first_name',
        'middle_name',
        'last_name',
        'gender',
        'date_of_birth',
        'nationality',
        'is_primary'
    ]
    readonly_fields = ['created_at', 'updated_at']

class ActivitySubmissionInline(admin.TabularInline):
    model = ActivitySubmission
    extra = 0
    readonly_fields = ['submitted_at', 'status']
    fields = [
        'student',
        'status',
        'score',
        'submitted_at'
    ]
    raw_id_fields = ['student', 'booking']
    can_delete = False

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'section',
        'activity_type',
        'status',
        'total_points',
        'due_date',
        'is_code_active',
        'submissions_count',
        'created_at'
    ]
    list_filter = [
        'status',
        'activity_type',
        'section__semester',
        'section__academic_year',
        'is_code_active',
        'created_at',
        'due_date'
    ]
    search_fields = [
        'title',
        'activity_code',
        'section__section_code',
        'section__section_name'
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'activity_code',
        'code_generated_at',
       
        'submissions_count_display',
        'get_total_passengers_display'
    ]
    fieldsets = [
        ('Basic Information', {
            'fields': [
                'title',
                'description',
                'activity_type',
                'section',
                'status'
            ]
        }),
        ('Flight Requirements', {
            'fields': [
                'required_trip_type',
                'required_origin',
                'required_destination',
                'required_departure_date',
                'required_return_date',
                'required_travel_class'
            ]
        }),
        ('Passenger Requirements', {
            'fields': [
                'required_passengers',
                'required_children',
                'required_infants',
                'get_total_passengers_display',
                'require_passenger_details'
            ]
        }),
        ('Grading & Instructions', {
            'fields': [
                'instructions',
                'total_points',
                'required_max_price'
            ]
        }),
        ('Timing', {
            'fields': [
                'due_date',
                'time_limit_minutes'
            ]
        }),
        ('Activity Code System', {
            'fields': [
                'activity_code',
                'is_code_active',
                'code_generated_at',
                
            ],
            'classes': ['collapse']
        }),
        ('Statistics', {
            'fields': [
                'submissions_count_display'
            ]
        }),
        ('Timestamps', {
            'fields': [
                'created_at',
                'updated_at'
            ],
            'classes': ['collapse']
        })
    ]
    inlines = [ActivityPassengerInline, ActivitySubmissionInline]
    actions = ['activate_codes', 'deactivate_codes', 'close_activities']
    
    def submissions_count(self, obj):
        return obj.submissions.count()
    submissions_count.short_description = 'Submissions'
    
    def submissions_count_display(self, obj):
        return obj.submissions.count()
    submissions_count_display.short_description = 'Total Submissions'
    
    def get_total_passengers_display(self, obj):
        return obj.get_total_passengers()
    get_total_passengers_display.short_description = 'Total Required Passengers'
    
    def activate_codes(self, request, queryset):
        for activity in queryset:
            if activity.status != 'closed':
                activity.activate_code()
                self.message_user(
                    request, 
                    f"Activated code for {activity.title}: {activity.activity_code}"
                )
    activate_codes.short_description = "Activate codes for selected activities"
    
    def deactivate_codes(self, request, queryset):
        updated = queryset.update(is_code_active=False)
        self.message_user(request, f"Deactivated codes for {updated} activities")
    deactivate_codes.short_description = "Deactivate codes for selected activities"
    
    def close_activities(self, request, queryset):
        updated = queryset.update(status='closed')
        self.message_user(request, f"Closed {updated} activities")
    close_activities.short_description = "Close selected activities"

@admin.register(ActivityPassenger)
class ActivityPassengerAdmin(admin.ModelAdmin):
    list_display = [
        'first_name',
        'last_name',
        'activity',
        'gender',
        'date_of_birth',
        'nationality',
        'is_primary',
        'created_at'
    ]
    list_filter = [
        'gender',
        'is_primary',
        'activity__section',
        'created_at'
    ]
    search_fields = [
        'first_name',
        'last_name',
        'activity__title',
        'nationality'
    ]
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['activity']
    
    def get_passenger_type_display(self, obj):
        return obj.get_passenger_type()
    get_passenger_type_display.short_description = 'Passenger Type'

@admin.register(ActivitySubmission)
class ActivitySubmissionAdmin(admin.ModelAdmin):
    list_display = [
        'activity',
        'student',
        'status',
        'score',
        'submitted_at',
        'is_late'
    ]
    list_filter = [
        'status',
        'activity__section',
        'submitted_at',
        'activity__due_date'
    ]
    search_fields = [
        'activity__title',
        'student__student_number',
        'student__user__first_name',
        'student__user__last_name'
    ]
    readonly_fields = [
        'submitted_at',
        'is_late_display'
    ]
    raw_id_fields = ['activity', 'student', 'booking']
    list_editable = ['status', 'score']
    fieldsets = [
        ('Submission Information', {
            'fields': [
                'activity',
                'student',
                'booking',
                'status'
            ]
        }),
        ('Grading', {
            'fields': [
                'score',
                'feedback'
            ]
        }),
        ('Activity Requirements', {
            'fields': [
                'required_trip_type',
                'required_travel_class',
                'required_passengers',
                'required_children',
                'required_infants',
                'require_passenger_details',
                
            ],
            'classes': ['collapse']
        }),
        ('Airports', {
            'fields': [
                'required_origin_airport',
                'required_destination_airport'
            ],
            'classes': ['collapse']
        }),
        ('Timing', {
            'fields': [
                'submitted_at',
                'is_late_display'
            ]
        })
    ]
    actions = ['mark_as_graded', 'mark_as_late']
    
    def is_late(self, obj):
        if obj.submitted_at and obj.activity.due_date:
            return obj.submitted_at > obj.activity.due_date
        return False
    is_late.boolean = True
    is_late.short_description = 'Late'
    
    def is_late_display(self, obj):
        if obj.submitted_at and obj.activity.due_date:
            is_late = obj.submitted_at > obj.activity.due_date
            if is_late:
                return format_html('<span style="color: red;">⚠ Late Submission</span>')
            else:
                return format_html('<span style="color: green;">✓ On Time</span>')
        return 'N/A'
    is_late_display.short_description = 'Submission Status'
    
    def mark_as_graded(self, request, queryset):
        updated = queryset.update(status='graded')
        self.message_user(request, f"Marked {updated} submissions as graded")
    mark_as_graded.short_description = "Mark selected submissions as graded"
    
    def mark_as_late(self, request, queryset):
        updated = queryset.update(status='late')
        self.message_user(request, f"Marked {updated} submissions as late")
    mark_as_late.short_description = "Mark selected submissions as late"

# Optional: Custom admin site configuration
class InstructorAppAdminSite(admin.AdminSite):
    site_header = "Instructor App Administration"
    site_title = "Instructor App Admin"
    index_title = "Welcome to Instructor App Administration"

# You can also register models with custom admin site if needed
# instructor_admin_site = InstructorAppAdminSite(name='instructor_admin')
# instructor_admin_site.register(Section, SectionAdmin)
# instructor_admin_site.register(Activity, ActivityAdmin)
# ... and so on