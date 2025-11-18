from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.contrib import messages
from django.db import models
from decimal import Decimal, InvalidOperation
from .models import Section, Activity, ActivitySubmission, SectionEnrollment, ActivityPassenger, ActivityAddOn
from flightapp.models import User, Student  # Add these imports
from django.db import models, connection
from collections import defaultdict


# Helper function for session-based authentication
def get_current_user(request):
    """Get the current user from session"""
    user_id = request.session.get('user_id')
    if user_id:
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None
    return None

def is_instructor(user):
    """Check if user is instructor"""
    return user and user.role == 'instructor'

# Authentication Views
def instructor_login(request):
    # If already logged in, redirect to home
    if get_current_user(request):
        return redirect('instructor_home')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(username=username)
            if user.password == password:
                # Manual session-based login
                request.session['user_id'] = user.id
                request.session['username'] = user.username
                request.session['role'] = user.role
                request.session.set_expiry(86400)  # 24 hours
                
                messages.success(request, f'Welcome back {username}!')
                return redirect('instructor_home')
            else:
                messages.error(request, 'Invalid credentials')
        except User.DoesNotExist:
            messages.error(request, 'User does not exist')
    
    template = loader.get_template('instructorapp/auth/login.html')
    context = {}
    return HttpResponse(template.render(context, request))

def instructor_register(request):
    # If already logged in, redirect to home
    if get_current_user(request):
        return redirect('instructor_home')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        role = 'instructor'
        
        # Validation
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
        else:
            user = User.objects.create(
                username=username,
                email=email,
                password=password,
                role=role
            )
            # Manual session-based login after registration
            request.session['user_id'] = user.id
            request.session['username'] = user.username
            request.session['role'] = user.role
            request.session.set_expiry(86400)  # 24 hours
            
            messages.success(request, f'Account created successfully! Welcome {username}')
            return redirect('instructor_home')
    
    template = loader.get_template('instructorapp/auth/register.html')
    context = {}
    return HttpResponse(template.render(context, request))

def logout_view(request):
    # Manual logout
    request.session.flush()
    messages.success(request, 'You have been logged out successfully.')
    return redirect('instructor_login')

