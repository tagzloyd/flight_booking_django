from django.shortcuts import render,redirect
from django.http import HttpResponse
from django.urls import reverse
from django.template import loader
from datetime import datetime
from flightapp.models import Schedule, Route,  Airport,Seat, PassengerInfo, Flight, Airline
from flightapp.models import Booking, BookingDetail, Payment, PassengerInfo, Student,AddOn, SeatClass
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from datetime import date
from django.views.decorators.cache import never_cache
from .utils import login_required, redirect_if_logged_in
from instructorapp.models import Activity, ActivitySubmission, SectionEnrollment, PracticeBooking, ActivityAddOn
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.utils import timezone

from decimal import Decimal

def calculate_activity_score(booking, activity):
    """
    Calculate score based on how well the booking matches activity requirements
    """
    total_points = float(activity.total_points)
    points_earned = 0
    deduction_reasons = []
    
    print(f"=== SCORING DEBUG ===")
    print(f"Activity: {activity.title}")
    print(f"Total points available: {total_points}")
    
    # CORRECTED WEIGHTS - Total 100%
    base_weight = 0.25      # 25% - Completion
    passenger_weight = 0.25 # 25% - Passenger requirements  
    price_weight = 0.20     # 20% - Budget compliance (now always full points)
    compliance_weight = 0.15 # 15% - Trip type & class
    addon_weight = 0.15     # 15% - Add-ons
    
    # 1. Base points for completing the booking (25%)
    base_points = total_points * base_weight
    points_earned += base_points
    print(f"Base points (completion): {base_points}")
    
    # 2. Check passenger requirements (25% of total)
    passenger_points = total_points * passenger_weight
    booking_details = booking.details.all()
    
    # Count passenger types in booking
    adult_count = 0
    child_count = 0
    infant_count = 0
    
    for detail in booking_details:
        passenger_type = detail.passenger.passenger_type.lower()
        if passenger_type == 'adult':
            adult_count += 1
        elif passenger_type == 'child':
            child_count += 1
        elif passenger_type == 'infant':
            infant_count += 1
    
    print(f"Required - Adults: {activity.required_passengers}, Children: {activity.required_children}, Infants: {activity.required_infants}")
    print(f"Actual - Adults: {adult_count}, Children: {child_count}, Infants: {infant_count}")
    
    # FIXED: Calculate passenger match with proper handling for zero requirements
    total_required_passengers = activity.required_passengers + activity.required_children + activity.required_infants
    
    if total_required_passengers > 0:
        # Calculate match percentage based on actual requirements
        passenger_match = 0
        max_possible_match = 0
        
        # Adults (50% weight if required, otherwise 0)
        if activity.required_passengers > 0:
            max_possible_match += 0.5
            if adult_count == activity.required_passengers:
                passenger_match += 0.5
            else:
                deduction_reasons.append(f"Adult passenger count mismatch: required {activity.required_passengers}, got {adult_count}")
        elif adult_count > 0:
            # Extra adults when not required - small penalty
            passenger_match += 0.4  # Reduced points for unnecessary adults
            deduction_reasons.append(f"Extra adults booked: {adult_count} (none required)")
        
        # Children (30% weight if required, otherwise 0)  
        if activity.required_children > 0:
            max_possible_match += 0.3
            if child_count == activity.required_children:
                passenger_match += 0.3
            else:
                deduction_reasons.append(f"Child passenger count mismatch: required {activity.required_children}, got {child_count}")
        elif child_count > 0:
            # Extra children when not required - small penalty
            passenger_match += 0.2  # Reduced points for unnecessary children
            deduction_reasons.append(f"Extra children booked: {child_count} (none required)")
        
        # Infants (20% weight if required, otherwise 0)
        if activity.required_infants > 0:
            max_possible_match += 0.2
            if infant_count == activity.required_infants:
                passenger_match += 0.2
            else:
                deduction_reasons.append(f"Infant passenger count mismatch: required {activity.required_infants}, got {infant_count}")
        elif infant_count > 0:
            # Extra infants when not required - small penalty  
            passenger_match += 0.1  # Reduced points for unnecessary infants
            deduction_reasons.append(f"Extra infants booked: {infant_count} (none required)")
        
        # Normalize if max possible is less than 1.0 (when some passenger types not required)
        if max_possible_match > 0:
            normalized_match = passenger_match / max_possible_match
        else:
            normalized_match = 1.0  # No passenger requirements = full points
            
    else:
        # No passenger requirements at all
        normalized_match = 1.0
    
    passenger_earned = passenger_points * normalized_match
    points_earned += passenger_earned
    print(f"Passenger match: {normalized_match * 100}% -> {passenger_earned} points")
    
    # 3. Price compliance (20% of total) - NOW ALWAYS FULL POINTS
    price_points = total_points * price_weight
    price_earned = price_points  # Always full points since budget is removed
    points_earned += price_earned
    print(f"Price compliance: No budget limit -> {price_earned} points")
    
    # 4. Check trip type and class (15% of total)
    compliance_points = total_points * compliance_weight
    
    # Trip type check (50% of compliance points)
    trip_type_match = booking.trip_type == activity.required_trip_type
    if trip_type_match:
        print(f"Trip type match: {booking.trip_type} == {activity.required_trip_type}")
    else:
        deduction_reasons.append(f"Trip type mismatch: required {activity.required_trip_type}, got {booking.trip_type}")
    
    # Travel class check (50% of compliance points) - FIXED: Only need at least one passenger with correct class
    has_correct_class = False
    actual_classes = set()
    
    for detail in booking_details:
        if detail.seat_class:
            class_name = detail.seat_class.name.lower()
            actual_classes.add(class_name)
            if class_name == activity.required_travel_class.lower():
                has_correct_class = True
                break  # Only need one passenger with correct class
    
    if has_correct_class:
        print(f"Travel class match: Found {activity.required_travel_class}")
    else:
        deduction_reasons.append(f"Travel class mismatch: required {activity.required_travel_class}, got {', '.join(actual_classes)}")
    
    # Calculate compliance points
    compliance_match = 0
    if trip_type_match:
        compliance_match += 0.5
    if has_correct_class:
        compliance_match += 0.5
        
    compliance_earned = compliance_points * compliance_match
    points_earned += compliance_earned
    print(f"Compliance match: {compliance_match * 100}% -> {compliance_earned} points")
    
    # 5. Add-on compliance (15% of total)
    addon_points = total_points * addon_weight
    
    # This should use the submission's calculated addon_score
    # For now, we'll calculate it here but it should come from submission.addon_score
    if hasattr(activity, 'activity_addons') and activity.activity_addons.exists() and activity.addon_grading_enabled:
        required_addons = activity.activity_addons.filter(is_required=True)
        optional_addons = activity.activity_addons.filter(is_required=False)
        
        total_required_addons = required_addons.count()
        total_optional_addons = optional_addons.count()
        
        print(f"Add-on Requirements - Required: {total_required_addons}, Optional: {total_optional_addons}")
        
        # Simple scoring: count matched add-ons
        matched_required = 0
        matched_optional = 0
        
        student_addons = set()
        for detail in booking_details:
            for addon in detail.addons.all():
                student_addons.add(addon.id)
        
        for req_addon in required_addons:
            if req_addon.addon.id in student_addons:
                matched_required += 1
                print(f"✅ Required add-on matched: {req_addon.addon.name}")
        
        for opt_addon in optional_addons:
            if opt_addon.addon.id in student_addons:
                matched_optional += 1
                print(f"✅ Optional add-on matched: {opt_addon.addon.name}")
        
        # Calculate add-on score
        if total_required_addons > 0:
            required_ratio = matched_required / total_required_addons
        else:
            required_ratio = 1.0  # No required add-ons = full points for required portion
            
        if total_optional_addons > 0:
            optional_ratio = matched_optional / total_optional_addons
        else:
            optional_ratio = 1.0  # No optional add-ons = full points for optional portion
        
        # 70% for required, 30% for optional (bonus)
        addon_score = addon_points * (0.7 * required_ratio + 0.3 * optional_ratio)
        
        if matched_required < total_required_addons:
            deduction_reasons.append(f"Missing {total_required_addons - matched_required} required add-on(s)")
            
        print(f"Add-ons: {matched_required}/{total_required_addons} required, {matched_optional}/{total_optional_addons} optional -> {addon_score} points")
    else:
        # If no add-on requirements or add-on grading disabled, give full add-on points
        addon_score = addon_points
        print(f"No add-on requirements -> full add-on points: {addon_score}")
    
    points_earned += addon_score
    
    # Ensure score doesn't exceed total points and convert back to Decimal
    final_score = Decimal(str(min(points_earned, total_points)))
    
    print(f"Final score: {final_score}/{activity.total_points}")
    print(f"Breakdown: Base={base_points}, Passengers={passenger_earned}, Price={price_earned}, Compliance={compliance_earned}, Addons={addon_score}")
    if deduction_reasons:
        print(f"Deduction reasons: {', '.join(deduction_reasons)}")
    print("=====================")
    
    return final_score



@login_required
def student_home(request):
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        
        # Get student's enrolled sections
        enrolled_sections = SectionEnrollment.objects.filter(
            student=student, 
            is_active=True
        ).select_related('section')
        
        # Get active activities from enrolled sections - REMOVE invalid select_related fields
        activities = Activity.objects.filter(
            section__in=[enrollment.section for enrollment in enrolled_sections],
            is_code_active=True,
            status='published'
        ).select_related('section')  # Only select_related on valid fields
        
        # Check which activities the student has already submitted
        submitted_activities = ActivitySubmission.objects.filter(
            student=student,
            activity__in=activities
        ).values_list('activity_id', flat=True)
        
        template = loader.get_template('booking/student/home.html')
        context = {
            'activities': activities,
            'student': student,
            'submitted_activities': list(submitted_activities),
            'enrolled_sections': enrolled_sections,
        }
        return HttpResponse(template.render(context, request))
        
    except Student.DoesNotExist:
        messages.error(request, "Student not found.")
        return redirect('bookingapp:login')


# bookingapp/views.py - Update the student_activity_detail view
@login_required
def student_activity_detail(request, activity_id):
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        activity = get_object_or_404(Activity, id=activity_id, status='published')
        student = Student.objects.get(id=student_id)
        
        # Check if student is enrolled in this section
        if not SectionEnrollment.objects.filter(
            section=activity.section, 
            student=student, 
            is_active=True
        ).exists():
            messages.error(request, "You are not enrolled in this section.")
            return redirect('bookingapp:student_home')
        
        # Check if student has already submitted
        existing_submission = ActivitySubmission.objects.filter(
            activity=activity, 
            student=student
        ).first()
        
        # Get pre-defined passengers for this activity
        passengers = activity.passengers.all()
        
        template = loader.get_template('booking/student/activity_detail.html')
        context = {
            'activity': activity,
            'student': student,
            'existing_submission': existing_submission,
            'passengers': passengers,
            'code_active': activity.is_code_active,
            # SIMPLIFIED: Use due_date for expiration check
            'code_expired': activity.is_due_date_passed,  # Changed this line
        }
        return HttpResponse(template.render(context, request))
        
    except Activity.DoesNotExist:
        messages.error(request, "Activity not found or not available.")
        return redirect('bookingapp:student_home')
    
    
    
def validate_booking_for_activity(booking, activity):
    """Validate if the booking meets activity requirements"""
    try:
        print(f"=== VALIDATION DEBUG ===")
        print(f"Booking ID: {booking.id}")
        print(f"Activity: {activity.title}")
        
        # Check if booking has details
        if not booking.details.exists():
            print("❌ No booking details")
            return False
            
        # Check trip type
        if booking.trip_type != activity.required_trip_type:
            print(f"❌ Trip type mismatch: {booking.trip_type} vs {activity.required_trip_type}")
            return False
            
        # Get all passengers from booking
        booking_passengers = booking.details.all()
        
        # Count passenger types
        adult_count = 0
        child_count = 0
        infant_count = 0
        
        for detail in booking_passengers:
            passenger_type = detail.passenger.passenger_type.lower()
            if passenger_type == 'adult':
                adult_count += 1
            elif passenger_type == 'child':
                child_count += 1
            elif passenger_type == 'infant':
                infant_count += 1
        
        print(f"Passenger counts - Adults: {adult_count}, Children: {child_count}, Infants: {infant_count}")
        print(f"Required - Adults: {activity.required_passengers}, Children: {activity.required_children}, Infants: {activity.required_infants}")
        
        # Check passenger counts
        if (adult_count != activity.required_passengers or 
            child_count != activity.required_children or 
            infant_count != activity.required_infants):
            print("❌ Passenger count mismatch")
            return False
            
        # Check total price if max price is specified
        # if activity.required_max_price:
        #     total_amount = sum(detail.price for detail in booking_passengers if detail.passenger.passenger_type.lower() != 'infant')
        #     print(f"Total amount: {total_amount}, Max allowed: {activity.required_max_price}")
        #     if total_amount > activity.required_max_price:
        #         print("❌ Price exceeds maximum")
        #         return False
        
        print("✅ Validation passed")
        return True
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False
    


@login_required
def student_activities(request):
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        
        # Get all activities (both active and completed) for the student
        enrolled_sections = SectionEnrollment.objects.filter(
            student=student, 
            is_active=True
        ).select_related('section')
        
        # Get all activities from enrolled sections
        all_activities = Activity.objects.filter(
            section__in=[enrollment.section for enrollment in enrolled_sections]
        ).select_related('section')
        
        # Get submitted activities - FIX: Use filter() instead of values_list()
        submitted_activities = ActivitySubmission.objects.filter(
            student=student
        ).select_related('activity')
        
        # DEBUG PRINT
        print(f"=== STUDENT ACTIVITIES DEBUG ===")
        print(f"Student: {student.first_name} {student.last_name}")
        print(f"Total activities: {all_activities.count()}")
        print(f"Submitted activities: {submitted_activities.count()}")
        
        for submission in submitted_activities:
            print(f"Submission: {submission.id} - Activity: {submission.activity.title} - Activity ID: {submission.activity.id}")
        
        for activity in all_activities:
            has_submission = submitted_activities.filter(activity=activity).exists()
            print(f"Activity: {activity.title} (ID: {activity.id}) - Has submission: {has_submission}")
        
        template = loader.get_template('booking/student/activities.html')
        context = {
            'all_activities': all_activities,
            'student': student,
            'submitted_activities': submitted_activities,  # Pass the queryset directly
            'enrolled_sections': enrolled_sections,
        }
        return HttpResponse(template.render(context, request))
        
    except Student.DoesNotExist:
        messages.error(request, "Student not found.")
        return redirect('bookingapp:login')



@login_required
def home(request):
    from_airports = Airport.objects.all()
    to_airports = Airport.objects.all()

    print("=== HOME PAGE SESSION DEBUG ===")
    print(f"Session activity_id: {request.session.get('activity_id')}")
    print(f"GET params - activity_id: {request.GET.get('activity_id')}, activity_code: {request.GET.get('activity_code')}")
    print(f"Practice mode: {request.session.get('is_practice_booking')}")

    # Check for activity code from modal OR activity_id from URL
    activity_code = request.GET.get('activity_code')
    activity_id = request.GET.get('activity_id')
    activity = None
    
    # Clear any previous activity data if we're starting fresh
    if 'clear_activity' in request.GET:
        request.session.pop('activity_id', None)
        request.session.pop('activity_requirements', None)
        print("🧹 Cleared previous activity data")
    
    # If we have activity_id from GET parameters, verify it has an active code
       # If we have BOTH activity_id AND activity_code (from modal form)
    if activity_id and activity_code:
        try:
            activity = Activity.objects.get(
                id=activity_id,
                activity_code=activity_code.upper().strip(),
                is_code_active=True,
                status='published'
            )
            # Check if code is expired
            if activity.is_due_date_passed:
                messages.error(request, "This activity has expired. The due date has passed.")
                activity = None
            else:
                # SET ACTIVITY SESSION DATA
                request.session['activity_id'] = activity.id
                request.session['activity_requirements'] = {
                    'max_price': None,  # Always set to None since budget is removed
                    'travel_class': activity.required_travel_class,
                    'require_passenger_details': activity.require_passenger_details,
                }
                print(f"🎯 ACTIVITY SESSION SET via code+ID: {activity.title} (ID: {activity.id})")
                messages.success(request, f"Activity '{activity.title}' loaded successfully!")
                
        except Activity.DoesNotExist:
            print(f"❌ Activity not found with code {activity_code} and ID {activity_id}")
            messages.error(request, "Invalid activity code or ID. Please check with your instructor.")
    
    # Check if we have activity from session - verify it's still active
    elif request.session.get('activity_id'):
        try:
            activity = Activity.objects.get(
                id=request.session.get('activity_id'), 
                is_code_active=True,  # REQUIRE active code
                status='published'
            )
            # Check if code is expired
            if activity.is_due_date_passed:
                messages.error(request, "This activity has expired. The due date has passed.")
                request.session.pop('activity_id', None)
                request.session.pop('activity_requirements', None)
                activity = None
            else:
                print(f"🎯 ACTIVITY FROM SESSION: {activity.title} (ID: {activity.id})")
        except Activity.DoesNotExist:
            print(f"❌ Session activity not found or inactive: {request.session.get('activity_id')}")
            request.session.pop('activity_id', None)
            request.session.pop('activity_requirements', None)
            messages.error(request, "Activity session expired or code deactivated.")
    
    # If we have a valid activity, set up flight requirements
    if activity:
        print(f"⚙️ Setting up activity requirements for: {activity.title}")
        # Clear any previous booking session data but KEEP activity data
        booking_keys = [
            'trip_type', 'origin', 'destination', 'departure_date', 'return_date',
            'adults', 'children', 'infants', 'passenger_count'
        ]
        for key in booking_keys:
            request.session.pop(key, None)
        
        # Set flight requirements from activity
        if hasattr(activity, 'required_origin') and activity.required_origin:
            try:
                origin_airport = Airport.objects.get(code=activity.required_origin)
                request.session['origin'] = origin_airport.id
                print(f"  - Origin: {activity.required_origin}")
            except Airport.DoesNotExist:
                print(f"  - ❌ Origin airport not found: {activity.required_origin}")
                pass
                
        if hasattr(activity, 'required_destination') and activity.required_destination:
            try:
                dest_airport = Airport.objects.get(code=activity.required_destination)
                request.session['destination'] = dest_airport.id
                print(f"  - Destination: {activity.required_destination}")
            except Airport.DoesNotExist:
                print(f"  - ❌ Destination airport not found: {activity.required_destination}")
                pass
        
        request.session['trip_type'] = activity.required_trip_type
        request.session['adults'] = activity.required_passengers
        request.session['children'] = activity.required_children
        request.session['infants'] = activity.required_infants
        
        print(f"  - Trip type: {activity.required_trip_type}")
        print(f"  - Passengers: {activity.required_passengers} adults, {activity.required_children} children, {activity.required_infants} infants")
        
        messages.info(request, f"Activity mode: {activity.title} - Requirements have been pre-filled.")

    # If in practice mode, show practice info
    practice_requirements = request.session.get('practice_requirements')

    template = loader.get_template('booking/home.html')
    context = {
        "origins": from_airports,
        "destinations": to_airports,
        "activity": activity,
        "practice_requirements": practice_requirements,
        "is_practice_booking": request.session.get('is_practice_booking', False),

    }
    return HttpResponse(template.render(context, request))


