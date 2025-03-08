# schedule.py
from datetime import date, timedelta
from models import PickupRequest, ServiceSchedule  # or wherever these are coming from

def get_service_schedule():
    """
    Returns a list of ServiceSchedule entries for all 7 days of the week
    (or however many you choose to store).
    """
    return ServiceSchedule.query.order_by(ServiceSchedule.id).all()

def build_schedule(offset: int = 0):
    """
    Returns a tuple of (days_list, base_date_str).

    days_list is a list of dictionaries with the following structure:
    {
        'date_obj': <python date>,
        'date_str': "e.g. Jan. 11",
        'day_of_week': "e.g. Saturday",
        'slots': [ (start,end), (start2,end2) ]
    }
    
    base_date_str is a string representation of the base date,
    e.g. 'Jan. 01'
    """

    # Ensure offset is within 0..2
    if offset < 0:
        offset = 0
    if offset > 2:
        offset = 2

    # The base date is "today" + X weeks
    base_date = date.today() + timedelta(weeks=offset)
    base_date_str = base_date.strftime("%b. %d")

    schedule_data = get_service_schedule()

    # Create a dict keyed by day_of_week ("monday", "tuesday", etc.)
    schedule_map = {}
    for s in schedule_data:
        schedule_map[s.day_of_week.lower()] = s

    days_list = []
    for i in range(7):
        day_date = base_date + timedelta(days=i)
        # Skip if day_date is the same as "today"
        # (i.e. do not return same-day entries)
        if day_date == date.today():
            continue
        
        day_of_week_str = day_date.strftime("%A").lower()

        if day_of_week_str in schedule_map:
            sched = schedule_map[day_of_week_str]
            if sched.is_available:
                # Build up to 2 time slot entries if they exist
                slots = []
                if sched.slot1_start and sched.slot1_end:
                    slots.append((sched.slot1_start, sched.slot1_end))
                if sched.slot2_start and sched.slot2_end:
                    slots.append((sched.slot2_start, sched.slot2_end))

                if slots:
                    days_list.append({
                        'date_obj': day_date,
                        'date_str': day_date.strftime("%b. %d"),
                        'day_of_week': day_date.strftime("%A"),
                        'slots': slots
                    })

    return days_list, base_date_str