# Instructor Views
def instructor_home(request):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    # Handle section creation from modal form
    if request.method == 'POST':
        section_name = request.POST.get('section_name')
        section_code = request.POST.get('section_code')
        semester = request.POST.get('semester')
        academic_year = request.POST.get('academic_year')
        schedule = request.POST.get('schedule')
        description = request.POST.get('description')
        
        # Basic validation
        if not section_name or not section_code or not semester or not academic_year:
            messages.error(request, 'Please fill all required fields')
        elif Section.objects.filter(section_code=section_code).exists():
            messages.error(request, 'Section code already exists')
        else:
            # Create section
            section = Section.objects.create(
                section_name=section_name,
                section_code=section_code,
                semester=semester,
                academic_year=academic_year,
                schedule=schedule,
                description=description,
                instructor=user
            )
            messages.success(request, f'Section {section.section_code} created successfully!')
            return redirect('instructor_home')
    
    sections = Section.objects.filter(instructor=user)
    activities = Activity.objects.filter(section__instructor=user)
    
    template = loader.get_template('instructorapp/instructor/home.html')
    context = {
        'sections': sections,
        'activities': activities,
        'total_students': SectionEnrollment.objects.filter(section__instructor=user).count(),
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def instructor_section(request):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    # Handle section creation
    if request.method == 'POST':
        section_name = request.POST.get('section_name')
        section_code = request.POST.get('section_code')
        semester = request.POST.get('semester')
        academic_year = request.POST.get('academic_year')
        schedule = request.POST.get('schedule')
        description = request.POST.get('description')
        
        # Basic validation
        if not section_name or not section_code or not semester or not academic_year:
            messages.error(request, 'Please fill all required fields')
        elif Section.objects.filter(section_code=section_code).exists():
            messages.error(request, 'Section code already exists')
        else:
            # Create section
            section = Section.objects.create(
                section_name=section_name,
                section_code=section_code,
                semester=semester,
                academic_year=academic_year,
                schedule=schedule,
                description=description,
                instructor=user
            )
            messages.success(request, f'Section {section.section_code} created successfully!')
            return redirect('instructor_section')
    
    sections = Section.objects.filter(instructor=user)
    
    template = loader.get_template('instructorapp/instructor/section_detail.html')
    context = {
        'sections': sections,
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def instructor_activity(request):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    activities = Activity.objects.filter(section__instructor=user)
    
    template = loader.get_template('instructorapp/instructor/activity/activity.html')
    context = {
        'activities': activities,
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def create_activity(request, section_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    section = get_object_or_404(Section, id=section_id, instructor=user)
    
    # Get available add-ons for the form
    from flightapp.models import AddOn, Airline
    
    airlines = Airline.objects.all()
    addons = AddOn.objects.select_related('type', 'airline').filter(included=False)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        activity_type = request.POST.get('activity_type', 'Flight Booking')
        required_trip_type = request.POST.get('required_trip_type', 'one_way')
        required_origin = request.POST.get('required_origin', '')
        required_destination = request.POST.get('required_destination', '')
        required_departure_date = request.POST.get('required_departure_date')
        required_return_date = request.POST.get('required_return_date')
        required_travel_class = request.POST.get('required_travel_class', 'economy')
        
        # Passenger counts - with proper default handling
        required_passengers = request.POST.get('required_passengers', '1')
        required_children = request.POST.get('required_children', '0')
        required_infants = request.POST.get('required_infants', '0')
        
        # Passenger information requirements
        require_passenger_details = request.POST.get('require_passenger_details') == 'on'
        
        required_max_price = request.POST.get('required_max_price')
        instructions = request.POST.get('instructions')
        total_points = request.POST.get('total_points', '100')
        due_date = request.POST.get('due_date')
        time_limit_minutes = request.POST.get('time_limit_minutes')
        
        # Add-on requirements
        require_addons = request.POST.get('require_addons') == 'on'
        
        # NEW: Collect per-passenger add-on requirements for ALL addons
        passenger_addon_requirements = {}

        # Get passenger count from form
        passenger_first_names = request.POST.getlist('passenger_first_name[]')
        passenger_count = len(passenger_first_names)

        # Get ALL selected addons (not per passenger)
        all_selected_addons = request.POST.getlist('selected_addons[]')

        # Collect per-passenger add-on requirements for ALL selected addons
        for passenger_index in range(passenger_count):
            passenger_addons = {}
            
            for addon_id in all_selected_addons:
                # Check if this addon is required for this specific passenger
                is_required = request.POST.get(f'addon_required_{addon_id}_passenger_{passenger_index}') == 'on'
                quantity = request.POST.get(f'addon_quantity_{addon_id}_passenger_{passenger_index}', '1')
                notes = request.POST.get(f'addon_notes_{addon_id}_passenger_{passenger_index}', '')
                
                # Only store if this addon is selected for this passenger
                if is_required:
                    passenger_addons[addon_id] = {
                        'is_required': is_required,
                        'quantity': int(quantity) if quantity and quantity.isdigit() else 1,
                        'notes': notes
                    }
            passenger_addon_requirements[passenger_index] = passenger_addons
        
        # Basic validation
        if not title or not instructions or not due_date:
            messages.error(request, 'Please fill all required fields')
            return redirect('section_detail', section_id=section_id)
        
        try:
            # Convert passenger counts with error handling
            required_passengers_int = int(required_passengers) if required_passengers and required_passengers.strip() else 1
            required_children_int = int(required_children) if required_children and required_children.strip() else 0
            required_infants_int = int(required_infants) if required_infants and required_infants.strip() else 0
            
            # Validate passenger counts
            if required_passengers_int < 1:
                messages.error(request, 'At least one adult passenger is required')
                return redirect('section_detail', section_id=section_id)
            
            # Validate infants don't exceed adults
            if required_infants_int > required_passengers_int:
                messages.error(request, 'Number of infants cannot exceed number of adults')
                return redirect('section_detail', section_id=section_id)
            
            # Create activity with addon_grading_enabled
            activity = Activity.objects.create(
                title=title,
                description=description or "",
                activity_type=activity_type,
                section=section,
                required_trip_type=required_trip_type,
                required_origin=required_origin,
                required_destination=required_destination,
                required_departure_date=required_departure_date if required_departure_date else None,
                required_return_date=required_return_date if required_return_date else None,
                required_travel_class=required_travel_class,
                required_passengers=required_passengers_int,
                required_children=required_children_int,
                required_infants=required_infants_int,
                require_passenger_details=require_passenger_details,
                required_max_price=float(required_max_price) if required_max_price and required_max_price.strip() else None,
                instructions=instructions,
                total_points=float(total_points) if total_points and total_points.strip() else 100.00,
                due_date=due_date,
                time_limit_minutes=int(time_limit_minutes) if time_limit_minutes and time_limit_minutes.strip() else None,
                addon_grading_enabled=require_addons,  # Enable grading if add-ons are required
            )
            
            # Handle passenger details if required
            passenger_objects = []
            if require_passenger_details:
                passenger_first_names = request.POST.getlist('passenger_first_name[]')
                passenger_middle_names = request.POST.getlist('passenger_middle_name[]')
                passenger_last_names = request.POST.getlist('passenger_last_name[]')
                passenger_genders = request.POST.getlist('passenger_gender[]')
                passenger_dobs = request.POST.getlist('passenger_dob[]')
                passenger_nationalities = request.POST.getlist('passenger_nationality[]')
                
                # Create passenger objects only for valid entries
                passengers_created = 0
                for i in range(len(passenger_first_names)):
                    # Check if all required fields are filled
                    if (passenger_first_names[i].strip() and 
                        passenger_last_names[i].strip() and 
                        passenger_genders[i] and 
                        passenger_dobs[i] and 
                        passenger_nationalities[i].strip()):
                        
                        passenger = ActivityPassenger.objects.create(
                            activity=activity,
                            first_name=passenger_first_names[i].strip(),
                            middle_name=passenger_middle_names[i].strip() if passenger_middle_names[i] else None,
                            last_name=passenger_last_names[i].strip(),
                            gender=passenger_genders[i],
                            date_of_birth=passenger_dobs[i],
                            nationality=passenger_nationalities[i].strip(),
                            is_primary=(i == 0)  # First passenger is primary
                        )
                        passenger_objects.append(passenger)
                        passengers_created += 1
                
                if passengers_created == 0 and require_passenger_details:
                    messages.warning(request, 'Activity created but no passenger details were provided despite the requirement.')
            
            # NEW: Handle PER-PASSENGER add-on requirements with points
            if require_addons and all_selected_addons and passenger_objects:
                addons_created = 0
                
                # For each passenger, create their specific add-on requirements
                for passenger_index, passenger in enumerate(passenger_objects):
                    passenger_requirements = passenger_addon_requirements.get(passenger_index, {})
                    
                    for addon_id, requirements in passenger_requirements.items():
                        try:
                            addon = AddOn.objects.get(id=addon_id)
                            
                            ActivityAddOn.objects.create(
                                activity=activity,
                                addon=addon,
                                passenger=passenger,  # Link to specific passenger
                                is_required=requirements.get('is_required', False),
                                quantity_per_passenger=requirements.get('quantity', 1),
                                points_value=10.00,  # SET DEFAULT POINTS VALUE FOR GRADING
                                notes=requirements.get('notes', '')
                            )
                            addons_created += 1
                                
                        except AddOn.DoesNotExist:
                            messages.warning(request, f'Add-on with ID {addon_id} not found and was skipped.')
                
                if addons_created > 0:
                    messages.success(request, f'Activity created with {addons_created} passenger-specific add-on requirements!')
                else:
                    messages.warning(request, 'Activity created but no valid add-ons were selected for any passenger.')
            elif require_addons and not all_selected_addons:
                messages.warning(request, 'Activity created but no add-ons were selected despite the requirement.')
            elif require_addons and not passenger_objects:
                messages.warning(request, 'Activity created but no passengers were defined for add-on assignment.')
            else:
                messages.success(request, f'Activity "{activity.title}" created successfully!')
            
            return redirect('section_detail', section_id=section_id)
            
        except ValueError as e:
            messages.error(request, f'Invalid number format: {str(e)}')
            return redirect('section_detail', section_id=section_id)
        except Exception as e:
            messages.error(request, f'Error creating activity: {str(e)}')
            return redirect('section_detail', section_id=section_id)
    
    # If GET request, redirect to section detail
    return redirect('section_detail', section_id=section_id)

def section_detail(request, section_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    section = get_object_or_404(Section, id=section_id, instructor=user)
    enrollments = SectionEnrollment.objects.filter(section=section)
    activities = Activity.objects.filter(section=section)
    
    # Get airports and add-ons from flightapp
    from flightapp.models import Airport, AddOn, Airline
    airports = Airport.objects.all()
    airlines = Airline.objects.all()
    
    # FILTER: Only show add-ons that are NOT included (included=False)
    addons = AddOn.objects.select_related('type', 'airline').filter(included=False)
    
    # Handle student enrollment
    if request.method == 'POST' and 'enroll_student' in request.POST:
        student_number = request.POST.get('student_number')
        try:
            student = Student.objects.get(student_number=student_number)
            if not SectionEnrollment.objects.filter(section=section, student=student).exists():
                SectionEnrollment.objects.create(section=section, student=student)
                messages.success(request, f'Student {student.student_number} enrolled successfully!')
            else:
                messages.warning(request, f'Student {student.student_number} is already enrolled.')
        except Student.DoesNotExist:
            messages.error(request, f'Student with number {student_number} not found.')
        return redirect('section_detail', section_id=section_id)
    
    template = loader.get_template('instructorapp/instructor/section_detail.html')
    context = {
        'section': section,
        'enrollments': enrollments,
        'activities': activities,
        'airports': airports,
        'airlines': airlines,
        'addons': addons,  # Add add-ons to context
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def edit_activity(request, activity_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    activity = get_object_or_404(Activity, id=activity_id, section__instructor=user)
    
    # Get available add-ons for the form
    from flightapp.models import AddOn, Airline, Airport
    
    airlines = Airline.objects.all()
    addons = AddOn.objects.select_related('type', 'airline').filter(included=False)
    airports = Airport.objects.all()
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        activity_type = request.POST.get('activity_type', 'Flight Booking')
        required_trip_type = request.POST.get('required_trip_type', 'one_way')
        required_origin = request.POST.get('required_origin', '')
        required_destination = request.POST.get('required_destination', '')
        required_departure_date = request.POST.get('required_departure_date')
        required_return_date = request.POST.get('required_return_date')
        required_travel_class = request.POST.get('required_travel_class', 'economy')
        
        # Passenger counts - with proper default handling
        required_passengers = request.POST.get('required_passengers', '1')
        required_children = request.POST.get('required_children', '0')
        required_infants = request.POST.get('required_infants', '0')
        
        # Passenger information requirements
        require_passenger_details = request.POST.get('require_passenger_details') == 'on'
        
        required_max_price = request.POST.get('required_max_price')
        instructions = request.POST.get('instructions')
        total_points = request.POST.get('total_points', '100')
        due_date = request.POST.get('due_date')
        time_limit_minutes = request.POST.get('time_limit_minutes')
        
        # Add-on requirements - PER PASSENGER
        require_addons = request.POST.get('require_addons') == 'on'
        
        # NEW: Collect per-passenger add-on requirements for ALL passengers
        passenger_addon_requirements = {}

        # Get passenger count from form
        passenger_first_names = request.POST.getlist('passenger_first_name[]')
        passenger_count = len(passenger_first_names)

        # Get ALL selected addons for each passenger
        for passenger_index in range(passenger_count):
            passenger_addons = {}
            
            # Get addons selected for this specific passenger
            selected_addons_for_passenger = request.POST.getlist(f'selected_addons_passenger_{passenger_index}[]')
            
            for addon_id in selected_addons_for_passenger:
                # Check if this addon is required for this specific passenger
                is_required = request.POST.get(f'addon_required_{addon_id}_passenger_{passenger_index}') == 'on'
                quantity = request.POST.get(f'addon_quantity_{addon_id}_passenger_{passenger_index}', '1')
                notes = request.POST.get(f'addon_notes_{addon_id}_passenger_{passenger_index}', '')
                
                passenger_addons[addon_id] = {
                    'is_required': is_required,
                    'quantity': int(quantity) if quantity and quantity.isdigit() else 1,
                    'notes': notes
                }
            
            passenger_addon_requirements[passenger_index] = passenger_addons
        
        # Basic validation
        if not title or not instructions or not due_date:
            messages.error(request, 'Please fill all required fields')
            return redirect('edit_activity', activity_id=activity_id)
        
        try:
            # Convert passenger counts with error handling
            required_passengers_int = int(required_passengers) if required_passengers else 1
            required_children_int = int(required_children) if required_children else 0
            required_infants_int = int(required_infants) if required_infants else 0
            
            # Validate passenger counts
            if required_passengers_int < 1:
                messages.error(request, 'At least one adult passenger is required')
                return redirect('edit_activity', activity_id=activity_id)
            
            # Validate infants don't exceed adults
            if required_infants_int > required_passengers_int:
                messages.error(request, 'Number of infants cannot exceed number of adults')
                return redirect('edit_activity', activity_id=activity_id)
            
            # Update activity with addon_grading_enabled
            activity.title = title
            activity.description = description or ""
            activity.activity_type = activity_type
            activity.required_trip_type = required_trip_type
            activity.required_origin = required_origin
            activity.required_destination = required_destination
            activity.required_departure_date = required_departure_date if required_departure_date else None
            activity.required_return_date = required_return_date if required_return_date else None
            activity.required_travel_class = required_travel_class
            activity.required_passengers = required_passengers_int
            activity.required_children = required_children_int
            activity.required_infants = required_infants_int
            activity.require_passenger_details = require_passenger_details
            activity.required_max_price = float(required_max_price) if required_max_price else None
            activity.instructions = instructions
            activity.total_points = float(total_points) if total_points else 100.00
            activity.due_date = due_date
            activity.time_limit_minutes = int(time_limit_minutes) if time_limit_minutes else None
            activity.addon_grading_enabled = require_addons  # Update grading setting
            
            activity.save()
            
            # Handle passenger details if required
            passenger_objects = []
            if require_passenger_details:
                # Delete existing passengers
                activity.passengers.all().delete()
                
                passenger_first_names = request.POST.getlist('passenger_first_name[]')
                passenger_middle_names = request.POST.getlist('passenger_middle_name[]')
                passenger_last_names = request.POST.getlist('passenger_last_name[]')
                passenger_genders = request.POST.getlist('passenger_gender[]')
                passenger_dobs = request.POST.getlist('passenger_dob[]')
                passenger_nationalities = request.POST.getlist('passenger_nationality[]')
                passenger_is_primary = request.POST.getlist('passenger_is_primary[]')
                
                # Create passenger objects only for valid entries
                for i in range(len(passenger_first_names)):
                    # Check if all required fields are filled
                    if (passenger_first_names[i].strip() and 
                        passenger_last_names[i].strip() and 
                        passenger_genders[i] and 
                        passenger_dobs[i] and 
                        passenger_nationalities[i].strip()):
                        
                        # Determine if this passenger is primary
                        is_primary = str(i) in passenger_is_primary
                        
                        passenger = ActivityPassenger.objects.create(
                            activity=activity,
                            first_name=passenger_first_names[i].strip(),
                            middle_name=passenger_middle_names[i].strip() if passenger_middle_names[i] else None,
                            last_name=passenger_last_names[i].strip(),
                            gender=passenger_genders[i],
                            date_of_birth=passenger_dobs[i],
                            nationality=passenger_nationalities[i].strip(),
                            is_primary=is_primary
                        )
                        passenger_objects.append(passenger)
            
            # NEW: Handle PER-PASSENGER add-on requirements with points
            # Delete existing add-ons
            activity.activity_addons.all().delete()
            
            if require_addons and passenger_objects:
                addons_created = 0
                
                # For each passenger, create their specific add-on requirements
                for passenger_index, passenger in enumerate(passenger_objects):
                    passenger_requirements = passenger_addon_requirements.get(passenger_index, {})
                    
                    for addon_id, requirements in passenger_requirements.items():
                        try:
                            addon = AddOn.objects.get(id=addon_id)
                            
                            ActivityAddOn.objects.create(
                                activity=activity,
                                addon=addon,
                                passenger=passenger,  # Link to specific passenger
                                is_required=requirements.get('is_required', False),
                                quantity_per_passenger=requirements.get('quantity', 1),
                                points_value=10.00,  # SET DEFAULT POINTS VALUE FOR GRADING
                                notes=requirements.get('notes', '')
                            )
                            addons_created += 1
                                
                        except AddOn.DoesNotExist:
                            messages.warning(request, f'Add-on with ID {addon_id} not found and was skipped.')
                
                if addons_created > 0:
                    messages.success(request, f'Activity updated with {addons_created} passenger-specific add-on requirements!')
                else:
                    messages.warning(request, 'Activity updated but no add-ons were selected for any passenger.')
            elif require_addons and not passenger_objects:
                messages.warning(request, 'Activity updated but no passengers were defined for add-on assignment.')
            else:
                messages.success(request, f'Activity "{activity.title}" updated successfully!')
            
            return redirect('section_detail', section_id=activity.section.id)
            
        except Exception as e:
            messages.error(request, f'Error updating activity: {str(e)}')
            return redirect('edit_activity', activity_id=activity_id)
    
    # Prepare context for existing add-ons data
    existing_addon_data = {}
    for addon_req in activity.activity_addons.all():
        if addon_req.passenger:
            passenger_id = addon_req.passenger.id
            if passenger_id not in existing_addon_data:
                existing_addon_data[passenger_id] = []
            existing_addon_data[passenger_id].append({
                'addon_id': addon_req.addon.id,
                'is_required': addon_req.is_required,
                'quantity': addon_req.quantity_per_passenger,
                'notes': addon_req.notes
            })
    
    template = loader.get_template('instructorapp/instructor/activity/edit_activity.html')
    context = {
        'activity': activity,
        'airports': airports,
        'addons': addons,
        'existing_addon_data': existing_addon_data,
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def delete_activity(request, activity_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    activity = get_object_or_404(Activity, id=activity_id, section__instructor=user)
    
    if request.method == 'POST':
        activity_title = activity.title
        section_id = activity.section.id
        activity.delete()
        messages.success(request, f'Activity "{activity_title}" deleted successfully!')
        return redirect('section_detail', section_id=section_id)
    
    # If GET request, return JSON for modal
    return JsonResponse({
        'title': activity.title,
        'section_code': activity.section.section_code,
        'activity_type': activity.activity_type,
        'due_date': activity.due_date.strftime("%B %d, %Y"),
        'submissions_count': activity.submissions.count()
    })

def activate_activity(request, activity_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    activity = get_object_or_404(Activity, id=activity_id, section__instructor=user)
    
    if request.method == 'POST':
        activity.activate_code()
        messages.success(request, f'Activity code activated: {activity.activity_code}')
    
    return redirect('section_detail', section_id=activity.section.id)

def activity_detail(request, activity_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    activity = get_object_or_404(Activity, id=activity_id, section__instructor=user)
    
    # Get additional context for the template
    total_passengers = activity.get_total_passengers()
    has_passenger_details = activity.passengers.exists()
    
    template = loader.get_template('instructorapp/instructor/activity/activity_detail.html')
    context = {
        'activity': activity,
        'total_passengers': total_passengers,
        'has_passenger_details': has_passenger_details,
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def activity_submissions(request, activity_id):
    user = get_current_user(request)
    if not user:
        return redirect('instructor_login')
    
    if not is_instructor(user):
        messages.error(request, 'Access denied. Instructor role required.')
        return redirect('instructor_login')
    
    print(f"=== ACTIVITY_SUBMISSIONS DEBUG ===")
    print(f"Requested activity_id: {activity_id}")
    print(f"Current user: {user.username} (ID: {user.id})")
    print(f"User role: {user.role}")
    
    # First, try to get the activity without instructor filter to see if it exists
    try:
        activity = Activity.objects.get(id=activity_id)
        print(f"Activity exists: {activity.title} (ID: {activity.id})")
        print(f"Activity section instructor: {activity.section.instructor.username} (ID: {activity.section.instructor.id})")
        
        # Check if current user owns this activity
        if activity.section.instructor.id != user.id:
            print(f"❌ ACCESS DENIED: Activity belongs to instructor {activity.section.instructor.id}, but current user is {user.id}")
            messages.error(request, "You don't have permission to view submissions for this activity.")
            return redirect('instructor_home')
            
        print(f"✅ ACCESS GRANTED: User {user.id} owns this activity")
        
    except Activity.DoesNotExist:
        print(f"❌ Activity {activity_id} not found")
        messages.error(request, "Activity not found.")
        return redirect('instructor_home')
    
    # Now get submissions for this activity
    submissions = ActivitySubmission.objects.filter(activity=activity)
    print(f"Submissions found: {submissions.count()}")
    
    for sub in submissions:
        print(f"  - Submission {sub.id}: Student {sub.student.first_name}, Booking {sub.booking.id if sub.booking else 'None'}")
    
    template = loader.get_template('instructorapp/instructor/activity/activity_submissions.html')
    context = {
        'activity': activity,
        'submissions': submissions,
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def manage_addon_points(request, activity_id):
    """View to manage points for activity add-ons"""
    user = get_current_user(request)
    if not user or not is_instructor(user):
        messages.error(request, 'Access denied.')
        return redirect('instructor_login')
    
    activity = get_object_or_404(Activity, id=activity_id, section__instructor=user)
    
    if request.method == 'POST':
        # Update add-on points
        for addon_req in activity.activity_addons.all():
            points_field = f'points_{addon_req.id}'
            if points_field in request.POST:
                try:
                    points_value = Decimal(request.POST[points_field])
                    addon_req.points_value = points_value
                    addon_req.save()
                except (ValueError, InvalidOperation):
                    messages.error(request, f'Invalid points value for {addon_req.addon.name}')
        
        messages.success(request, 'Add-on points updated successfully!')
        return redirect('section_detail', section_id=activity.section.id)
    
    template = loader.get_template('instructorapp/instructor/activity/manage_addon_points.html')
    context = {
        'activity': activity,
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def debug_submissions(request):
    """Debug view to check all ActivitySubmission data"""
    user = get_current_user(request)
    if not user or not is_instructor(user):
        messages.error(request, 'Access denied.')
        return redirect('instructor_login')
    
    # Get all submissions with related data
    submissions = ActivitySubmission.objects.select_related(
        'activity', 'student', 'booking'
    ).all()
    
    # Get activities with submission counts
    activities = Activity.objects.annotate(
        submission_count=models.Count('submissions')
    )
    
    template = loader.get_template('instructorapp/debug_submissions.html')
    context = {
        'submissions': submissions,
        'activities': activities,
        'total_submissions': submissions.count(),
        'current_user': user,
    }
    return HttpResponse(template.render(context, request))

def debug_session(request):
    """Temporary debug view to check session and user info"""
    user = get_current_user(request)
    
    print("=== SESSION DEBUG ===")
    for key, value in request.session.items():
        print(f"{key}: {value}")
    
    print(f"Current user from session: {user}")
    if user:
        print(f"User ID: {user.id}, Username: {user.username}, Role: {user.role}")
    
    # Check all instructors
    instructors = User.objects.filter(role='instructor')
    print("=== ALL INSTRUCTORS ===")
    for instructor in instructors:
        print(f"ID: {instructor.id}, Username: {instructor.username}")
    
    return HttpResponse("Check console for debug output")

    
def index(request, activity_id):
    """View to display student work comparison"""
    activity = get_object_or_404(Activity, id=activity_id)
    
    # Get airports for the template if needed
    from flightapp.models import Airport
    airports = Airport.objects.all()
    
    context = {
        'activity': activity,
        'airports': airports,
        'activity_id': activity.id,  # ✅ Add this line
    }
    
    return render(request, 'instructorapp/instructor/submission/index.html', context)

def activity_submissions_api(request, activity_id=None):
    """
    Returns submissions with multi-passenger support.
    Matching algorithm: For each student passenger, find the best-matching
    correct passenger (by comparing fields). Matching is order-independent.
    """

    # ============================================================
    # 1. MAIN QUERY — NO passenger join to avoid duplicates
    # ============================================================
    query = """
        SELECT 
            s.id AS submission_id,
            s.activity_id AS activity_id,
            st.id AS student_school_id,
            st.last_name AS student_name,
            st.student_number AS student_number,
            s.submitted_at,
            s.score,
            s.feedback,
            s.status AS submission_status,

            a.title AS activity_title,
            a.total_points AS activity_total_points,

            s.required_trip_type AS student_trip_type,
            a.required_trip_type AS correct_trip_type,

            s.required_travel_class AS student_travel_class,
            a.required_travel_class AS correct_travel_class,

            sa.code AS student_origin,
            a.required_origin AS correct_origin,

            da.code AS student_destination,
            a.required_destination AS correct_destination,

            s.required_passengers AS student_adults,
            a.required_passengers AS correct_adults,

            s.required_children AS student_children,
            a.required_children AS correct_children,

            s.required_infants AS student_infants,
            a.required_infants AS correct_infants,

            s.required_max_price AS student_max_price,
            a.required_max_price AS correct_max_price

        FROM instructorapp_activitysubmission s
        JOIN instructorapp_activity a ON s.activity_id = a.id
        JOIN flightapp_student st ON s.student_id = st.id
        LEFT JOIN flightapp_airport sa ON sa.id = s.required_origin_airport_id
        LEFT JOIN flightapp_airport da ON da.id = s.required_destination_airport_id
    """

    params = []
    if activity_id:
        query += " WHERE s.activity_id = %s"
        params.append(activity_id)

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    # ============================================================
    # 2. GET CORRECT PASSENGERS PER ACTIVITY
    # ============================================================
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                activity_id,
                first_name, middle_name, last_name,
                gender, date_of_birth, nationality
            FROM instructorapp_activitypassenger
            ORDER BY activity_id, id
        """)
        correct_rows = cursor.fetchall()
        correct_cols = [col[0] for col in cursor.description]

    correct_passenger_map = defaultdict(list)
    for p in correct_rows:
        # p[0] is activity_id
        correct_passenger_map[p[0]].append(dict(zip(correct_cols, p)))

    # ============================================================
    # 3. GET STUDENT PASSENGERS PER SUBMISSION
    # ============================================================
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                activity_submission_id,
                first_name, middle_name, last_name,
                gender, date_of_birth, nationality
            FROM instructorapp_activitysubmission_passenger
            ORDER BY activity_submission_id, id
        """)
        student_pax_rows = cursor.fetchall()
        student_pax_cols = [col[0] for col in cursor.description]

    student_passenger_map = defaultdict(list)
    for p in student_pax_rows:
        sid = p[0]
        student_passenger_map[sid].append(dict(zip(student_pax_cols, p)))

    # ============================================================
    # 4. BUILD JSON RESPONSE
    # ============================================================
    data = []
    # We'll give each passenger detail equal weight. 6 fields -> total passenger points ≈ 10.
    FIELD_POINTS = 10.0 / 6.0  # ~1.6666667 per-field

    # helper to normalize values for comparison
    def norm(v):
        if v is None:
            return ""
        # dates may come as date objects; convert to iso string
        return str(v).strip().lower()

    for row in rows:
        r = dict(zip(columns, row))
        sid = r["submission_id"]
        this_activity_id = r["activity_id"]

        correct_passengers_orig = correct_passenger_map.get(this_activity_id, [])
        # we will not mutate original map; make a list of indices for matching
        correct_indices_available = list(range(len(correct_passengers_orig)))

        # copy correct_passengers for easy lookup
        correct_passengers = correct_passengers_orig[:]  # shallow copy

        student_passengers = student_passenger_map.get(sid, [])

        passenger_correctness = []
        passenger_points = []
        passenger_total = 0.0

        # For each student passenger, find the best matching correct passenger (by max field matches)
        for sp in student_passengers:
            # compute normalized values for student
            best_idx = None
            best_matches = -1

            for j in correct_indices_available:
                cp = correct_passengers[j]
                # count matching fields (case-insensitive, trimmed)
                matches = 0
                for field in ("first_name", "middle_name", "last_name", "gender", "date_of_birth", "nationality"):
                    if norm(sp.get(field)) != "" and norm(sp.get(field)) == norm(cp.get(field)):
                        matches += 1
                # prefer a candidate with more matches
                if matches > best_matches:
                    best_matches = matches
                    best_idx = j

            # take the matched correct passenger if it has at least 1 match; else empty dict
            matched_cp = {}
            if best_idx is not None and best_matches > 0:
                matched_cp = correct_passengers[best_idx]
                # remove index from available list so it's not matched again
                correct_indices_available.remove(best_idx)

            # now compute per-field correctness and points vs matched_cp
            correctness = {}
            points = {}
            for field in ("first_name", "middle_name", "last_name", "gender", "date_of_birth", "nationality"):
                is_correct = norm(sp.get(field)) == norm(matched_cp.get(field))
                correctness[field] = "Correct" if is_correct else "Wrong"
                points[f"{field}_points"] = FIELD_POINTS if is_correct else 0.0

            passenger_correctness.append(correctness)
            passenger_points.append(points)
            passenger_total += sum(points.values())

        # ============================================================
        # 5. CALCULATE FINAL SCORE (sum of all field points)
        # ============================================================
        base_points = (
            (10 if r["student_trip_type"] == r["correct_trip_type"] else 0) +
            (10 if r["student_travel_class"] == r["correct_travel_class"] else 0) +
            (10 if r["student_origin"] == r["correct_origin"] else 0) +
            (10 if r["student_destination"] == r["correct_destination"] else 0) +
            (10 if r["student_adults"] == r["correct_adults"] else 0) +
            (10 if r["student_children"] == r["correct_children"] else 0) +
            (10 if r["student_infants"] == r["correct_infants"] else 0) +
            (10 if r["student_max_price"] == r["correct_max_price"] else 0)
        )

        final_score = base_points + passenger_total

        # ============================================================
        # 6. SAVE FINAL SCORE TO DATABASE
        # ============================================================
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE instructorapp_activitysubmission SET score = %s WHERE id = %s",
                [final_score, sid]
            )

        # also overwrite score in the response
        r["score"] = final_score    

        # If there are correct_passengers that were not matched at all (student provided fewer),
        # we may want to show them in correct_answers (we already include correct_passengers below).
        expected_total = len(correct_passengers_orig) * (FIELD_POINTS * 6)

        # compute result_status: try to determine Passed/Failed via score vs activity total (70% threshold).
        result_status = None
        try:
            if r.get("score") is not None and r.get("activity_total_points") is not None:
                pct = float(r["score"]) / float(r["activity_total_points"]) if float(r["activity_total_points"]) != 0 else 0
                result_status = "Passed" if pct >= 0.7 else "Failed"
        except Exception:
            result_status = None
        if result_status is None:
            # fallback to submission_status or N/A
            result_status = r.get("submission_status") or "N/A"

        data.append({
            "submission_id": sid,
            "student_id": r["student_school_id"],
            "student_name": r["student_name"],
            "student_number": r["student_number"],
            "submitted_at": r["submitted_at"],
            "score": r["score"],
            "feedback": r["feedback"],
            "submission_status": r["submission_status"],
            "result_status": result_status,
            "activity_title": r["activity_title"],

            "answers": {
                "trip_type": r["student_trip_type"],
                "travel_class": r["student_travel_class"],
                "origin": r["student_origin"],
                "destination": r["student_destination"],
                "adults": r["student_adults"],
                "children": r["student_children"],
                "infants": r["student_infants"],
                "max_price": r["student_max_price"],
                "passengers": student_passengers,
            },

            "correct_answers": {
                "trip_type": r["correct_trip_type"],
                "travel_class": r["correct_travel_class"],
                "origin": r["correct_origin"],
                "destination": r["correct_destination"],
                "adults": r["correct_adults"],
                "children": r["correct_children"],
                "infants": r["correct_infants"],
                "max_price": r["correct_max_price"],
                "passengers": correct_passengers_orig,
            },

            "points": {
                "trip_type": 10 if r["student_trip_type"] == r["correct_trip_type"] else 0,
                "travel_class": 10 if r["student_travel_class"] == r["correct_travel_class"] else 0,
                "origin": 10 if r["student_origin"] == r["correct_origin"] else 0,
                "destination": 10 if r["student_destination"] == r["correct_destination"] else 0,
                "adults": 10 if r["student_adults"] == r["correct_adults"] else 0,
                "children": 10 if r["student_children"] == r["correct_children"] else 0,
                "infants": 10 if r["student_infants"] == r["correct_infants"] else 0,
                "max_price": 10 if r["student_max_price"] == r["correct_max_price"] else 0,

                "passenger_details": passenger_points,
                "passenger_total": passenger_total,
            },

            "correctness": {
                "trip_type": "Correct" if r["student_trip_type"] == r["correct_trip_type"] else "Wrong",
                "travel_class": "Correct" if r["student_travel_class"] == r["correct_travel_class"] else "Wrong",
                "origin": "Correct" if r["student_origin"] == r["correct_origin"] else "Wrong",
                "destination": "Correct" if r["student_destination"] == r["correct_destination"] else "Wrong",
                "adults": "Correct" if r["student_adults"] == r["correct_adults"] else "Wrong",
                "children": "Correct" if r["student_children"] == r["correct_children"] else "Wrong",
                "infants": "Correct" if r["student_infants"] == r["correct_infants"] else "Wrong",
                "max_price": "Correct" if r["student_max_price"] == r["correct_max_price"] else "Wrong",

                "passenger": passenger_correctness,
                "passenger_summary": "Correct" if abs(passenger_total - expected_total) < 0.0001 else "Wrong",
            },
        })

    return JsonResponse(data, safe=False)