@login_required
def search_flight(request):
    # Preserve activity_id if it exists
    activity_id = request.session.get('activity_id')
    
    # Validate activity is still active if this is an activity booking
    if activity_id:
        try:
            activity = Activity.objects.get(
                id=activity_id, 
                is_code_active=True,
                status='published'
            )
            # Check if code expired
            if activity.is_due_date_passed:
                messages.error(request, "Activity has expired. The due date has passed.")
                request.session.pop('activity_id', None)
                request.session.pop('activity_requirements', None)
                return redirect('bookingapp:main')
        except Activity.DoesNotExist:
            messages.error(request, "Activity is no longer available.")
            request.session.pop('activity_id', None)
            request.session.pop('activity_requirements', None)
            return redirect('bookingapp:main')
    
    if request.method == 'POST':
        trip_type = request.POST.get('trip_type')
        origin = request.POST.get('origin')
        destination = request.POST.get('destination')
        departure_date = request.POST.get('departure_date')
        return_date = request.POST.get('return_date')
        adults = int(request.POST.get('adults', 1))
        children = int(request.POST.get('children', 0))
        infants = int(request.POST.get('infants', 0))
        
        print(f"=== SEARCH_FLIGHT DEBUG ===")
        print(f"Activity ID in session: {activity_id}")
        
        if not trip_type and not origin and not destination and not departure_date and not return_date and (adults + children + infants == 0):
            return redirect('bookingapp:main')

        if trip_type:
            request.session['trip_type'] = trip_type
        if origin:    
            request.session['origin'] = int(origin)
        if destination:
            request.session['destination'] = int(destination)
        if departure_date:    
            request.session['departure_date'] = departure_date
        if return_date:    
            request.session['return_date'] = return_date

        request.session['adults'] = adults
        request.session['children'] = children
        request.session['infants'] = infants
        request.session['passenger_count'] = adults + children + infants
        request.session['seat'] = None

        # Preserve activity_id if it exists
        if activity_id:
            request.session['activity_id'] = activity_id
            print(f"✅ Preserved activity_id: {activity_id}")

        return redirect("bookingapp:flight_schedules")

@never_cache
@login_required
def flight_schedules(request):
    activity_id = request.session.get('activity_id')
    print(f"=== FLIGHT_SCHEDULES DEBUG ===")
    print(f"Activity ID: {activity_id}")
    origin_id = request.session.get('origin')
    destination_id = request.session.get('destination')
    depart_date = request.session.get('departure_date')
    dates = range(1, 8)

    if not origin_id or not destination_id or not depart_date:
        return redirect('bookingapp:main')

    origin = Airport.objects.get(id=origin_id)
    destination = Airport.objects.get(id=destination_id)

    # Departure date
    departure_obj = datetime.strptime(depart_date, "%Y-%m-%d")
    departure_date = departure_obj.strftime("%d %b %Y")

    # Return date
    return_date_str = request.session.get('return_date', '')
    return_schedules = None
    if return_date_str:
        return_obj = datetime.strptime(return_date_str, "%Y-%m-%d")
        return_date = return_obj.strftime("%d %b %Y")
        return_schedules = Schedule.objects.filter(
            flight__route__origin_airport=destination,
            flight__route__destination_airport=origin,
            departure_time__date=return_obj.date()
        )
    else:
        return_date = None

    passenger_count = request.session.get('passenger_count')

    # Departure schedules with optimized queries
    schedules = Schedule.objects.filter(
        flight__route__origin_airport=origin,
        flight__route__destination_airport=destination,
        departure_time__date=departure_obj.date()
    ).select_related(
        'flight__airline',
        'flight__aircraft',
        'flight__route__origin_airport',
        'flight__route__destination_airport'
    ).prefetch_related(
        'seats__seat_class'
    )

    # Get all seat classes and add-ons in optimized queries
    airline_ids = set()
    
    for schedule in schedules:
        airline_ids.add(schedule.flight.airline.id)
    
    # Fetch optional add-ons
    optional_addons_dict = {}
    if airline_ids:
        optional_addons = AddOn.objects.filter(
            airline_id__in=airline_ids,
            included=False
        ).select_related('type', 'seat_class')
        
        for addon in optional_addons:
            if addon.airline_id not in optional_addons_dict:
                optional_addons_dict[addon.airline_id] = []
            optional_addons_dict[addon.airline_id].append(addon)
    
    # Attach add-ons to schedules
    for schedule in schedules:
        airline_id = schedule.flight.airline.id
        
        # For included add-ons, we need to check based on seat classes available
        schedule_seat_classes = SeatClass.objects.filter(
            seats__schedule=schedule,
            seats__is_available=True
        ).distinct()
        
        # Get included add-ons for these seat classes
        included_addons = AddOn.objects.filter(
            seat_class__in=schedule_seat_classes,
            included=True
        ).select_related('type', 'seat_class')
        
        schedule.included_addons = list(included_addons)
        schedule.optional_addons = optional_addons_dict.get(airline_id, [])
        
        # Get available seat classes for this schedule
        schedule.available_seat_classes = schedule_seat_classes

    # Similarly for return schedules
    if return_schedules:
        return_schedules = return_schedules.select_related(
            'flight__airline',
            'flight__aircraft',
            'flight__route__origin_airport',
            'flight__route__destination_airport'
        ).prefetch_related(
            'seats__seat_class'
        )
        
        # Process return schedules similarly
        for schedule in return_schedules:
            airline_id = schedule.flight.airline.id
            
            # Get included add-ons for available seat classes
            schedule_seat_classes = SeatClass.objects.filter(
                seats__schedule=schedule,
                seats__is_available=True
            ).distinct()
            
            included_addons = AddOn.objects.filter(
                seat_class__in=schedule_seat_classes,
                included=True
            ).select_related('type', 'seat_class')
            
            schedule.included_addons = list(included_addons)
            schedule.optional_addons = optional_addons_dict.get(airline_id, [])
            
            schedule.available_seat_classes = schedule_seat_classes

    template = loader.get_template('booking/schedule.html')
    context = {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "passenger_count": passenger_count,
        "schedules": schedules,
        "return_schedules": return_schedules,
        'dates': dates,
        "origin_airport": origin,
        "destination_airport": destination,
    }
    return HttpResponse(template.render(context, request))

@login_required
def reset_selection(request):
    if request.method == "POST":
        request.session.pop('depart_schedule_id', None)
        request.session.pop('return_schedule_id', None)
    return redirect('bookingapp:flight_schedules')

@login_required
def cancel_selected_schedule(request):
    # remove selected schedules from session
    request.session.pop("depart_schedule_id", None)
    request.session.pop("return_schedule_id", None)
    # keep trip_type so roundtrip still works
    return redirect("bookingapp:flight_schedules")


@never_cache
@login_required
def select_schedule(request):
    if request.method == 'POST':
        schedule_id = request.POST.get('schedule_id')
        trip_type = request.session.get('trip_type', 'one_way')
        
        try:
            schedule = Schedule.objects.select_related(
                'flight__airline',
                'flight__route__origin_airport',
                'flight__route__destination_airport'
            ).get(id=schedule_id)
            
            # Store the selected schedule in session
            if trip_type == 'round_trip':
                # Check if we're selecting departure or return
                if not request.session.get('depart_schedule_id'):
                    # First selection is departure
                    request.session['depart_schedule_id'] = schedule_id
                    messages.success(request, "Departure flight selected. Now select your return flight.")
                    return redirect('bookingapp:flight_schedules')
                else:
                    # Second selection is return
                    request.session['return_schedule_id'] = schedule_id
                    # Redirect to review both schedules
                    return redirect('bookingapp:review_selected_scheduled')
            else:
                # One-way trip - store as departure and go to review
                request.session['depart_schedule_id'] = schedule_id
                return redirect('bookingapp:review_selected_scheduled')
            
        except Schedule.DoesNotExist:
            messages.error(request, "Selected schedule not found.")
            return redirect('bookingapp:flight_schedules')
    
    # If not POST, redirect to flight schedules
    return redirect('bookingapp:flight_schedules')

@never_cache
@login_required
def proceed_to_passengers(request):
    if request.method == 'POST':
        schedule_id = request.POST.get('schedule_id')
        optional_addons = request.POST.getlist('optional_addons')
        
        # Store in session for the booking process
        request.session['selected_schedule'] = schedule_id
        request.session['selected_optional_addons'] = optional_addons
        
        # Redirect to passenger details page
        return redirect('bookingapp:passenger_details')
    
    return redirect('bookingapp:flight_schedules')



""" review selected schedule  """
@never_cache   
@login_required
def review_scheduled(request):
    depart_id = request.session.get('depart_schedule_id')
    return_id = request.session.get('return_schedule_id')
    
    print(f"=== REVIEW SCHEDULED DEBUG ===")
    print(f"Depart ID: {depart_id}")
    print(f"Return ID: {return_id}")

    if not depart_id:
        messages.error(request, "Please select a departure flight first.")
        return redirect("bookingapp:flight_schedules")
        
    depart_schedule = Schedule.objects.filter(id=depart_id).first()
    return_schedule = Schedule.objects.filter(id=return_id).first() if return_id else None

    template = loader.get_template('booking/selected_scheduled.html')
    context = {
        'depart_schedule': depart_schedule,
        'return_schedule': return_schedule,
    }
    return HttpResponse(template.render(context, request))

@login_required
def confirm_schedule(request):
    if request.method == 'POST':
        depart_id = request.POST.get('depart_schedule')
        return_id = request.POST.get('return_schedule')

        if depart_id:
            request.session['confirm_depart_schedule'] = depart_id
        if return_id:
            request.session['confirm_return_schedule'] = return_id

        print("confirm_depart_schedule:", request.session.get('confirm_depart_schedule'))
        print("confirm_return_schedule:", request.session.get('confirm_return_schedule'))

        # Clear the selection session data
        request.session.pop('depart_schedule_id', None)
        request.session.pop('return_schedule_id', None)

        if depart_id:  
            return redirect('bookingapp:passenger_information')
        else:
            return redirect('bookingapp:flight_schedules')




@login_required
def passenger_information(request):
    activity_id = request.session.get('activity_id')
    print(f"=== PASSENGER_INFORMATION DEBUG ===")
    print(f"Activity ID: {activity_id}")
    adults = request.session.get('adults', 1)
    children = request.session.get('children', 0)
    infants = request.session.get('infants', 0)

    total_passengers = adults + children + infants
    if total_passengers == 0:
        return redirect('bookingapp:main')

    passenger_list = []
    adult_numbers = list(range(1, adults + 1))

    # Adults
    for i in adult_numbers:
        passenger_list.append({"number": i, "type": "Adult"})

    # Children
    for i in range(1, children + 1):
        passenger_list.append({"number": adults + i, "type": "Child"})

    # Infants
    for i in range(1, infants + 1):
        passenger_list.append({"number": adults + children + i, "type": "Infant", "adult_options": adult_numbers})

    request.session['passenger_count'] = total_passengers
    request.session['passenger_list'] = passenger_list  # 🔹 Save here

    student = None
    student_id = request.session.get("student_id")
    if student_id:
        student = Student.objects.filter(id=student_id).first()

    context = {
        'passenger_list': passenger_list,
        'student': student,
    }
    return render(request, 'booking/passenger.html', context)



@login_required
def save_passengers(request):
    if request.method != 'POST':
        return redirect('bookingapp:passenger_information')

    passenger_count = request.session.get('passenger_count', 1)
    passenger_list = request.session.get('passenger_list', [])
    passengers = []

    print("=== SAVE_PASSENGERS DEBUG ===")
    print(f"Passenger count: {passenger_count}")
    print(f"Passenger list from session: {passenger_list}")
    
    for i in range(passenger_count):
        # Assign a unique string ID to each passenger
        passenger_data = {
            "id": str(i),  # IDs: "0", "1", "2", "3"
            "gender": request.POST.get(f"gender_{i+1}", "").strip(),
            "first_name": request.POST.get(f"first_name_{i+1}", "").strip(),
            "mi": request.POST.get(f"mi_{i+1}", "").strip(),
            "last_name": request.POST.get(f"last_name_{i+1}", "").strip(),
            "dob_day": request.POST.get(f"dob_day_{i+1}", "").strip(),
            "dob_month": request.POST.get(f"dob_month_{i+1}", "").strip(),
            "dob_year": request.POST.get(f"dob_year_{i+1}", "").strip(),
            "passport": request.POST.get(f"passport_{i+1}", "").strip(),
            "nationality": request.POST.get(f"nationality_{i+1}", "").strip(),
            "passenger_type": passenger_list[i]["type"] if passenger_list else "Adult"
        }

        # For infants, link to the selected adult
        if passenger_data["passenger_type"].lower() == "infant":
            adult_selection = request.POST.get(f"infant_adult_{i+1}")
            # Convert the adult selection (1-based) to passenger ID (0-based)
            if adult_selection:
                adult_id = str(int(adult_selection) - 1)  # Convert 1-based to 0-based
                passenger_data["adult_id"] = adult_id
                print(f"Infant {i+1} linked to adult selection: {adult_selection} -> passenger ID: {adult_id}")
            else:
                # Default to first adult if no selection
                adult_id = "0"
                passenger_data["adult_id"] = adult_id
                print(f"Infant {i+1} defaulted to adult ID: {adult_id}")

        passengers.append(passenger_data)
        print(f"Passenger {i}: {passenger_data['first_name']} ({passenger_data['passenger_type']}) - ID: {passenger_data['id']} - Adult ID: {passenger_data.get('adult_id', 'N/A')}")

    # Contact info
    contact_info = {
        "first_name": request.POST.get("f_name_contact", "").strip(),
        "mi": request.POST.get("m_name_contact", "").strip(),
        "last_name": request.POST.get("l_name_contact", "").strip(),
        "number": request.POST.get("number_contact", "").strip(),
        "email": request.POST.get("email_contact", "").strip(),
    }

    request.session['passengers'] = passengers
    request.session['contact_info'] = contact_info
    request.session.modified = True

    print("=== FINAL PASSENGERS IN SESSION ===")
    for p in passengers:
        print(f"ID: {p['id']}, Name: {p['first_name']}, Type: {p['passenger_type']}, Adult ID: {p.get('adult_id', 'N/A')}")
    print("===================================")

    return redirect('bookingapp:add_ons')

@login_required
def add_ons(request):
    """Page where each passenger can select individual add-ons"""
    depart_schedule_id = request.session.get('confirm_depart_schedule')
    return_schedule_id = request.session.get('confirm_return_schedule')
    
    print(f"=== ADD_ONS DEBUG ===")
    print(f"Depart schedule ID: {depart_schedule_id}")
    print(f"Return schedule ID: {return_schedule_id}")
    
    if not depart_schedule_id:
        messages.error(request, "Please select flights first.")
        return redirect('bookingapp:flight_schedules')
    
    try:
        # Get the schedules
        depart_schedule = Schedule.objects.get(id=depart_schedule_id)
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        
        print(f"Passengers in session: {len(passengers)}")
        for p in passengers:
            print(f"  - {p['first_name']} {p['last_name']} (ID: {p['id']})")
        
        if not passengers:
            messages.error(request, "Please enter passenger information first.")
            return redirect('bookingapp:passenger_information')
        
        # Get airline from departure flight
        airline = depart_schedule.flight.airline
        print(f"Airline: {airline.name} ({airline.code})")
        
        # Get available add-ons for this airline (only optional ones, not included)
        available_addons = AddOn.objects.filter(
            airline=airline,
            included=False  # Only show optional add-ons that passengers can choose
        ).select_related('type').order_by('type__name', 'name')
        
        print(f"Available add-ons: {available_addons.count()}")
        
        # Group add-ons by type for better organization
        addons_by_type = {}
        for addon in available_addons:
            type_name = addon.type.name if addon.type else "Other"
            if type_name not in addons_by_type:
                addons_by_type[type_name] = []
            addons_by_type[type_name].append(addon)
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        print(f"Selected add-ons from session: {selected_addons}")
        
        context = {
            'depart_schedule': depart_schedule,
            'return_schedule': return_schedule,
            'passengers': passengers,
            'addons_by_type': addons_by_type,
            'selected_addons': selected_addons,
            'airline': airline,
        }
        
        return render(request, 'booking/add_ons.html', context)
        
    except Schedule.DoesNotExist:
        messages.error(request, "Selected schedule not found.")
        return redirect('bookingapp:flight_schedules')
    except Exception as e:
        print(f"Error in add_ons view: {e}")
        import traceback
        traceback.print_exc()
        messages.error(request, "Error loading add-ons.")
        return redirect('bookingapp:passenger_information')

# Add these new views to your existing views.py file
@login_required
def baggage_addon(request):
    """Page specifically for baggage add-ons"""
    print(f"=== BAGGAGE_ADDON DEBUG ===")
    print(f"GET parameters: {request.GET}")
    
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    print(f"Airline ID: {airline_id}")
    print(f"Schedule ID: {schedule_id}")
    print(f"Return Schedule ID: {return_schedule_id}")
    
    try:
        # Get airline
        airline = None
        if airline_id:
            try:
                airline = Airline.objects.get(id=airline_id)
                print(f"Found airline: {airline.name}")
            except Airline.DoesNotExist:
                print(f"Airline not found with ID: {airline_id}")
                messages.error(request, "Airline not found.")
                return redirect('bookingapp:add_ons')
        
        # Get schedules
        schedule = None
        if schedule_id:
            try:
                schedule = Schedule.objects.get(id=schedule_id)
                print(f"Found schedule: {schedule.flight.flight_number}")
            except Schedule.DoesNotExist:
                print(f"Schedule not found with ID: {schedule_id}")
                messages.error(request, "Schedule not found.")
                return redirect('bookingapp:add_ons')
        
        return_schedule = None
        if return_schedule_id:
            try:
                return_schedule = Schedule.objects.get(id=return_schedule_id)
                print(f"Found return schedule: {return_schedule.flight.flight_number}")
            except Schedule.DoesNotExist:
                print(f"Return schedule not found with ID: {return_schedule_id}")
                # Don't redirect for return schedule - it might be optional
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        print(f"Passengers in session: {len(passengers)}")
        
        if not passengers:
            messages.error(request, "Please enter passenger information first.")
            return redirect('bookingapp:passenger_information')
        
        # Get baggage-specific add-ons
        baggage_addons = AddOn.objects.filter(
            airline=airline,
            type__name__icontains='baggage',
            included=False
        ).select_related('type').order_by('price')
        
        print(f"Found {baggage_addons.count()} baggage add-ons")
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        print(f"Selected add-ons: {selected_addons}")
        
        # Prepare passenger data with their selected add-ons
        passenger_data = []
        for passenger in passengers:
            passenger_id = str(passenger['id'])
            passenger_addons = selected_addons.get(passenger_id, [])
            
            # Get addon objects for this passenger
            addon_objects = []
            for addon_id in passenger_addons:
                try:
                    addon = AddOn.objects.get(id=addon_id)
                    addon_objects.append(addon)
                except AddOn.DoesNotExist:
                    continue
            
            passenger_data.append({
                'id': passenger_id,
                'first_name': passenger['first_name'],
                'last_name': passenger['last_name'],
                'passenger_type': passenger['passenger_type'],
                'selected_addons': addon_objects
            })
        
        context = {
            'addons': baggage_addons,
            'airline': airline,
            'schedule': schedule,
            'return_schedule': return_schedule,
            'passengers': passenger_data,  # Use processed passenger data
            'selected_addons': selected_addons,
            'addon_type': 'Baggage',
            'depart_schedule': schedule,
        }
        
        return render(request, 'booking/addons/baggage.html', context)
        
    except Exception as e:
        print(f"Error loading baggage options: {e}")
        import traceback
        traceback.print_exc()
        messages.error(request, "Error loading baggage options.")
        return redirect('bookingapp:add_ons')

@login_required
def meals_addon(request):
    """Page specifically for meal add-ons"""
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    try:
        airline = Airline.objects.get(id=airline_id) if airline_id else None
        schedule = Schedule.objects.get(id=schedule_id) if schedule_id else None
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        
        # Get meal-specific add-ons
        meal_addons = AddOn.objects.filter(
            airline=airline,
            type__name__icontains='meal',
            included=False
        )
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        
        context = {
            'addons': meal_addons,
            'airline': airline,
            'schedule': schedule,
            'return_schedule': return_schedule,
            'passengers': passengers,
            'selected_addons': selected_addons,
            'addon_type': 'Meals',
            'depart_schedule': schedule,  # For template compatibility
        }
        return render(request, 'booking/addons/meals.html', context)
        
    except Exception as e:
        print(f"Error loading meal options: {e}")
        messages.error(request, "Error loading meal options.")
        return redirect('bookingapp:add_ons')

@login_required
def seat_selection_addon(request):
    """Redirect to main seat selection page"""
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    redirect_url = f"{reverse('bookingapp:select_seat')}?from_addons=true&airline_id={airline_id}&schedule_id={schedule_id}"
    if return_schedule_id:
        redirect_url += f"&return_schedule_id={return_schedule_id}"
        
    return redirect(redirect_url)

@login_required
def lounge_addon(request):
    """Page specifically for lounge access add-ons"""
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    try:
        airline = Airline.objects.get(id=airline_id) if airline_id else None
        schedule = Schedule.objects.get(id=schedule_id) if schedule_id else None
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        
        # Get lounge access add-ons
        lounge_addons = AddOn.objects.filter(
            airline=airline,
            type__name__icontains='lounge',
            included=False
        )
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        
        context = {
            'addons': lounge_addons,
            'airline': airline,
            'schedule': schedule,
            'return_schedule': return_schedule,
            'passengers': passengers,
            'selected_addons': selected_addons,
            'addon_type': 'Lounge Access',
            'depart_schedule': schedule,  # For template compatibility
        }
        return render(request, 'booking/addons/lounge.html', context)
        
    except Exception as e:
        print(f"Error loading lounge options: {e}")
        messages.error(request, "Error loading lounge options.")
        return redirect('bookingapp:add_ons')

@login_required
def insurance_addon(request):
    """Page specifically for travel insurance"""
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    try:
        airline = Airline.objects.get(id=airline_id) if airline_id else None
        schedule = Schedule.objects.get(id=schedule_id) if schedule_id else None
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        
        # Get insurance add-ons
        insurance_addons = AddOn.objects.filter(
            airline=airline,
            type__name__icontains='insurance',
            included=False
        )
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        
        context = {
            'addons': insurance_addons,
            'airline': airline,
            'schedule': schedule,
            'return_schedule': return_schedule,
            'passengers': passengers,
            'selected_addons': selected_addons,
            'addon_type': 'Travel Insurance',
            'depart_schedule': schedule,  # For template compatibility
        }
        return render(request, 'booking/addons/insurance.html', context)
        
    except Exception as e:
        print(f"Error loading insurance options: {e}")
        messages.error(request, "Error loading insurance options.")
        return redirect('bookingapp:add_ons')
@login_required
def wheelchair_addon(request):
    """Page specifically for wheelchair service add-ons"""
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    try:
        airline = Airline.objects.get(id=airline_id) if airline_id else None
        schedule = Schedule.objects.get(id=schedule_id) if schedule_id else None
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        
        # Get wheelchair service add-ons
        wheelchair_addons = AddOn.objects.filter(
            airline=airline,
            type__name__icontains='wheelchair',
            included=False
        )
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        
        context = {
            'addons': wheelchair_addons,
            'airline': airline,
            'schedule': schedule,
            'return_schedule': return_schedule,
            'passengers': passengers,
            'selected_addons': selected_addons,
            'addon_type': 'Wheelchair Service',
            'depart_schedule': schedule,
        }
        return render(request, 'booking/addons/wheelchair.html', context)
        
    except Exception as e:
        print(f"Error loading wheelchair options: {e}")
        messages.error(request, "Error loading wheelchair service options.")
        return redirect('bookingapp:add_ons')    

@login_required
def quick_addons(request):
    """Quick selection page for all add-ons"""
    airline_id = request.GET.get('airline_id')
    schedule_id = request.GET.get('schedule_id')
    return_schedule_id = request.GET.get('return_schedule_id')
    
    try:
        airline = Airline.objects.get(id=airline_id) if airline_id else None
        schedule = Schedule.objects.get(id=schedule_id) if schedule_id else None
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        
        # Get passengers from session
        passengers = request.session.get('passengers', [])
        
        # Get all available add-ons for this airline
        available_addons = AddOn.objects.filter(
            airline=airline,
            included=False
        ).select_related('type').order_by('type__name', 'name')
        
        # Group add-ons by type for better organization
        addons_by_type = {}
        for addon in available_addons:
            type_name = addon.type.name if addon.type else "Other"
            if type_name not in addons_by_type:
                addons_by_type[type_name] = []
            addons_by_type[type_name].append(addon)
        
        # Get previously selected add-ons from session
        selected_addons = request.session.get('selected_addons', {})
        
        context = {
            'depart_schedule': schedule,
            'return_schedule': return_schedule,
            'passengers': passengers,
            'addons_by_type': addons_by_type,
            'selected_addons': selected_addons,
            'airline': airline,
        }
        return render(request, 'booking/addons/quick_selection.html', context)
        
    except Exception as e:
        print(f"Error loading quick add-ons: {e}")
        messages.error(request, "Error loading add-ons.")
        return redirect('bookingapp:add_ons')

@login_required
def save_single_addon(request):
    """Save add-on selections from individual add-on pages - handles both selection and deselection"""
    if request.method != 'POST':
        return redirect('bookingapp:add_ons')
    
    try:
        passengers = request.session.get('passengers', [])
        selected_addons = request.session.get('selected_addons', {})
        
        # Process add-on selections for each passenger
        for passenger in passengers:
            passenger_id = str(passenger['id'])
            
            # Get selected add-ons for this passenger from the form
            # This will be an empty list if nothing is checked
            passenger_addons = request.POST.getlist(f'addons_{passenger_id}')
            
            # Update the selected add-ons for this passenger
            # This REPLACES the entire list, so unchecked items are removed
            selected_addons[passenger_id] = passenger_addons
        
        # Save to session
        request.session['selected_addons'] = selected_addons
        request.session.modified = True
        
        print(f"=== SAVED SINGLE ADD-ON DEBUG ===")
        print(f"Selected add-ons after save: {selected_addons}")
        
        messages.success(request, "Baggage selections updated successfully!")
        
        # Redirect back to the baggage page with the same parameters
        airline_id = request.POST.get('airline_id')
        schedule_id = request.POST.get('schedule_id')
        return_schedule_id = request.POST.get('return_schedule_id')
        
        redirect_url = f"{reverse('bookingapp:baggage_addon')}?airline_id={airline_id}&schedule_id={schedule_id}"
        if return_schedule_id:
            redirect_url += f"&return_schedule_id={return_schedule_id}"
            
        return redirect(redirect_url)
        
    except Exception as e:
        print(f"Error saving add-ons: {e}")
        messages.error(request, "Error saving baggage selections.")
        return redirect('bookingapp:add_ons')

@login_required
def remove_addon(request):
    """Remove a specific add-on from a passenger"""
    if request.method == 'POST':
        try:
            passenger_id = request.POST.get('passenger_id')
            addon_id = request.POST.get('addon_id')
            
            selected_addons = request.session.get('selected_addons', {})
            
            if passenger_id in selected_addons and addon_id in selected_addons[passenger_id]:
                selected_addons[passenger_id].remove(addon_id)
                request.session['selected_addons'] = selected_addons
                request.session.modified = True
                
                messages.success(request, "Add-on removed successfully!")
            
        except Exception as e:
            print(f"Error removing add-on: {e}")
            messages.error(request, "Error removing add-on.")
    
    return redirect('bookingapp:add_ons')    

@login_required
def save_add_ons(request):
    """Save add-on selections for each passenger"""
    if request.method != 'POST':
        return redirect('bookingapp:add_ons')
    
    try:
        passengers = request.session.get('passengers', [])
        selected_addons = {}
        
        # Process add-on selections for each passenger
        for passenger in passengers:
            passenger_id = str(passenger['id'])
            
            # Get selected add-ons for this passenger
            passenger_addons = request.POST.getlist(f'addons_{passenger_id}')
            
            # Store with passenger ID as key
            selected_addons[passenger_id] = passenger_addons
        
        # Save to session
        request.session['selected_addons'] = selected_addons
        request.session.modified = True
        
        print(f"=== SAVED ADD-ONS DEBUG ===")
        print(f"Selected add-ons: {selected_addons}")
        
        messages.success(request, "Add-ons selected successfully!")
        return redirect('bookingapp:select_seat')  # Now proceed to seat selection
        
    except Exception as e:
        print(f"Error saving add-ons: {e}")
        messages.error(request, "Error saving add-on selections.")
        return redirect('bookingapp:add_ons')

@login_required
def select_seat(request):
    depart_id = request.session.get('confirm_depart_schedule')
    return_id = request.session.get('confirm_return_schedule')

    if not depart_id:
        return redirect("bookingapp:flight_schedules")

    # Check if coming from add-ons page
    from_addons = request.GET.get('from_addons') == 'true'
    skip_addons = request.GET.get('skip_addons') == 'true'
    
    # If skipping add-ons, clear any selected add-ons
    if skip_addons:
        request.session['selected_addons'] = {}
        request.session.modified = True
        messages.info(request, "Add-ons skipped. You can add them later if needed.")

    depart_schedule = Schedule.objects.get(id=depart_id)
    return_schedule = Schedule.objects.filter(id=return_id).first() if return_id else None

    # Fetch all seats, not just available ones
    depart_seats = depart_schedule.seats.all().order_by("seat_number")
    return_seats = return_schedule.seats.all().order_by("seat_number") if return_schedule else None

    passengers = request.session.get("passengers", [])
    selected_seats = request.session.get("selected_seats", {})  # { passenger_id: {"depart": "A1", "return": "B1"} }

    context = {
        'depart_schedule': depart_schedule,
        'return_schedule': return_schedule,
        "depart_seats": depart_seats,
        "return_seats": return_seats,
        "passengers": passengers,
        "selected_seats": selected_seats,
        "from_addons": from_addons,  # Pass this to template to show different messaging
    }
    return render(request, "booking/select_seats.html", context)



from django.db import transaction
from django.http import JsonResponse

# @csrf_exempt
@login_required
def confirm_seat(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request."})

    seat_number = request.POST.get("seat_number")
    passenger_id = request.POST.get("passenger_id")
    trip = request.POST.get("trip")  # 'depart' or 'return'

    if not all([seat_number, passenger_id, trip]):
        return JsonResponse({"success": False, "message": "Missing required data."})

    # Initialize session storage
    selected_seats = request.session.get('selected_seats', {})
    passengers = request.session.get("passengers", [])

    # Find the selecting passenger to determine their type
    selecting_passenger = None
    for p in passengers:
        if str(p.get("id")) == passenger_id:
            selecting_passenger = p
            break

    # Assign seat to the passenger (adult or child)
    if passenger_id not in selected_seats:
        selected_seats[passenger_id] = {}
    selected_seats[passenger_id][trip] = seat_number

    # Handle infant seat assignment based on passenger type
    if selecting_passenger:
        passenger_type = selecting_passenger.get("passenger_type", "").lower()
        
        if passenger_type == "adult":
            # If an adult selects a seat, assign same seat to their infant(s)
            for p in passengers:
                p_type = p.get("passenger_type", "").lower()
                adult_id = str(p.get("adult_id", ""))
                pid = str(p.get("id"))

                if p_type == "infant" and adult_id == passenger_id:
                    if pid not in selected_seats:
                        selected_seats[pid] = {}
                    selected_seats[pid][trip] = seat_number
        elif passenger_type == "child":
            # If a child selects a seat, infants don't get assigned (infants only share with adults)
            pass  # Children don't have infants attached to them
        elif passenger_type == "infant":
            # If an infant somehow selects a seat directly, handle accordingly
            pass  # Infants shouldn't be selecting seats directly

    # Save back to session
    request.session['selected_seats'] = selected_seats
    request.session.modified = True

    # Debugging logs
    print("=== PASSENGER SEAT SELECTION ===")
    for p in passengers:
        pid = str(p.get("id"))
        seat_info = selected_seats.get(pid, {})
        print(f"{p.get('first_name')} ({p.get('passenger_type')}): {seat_info}")
    print("===============================")
    print("POST data:", request.POST)
    print("Session selected_seats:", selected_seats)

    return JsonResponse({
        "success": True,
        "seat": seat_number,
        "passenger_id": passenger_id,
        "trip": trip
    })


from decimal import Decimal

@login_required
def booking_summary(request):
    activity_id = request.session.get('activity_id')
    print(f"=== BOOKING_SUMMARY DEBUG ===")
    print(f"Activity ID: {activity_id}")
    
    depart_schedule_id = request.session.get('confirm_depart_schedule')
    return_schedule_id = request.session.get('confirm_return_schedule')

    if not depart_schedule_id and not return_schedule_id:
        return redirect("bookingapp:main")

    depart_schedule = Schedule.objects.filter(id=depart_schedule_id).first() if depart_schedule_id else None
    return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None

    passengers = request.session.get('passengers', [])
    seats = request.session.get('selected_seats', {})

    # Get selected add-ons and calculate total cost
    selected_addons = request.session.get('selected_addons', {})
    addons_details = {}
    addons_total = Decimal('0.00')
    
    # Calculate add-ons cost
    for passenger_id, addon_ids in selected_addons.items():
        addons_details[passenger_id] = []
        for addon_id in addon_ids:
            try:
                addon = AddOn.objects.get(id=addon_id)
                addons_details[passenger_id].append(addon)
                addons_total += addon.price
            except AddOn.DoesNotExist:
                continue

    # Get included add-ons for both schedules based on seat classes
    depart_included_addons = []
    return_included_addons = []
    
    if depart_schedule:
        # Get unique seat classes from selected seats for departure
        depart_seat_classes = set()
        for passenger in passengers:
            pid = str(passenger.get("id"))
            seat_info = seats.get(pid, {})
            depart_seat_number = seat_info.get("depart")
            
            if depart_seat_number and depart_schedule:
                try:
                    seat_obj = Seat.objects.get(
                        schedule=depart_schedule, 
                        seat_number=depart_seat_number
                    )
                    if seat_obj.seat_class:
                        depart_seat_classes.add(seat_obj.seat_class)
                except Seat.DoesNotExist:
                    pass
        
        # Get included add-ons for these seat classes
        if depart_seat_classes:
            depart_included_addons = AddOn.objects.filter(
                seat_class__in=depart_seat_classes,
                included=True  # This is the key filter for included add-ons
            ).select_related('type', 'seat_class', 'airline').distinct()
    
    if return_schedule:
        # Get unique seat classes from selected seats for return flight
        return_seat_classes = set()
        for passenger in passengers:
            pid = str(passenger.get("id"))
            seat_info = seats.get(pid, {})
            return_seat_number = seat_info.get("return")
            
            if return_seat_number and return_schedule:
                try:
                    seat_obj = Seat.objects.get(
                        schedule=return_schedule, 
                        seat_number=return_seat_number
                    )
                    if seat_obj.seat_class:
                        return_seat_classes.add(seat_obj.seat_class)
                except Seat.DoesNotExist:
                    pass
        
        # Get included add-ons for these seat classes
        if return_seat_classes:
            return_included_addons = AddOn.objects.filter(
                seat_class__in=return_seat_classes,
                included=True  # This is the key filter for included add-ons
            ).select_related('type', 'seat_class', 'airline').distinct()

    # DEBUG PRINT START
    print("=== INCLUDED ADD-ONS DEBUG ===")
    print("Departure seat classes:", [sc.name for sc in depart_seat_classes] if depart_schedule else "No departure schedule")
    print("Departure included add-ons:", [f"{addon.name} ({addon.seat_class.name})" for addon in depart_included_addons])
    print("Return seat classes:", [sc.name for sc in return_seat_classes] if return_schedule else "No return schedule")
    print("Return included add-ons:", [f"{addon.name} ({addon.seat_class.name})" for addon in return_included_addons])
    print("=========================================")
    # DEBUG PRINT END

    passenger_data = []
    for passenger in passengers:
        pid = str(passenger.get("id"))
        seat_info = seats.get(pid, {})  # fetch the seat info of this passenger

        # Only infants inherit adult seat if they haven't selected one
        if passenger["passenger_type"].lower() == "infant" and not seat_info:
            adult_id = passenger.get("adult_id")
            if adult_id:
                seat_info = seats.get(str(adult_id), {})

        # Get seat class for this passenger
        depart_seat_class = None
        return_seat_class = None
        
        if depart_schedule and seat_info.get("depart"):
            try:
                depart_seat_obj = Seat.objects.get(
                    schedule=depart_schedule, 
                    seat_number=seat_info.get("depart")
                )
                depart_seat_class = depart_seat_obj.seat_class
            except Seat.DoesNotExist:
                pass
        
        if return_schedule and seat_info.get("return"):
            try:
                return_seat_obj = Seat.objects.get(
                    schedule=return_schedule, 
                    seat_number=seat_info.get("return")
                )
                return_seat_class = return_seat_obj.seat_class
            except Seat.DoesNotExist:
                pass

        # Get included add-ons specific to this passenger's seat classes
        passenger_depart_included = []
        passenger_return_included = []
        
        if depart_seat_class:
            passenger_depart_included = AddOn.objects.filter(
                seat_class=depart_seat_class,
                included=True
            ).select_related('type', 'seat_class', 'airline')
        
        if return_seat_class:
            passenger_return_included = AddOn.objects.filter(
                seat_class=return_seat_class,
                included=True
            ).select_related('type', 'seat_class', 'airline')

        passenger_data.append({
            "full_name": f"{passenger['first_name']} {passenger.get('mi', '')} {passenger['last_name']}",
            "depart_seat": seat_info.get("depart", "Not selected"),
            "return_seat": seat_info.get("return", "Not selected"),
            "depart_seat_class": depart_seat_class,
            "return_seat_class": return_seat_class,
            "gender": passenger['gender'],
            "dob": f"{passenger['dob_month']}/{passenger['dob_day']}/{passenger['dob_year']}",
            "passport": passenger.get('passport', ''),
            "nationality": passenger.get('nationality', ''),
            'passenger_type': passenger.get('passenger_type', ''),
            'id': passenger['id'],  # Add passenger ID for add-ons display
            'selected_addons': addons_details.get(pid, []),  # Add selected add-ons for this passenger
            'depart_included_addons': passenger_depart_included,  # Included add-ons for departure
            'return_included_addons': passenger_return_included,  # Included add-ons for return
        })

    contact_info = request.session.get('contact_info', {})

    # **CORRECT PRICE CALCULATION - INCLUDING ADD-ONS**
    subtotal = Decimal('0.00')
    num_passengers = len(passengers)
    
    # Count passenger types
    adult_child_count = sum(1 for p in passengers if p.get('passenger_type', '').lower() in ['adult', 'child'])
    infant_count = sum(1 for p in passengers if p.get('passenger_type', '').lower() == 'infant')
    
    print(f"📊 Booking Summary Calculation:")
    print(f"  - Total passengers: {num_passengers}")
    print(f"  - Adults/Children: {adult_child_count}")
    print(f"  - Infants: {infant_count}")

    # Calculate price for each adult/child passenger using EXACT SAME LOGIC as BookingDetail.save()
    for passenger in passengers:
        passenger_type = passenger.get('passenger_type', '').lower()
        
        # Infants are FREE (PHP 0.00)
        if passenger_type == 'infant':
            continue
            
        passenger_price = Decimal('0.00')
        pid = str(passenger.get("id"))
        seat_info = seats.get(pid, {})
        
        # Departure flight price
        if depart_schedule:
            base_price = depart_schedule.flight.route.base_price
            
            # Get seat class multiplier for this passenger
            depart_seat_number = seat_info.get("depart")
            multiplier = Decimal('1.0')  # Default multiplier
            
            if depart_seat_number and depart_schedule:
                try:
                    seat_obj = Seat.objects.get(
                        schedule=depart_schedule, 
                        seat_number=depart_seat_number
                    )
                    if seat_obj.seat_class:
                        multiplier = seat_obj.seat_class.price_multiplier
                        print(f"  - {passenger['first_name']} depart seat class: {seat_obj.seat_class.name} (multiplier: {multiplier})")
                except Seat.DoesNotExist:
                    print(f"  - {passenger['first_name']} depart seat not found: {depart_seat_number}")
                    pass
            
            # Calculate days difference factor (same as model logic)
            days_diff = (depart_schedule.departure_time.date() - timezone.now().date()).days
            if days_diff >= 30:
                factor = Decimal("0.8")
            elif 7 <= days_diff <= 29:
                factor = Decimal("1.0")
            else:
                factor = Decimal("1.5")
            
            depart_price = base_price * multiplier * factor
            passenger_price += depart_price
            print(f"  - {passenger['first_name']} depart: {base_price} × {multiplier} × {factor} = {depart_price}")
        
        # Return flight price (if applicable)
        if return_schedule:
            return_base_price = return_schedule.flight.route.base_price
            
            # Get seat class multiplier for return flight
            return_seat_number = seat_info.get("return")
            return_multiplier = Decimal('1.0')  # Default multiplier
            
            if return_seat_number and return_schedule:
                try:
                    return_seat_obj = Seat.objects.get(
                        schedule=return_schedule, 
                        seat_number=return_seat_number
                    )
                    if return_seat_obj.seat_class:
                        return_multiplier = return_seat_obj.seat_class.price_multiplier
                        print(f"  - {passenger['first_name']} return seat class: {return_seat_obj.seat_class.name} (multiplier: {return_multiplier})")
                except Seat.DoesNotExist:
                    print(f"  - {passenger['first_name']} return seat not found: {return_seat_number}")
                    pass
            
            # Calculate days difference factor for return flight
            return_days_diff = (return_schedule.departure_time.date() - timezone.now().date()).days
            if return_days_diff >= 30:
                return_factor = Decimal("0.8")
            elif 7 <= return_days_diff <= 29:
                return_factor = Decimal("1.0")
            else:
                return_factor = Decimal("1.5")
            
            return_price = return_base_price * return_multiplier * return_factor
            passenger_price += return_price
            print(f"  - {passenger['first_name']} return: {return_base_price} × {return_multiplier} × {return_factor} = {return_price}")
        
        subtotal += passenger_price
        print(f"  - {passenger['first_name']} total passenger price: {passenger_price}")
    
    # Taxes and insurance (ALL passengers pay these, including infants)
    taxes = Decimal('20.00') * num_passengers  # PHP 20 per passenger
    insurance = Decimal('515.00') * num_passengers  # PHP 515 per passenger
    
    # Calculate totals INCLUDING ADD-ONS
    total_flight_price = subtotal + taxes + insurance
    grand_total = total_flight_price + addons_total

    print(f"💰 Final Calculation:")
    print(f"  - Subtotal (flight fares): {subtotal}")
    print(f"  - Taxes ({num_passengers} passengers × PHP 20): {taxes}")
    print(f"  - Insurance ({num_passengers} passengers × PHP 515): {insurance}")
    print(f"  - Flight Total: {total_flight_price}")
    print(f"  - Add-ons Total: {addons_total}")
    print(f"  - Grand Total: {grand_total}")

    template = loader.get_template("booking/booking_summary.html")
    context = {
        "depart_schedule": depart_schedule,
        "return_schedule": return_schedule,
        "passengers": passenger_data,
        "contact_info": contact_info,
        "num_passengers": num_passengers,
        "adult_child_count": adult_child_count,
        "infant_count": infant_count,
        "subtotal": subtotal,
        "taxes": taxes,
        "insurance": insurance,
        "total_flight_price": total_flight_price,
        "selected_addons": selected_addons,
        "addons_details": addons_details,
        "addons_total": addons_total,
        "grand_total": grand_total,
        "depart_included_addons": depart_included_addons,  # All included add-ons for departure
        "return_included_addons": return_included_addons,  # All included add-ons for return
    }

    return HttpResponse(template.render(context, request))


from django.db import transaction
from django.contrib import messages
from datetime import date

@login_required
@transaction.atomic
def confirm_booking(request):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect('bookingapp:booking_summary')
    
    passengers = request.session.get('passengers', [])
    seats = request.session.get('selected_seats', {})
    depart_schedule_id = request.session.get('confirm_depart_schedule')
    return_schedule_id = request.session.get('confirm_return_schedule')
    student_id = request.session.get('student_id')
    selected_addons = request.session.get('selected_addons', {})

    # Validate required data
    if not (depart_schedule_id and student_id and passengers):
        messages.error(request, "Booking data is missing. Please start over.")
        return redirect('bookingapp:main')

    try:
        depart_schedule = Schedule.objects.get(id=depart_schedule_id)
        return_schedule = Schedule.objects.filter(id=return_schedule_id).first() if return_schedule_id else None
        student = Student.objects.get(id=student_id)

        # 1️⃣ Create Booking
        booking = Booking.objects.create(
            student=student,
            trip_type=request.session.get('trip_type', 'one_way'),
            status="Pending"
        )

        print("=== CONFIRM_BOOKING DEBUG ===")
        print(f"Created booking: {booking.id}")
        print(f"Total passengers from session: {len(passengers)}")
        print("Selected add-ons:", selected_addons)
        print("=============================")

        # Store created PassengerInfo objects for infant linking
        passenger_objects = {}
        
        # First pass: Create all PassengerInfo objects
        for p in passengers:
            pid = str(p.get("id"))
            
            print(f"Creating PassengerInfo for {p.get('first_name', 'No Name')} (ID: {pid}, Type: {p.get('passenger_type')})")

            # Validate required passenger data
            if not all([p.get('first_name'), p.get('last_name'), p.get('dob_year'), p.get('dob_month'), p.get('dob_day')]):
                raise ValueError(f"Missing required data for passenger {pid}")

            # Create date of birth
            dob = date(
                int(p['dob_year']), 
                int(p['dob_month']), 
                int(p['dob_day'])
            )
            
            # Create PassengerInfo
            passenger_obj = PassengerInfo.objects.create(
                first_name=p['first_name'],
                middle_name=p.get('mi', ''),
                last_name=p['last_name'],
                gender=p.get('gender', ''),
                date_of_birth=dob,
                passport_number=p.get('passport', ''),
                email=student.email,
                phone=student.phone,
                passenger_type=p.get('passenger_type', 'Adult')
            )
            
            # Store for later reference
            passenger_objects[pid] = passenger_obj
            print(f"✅ Created PassengerInfo: {passenger_obj}")

        # Track which seats we've already processed to avoid double-booking
        processed_seats = {
            'depart': set(),
            'return': set()
        }

        # Store booking details for add-on linking
        booking_details_map = {}  # { passenger_id: { 'depart': booking_detail, 'return': booking_detail } }

        # Second pass: Link infants to adults and create BookingDetails
        for p in passengers:
            pid = str(p.get("id"))
            passenger_obj = passenger_objects[pid]
            seat_info = seats.get(pid, {})
            depart_seat_number = seat_info.get("depart")
            return_seat_number = seat_info.get("return")

            print(f"Processing bookings for {p.get('first_name', 'No Name')} (ID: {pid}, Type: {p.get('passenger_type')}): {seat_info}")

            # For infants, link to the adult passenger
            if p.get('passenger_type', '').lower() == 'infant' and p.get('adult_id'):
                adult_pid = p.get('adult_id')
                if adult_pid in passenger_objects:
                    adult_passenger = passenger_objects[adult_pid]
                    passenger_obj.linked_adult = adult_passenger
                    passenger_obj.save()
                    print(f"✅ Linked infant {p['first_name']} to adult {adult_passenger.first_name}")
                else:
                    print(f"⚠️ Could not find adult passenger with ID: {adult_pid}")

            # Initialize booking details map for this passenger
            booking_details_map[pid] = {}

            # Handle departure flight booking
            if depart_seat_number:
                try:
                    # Check if this seat has already been processed for this schedule
                    seat_key = f"{depart_schedule.id}_{depart_seat_number}"
                    if seat_key in processed_seats['depart']:
                        print(f"ℹ️ Seat {depart_seat_number} already processed for depart schedule, reusing...")
                        # Seat already processed, find the existing seat object
                        outbound_seat_obj = Seat.objects.get(
                            schedule=depart_schedule, 
                            seat_number=depart_seat_number
                        )
                    else:
                        # First time processing this seat, lock and mark as unavailable
                        outbound_seat_obj = Seat.objects.select_for_update().get(
                            schedule=depart_schedule, 
                            seat_number=depart_seat_number,
                            is_available=True
                        )
                        # Mark seat as unavailable immediately
                        outbound_seat_obj.is_available = False
                        outbound_seat_obj.save()
                        processed_seats['depart'].add(seat_key)
                        print(f"✅ Marked seat {depart_seat_number} as unavailable for depart")
                    
                    # Create booking detail for departure
                    depart_booking_detail = BookingDetail.objects.create(
                        booking=booking,
                        passenger=passenger_obj,
                        schedule=depart_schedule,
                        seat=outbound_seat_obj,
                        seat_class=outbound_seat_obj.seat_class,
                        price=0.00 if p.get('passenger_type', '').lower() == 'infant' else depart_schedule.price
                    )

                    # Store for add-on linking
                    booking_details_map[pid]['depart'] = depart_booking_detail

                    print(f"✅ Created depart booking for {p['first_name']} ({p.get('passenger_type')}) - Seat: {depart_seat_number}")        

                except Seat.DoesNotExist:
                    print(f"❌ Seat {depart_seat_number} not found or unavailable for depart schedule")
                    raise ValueError(f"Seat {depart_seat_number} is not available for departure flight")

            # Handle return flight booking
            if return_schedule and return_seat_number:
                try:
                    # Check if this seat has already been processed for this schedule
                    seat_key = f"{return_schedule.id}_{return_seat_number}"
                    if seat_key in processed_seats['return']:
                        print(f"ℹ️ Seat {return_seat_number} already processed for return schedule, reusing...")
                        # Seat already processed, find the existing seat object
                        return_seat_obj = Seat.objects.get(
                            schedule=return_schedule, 
                            seat_number=return_seat_number
                        )
                    else:
                        # First time processing this seat, lock and mark as unavailable
                        return_seat_obj = Seat.objects.select_for_update().get(
                            schedule=return_schedule, 
                            seat_number=return_seat_number,
                            is_available=True
                        )
                        # Mark seat as unavailable immediately
                        return_seat_obj.is_available = False
                        return_seat_obj.save()
                        processed_seats['return'].add(seat_key)
                        print(f"✅ Marked seat {return_seat_number} as unavailable for return")
                    
                    # Create booking detail for return
                    return_booking_detail = BookingDetail.objects.create(
                        booking=booking,
                        passenger=passenger_obj,
                        schedule=return_schedule,
                        seat=return_seat_obj,
                        seat_class=return_seat_obj.seat_class,
                        price=0.00 if p.get('passenger_type', '').lower() == 'infant' else return_schedule.price
                    )

                    # Store for add-on linking
                    booking_details_map[pid]['return'] = return_booking_detail

                    print(f"✅ Created return booking for {p['first_name']} ({p.get('passenger_type')}) - Seat: {return_seat_number}")
                    
                except Seat.DoesNotExist:
                    print(f"❌ Seat {return_seat_number} not found or unavailable for return schedule")
                    raise ValueError(f"Seat {return_seat_number} is not available for return flight")

        # 🔥 NEW: PROCESS ADD-ONS FOR EACH PASSENGER
        print("=== PROCESSING ADD-ONS ===")
        addons_processed = 0
        
        for passenger_id, addon_ids in selected_addons.items():
            print(f"Processing add-ons for passenger {passenger_id}: {addon_ids}")
            
            if passenger_id in booking_details_map:
                passenger_details = booking_details_map[passenger_id]
                
                for addon_id in addon_ids:
                    try:
                        addon = AddOn.objects.get(id=addon_id)
                        
                        # Link add-on to ALL booking details for this passenger
                        for flight_type, booking_detail in passenger_details.items():
                            # Create the relationship between booking detail and add-on
                            # This assumes you have a ManyToMany relationship between BookingDetail and AddOn
                            # If not, you might need to create an intermediate model
                            booking_detail.addons.add(addon)
                            
                            print(f"✅ Linked add-on '{addon.name}' ({addon.type}) to {flight_type} flight for passenger {passenger_id}")
                            addons_processed += 1
                            
                    except AddOn.DoesNotExist:
                        print(f"⚠️ Add-on with ID {addon_id} not found - skipping")
                        continue
        
        print(f"✅ Successfully processed {addons_processed} add-on links")

        # DEBUG: Count actual booking details created
        total_booking_details = booking.details.count()
        unique_passengers_in_booking = booking.details.values('passenger').distinct().count()
        
        print(f"📊 BOOKING CREATION SUMMARY:")
        print(f"  - Total BookingDetail objects created: {total_booking_details}")
        print(f"  - Unique passengers in booking: {unique_passengers_in_booking}")
        print(f"  - Expected passengers: {len(passengers)}")
        
        if total_booking_details > len(passengers):
            print(f"⚠️ WARNING: More BookingDetail objects ({total_booking_details}) than passengers ({len(passengers)})")
            print(f"   This indicates double-counting in round-trip bookings")

        print("✅ Booking created successfully! ID:", booking.id)
        
        # CRITICAL FIX: Save booking ID to session and ensure it persists
        request.session['current_booking_id'] = booking.id
        request.session.modified = True  # Force session save
        
        print(f"✅ Session updated - current_booking_id: {request.session.get('current_booking_id')}")
        
        # Debug session state before redirect
        print("=== SESSION STATE BEFORE REDIRECT ===")
        for key, value in request.session.items():
            print(f"{key}: {value}")
        print("====================================")

    except Exception as e:
        print(f"❌ Unexpected error in confirm_booking: {str(e)}")
        messages.error(request, "An unexpected error occurred. Please try again.")
        return redirect('bookingapp:booking_summary')

    return redirect('bookingapp:payment_method')

from decimal import Decimal
from django.contrib import messages



@login_required
def payment_method(request):
    booking_id = request.session.get('current_booking_id')
    activity_id = request.session.get('activity_id')
    
    print(f"=== PAYMENT_METHOD DEBUG ===")
    print(f"Booking ID from session: {booking_id}")
    print(f"Activity ID from session: {activity_id}")

    try:
        booking = Booking.objects.get(id=booking_id)
        
        print(f"✅ Found booking: {booking.id}")

        # **ENHANCED DETAILED CALCULATION INCLUDING ADD-ONS**
        print("=== ENHANCED PRICE CALCULATION BREAKDOWN ===")
        
        # Initialize detailed breakdown
        calculation_breakdown = {
            'flight_fares': {
                'departure': Decimal('0.00'),
                'return': Decimal('0.00'),
                'total': Decimal('0.00')
            },
            'passengers': {
                'adults': 0,
                'children': 0,
                'infants': 0,
                'total': 0
            },
            'taxes_per_passenger': Decimal('20.00'),
            'insurance_per_passenger': Decimal('515.00'),
            'totals': {
                'subtotal': Decimal('0.00'),
                'taxes': Decimal('0.00'),
                'insurance': Decimal('0.00'),
                'grand_total': Decimal('0.00')
            }
        }
        
        # FIX: Get UNIQUE passengers to avoid double counting
        unique_passengers = set()
        passenger_types = {
            'adults': 0,
            'children': 0, 
            'infants': 0
        }
        
        # Calculate flight fares for each booking detail
        for detail in booking.details.all():
            passenger = detail.passenger
            passenger_type = passenger.passenger_type.lower()
            
            # Count UNIQUE passengers only once
            if passenger.id not in unique_passengers:
                unique_passengers.add(passenger.id)
                
                # Count passenger types
                if passenger_type == 'adult':
                    passenger_types['adults'] += 1
                elif passenger_type == 'child':
                    passenger_types['children'] += 1
                elif passenger_type == 'infant':
                    passenger_types['infants'] += 1
            
            # Add to flight fares (infants are free)
            if passenger_type != 'infant':
                calculation_breakdown['flight_fares']['total'] += detail.price
                
                # Determine if this is departure or return flight
                # Simple heuristic: first occurrence is departure, subsequent are return
                if calculation_breakdown['flight_fares']['departure'] == Decimal('0.00'):
                    calculation_breakdown['flight_fares']['departure'] += detail.price
                else:
                    calculation_breakdown['flight_fares']['return'] += detail.price
        
        # Update passenger counts with unique values
        calculation_breakdown['passengers']['adults'] = passenger_types['adults']
        calculation_breakdown['passengers']['children'] = passenger_types['children']
        calculation_breakdown['passengers']['infants'] = passenger_types['infants']
        calculation_breakdown['passengers']['total'] = len(unique_passengers)
        
        print(f"📊 PASSENGER COUNT DEBUG:")
        print(f"  - Unique passengers: {len(unique_passengers)}")
        print(f"  - Adults: {passenger_types['adults']}")
        print(f"  - Children: {passenger_types['children']}")
        print(f"  - Infants: {passenger_types['infants']}")
        
        # Calculate taxes and insurance (ALL passengers pay these)
        calculation_breakdown['totals']['taxes'] = (
            calculation_breakdown['taxes_per_passenger'] * calculation_breakdown['passengers']['total']
        )
        calculation_breakdown['totals']['insurance'] = (
            calculation_breakdown['insurance_per_passenger'] * calculation_breakdown['passengers']['total']
        )
        
        # Calculate subtotal and grand total
        calculation_breakdown['totals']['subtotal'] = calculation_breakdown['flight_fares']['total']
        
        # **ADD ADD-ONS TO THE CALCULATION**
        selected_addons = request.session.get('selected_addons', {})
        addons_total = Decimal('0.00')
        
        for passenger_id, addon_ids in selected_addons.items():
            for addon_id in addon_ids:
                try:
                    addon = AddOn.objects.get(id=addon_id)
                    addons_total += addon.price
                except AddOn.DoesNotExist:
                    continue
        
        # Use the calculated totals INCLUDING ADD-ONS
        calculation_breakdown['totals']['addons'] = addons_total
        calculation_breakdown['totals']['grand_total'] = (
            calculation_breakdown['totals']['subtotal'] + 
            calculation_breakdown['totals']['taxes'] + 
            calculation_breakdown['totals']['insurance'] +
            calculation_breakdown['totals']['addons']
        )

        total_amount = calculation_breakdown['totals']['grand_total']

        print(f"💰 FINAL PAYMENT CALCULATION:")
        print(f"  - Flight fares: {calculation_breakdown['flight_fares']['total']}")
        print(f"  - Taxes ({calculation_breakdown['passengers']['total']} passengers): {calculation_breakdown['totals']['taxes']}")
        print(f"  - Insurance ({calculation_breakdown['passengers']['total']} passengers): {calculation_breakdown['totals']['insurance']}")
        print(f"  - Add-ons: {addons_total}")
        print(f"  - Grand Total: {total_amount}")

        if request.method == "POST":
            method = request.POST.get("payment_method")
            if method:
                try:
                    with transaction.atomic():
                        # Create Payment
                        payment = Payment.objects.create(
                            booking=booking,
                            amount=total_amount,
                            method=method,
                            status="Completed",
                            transaction_id=f"MOCK{booking.id:05d}"
                        )

                        # Mark booking as Paid
                        booking.status = "Paid"
                        booking.save()

                        # FIX: Get unique seat IDs and verify they're properly reserved
                        seat_ids = list(booking.details
                                       .filter(seat__isnull=False)
                                       .values_list('seat_id', flat=True)
                                       .distinct())
                        
                        if seat_ids:
                            # Just verify seats are properly marked as unavailable
                            unavailable_seats = Seat.objects.filter(
                                id__in=seat_ids, 
                                is_available=True
                            )
                            if unavailable_seats.exists():
                                unavailable_seats.update(is_available=False)
                                print(f"⚠️ Fixed {unavailable_seats.count()} seats that were not properly reserved")

                        # IMPORTANT: Don't clear current_booking_id and activity_id yet!
                        keys_to_clear = [
                            "passengers", "selected_seats", "confirm_depart_schedule",
                            "confirm_return_schedule", "trip_type",
                            "origin", "destination", "departure_date", "return_date",
                            "passenger_count", "contact_info", "adults", "children", "infants",
                            "selected_addons"  # Clear add-ons too
                        ]
                        
                        student_id = request.session.get('student_id')
                        for key in keys_to_clear:
                            request.session.pop(key, None)
                        
                        # Keep these for payment_success
                        request.session['student_id'] = student_id
                        # current_booking_id and activity_id remain in session
                        request.session.modified = True

                        print(f"✅ Payment completed. Keeping booking_id ({booking_id}) and activity_id for payment_success")
                        messages.success(request, "Payment completed successfully!")

                        return redirect("bookingapp:payment_success")

                except Exception as e:
                    print(f"❌ Payment error: {str(e)}")
                    messages.error(request, f"Payment failed: {str(e)}")
                    return redirect("bookingapp:payment_method")
        
        # Render payment page with enhanced breakdown data INCLUDING ADD-ONS
        return render(request, "booking/payment.html", {
            "booking": booking,
            "payment_methods": Payment.PAYMENT_METHODS,
            "total_amount": total_amount,
            "calculation_breakdown": calculation_breakdown,  # Pass breakdown to template
            "subtotal": calculation_breakdown['totals']['subtotal'],
            "taxes": calculation_breakdown['totals']['taxes'],
            "insurance": calculation_breakdown['totals']['insurance'],
            "addons_total": addons_total,
            "num_passengers": calculation_breakdown['passengers']['total'],  # Pass correct passenger count
        })

    except Booking.DoesNotExist:
        messages.error(request, "Booking not found.")
        return redirect("bookingapp:main")



@login_required
def payment_success(request):
    booking_id = request.session.get('current_booking_id')
    activity_id = request.session.get('activity_id')
    
    print(f"=== PAYMENT_SUCCESS DEBUG ===")
    print(f"Booking ID from session: {booking_id}")
    print(f"Activity ID from session: {activity_id}")
    print(f"Practice Booking: {request.session.get('is_practice_booking')}")

    # Check if this is a practice booking
    if request.session.get('is_practice_booking'):
        return save_practice_booking(request)
    
    if booking_id and activity_id:
        try:
            booking = Booking.objects.get(id=booking_id)
            activity = Activity.objects.get(id=activity_id)
            student = Student.objects.get(id=request.session.get('student_id'))
            
            print(f"✅ Database objects found:")
            print(f"   - Booking: {booking.id} (Status: {booking.status})")
            print(f"   - Activity: {activity.title} (ID: {activity.id})")
            print(f"   - Student: {student.first_name} {student.last_name} (ID: {student.id})")
            
            # Check if submission already exists
            existing_submission = ActivitySubmission.objects.filter(
                activity=activity, 
                student=student
            ).first()
            
            if existing_submission:
                print(f"⚠️ Submission already exists: {existing_submission.id}")
                messages.info(request, f"You have already submitted this activity.")
            else:
                print("🆕 No existing submission found - creating new submission")
                
                try:
                    # Calculate score before creating submission
                    score = calculate_activity_score(booking, activity)
                    print(f"📊 Calculated score: {score}/{activity.total_points}")
                    
                    # FIX: Create activity submission WITHOUT required_max_price
                    submission_data = {
                        'activity': activity,
                        'student': student,
                        'booking': booking,
                        'status': 'submitted',
                        'required_trip_type': activity.required_trip_type,
                        'required_travel_class': activity.required_travel_class,
                        'required_passengers': activity.required_passengers,
                        'required_children': activity.required_children,
                        'required_infants': activity.required_infants,
                        'require_passenger_details': activity.require_passenger_details,
                        # REMOVED: required_max_price since it's no longer in the model
                        'score': score,
                        'submitted_at': timezone.now()
                    }
                    
                    # Create the submission
                    submission = ActivitySubmission.objects.create(**submission_data)
                    
                    # Calculate add-on scores
                    addon_score, max_addon_points = submission.calculate_addon_score()
                    submission.addon_score = addon_score
                    submission.max_addon_points = max_addon_points
                    submission.save()
                    
                    print(f"✅ SUCCESS: Created submission: {submission.id}")
                    print(f"   Submission details - Activity: {submission.activity.title}, Student: {submission.student.first_name}, Booking: {submission.booking.id}, Score: {submission.score}")
                    print(f"   Add-on Score: {submission.addon_score}/{submission.max_addon_points}")
                    messages.success(request, f"Activity '{activity.title}' submitted successfully! Score: {score}/{activity.total_points}")
                    
                except Exception as create_error:
                    print(f"❌ ERROR creating submission: {create_error}")
                    import traceback
                    traceback.print_exc()
                    
                    # Create minimal submission without score if creation fails
                    minimal_submission_data = {
                        'activity': activity,
                        'student': student,
                        'booking': booking,
                        'status': 'submitted',
                        'required_trip_type': activity.required_trip_type,
                        'required_travel_class': activity.required_travel_class,
                        'required_passengers': activity.required_passengers,
                        'required_children': activity.required_children,
                        'required_infants': activity.required_infants,
                        'require_passenger_details': activity.require_passenger_details,
                        'score': Decimal('0.0'),
                        'submitted_at': timezone.now()
                    }
                    submission = ActivitySubmission.objects.create(**minimal_submission_data)
                    messages.warning(request, f"Activity submitted but scoring failed. Please contact instructor.")
            
            # NOW clear the session data after successful submission creation
            request.session.pop('activity_id', None)
            request.session.pop('activity_requirements', None)
            request.session.pop('current_booking_id', None)
            request.session.modified = True
            print("🧹 Cleared activity and booking data from session")
            
        except Exception as e:
            print(f"❌ Error in payment_success: {e}")
            import traceback
            traceback.print_exc()
            messages.error(request, "Error processing submission. Please contact support.")

    else:
        print("❌ Missing required session data:")
        if not booking_id:
            print("   - No booking_id in session")
        if not activity_id:
            print("   - No activity_id in session")

    # Keep student login only
    student_id = request.session.get('student_id')
    print(f"🔑 Student ID: {student_id}")

    return render(request, "booking/payment_success.html")


@login_required
def book_again(request):
    # Clear all booking-related session data but keep student login
    keys_to_clear = [
        "passengers",
        "selected_seats",
        "confirm_depart_schedule",
        "confirm_return_schedule",
        "current_booking_id",
        "trip_type",
        "origin",
        "destination",
        "departure_date",
        "return_date",
        "passenger_count",
        "contact_info",
        "selected_addons"  # Clear add-ons too
    ]
    student_id = request.session.get('student_id')
    for key in keys_to_clear:
        request.session.pop(key, None)
    request.session['student_id'] = student_id

    return redirect('bookingapp:main')






@login_required
def print_booking_info(request):
    # Get selected schedule
    schedule_id = request.session.get('confirm_schedule')
    schedule = None
    if schedule_id:
        schedule = Schedule.objects.filter(id=schedule_id).first()

    # Get passengers, seats, and contact info
    passengers = request.session.get('passengers', [])
    seats = request.session.get('seats', {})
    contact_info = request.session.get('contact_info', {}) 

    print("===== BOOKING INFO =====")
    if schedule:
        print(f"Selected Schedule: {schedule.flight.route.origin_airport} -> {schedule.flight.route.destination_airport}")
        print(f"Departure: {schedule.departure_time}")
        print(f"Flight: {schedule.flight}")
    else:
        print("No schedule selected.")

    print("\n--- Passengers ---")
    for idx, passenger in enumerate(passengers):
        seat = seats.get(str(idx), "Not selected")
        print(f"{idx+1}. {passenger['first_name']} {passenger['mi']} {passenger['last_name']} | Seat: {seat} | Gender: {passenger['gender']} | DOB: {passenger['dob_month']}/{passenger['dob_day']}/{passenger['dob_year']} | Passport: {passenger['passport']} | Nationality: {passenger['nationality']}")

    print("\n--- Booker / Contact Info ---")
    if contact_info:
        print(f"{contact_info.get('first_name', '')} {contact_info.get('mi', '')} {contact_info.get('last_name', '')}")
        print(f"Email: {contact_info.get('email', '')}")
        print(f"Phone: {contact_info.get('number', '')}")
    else:
        print("No contact info.")

    print("=========================\n")

    return HttpResponse("Booking info printed to terminal.")





from django.contrib import messages
from django.shortcuts import render, redirect
from flightapp.models import Student
from django.contrib.auth.hashers import make_password

@redirect_if_logged_in
def register_view(request):
    if request.method == "POST":
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # Required fields
        if not all([first_name, last_name, email, password, confirm_password]):
            messages.error(request, "All fields are required.")
            return redirect('bookingapp:register')

        # Password match
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect('bookingapp:register')

        # Check email uniqueness
        if Student.objects.filter(email=email).exists():
            messages.error(request, "Email already exists. Please use a different email.")
            return redirect('bookingapp:register')

        try:
            # Generate student number
            student_count = Student.objects.count()
            student_number = f"STU{student_count + 1:04d}"

            # Create student with hashed password
            student = Student.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone if phone else None,  # Handle optional phone
                password=make_password(password),  # Hash the password
                student_number=student_number
            )

            messages.success(request, "Registration successful! Please login.")
            return redirect('bookingapp:login')

        except Exception as e:
            messages.error(request, "An error occurred during registration. Please try again.")
            print(f"Registration error: {e}")

        messages.success(request, "Registration successful! Please login.")
        return redirect('bookingapp:login')
    
    template = loader.get_template("booking/auth/register.html")

    context = {

    }

    return HttpResponse(template.render(context, request))

from django.contrib.auth.hashers import check_password

@redirect_if_logged_in
def login_view(request):
    if request.method == "POST":
        email = request.POST.get('email').strip()
        password = request.POST.get('password')

        # Basic validation
        if not email or not password:
            messages.error(request, "Email and password are required.")
            return redirect('bookingapp:login')

        try:
            student = Student.objects.get(email=email)
            if check_password(password, student.password):
                request.session['student_id'] = student.id
                messages.success(request, f"Welcome {student.first_name}!")
                # Redirect to student dashboard
                return redirect('bookingapp:student_home')
            else:
                messages.error(request, "Incorrect password.")
        except Student.DoesNotExist:
            messages.error(request, "Email not registered.")
        except Exception as e:
            messages.error(request, "An error occurred during login. Please try again.")
            print(f"Login error: {e}")    

    template = loader.get_template("booking/auth/login.html")
    context = {}
    return HttpResponse(template.render(context, request))


def logout_view(request):
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect('bookingapp:login')




# Add to bookingapp/views.py
@login_required
def debug_student_activities(request):
    """Debug view to check student's available activities"""
    student_id = request.session.get('student_id')
    if not student_id:
        return redirect('bookingapp:login')
    
    student = Student.objects.get(id=student_id)
    
    print("=== STUDENT ACTIVITIES DEBUG ===")
    print(f"Student: {student.first_name} {student.last_name} (ID: {student.id})")
    
    # Get enrolled sections
    enrolled_sections = SectionEnrollment.objects.filter(
        student=student, 
        is_active=True
    ).select_related('section')
    
    print("Enrolled sections:")
    for enrollment in enrolled_sections:
        print(f"  - {enrollment.section.section_code}: {enrollment.section.section_name}")
    
    # Get active activities
    activities = Activity.objects.filter(
        section__in=[enrollment.section for enrollment in enrolled_sections],
        is_code_active=True,
        status='published'
    )
    
    print("Available activities:")
    for activity in activities:
        print(f"  - {activity.id}: {activity.title} (Code: {activity.activity_code})")
        print(f"    Section: {activity.section.section_code}")
        print(f"    Status: {activity.status}, Active: {activity.is_code_active}")
    
    return HttpResponse("Check console for debug output")

def get_booking_details(booking):
    """Get detailed information about what was actually booked"""
    print(f"=== GET_BOOKING_DETAILS DEBUG ===")
    print(f"Booking ID: {booking.id}")
    
    booking_details = booking.details.all().select_related(
        'passenger', 'schedule', 'schedule__flight', 'schedule__flight__route'
    )
    
    print(f"Found {booking_details.count()} booking details")
    
    details = {
        'passengers': [],
        'flights': {},
        'total_cost': 0,
        'seat_classes_used': set()
    }
    
    # Group by flight schedule
    flight_groups = {}
    for detail in booking_details:
        print(f"Processing detail: {detail.id} - Passenger: {detail.passenger.first_name}")
        schedule_id = detail.schedule.id
        if schedule_id not in flight_groups:
            flight_groups[schedule_id] = {
                'schedule': detail.schedule,
                'passengers': [],
                'total_seats': 0
            }
        
        flight_groups[schedule_id]['passengers'].append({
            'passenger': detail.passenger,
            'seat_class': detail.seat_class,
            'seat_number': detail.seat.seat_number if detail.seat else 'Not assigned',
            'price': detail.price
        })
        flight_groups[schedule_id]['total_seats'] += 1
        
        # Add to overall details
        details['seat_classes_used'].add(detail.seat_class)
        if detail.passenger.passenger_type.lower() != 'infant':
            details['total_cost'] += float(detail.price)
    
    details['flights'] = flight_groups
    details['seat_classes_used'] = list(details['seat_classes_used'])
    
    print(f"Flight groups: {len(flight_groups)}")
    
    # Get all passengers with their details
    for detail in booking_details:
        passenger_info = {
            'name': f"{detail.passenger.first_name} {detail.passenger.last_name}",
            'type': detail.passenger.passenger_type,
            'date_of_birth': detail.passenger.date_of_birth,
            'gender': detail.passenger.gender,
            'passport': detail.passenger.passport_number,
            'nationality': detail.passenger.nationality,
            'flights': []
        }
        
        # Add flight details for this passenger
        for flight_group in flight_groups.values():
            for passenger in flight_group['passengers']:
                if passenger['passenger'].id == detail.passenger.id:
                    passenger_info['flights'].append({
                        'route': f"{flight_group['schedule'].flight.route.origin_airport.code} → {flight_group['schedule'].flight.route.destination_airport.code}",
                        'date': flight_group['schedule'].departure_time.date(),
                        'seat_class': passenger['seat_class'],
                        'seat_number': passenger['seat_number'],
                        'price': passenger['price']
                    })
        
        # Only add each passenger once
        if not any(p['name'] == passenger_info['name'] for p in details['passengers']):
            details['passengers'].append(passenger_info)
    
    print(f"Final passengers count: {len(details['passengers'])}")
    print(f"Final flights count: {len(details['flights'])}")
    print("=== END GET_BOOKING_DETAILS ===")
    
    return details



# Add to bookingapp/views.py

# @login_required
# def submission_detail(request, submission_id):
#     """Show detailed comparison between activity requirements and student submission"""
#     student_id = request.session.get('student_id')
    
#     if not student_id:
#         return redirect('bookingapp:login')
    
#     try:
#         print(f"=== ACCESSING SUBMISSION DETAIL ===")
#         print(f"Submission ID: {submission_id}")
#         print(f"Student ID: {student_id}")
        
#         student = Student.objects.get(id=student_id)
#         submission = get_object_or_404(ActivitySubmission, id=submission_id, student=student)
        
#         print(f"Found submission: {submission.id}")
#         print(f"Activity: {submission.activity.title}")
#         print(f"Booking: {submission.booking.id if submission.booking else 'No booking'}")
        
#         activity = submission.activity
#         booking = submission.booking
        
#         # Get comparison data
#         comparison_data = get_submission_comparison(submission, activity, booking)
#         booking_details = get_booking_details(booking)
        
#         print(f"Comparison data: {comparison_data is not None}")
#         print(f"Booking details: {booking_details is not None}")
        
#         # Use render instead of loader.get_template for better error handling
#         return render(request, 'booking/student/submission_detail.html', {
#             'submission': submission,
#             'activity': activity,
#             'booking': booking,
#             'comparison': comparison_data,
#             'booking_details': booking_details,
#             'student': student,
#         })
        
#     except ActivitySubmission.DoesNotExist:
#         print(f"Submission {submission_id} not found for student {student_id}")
#         messages.error(request, "Submission not found.")
#         return redirect('bookingapp:student_activities')
#     except Exception as e:
#         print(f"Error in submission_detail: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         messages.error(request, f"Error loading submission: {str(e)}")
#         return redirect('bookingapp:student_activities')
    



def get_submission_comparison(submission, activity, booking):
    """Generate detailed comparison between requirements and submission"""
    
    # Get booking details
    booking_details = booking.details.all()
    booking_info = get_booking_details(booking)
    
    # Count passenger types in booking
    adult_count = 0
    child_count = 0
    infant_count = 0
    total_price = booking_info['total_cost']
    
    for passenger in booking_info['passengers']:
        passenger_type = passenger['type'].lower()
        if passenger_type == 'adult':
            adult_count += 1
        elif passenger_type == 'child':
            child_count += 1
        elif passenger_type == 'infant':
            infant_count += 1
    
    # Check travel class compliance
    has_correct_class = any(
        seat_class.lower() == activity.required_travel_class.lower() 
        for seat_class in booking_info['seat_classes_used']
    )
    
    # Get actual seat classes used
    actual_classes = ", ".join([cls.title() for cls in booking_info['seat_classes_used']])
    
    # Calculate deductions with specific details
    deductions = []
    recommendations = []
    
    # Passenger count deductions
    if adult_count != activity.required_passengers:
        deductions.append({
            'category': 'Passenger Count',
            'issue': f'Adults: Required {activity.required_passengers}, You booked {adult_count}',
            'details': f'You booked {adult_count} adult(s) but the activity required {activity.required_passengers} adult(s)',
            'points_lost': 'Up to 15%',
            'type': 'passenger_count'
        })
        recommendations.append(f"Book exactly {activity.required_passengers} adult passenger(s) for full points")
    
    if child_count != activity.required_children:
        deductions.append({
            'category': 'Passenger Count', 
            'issue': f'Children: Required {activity.required_children}, You booked {child_count}',
            'details': f'You booked {child_count} child(ren) but the activity required {activity.required_children} child(ren)',
            'points_lost': 'Up to 9%',
            'type': 'passenger_count'
        })
        recommendations.append(f"Book exactly {activity.required_children} child passenger(s) for full points")
    
    if infant_count != activity.required_infants:
        deductions.append({
            'category': 'Passenger Count',
            'issue': f'Infants: Required {activity.required_infants}, You booked {infant_count}',
            'details': f'You booked {infant_count} infant(s) but the activity required {activity.required_infants} infant(s)',
            'points_lost': 'Up to 6%',
            'type': 'passenger_count'
        })
        recommendations.append(f"Book exactly {activity.required_infants} infant passenger(s) for full points")
    
    # Price compliance
    # if activity.required_max_price and total_price > float(activity.required_max_price):
    #     overage_amount = total_price - float(activity.required_max_price)
    #     overage_percentage = (overage_amount / float(activity.required_max_price)) * 100
    #     deductions.append({
    #         'category': 'Budget',
    #         'issue': f'Budget exceeded by ${overage_amount:.2f}',
    #         'details': f'Your booking cost ${total_price:.2f} but the maximum allowed was ${activity.required_max_price} (${overage_amount:.2f} over budget)',
    #         'points_lost': 'Up to 20%',
    #         'type': 'budget'
    #     })
    #     recommendations.append(f"Look for cheaper flight options or different travel dates to stay within ${activity.required_max_price} budget")
    
    # Travel class compliance
    if not has_correct_class:
        deductions.append({
            'category': 'Travel Class',
            'issue': f'Required {activity.required_travel_class.title()}, You booked {actual_classes}',
            'details': f'The activity required {activity.required_travel_class.title()} class, but you booked {actual_classes}',
            'points_lost': 'Up to 10%',
            'type': 'travel_class'
        })
        recommendations.append(f"Select {activity.required_travel_class.title()} class when booking flights for this activity")
    
    # Trip type compliance
    if booking.trip_type != activity.required_trip_type:
        deductions.append({
            'category': 'Trip Type',
            'issue': f'Required {activity.required_trip_type.title()}, You booked {booking.trip_type.title()}',
            'details': f'The activity required a {activity.required_trip_type.title()} trip, but you booked a {booking.trip_type.title()} trip',
            'points_lost': 'Up to 10%',
            'type': 'trip_type'
        })
        recommendations.append(f"Select {activity.required_trip_type.title()} trip type when searching for flights")
    
    # Check if origin/destination match
    if hasattr(activity, 'required_origin') and activity.required_origin:
        # Get first flight's origin
        first_flight = next(iter(booking_info['flights'].values()), None)
        if first_flight:
            booked_origin = first_flight['schedule'].flight.route.origin_airport.code
            if booked_origin != activity.required_origin:
                deductions.append({
                    'category': 'Flight Route',
                    'issue': f'Origin: Required {activity.required_origin}, You booked from {booked_origin}',
                    'details': f'The activity required flights from {activity.required_origin}, but you booked from {booked_origin}',
                    'points_lost': 'Up to 10%',
                    'type': 'route'
                })
                recommendations.append(f"Start your flight search from {activity.required_origin} airport")
    
    if hasattr(activity, 'required_destination') and activity.required_destination:
        # Get first flight's destination
        first_flight = next(iter(booking_info['flights'].values()), None)
        if first_flight:
            booked_destination = first_flight['schedule'].flight.route.destination_airport.code
            if booked_destination != activity.required_destination:
                deductions.append({
                    'category': 'Flight Route',
                    'issue': f'Destination: Required {activity.required_destination}, You booked to {booked_destination}',
                    'details': f'The activity required flights to {activity.required_destination}, but you booked to {booked_destination}',
                    'points_lost': 'Up to 10%',
                    'type': 'route'
                })
                recommendations.append(f"Search for flights going to {activity.required_destination} airport")
    
    return {
        'passenger_comparison': {
            'required_adults': activity.required_passengers,
            'submitted_adults': adult_count,
            'required_children': activity.required_children,
            'submitted_children': child_count,
            'required_infants': activity.required_infants,
            'submitted_infants': infant_count,
            'adults_match': adult_count == activity.required_passengers,
            'children_match': child_count == activity.required_children,
            'infants_match': infant_count == activity.required_infants,
        },
        'price_comparison': {
            'submitted_total': total_price,
            'within_budget': True,  # Always true since budget is removed
            'overage': 0,  # Always 0 since budget is removed
        },
        'flight_comparison': {
            'required_trip_type': activity.required_trip_type,
            'submitted_trip_type': booking.trip_type,
            'trip_type_match': booking.trip_type == activity.required_trip_type,
            'required_travel_class': activity.required_travel_class,
            'actual_travel_classes': actual_classes,
            'has_correct_class': has_correct_class,
            'required_origin': getattr(activity, 'required_origin', None),
            'required_destination': getattr(activity, 'required_destination', None),
        },
        'deductions': deductions,
        'recommendations': recommendations,
        'score_breakdown': {
            'base_points': float(activity.total_points) * 0.3,
            'passenger_points': calculate_passenger_points(adult_count, child_count, infant_count, activity),
            'price_points': calculate_price_points(total_price, activity),
            'compliance_points': calculate_compliance_points(booking, activity, has_correct_class),
        }
    }

def calculate_passenger_points(adult_count, child_count, infant_count, activity):
    """Calculate points for passenger requirements"""
    total_points = float(activity.total_points) * 0.3
    match_percentage = 0
    
    if adult_count == activity.required_passengers:
        match_percentage += 0.5
    if child_count == activity.required_children:
        match_percentage += 0.3
    if infant_count == activity.required_infants:
        match_percentage += 0.2
    
    return total_points * match_percentage

def calculate_price_points(total_price, activity):
    """Calculate points for price compliance - now always full points"""
    return float(activity.total_points) * 0.2  # Always full points since budget is removed

def calculate_compliance_points(booking, activity, has_correct_class):
    """Calculate points for trip type and travel class compliance"""
    compliance_points = float(activity.total_points) * 0.2
    match_percentage = 0
    
    if booking.trip_type == activity.required_trip_type:
        match_percentage += 0.5
    if has_correct_class:
        match_percentage += 0.5
    
    return compliance_points * match_percentage



@login_required
def student_work_detail(request, submission_id):
    """Detailed view showing student's work compared to activity requirements"""
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        submission = get_object_or_404(ActivitySubmission, id=submission_id, student=student)
        activity = submission.activity
        booking = submission.booking
        
        print(f"=== STUDENT WORK DETAIL DEBUG ===")
        print(f"Submission: {submission.id}")
        print(f"Activity: {activity.title}")
        print(f"Booking: {booking.id}")
        print(f"Submission Score: {submission.score}")
        print(f"Add-on Score: {submission.addon_score}")
        
        # Get detailed booking information
        booking_details = get_booking_details(booking)
        
        # Get comprehensive comparison data
        comparison_data = get_detailed_comparison(activity, booking, booking_details, submission)
        
        # Calculate add-on score
        addon_score, max_addon_points = submission.calculate_addon_score()
        
        # Update submission with add-on scores if not already set
        if not submission.addon_score:
            submission.addon_score = addon_score
            submission.max_addon_points = max_addon_points
            submission.save()
        
        # Get student's selected add-ons
        student_addons = submission.get_student_selected_addons()
        
        # Calculate overall compliance percentage
        total_requirements = len([req for req in comparison_data['requirements'] if not req.get('optional', False)])
        met_requirements = len([req for req in comparison_data['requirements'] if req.get('met', False) and not req.get('optional', False)])
        
        compliance_percentage = (met_requirements / total_requirements * 100) if total_requirements > 0 else 0
        
        # Get activity required add-ons for template
        activity_required_addons = [req.addon for req in activity.activity_addons.all()]
        
        # Get activity passengers (if any were predefined)
        activity_passengers = activity.passengers.all()
        
        # Get passenger-specific information
        passenger_details = []
        passenger_addons_data = {}
        
        if booking:
            print(f"=== BOOKING DEBUG ===")
            print(f"Booking ID: {booking.id}")
            print(f"Number of booking details: {booking.details.count()}")
            
            # Group booking details by passenger to avoid duplicates
            from collections import defaultdict
            passenger_booking_map = defaultdict(list)
            
            for booking_detail in booking.details.all():
                passenger = booking_detail.passenger
                passenger_booking_map[passenger].append(booking_detail)
            
            # Process each passenger and their booking details
            for passenger, booking_details_list in passenger_booking_map.items():
                passenger_key = f"{passenger.first_name}_{passenger.last_name}"
                
                print(f"Processing passenger: {passenger.first_name} {passenger.last_name}")
                
                # Collect all add-ons for this passenger across all booking details
                passenger_addons_list = []
                for booking_detail in booking_details_list:
                    print(f"  Booking Detail ID: {booking_detail.id}")
                    print(f"  Number of addons: {booking_detail.addons.count()}")
                    
                    for addon in booking_detail.addons.all():
                        print(f"    - Addon: {addon.name} (ID: {addon.id})")
                        addon_data = {
                            'addon': addon,
                            'quantity': 1,
                        }
                        passenger_addons_list.append(addon_data)
                
                # Store passenger add-ons data
                passenger_addons_data[passenger_key] = {
                    'addons': passenger_addons_list
                }
                
                # Use the first booking detail for seat information
                primary_booking_detail = booking_details_list[0]
                passenger_details.append({
                    'passenger': passenger,
                    'booking_detail': primary_booking_detail,
                    'seat': primary_booking_detail.seat,
                    'seat_class': primary_booking_detail.seat_class,
                })
        
        # Build the comparison context for the template
        score_breakdown = comparison_data.get('score_breakdown', {})
        
        # Calculate the total WITHOUT add-ons for display purposes
        calculated_without_addons = (
            score_breakdown.get('base_points', 0) +
            score_breakdown.get('passenger_points', 0) + 
            score_breakdown.get('price_points', 0) +
            score_breakdown.get('compliance_points', 0)
        )
        
        # For template display, we want to show the breakdown WITHOUT add-ons
        # since add-ons are displayed separately
        display_score_breakdown = score_breakdown.copy()
        display_score_breakdown['total_earned'] = calculated_without_addons
        
        comparison_context = {
            'passenger_comparison': comparison_data.get('passenger_comparison', {}),
            'price_comparison': comparison_data.get('price_comparison', {}),
            'flight_comparison': comparison_data.get('flight_comparison', {}),
            'score_breakdown': display_score_breakdown,  # Use display version without add-ons
            'requirements': comparison_data.get('requirements', []),
            'deductions': comparison_data.get('deductions', []),
            'recommendations': comparison_data.get('recommendations', []),
        }
        
        return render(request, 'booking/student/work_detail.html', {
            'submission': submission,
            'activity': activity,
            'booking': booking,
            'booking_details': booking_details,
            'comparison': comparison_context,
            'student': student,
            'compliance_percentage': compliance_percentage,
            'met_requirements': met_requirements,
            'total_requirements': total_requirements,
            'activity_required_addons': activity_required_addons,
            'activity_passengers': activity_passengers,
            'student_addons': student_addons,
            'passenger_details': passenger_details,
            'passenger_addons_data': passenger_addons_data,
        })
        
    except Exception as e:
        print(f"Error in student_work_detail: {str(e)}")
        import traceback
        traceback.print_exc()
        messages.error(request, "Error loading work details.")
        return redirect('bookingapp:student_activities')

def get_detailed_comparison(activity, booking, booking_details):
    """Get detailed comparison between activity requirements and student work"""
    
    # Count passenger types
    adult_count = 0
    child_count = 0
    infant_count = 0
    total_price = booking_details['total_cost']
    
    for passenger in booking_details['passengers']:
        passenger_type = passenger['type'].lower()
        if passenger_type == 'adult':
            adult_count += 1
        elif passenger_type == 'child':
            child_count += 1
        elif passenger_type == 'infant':
            infant_count += 1
    
    # Check travel class compliance
    seat_class_names = [seat_class.name.lower() for seat_class in booking_details['seat_classes_used']]
    has_correct_class = any(
        seat_class_name == activity.required_travel_class.lower() 
        for seat_class_name in seat_class_names
    )
    
    # Get actual seat classes used
    actual_classes = ", ".join([seat_class.name for seat_class in booking_details['seat_classes_used']])
    
    # Build detailed requirements comparison
    requirements = []
    
    # 1. Trip Type Requirement
    requirements.append({
        'category': 'Trip Type',
        'requirement': f'{activity.required_trip_type.title()} Trip',
        'student_work': f'{booking.trip_type.title()} Trip',
        'met': booking.trip_type == activity.required_trip_type,
        'icon': '✓' if booking.trip_type == activity.required_trip_type else '✗',
        'weight': 'High'
    })
    
    # 2. Passenger Count Requirements
    requirements.append({
        'category': 'Passengers',
        'requirement': f'{activity.required_passengers} Adult(s)',
        'student_work': f'{adult_count} Adult(s)',
        'met': adult_count == activity.required_passengers,
        'icon': '✓' if adult_count == activity.required_passengers else '✗',
        'weight': 'High'
    })
    
    if activity.required_children > 0:
        requirements.append({
            'category': 'Passengers',
            'requirement': f'{activity.required_children} Child(ren)',
            'student_work': f'{child_count} Child(ren)',
            'met': child_count == activity.required_children,
            'icon': '✓' if child_count == activity.required_children else '✗',
            'weight': 'Medium'
        })
    
    if activity.required_infants > 0:
        requirements.append({
            'category': 'Passengers',
            'requirement': f'{activity.required_infants} Infant(s)',
            'student_work': f'{infant_count} Infant(s)',
            'met': infant_count == activity.required_infants,
            'icon': '✓' if infant_count == activity.required_infants else '✗',
            'weight': 'Medium'
        })
    
    # 3. Travel Class Requirement
    requirements.append({
        'category': 'Travel Class',
        'requirement': f'{activity.required_travel_class.title()} Class',
        'student_work': actual_classes,
        'met': has_correct_class,
        'icon': '✓' if has_correct_class else '✗',
        'weight': 'High'
    })
    
    # 4. Budget Requirement
    if activity.required_max_price:
        requirements.append({
            'category': 'Budget',
            'requirement': f'Under ${activity.required_max_price}',
            'student_work': f'${total_price:.2f}',
            'met': total_price <= float(activity.required_max_price),
            'icon': '✓' if total_price <= float(activity.required_max_price) else '✗',
            'weight': 'High',
            'overage': total_price - float(activity.required_max_price) if total_price > float(activity.required_max_price) else 0
        })
    
    # 5. Origin/Destination Requirements
    if hasattr(activity, 'required_origin') and activity.required_origin:
        first_flight = next(iter(booking_details['flights'].values()), None)
        booked_origin = first_flight['schedule'].flight.route.origin_airport.code if first_flight else 'N/A'
        requirements.append({
            'category': 'Flight Route',
            'requirement': f'Depart from {activity.required_origin}',
            'student_work': f'Depart from {booked_origin}',
            'met': booked_origin == activity.required_origin,
            'icon': '✓' if booked_origin == activity.required_origin else '✗',
            'weight': 'Medium'
        })
    
    if hasattr(activity, 'required_destination') and activity.required_destination:
        first_flight = next(iter(booking_details['flights'].values()), None)
        booked_destination = first_flight['schedule'].flight.route.destination_airport.code if first_flight else 'N/A'
        requirements.append({
            'category': 'Flight Route',
            'requirement': f'Arrive at {activity.required_destination}',
            'student_work': f'Arrive at {booked_destination}',
            'met': booked_destination == activity.required_destination,
            'icon': '✓' if booked_destination == activity.required_destination else '✗',
            'weight': 'Medium'
        })
    
    # 6. Flight Details (informational)
    for flight_id, flight_data in booking_details['flights'].items():
        schedule = flight_data['schedule']
        route = schedule.flight.route
        requirements.append({
            'category': 'Flight Details',
            'requirement': f'Flight {schedule.flight.flight_number}',
            'student_work': f'{route.origin_airport.code} → {route.destination_airport.code} on {schedule.departure_time.strftime("%b %d, %Y")}',
            'met': True,
            'icon': '✓',
            'weight': 'Info',
            'optional': True
        })
    
    # Calculate score breakdown
    score_breakdown = calculate_detailed_score_breakdown(activity, booking, booking_details, seat_class_names)
    
    return {
        'requirements': requirements,
        'score_breakdown': score_breakdown,
        'summary': {
            'total_passengers': adult_count + child_count + infant_count,
            'total_flights': len(booking_details['flights']),
            'total_cost': total_price,
            'seat_classes': actual_classes
        }
    }

def calculate_detailed_score_breakdown(activity, booking, booking_details, seat_class_names):
    """Calculate detailed score breakdown for display with CORRECT weights"""
    total_points = float(activity.total_points)
    
    # CORRECTED WEIGHTS (matching calculate_activity_score):
    # Base: 25%, Passengers: 25%, Price: 20%, Compliance: 15%, Add-ons: 15%
    
    # Count passenger types
    adult_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'adult'])
    child_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'child'])
    infant_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'infant'])
    
    # Base completion points (25%)
    base_points = total_points * 0.25
    
    # Passenger points (25%)
    passenger_match = 0
    if adult_count == activity.required_passengers:
        passenger_match += 0.5  # 50% weight for adults
    if child_count == activity.required_children:
        passenger_match += 0.3  # 30% weight for children  
    if infant_count == activity.required_infants:
        passenger_match += 0.2  # 20% weight for infants
    
    passenger_points = (total_points * 0.25) * passenger_match
    
    # Price points (20%)
    total_price = booking_details['total_cost']
    price_points = total_points * 0.20
    if activity.required_max_price and total_price > float(activity.required_max_price):
        overage_percentage = min((total_price - float(activity.required_max_price)) / float(activity.required_max_price), 1.0)
        price_points *= (1 - overage_percentage)
    
    # Compliance points (15%)
    compliance_match = 0
    if booking.trip_type == activity.required_trip_type:
        compliance_match += 0.5  # 50% weight for trip type
    
    has_correct_class = any(
        seat_class_name == activity.required_travel_class.lower() 
        for seat_class_name in seat_class_names
    )
    if has_correct_class:
        compliance_match += 0.5  # 50% weight for travel class
    
    compliance_points = (total_points * 0.15) * compliance_match
    
    # Add-on points (15%) - This should come from the actual submission
    addon_points = total_points * 0.15  # Default full points if no specific add-on grading
    
    return {
        'base_points': base_points,  # 25 pts
        'passenger_points': passenger_points,  # Up to 25 pts
        'price_points': price_points,  # Up to 20 pts  
        'compliance_points': compliance_points,  # Up to 15 pts
        'addon_points': addon_points,  # Up to 15 pts
        'total_earned': base_points + passenger_points + price_points + compliance_points + addon_points,
        'total_possible': total_points,
    }




def get_booking_details(booking):
    """Get detailed information about what was actually booked"""
    print(f"=== GET_BOOKING_DETAILS DEBUG ===")
    print(f"Booking ID: {booking.id}")
    
    booking_details = booking.details.all().select_related(
        'passenger', 'schedule', 'schedule__flight', 'schedule__flight__route'
    )
    
    print(f"Found {booking_details.count()} booking details")
    
    details = {
        'passengers': [],
        'flights': {},
        'total_cost': 0,
        'seat_classes_used': set()
    }
    
    # Group by flight schedule
    flight_groups = {}
    for detail in booking_details:
        print(f"Processing detail: {detail.id} - Passenger: {detail.passenger.first_name}")
        schedule_id = detail.schedule.id
        if schedule_id not in flight_groups:
            flight_groups[schedule_id] = {
                'schedule': detail.schedule,
                'passengers': [],
                'total_seats': 0
            }
        
        flight_groups[schedule_id]['passengers'].append({
            'passenger': detail.passenger,
            'seat_class': detail.seat_class,
            'seat_number': detail.seat.seat_number if detail.seat else 'Not assigned',
            'price': detail.price
        })
        flight_groups[schedule_id]['total_seats'] += 1
        
        # Add to overall details
        details['seat_classes_used'].add(detail.seat_class)
        if detail.passenger.passenger_type.lower() != 'infant':
            details['total_cost'] += float(detail.price)
    
    details['flights'] = flight_groups
    details['seat_classes_used'] = list(details['seat_classes_used'])
    
    print(f"Flight groups: {len(flight_groups)}")
    
    # Get all passengers with their details - USING CORRECT FIELD NAMES FROM YOUR MODEL
    for detail in booking_details:
        # Build the full name with middle name if available
        if detail.passenger.middle_name:
            full_name = f"{detail.passenger.first_name} {detail.passenger.middle_name} {detail.passenger.last_name}"
        else:
            full_name = f"{detail.passenger.first_name} {detail.passenger.last_name}"
        
        passenger_info = {
            'name': full_name,
            'type': detail.passenger.passenger_type,
            'date_of_birth': detail.passenger.date_of_birth,
            'gender': detail.passenger.gender,
            'passport': detail.passenger.passport_number,
            'email': detail.passenger.email,
            'phone': detail.passenger.phone,
            'flights': []
        }
        
        # Add flight details for this passenger
        for flight_group in flight_groups.values():
            for passenger in flight_group['passengers']:
                if passenger['passenger'].id == detail.passenger.id:
                    passenger_info['flights'].append({
                        'route': f"{flight_group['schedule'].flight.route.origin_airport.code} → {flight_group['schedule'].flight.route.destination_airport.code}",
                        'date': flight_group['schedule'].departure_time.date(),
                        'seat_class': passenger['seat_class'].name if passenger['seat_class'] else 'Not assigned',
                        'seat_number': passenger['seat_number'],
                        'price': passenger['price']
                    })
        
        # Only add each passenger once
        if not any(p['name'] == passenger_info['name'] for p in details['passengers']):
            details['passengers'].append(passenger_info)
    
    print(f"Final passengers count: {len(details['passengers'])}")
    print(f"Final flights count: {len(details['flights'])}")
    print("=== END GET_BOOKING_DETAILS ===")
    
    return details


from decimal import Decimal

def get_detailed_comparison(activity, booking, booking_details, submission=None):
    """Get detailed comparison between activity requirements and student work"""
    
    # Initialize counts
    adult_count = 0
    child_count = 0
    infant_count = 0
    total_price = booking_details.get('total_cost', 0)
    
    # Count passenger types
    for passenger in booking_details.get('passengers', []):
        passenger_type = passenger.get('type', '').lower()
        if passenger_type == 'adult':
            adult_count += 1
        elif passenger_type == 'child':
            child_count += 1
        elif passenger_type == 'infant':
            infant_count += 1
    
    # Check travel class compliance
    seat_classes_used = booking_details.get('seat_classes_used', [])
    seat_class_names = [seat_class.name.lower() for seat_class in seat_classes_used]
    has_correct_class = any(
        seat_class_name == activity.required_travel_class.lower() 
        for seat_class_name in seat_class_names
    )
    
    # Get actual seat classes used
    actual_classes = ", ".join([seat_class.name for seat_class in seat_classes_used]) if seat_classes_used else "Not specified"
    
    # Get trip type from booking
    submitted_trip_type = getattr(booking, 'trip_type', 'Not specified')
    
    # Build passenger comparison
    passenger_comparison = {
        'required_adults': activity.required_passengers,
        'submitted_adults': adult_count,
        'required_children': activity.required_children,
        'submitted_children': child_count,
        'required_infants': activity.required_infants,
        'submitted_infants': infant_count,
        'adults_match': adult_count == activity.required_passengers,
        'children_match': child_count == activity.required_children,
        'infants_match': infant_count == activity.required_infants,
    }
    
    # Build price comparison
    price_comparison = {
        'submitted_total': total_price,
        'within_budget': True,  # Always true since budget is removed
        'overage': 0,  # Always 0 since budget is removed
    }
    
    # Build flight comparison
    flight_comparison = {
        'required_trip_type': activity.required_trip_type,
        'submitted_trip_type': submitted_trip_type,
        'trip_type_match': submitted_trip_type == activity.required_trip_type,
        'required_travel_class': activity.required_travel_class,
        'actual_travel_classes': actual_classes,
        'has_correct_class': has_correct_class,
    }
    
    # Build requirements list
    requirements = []
    deductions = []
    recommendations = []
    
    # 1. Trip Type Requirement
    requirements.append({
        'category': 'Trip Type',
        'requirement': f'{activity.required_trip_type.title()} Trip',
        'student_work': f'{booking.trip_type.title()} Trip',
        'met': booking.trip_type == activity.required_trip_type,
        'icon': '✓' if booking.trip_type == activity.required_trip_type else '✗',
        'weight': 'High'
    })
    
    # 2. Passenger Count Requirements
    requirements.append({
        'category': 'Passengers',
        'requirement': f'{activity.required_passengers} Adult(s)',
        'student_work': f'{adult_count} Adult(s)',
        'met': adult_count == activity.required_passengers,
        'icon': '✓' if adult_count == activity.required_passengers else '✗',
        'weight': 'High'
    })
    
    if activity.required_children > 0:
        requirements.append({
            'category': 'Passengers',
            'requirement': f'{activity.required_children} Child(ren)',
            'student_work': f'{child_count} Child(ren)',
            'met': child_count == activity.required_children,
            'icon': '✓' if child_count == activity.required_children else '✗',
            'weight': 'Medium'
        })
    
    if activity.required_infants > 0:
        requirements.append({
            'category': 'Passengers',
            'requirement': f'{activity.required_infants} Infant(s)',
            'student_work': f'{infant_count} Infant(s)',
            'met': infant_count == activity.required_infants,
            'icon': '✓' if infant_count == activity.required_infants else '✗',
            'weight': 'Medium'
        })
    
    # 3. Travel Class Requirement
    requirements.append({
        'category': 'Travel Class',
        'requirement': f'{activity.required_travel_class.title()} Class',
        'student_work': actual_classes,
        'met': has_correct_class,
        'icon': '✓' if has_correct_class else '✗',
        'weight': 'High'
    })
    
    # 4. Budget Requirement
    # if activity.required_max_price:
    #     requirements.append({
    #         'category': 'Budget',
    #         'requirement': f'Under ${activity.required_max_price}',
    #         'student_work': f'${total_price:.2f}',
    #         'met': total_price <= float(activity.required_max_price),
    #         'icon': '✓' if total_price <= float(activity.required_max_price) else '✗',
    #         'weight': 'High',
    #         'overage': total_price - float(activity.required_max_price) if total_price > float(activity.required_max_price) else 0
    #     })
    
    # Calculate score breakdown using the ACTUAL calculated points
    total_points = float(activity.total_points)
    
    # Use the submission's actual score if available
    if submission and submission.score is not None:
        actual_score = float(submission.score)
        
        # Calculate the ACTUAL earned points from each category
        # These should match what calculate_activity_score computed
        base_points = total_points * 0.25  # Always 25% for completion
        
        # Calculate passenger points based on actual match
        passenger_match = 0
        if adult_count == activity.required_passengers:
            passenger_match += 0.5
        if child_count == activity.required_children:
            passenger_match += 0.3  
        if infant_count == activity.required_infants:
            passenger_match += 0.2
        passenger_points = (total_points * 0.25) * passenger_match
        
        # Price points - always full points since budget is removed
        price_points = total_points * 0.20
        
        # Calculate compliance points based on actual match
        compliance_match = 0
        if booking.trip_type == activity.required_trip_type:
            compliance_match += 0.5
        if has_correct_class:
            compliance_match += 0.5
        compliance_points = (total_points * 0.15) * compliance_match
        
        # Use actual add-on score from submission (convert to float if it's Decimal)
        addon_points = float(submission.addon_score) if submission.addon_score else 0.0
        
    else:
        # Fallback calculation if no submission
        base_points = total_points * 0.25
        
        passenger_match = 0
        if adult_count == activity.required_passengers:
            passenger_match += 0.5
        if child_count == activity.required_children:
            passenger_match += 0.3  
        if infant_count == activity.required_infants:
            passenger_match += 0.2
        passenger_points = (total_points * 0.25) * passenger_match
        
         # Price points - always full points since budget is removed
        price_points = total_points * 0.20
        
        
        compliance_match = 0
        if booking.trip_type == activity.required_trip_type:
            compliance_match += 0.5
        if has_correct_class:
            compliance_match += 0.5
        compliance_points = (total_points * 0.15) * compliance_match
        
        addon_points = total_points * 0.15  # Default full points
    
    # Calculate total earned ensuring all values are floats
    total_earned = float(base_points) + float(passenger_points) + float(price_points) + float(compliance_points)
    if activity.addon_grading_enabled:
        total_earned += float(addon_points)
    
    # Build the final score breakdown with ACTUAL earned points
    score_breakdown = {
        'base_points': float(base_points),
        'passenger_points': float(passenger_points),
        'price_points': float(price_points),
        'compliance_points': float(compliance_points),
        'addon_points': float(addon_points) if activity.addon_grading_enabled else 0.0,
        'total_earned': total_earned,
        'total_possible': float(total_points),
        'total_possible_base_points': float(total_points) * 0.25,
        'total_possible_passenger_points': float(total_points) * 0.25,
        'total_possible_price_points': float(total_points) * 0.20,
        'total_possible_compliance_points': float(total_points) * 0.15,
        'total_possible_addon_points': float(total_points) * 0.15 if activity.addon_grading_enabled else 0.0,
    }
    
    return {
        'passenger_comparison': passenger_comparison,
        'price_comparison': price_comparison,
        'flight_comparison': flight_comparison,
        'requirements': requirements,
        'deductions': deductions,
        'recommendations': recommendations,
        'score_breakdown': score_breakdown,
    }




def calculate_detailed_score_breakdown(activity, booking, booking_details, seat_class_names):
    """Calculate detailed score breakdown for display with correct percentages"""
    total_points = float(activity.total_points)
    
    # Base completion points (25%)
    base_points = total_points * 0.25
    
    # Passenger points (25%)
    adult_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'adult'])
    child_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'child'])
    infant_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'infant'])
    
    passenger_match = 0
    if adult_count == activity.required_passengers:
        passenger_match += 0.5  # 50% weight for adults
    if child_count == activity.required_children:
        passenger_match += 0.3  # 30% weight for children  
    if infant_count == activity.required_infants:
        passenger_match += 0.2  # 20% weight for infants
    
    passenger_points = (total_points * 0.25) * passenger_match
    
    # Price points (20%)
    total_price = booking_details['total_cost']
    price_points = total_points * 0.20
    if activity.required_max_price and total_price > float(activity.required_max_price):
        overage_percentage = min((total_price - float(activity.required_max_price)) / float(activity.required_max_price), 1.0)
        price_points *= (1 - overage_percentage)
    
    # Compliance points (15%)
    compliance_match = 0
    if booking.trip_type == activity.required_trip_type:
        compliance_match += 0.5  # 50% weight for trip type
    
    has_correct_class = any(
        seat_class_name == activity.required_travel_class.lower() 
        for seat_class_name in seat_class_names
    )
    if has_correct_class:
        compliance_match += 0.5  # 50% weight for travel class
    
    compliance_points = (total_points * 0.15) * compliance_match
    
    # Add-on points (15%) - This should come from the submission, not recalculated here
    # We'll use the actual submission data
    
    return {
        'base_points': base_points,  # 25 pts
        'passenger_points': passenger_points,  # Up to 25 pts
        'price_points': price_points,  # Up to 20 pts  
        'compliance_points': compliance_points,  # Up to 15 pts
        'total_earned': base_points + passenger_points + price_points + compliance_points,
        'total_possible': total_points,
        # Add these for template percentage calculations
        'total_possible_passenger_points': total_points * 0.25,  # 25 pts
        'total_possible_price_points': total_points * 0.20,      # 20 pts
        'total_possible_compliance_points': total_points * 0.15, # 15 pts
        'total_possible_addon_points': total_points * 0.15,      # 15 pts
    }





def calculate_detailed_score_breakdown(activity, booking, booking_details, seat_class_names):
    """Calculate detailed score breakdown for display with CORRECT weights"""
    total_points = float(activity.total_points)
    
    # CORRECTED WEIGHTS (matching calculate_activity_score):
    # Base: 25%, Passengers: 25%, Price: 20%, Compliance: 15%, Add-ons: 15%
    
    # Base completion points (25%)
    base_points = total_points * 0.25
    
    # Passenger points (25%)
    adult_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'adult'])
    child_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'child'])
    infant_count = len([p for p in booking_details['passengers'] if p['type'].lower() == 'infant'])
    
    passenger_match = 0
    if adult_count == activity.required_passengers:
        passenger_match += 0.5  # 50% weight for adults
    if child_count == activity.required_children:
        passenger_match += 0.3  # 30% weight for children  
    if infant_count == activity.required_infants:
        passenger_match += 0.2  # 20% weight for infants
    
    passenger_points = (total_points * 0.25) * passenger_match
    
    # Price points (20%)
    total_price = booking_details['total_cost']
    price_points = total_points * 0.20
    if activity.required_max_price and total_price > float(activity.required_max_price):
        overage_percentage = min((total_price - float(activity.required_max_price)) / float(activity.required_max_price), 1.0)
        price_points *= (1 - overage_percentage)
    
    # Compliance points (15%)
    compliance_match = 0
    if booking.trip_type == activity.required_trip_type:
        compliance_match += 0.5  # 50% weight for trip type
    
    has_correct_class = any(
        seat_class_name == activity.required_travel_class.lower() 
        for seat_class_name in seat_class_names
    )
    if has_correct_class:
        compliance_match += 0.5  # 50% weight for travel class
    
    compliance_points = (total_points * 0.15) * compliance_match
    
    return {
        'base_points': base_points,  # 25 pts
        'passenger_points': passenger_points,  # Up to 25 pts
        'price_points': price_points,  # Up to 20 pts  
        'compliance_points': compliance_points,  # Up to 15 pts
        'total_earned': base_points + passenger_points + price_points + compliance_points,
        'total_possible': total_points,
        # Add these for template percentage calculations
        'total_possible_passenger_points': total_points * 0.25,  # 25 pts
        'total_possible_price_points': total_points * 0.20,      # 20 pts
        'total_possible_compliance_points': total_points * 0.15, # 15 pts
        'total_possible_addon_points': total_points * 0.15,      # 15 pts
    }





@login_required
def debug_scoring(request, submission_id):
    """Debug view to see exactly why scores are deducted"""
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        submission = get_object_or_404(ActivitySubmission, id=submission_id, student=student)
        activity = submission.activity
        booking = submission.booking
        
        print(f"=== SCORING DEBUG FOR SUBMISSION {submission_id} ===")
        print(f"Activity: {activity.title}")
        print(f"Final Score: {submission.score}/{activity.total_points}")
        
        # Get detailed booking information
        booking_details = get_booking_details(booking)
        
        # Debug passenger counts
        adult_count = 0
        child_count = 0 
        infant_count = 0
        
        for passenger in booking_details['passengers']:
            passenger_type = passenger['type'].lower()
            if passenger_type == 'adult':
                adult_count += 1
            elif passenger_type == 'child':
                child_count += 1
            elif passenger_type == 'infant':
                infant_count += 1
        
        print(f"Passenger Counts - Booked: {adult_count}A, {child_count}C, {infant_count}I")
        print(f"Passenger Required: {activity.required_passengers}A, {activity.required_children}C, {activity.required_infants}I")
        
        # Check trip type
        print(f"Trip Type - Booked: {booking.trip_type}, Required: {activity.required_trip_type}")
        
        # Check travel class
        seat_class_names = [seat_class.name.lower() for seat_class in booking_details['seat_classes_used']]
        print(f"Travel Class - Booked: {seat_class_names}, Required: {activity.required_travel_class}")
        
        # Check budget
        total_price = booking_details['total_cost']
        print(f"Total Cost: ${total_price:.2f}, Max Allowed: ${activity.required_max_price if activity.required_max_price else 'None'}")
        
        # Manual score calculation to see breakdown
        total_points = float(activity.total_points)
        
        # Base points (30%)
        base_points = total_points * 0.3
        print(f"Base points (completion): {base_points}")
        
        # Passenger points (30%)
        passenger_match = 0
        if adult_count == activity.required_passengers:
            passenger_match += 0.5
            print("✅ Adult count matches")
        else:
            print(f"❌ Adult count: required {activity.required_passengers}, booked {adult_count}")
            
        if child_count == activity.required_children:
            passenger_match += 0.3
            print("✅ Child count matches")
        else:
            print(f"❌ Child count: required {activity.required_children}, booked {child_count}")
            
        if infant_count == activity.required_infants:
            passenger_match += 0.2
            print("✅ Infant count matches")
        else:
            print(f"❌ Infant count: required {activity.required_infants}, booked {infant_count}")
            
        passenger_points = total_points * 0.3 * passenger_match
        print(f"Passenger points: {passenger_points}")
        
        # Price points (20%)
        price_points = total_points * 0.2
        if activity.required_max_price and total_price > float(activity.required_max_price):
            overage_percentage = min((total_price - float(activity.required_max_price)) / float(activity.required_max_price), 1.0)
            price_deduction = price_points * overage_percentage
            price_points -= price_deduction
            print(f"❌ Over budget: ${total_price - float(activity.required_max_price):.2f} over")
            print(f"Price points after deduction: {price_points}")
        else:
            print("✅ Within budget")
        
        # Compliance points (20%)
        compliance_match = 0
        if booking.trip_type == activity.required_trip_type:
            compliance_match += 0.5
            print("✅ Trip type matches")
        else:
            print(f"❌ Trip type: required {activity.required_trip_type}, booked {booking.trip_type}")
            
        has_correct_class = any(
            seat_class_name == activity.required_travel_class.lower() 
            for seat_class_name in seat_class_names
        )
        if has_correct_class:
            compliance_match += 0.5
            print("✅ Travel class matches")
        else:
            print(f"❌ Travel class: required {activity.required_travel_class}, booked {seat_class_names}")
            
        compliance_points = total_points * 0.2 * compliance_match
        print(f"Compliance points: {compliance_points}")
        
        # Total
        calculated_total = base_points + passenger_points + price_points + compliance_points
        print(f"Calculated total: {calculated_total}")
        print(f"Actual submission score: {submission.score}")
        
        return HttpResponse(f"Check console for detailed scoring breakdown. Submission: {submission_id}")
        
    except Exception as e:
        print(f"Debug error: {e}")
        return HttpResponse(f"Error: {e}")
    

@login_required
def check_original_scoring(request, submission_id):
    """Check how the score was originally calculated"""
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        submission = get_object_or_404(ActivitySubmission, id=submission_id, student=student)
        
        print(f"=== ORIGINAL SCORING INVESTIGATION ===")
        print(f"Submission ID: {submission.id}")
        print(f"Created at: {submission.submitted_at}")
        print(f"Original Score: {submission.score}")
        print(f"Activity Total Points: {submission.activity.total_points}")
        
        # Check if there's any manual adjustment or different scoring logic
        print(f"Submission fields:")
        print(f"  - required_trip_type: {submission.required_trip_type}")
        print(f"  - required_travel_class: {submission.required_travel_class}")
        print(f"  - required_passengers: {submission.required_passengers}")
        print(f"  - required_children: {submission.required_children}")
        print(f"  - required_infants: {submission.required_infants}")
        print(f"  - required_max_price: {submission.required_max_price}")
        
        # Let's recalculate using the original calculate_activity_score function
        from .utils import calculate_activity_score  # Make sure this import works
        
        original_calculation = calculate_activity_score(submission.booking, submission.activity)
        print(f"Recalculated with original function: {original_calculation}")
        
        return HttpResponse(f"Check console for original scoring investigation")
        
    except Exception as e:
        print(f"Error in check_original_scoring: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error: {e}")


@login_required
def deep_debug_scoring(request, submission_id):
    """Deep debug to find the missing 10 points"""
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        submission = get_object_or_404(ActivitySubmission, id=submission_id, student=student)
        activity = submission.activity
        booking = submission.booking
        
        print(f"=== DEEP SCORING DEBUG ===")
        print(f"Looking for missing 10 points...")
        
        # Check the original calculate_activity_score function in detail
        print("=== ORIGINAL SCORING FUNCTION BREAKDOWN ===")
        
        # Manually run through the original scoring logic
        total_points = float(activity.total_points)
        points_earned = 0
        deduction_reasons = []
        
        # Base points (30%)
        base_points = total_points * 0.3
        points_earned += base_points
        print(f"1. Base points: {base_points}")
        
        # Passenger points (30%)
        passenger_points = total_points * 0.3
        booking_details = booking.details.all()
        
        adult_count = 0
        child_count = 0
        infant_count = 0
        
        for detail in booking_details:
            passenger_type = detail.passenger.passenger_type.lower()
            if passenger_type == 'adult':
                adult_count += 1
            elif passenger_type == 'child':
                child_count += 1
            elif passenger_type == 'infant':
                infant_count += 1
        
        passenger_match = 0
        if adult_count == activity.required_passengers:
            passenger_match += 0.5
        else:
            deduction_reasons.append(f"Adult passenger count mismatch")
        
        if child_count == activity.required_children:
            passenger_match += 0.3
        else:
            deduction_reasons.append(f"Child passenger count mismatch")
        
        if infant_count == activity.required_infants:
            passenger_match += 0.2
        else:
            deduction_reasons.append(f"Infant passenger count mismatch")
        
        passenger_earned = passenger_points * passenger_match
        points_earned += passenger_earned
        print(f"2. Passenger points: {passenger_earned}/{passenger_points} (match: {passenger_match})")
        
        # Price points (20%)
        price_points = total_points * 0.2
        if activity.required_max_price:
            total_amount = sum(detail.price for detail in booking_details if detail.passenger.passenger_type.lower() != 'infant')
            
            if total_amount <= activity.required_max_price:
                points_earned += price_points
                print(f"3. Price points: {price_points}/{price_points} (within budget)")
            else:
                overage_percentage = min((float(total_amount) - float(activity.required_max_price)) / float(activity.required_max_price), 1.0)
                price_deduction = price_points * overage_percentage
                points_earned += price_points - price_deduction
                deduction_reasons.append(f"Exceeded budget by {overage_percentage * 100:.1f}%")
                print(f"3. Price points: {price_points - price_deduction}/{price_points} (over budget)")
        else:
            points_earned += price_points
            print(f"3. Price points: {price_points}/{price_points} (no budget limit)")
        
        # Compliance points (20%)
        compliance_points = total_points * 0.2
        compliance_match = 0
        
        if booking.trip_type == activity.required_trip_type:
            compliance_match += 0.5
        else:
            deduction_reasons.append(f"Trip type mismatch")
        
        has_correct_class = any(
            detail.seat_class and str(detail.seat_class.name).lower() == activity.required_travel_class.lower() 
            for detail in booking_details
        )
        if has_correct_class:
            compliance_match += 0.5
        else:
            deduction_reasons.append(f"Travel class mismatch")
        
        compliance_earned = compliance_points * compliance_match
        points_earned += compliance_earned
        print(f"4. Compliance points: {compliance_earned}/{compliance_points} (match: {compliance_match})")
        
        # Final score
        from decimal import Decimal
        final_score = Decimal(str(min(points_earned, total_points)))
        
        print(f"FINAL CALCULATION: {final_score}")
        print(f"ACTUAL SCORE IN DB: {submission.score}")
        print(f"DIFFERENCE: {float(final_score) - float(submission.score)}")
        
        if deduction_reasons:
            print(f"Deduction reasons from original function: {deduction_reasons}")
        
        return HttpResponse(f"Deep debug completed. Check console.")
        
    except Exception as e:
        print(f"Deep debug error: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error: {e}")        
    




@login_required
def practice_booking_home(request):
    """Home page for practice bookings"""
    student_id = request.session.get('student_id')
    
    if not student_id:
        return redirect('bookingapp:login')
    
    try:
        student = Student.objects.get(id=student_id)
        
        # Get student's practice bookings
        practice_bookings = PracticeBooking.objects.filter(
            student=student
        ).select_related('booking').order_by('-created_at')[:5]  # Last 5 practice bookings
        
        template = loader.get_template('booking/student/practice_home.html')
        context = {
            'student': student,
            'practice_bookings': practice_bookings,
        }
        return HttpResponse(template.render(context, request))
        
    except Student.DoesNotExist:
        messages.error(request, "Student not found.")
        return redirect('bookingapp:login')

@login_required
def start_practice_booking(request):
    """Start a new practice booking session"""
    # Clear any activity-related session data
    request.session.pop('activity_id', None)
    request.session.pop('activity_requirements', None)
    
    # Clear previous booking session data
    booking_keys = [
        'trip_type', 'origin', 'destination', 'departure_date', 'return_date',
        'adults', 'children', 'infants', 'passenger_count',
        'passengers', 'selected_seats', 'confirm_depart_schedule', 
        'confirm_return_schedule', 'current_booking_id',
        'selected_addons'  # Clear add-ons too
    ]
    
    for key in booking_keys:
        request.session.pop(key, None)
    
    # Set practice mode flag
    request.session['is_practice_booking'] = True
    request.session.modified = True
    
    messages.info(request, "Practice booking mode activated. This booking won't be graded.")
    return redirect('bookingapp:main')

@login_required
def guided_practice(request):
    """Start a guided practice with specific requirements"""
    if request.method == 'POST':
        # Get practice scenario from form
        scenario_type = request.POST.get('scenario_type')
        requirements = {}
        
        # Set requirements based on scenario type
        if scenario_type == 'business_trip':
            requirements = {
                'trip_type': 'round_trip',
                'passengers': 1,
                'travel_class': 'business',
                'max_price': 2000,
                'description': 'Business trip for one executive'
            }
        elif scenario_type == 'family_vacation':
            requirements = {
                'trip_type': 'round_trip', 
                'passengers': 2,
                'children': 2,
                'travel_class': 'economy',
                'max_price': 1500,
                'description': 'Family vacation with 2 adults and 2 children'
            }
        elif scenario_type == 'budget_travel':
            requirements = {
                'trip_type': 'one_way',
                'passengers': 1,
                'travel_class': 'economy', 
                'max_price': 300,
                'description': 'Budget one-way trip'
            }
        else:
            # Custom requirements
            requirements = {
                'trip_type': request.POST.get('trip_type', 'one_way'),
                'passengers': int(request.POST.get('passengers', 1)),
                'children': int(request.POST.get('children', 0)),
                'infants': int(request.POST.get('infants', 0)),
                'travel_class': request.POST.get('travel_class', 'economy'),
                'max_price': float(request.POST.get('max_price', 0)) if request.POST.get('max_price') else None,
                'description': request.POST.get('description', 'Custom practice scenario')
            }
        
        # Store practice requirements in session
        request.session['practice_requirements'] = requirements
        request.session['is_practice_booking'] = True
        request.session['is_guided_practice'] = True
        
        # Clear previous data
        booking_keys = [
            'trip_type', 'origin', 'destination', 'departure_date', 'return_date',
            'adults', 'children', 'infants', 'passenger_count',
            'selected_addons'  # Clear add-ons too
        ]
        for key in booking_keys:
            request.session.pop(key, None)
        
        # Pre-fill based on requirements
        request.session['trip_type'] = requirements['trip_type']
        request.session['adults'] = requirements['passengers']
        request.session['children'] = requirements.get('children', 0)
        request.session['infants'] = requirements.get('infants', 0)
        
        messages.info(request, f"Guided practice started: {requirements['description']}")
        return redirect('bookingapp:main')
    
    
     # GET request - show guided practice options
    student_id = request.session.get('student_id')
    student = None
    if student_id:
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            pass


    # GET request - show guided practice options
    template = loader.get_template('booking/student/guided_practice.html')
    context = {
        'student': student,
    }
    return HttpResponse(template.render(context, request))

@login_required
def save_practice_booking(request):
    """Save a completed practice booking"""
    booking_id = request.session.get('current_booking_id')
    student_id = request.session.get('student_id')
    
    if not booking_id or not student_id:
        messages.error(request, "No booking found to save as practice.")
        return redirect('bookingapp:main')
    
    try:
        student = Student.objects.get(id=student_id)
        booking = Booking.objects.get(id=booking_id)
        
        # Determine practice type
        practice_type = 'guided_practice' if request.session.get('is_guided_practice') else 'free_practice'
        requirements = request.session.get('practice_requirements')
        
        # Create practice booking record
        practice_booking = PracticeBooking.objects.create(
            student=student,
            booking=booking,
            practice_type=practice_type,
            scenario_description=requirements.get('description') if requirements else 'Free practice booking',
            practice_requirements=requirements,
            is_completed=True
        )
        
        # Clear practice session data
        request.session.pop('is_practice_booking', None)
        request.session.pop('is_guided_practice', None)
        request.session.pop('practice_requirements', None)
        request.session.pop('selected_addons', None)  # Clear add-ons too
        
        messages.success(request, "Practice booking saved successfully!")
        return redirect('bookingapp:practice_booking_home')
        
    except Exception as e:
        print(f"Error saving practice booking: {e}")
        messages.error(request, "Error saving practice booking.")
        return redirect('bookingapp:payment_success')
    






# testing UI/UX


def test_home(request):
    from_airport = Airport.objects.all()
    to_airports = Airport.objects.all()


    today = timezone.now().date()
    template = loader.get_template("ui_test/home.html")
    context ={
        'origins' : from_airport,
        'destinations' : to_airports,
        'today': today.isoformat()
    }

    return HttpResponse(template.render(context, request))




def test_schedule(request):
    if request.method == 'POST':
        # Get form data
        trip_type = request.POST.get('trip_type', 'one_way')
        from_airport_id = request.POST.get('from_airport')
        to_airport_id = request.POST.get('to_airport')
        depart_date = request.POST.get('depart_date')
        return_date = request.POST.get('return_date')
        adults = int(request.POST.get('adults', 1))
        children = int(request.POST.get('children', 0))
        infants = int(request.POST.get('infants', 0))
        
        # Validate required fields
        if not all([from_airport_id, to_airport_id, depart_date]):
            return redirect('test_home')
        
        # Get airport objects
        try:
            from_airport = Airport.objects.get(id=from_airport_id)
            to_airport = Airport.objects.get(id=to_airport_id)
        except Airport.DoesNotExist:
            return redirect('test_home')
        
        # Parse dates
        depart_date_obj = datetime.strptime(depart_date, '%Y-%m-%d').date()
        return_date_obj = None
        
        if trip_type == 'round_trip' and return_date:
            return_date_obj = datetime.strptime(return_date, '%Y-%m-%d').date()
        
        # Calculate total passengers
        total_passengers = adults + children + infants
        
        # Query flights for depart date
        depart_flights = Flight.objects.filter(
            departure_airport=from_airport,
            arrival_airport=to_airport,
            departure_time__date=depart_date_obj
        ).select_related('departure_airport', 'arrival_airport', 'airline')
        
        # Query return flights if round trip
        return_flights = None
        if trip_type == 'round_trip' and return_date_obj:
            return_flights = Flight.objects.filter(
                departure_airport=to_airport,
                arrival_airport=from_airport,
                departure_time__date=return_date_obj
            ).select_related('departure_airport', 'arrival_airport', 'airline')
        
        template = loader.get_template("ui_test/schedule.html")
        context = {
            'trip_type': trip_type,
            'from_airport': from_airport,
            'to_airport': to_airport,
            'depart_date': depart_date_obj,
            'return_date': return_date_obj,
            'adults': adults,
            'children': children,
            'infants': infants,
            'total_passengers': total_passengers,
            'depart_flights': depart_flights,
            'return_flights': return_flights,
        }
        
        return HttpResponse(template.render(context, request))
    
    # If not POST, redirect to home
    return redirect('test_home')

def test_selected_schedule(request):
    template = loader.get_template("ui_test/selected_schedule.html")
    context ={
    }
    return HttpResponse(template.render(context, request))

def test_passenger(request):
    template = loader.get_template("ui_test/passenger.html")
    context ={

    }

    return HttpResponse(template.render(context, request))

def test_addons(request):
    template = loader.get_template("ui_test/add_ons.html")
    context ={

    }

    return HttpResponse(template.render(context, request))
def test_booking_summary(request):
    template = loader.get_template("ui_test/booking_summary.html")
    context ={

    }

    return HttpResponse(template.render(context, request))