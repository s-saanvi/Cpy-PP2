# models.py
#-------v2
class Department:
    def __init__(self, id, name):
        self.id = id
        self.name = name

    def __repr__(self):
        return f"Department(id={self.id}, name='{self.name}')"

class Semester:
    def __init__(self, id, semester_number):
        self.id = id
        self.semester_number = semester_number

    def __repr__(self):
        return f"Semester(id={self.id}, number={self.semester_number})"

class Faculty:
    def __init__(self, id, name, emp_id, department_id, department_name=None):
        self.id = id
        self.name = name
        self.emp_id = emp_id
        self.department_id = department_id
        self.department_name = department_name # Optional, for convenience in UI/display

    # To store reference to department object if needed
    def set_department(self, department_obj):
        self.department = department_obj
        self.department_name = department_obj.name

    def __repr__(self):
        return f"Faculty(id={self.id}, name='{self.name}', emp_id='{self.emp_id}', dept_id={self.department_id})"

class Course:
    def __init__(self, id, code, name, hours_per_week, type):
        self.id = id
        self.code = code
        self.name = name
        self.hours_per_week = hours_per_week
        self.type = type # 'theory' or 'lab'

    def __repr__(self):
        return f"Course(id={self.id}, code='{self.code}', name='{self.name}', hours={self.hours_per_week}, type='{self.type}')"

class TheoryMapping:
    def __init__(self, id, semester_id, course_id, faculty_id):
        self.id = id
        self.semester_id = semester_id
        self.course_id = course_id
        self.faculty_id = faculty_id
        # References to actual objects (will be set after loading all data)
        self.semester = None
        self.course = None
        self.faculty = None

    def __repr__(self):
        return f"TheoryMapping(id={self.id}, sem={self.semester.semester_number if self.semester else self.semester_id}, course='{self.course.code if self.course else self.course_id}', faculty='{self.faculty.name if self.faculty else self.faculty_id}')"

class LabMapping:
    def __init__(self, id, semester_id, lab_course_id, faculty_id_1, faculty_id_2):
        self.id = id
        self.semester_id = semester_id
        self.lab_course_id = lab_course_id
        self.faculty_id_1 = faculty_id_1
        self.faculty_id_2 = faculty_id_2
        # References to actual objects
        self.semester = None
        self.lab_course = None
        self.faculty_1 = None
        self.faculty_2 = None

    def __repr__(self):
        return f"LabMapping(id={self.id}, sem={self.semester.semester_number if self.semester else self.semester_id}, lab='{self.lab_course.code if self.lab_course else self.lab_course_id}', fac1='{self.faculty_1.name if self.faculty_1 else self.faculty_id_1}', fac2='{self.faculty_2.name if self.faculty_2 else self.faculty_id_2}')"

class FacultyPreference:
    def __init__(self, id, faculty_id, day, period_start, period_end, preference_type):
        self.id = id
        self.faculty_id = faculty_id
        self.day = day
        self.period_start = period_start
        self.period_end = period_end
        self.preference_type = preference_type # 'blocked' or 'preferred'
        self.faculty = None # Reference to faculty object

    def __repr__(self):
        return f"FacultyPref(id={self.id}, fac='{self.faculty.name if self.faculty else self.faculty_id}', day={self.day}, periods={self.period_start}-{self.period_end}, type='{self.preference_type}')"

# --- Timetable specific models ---
class Timeslot:
    """Represents a single 1-hour period within a day."""
    def __init__(self, day, period):
        self.day = day
        self.period = period # 1 to 6

    def __eq__(self, other):
        return isinstance(other, Timeslot) and self.day == other.day and self.period == other.period

    def __hash__(self):
        return hash((self.day, self.period))

    def __repr__(self):
        return f"Timeslot({self.day},{self.period})"

class Slot:
    """Represents a period block (e.g., Slot 1: Period 1,2). This might be useful for scheduling labs."""
    def __init__(self, day, slot_number, periods): # periods is a list of integers, e.g., [1,2]
        self.day = day
        self.slot_number = slot_number
        self.periods = periods # e.g., [1,2], [3,4], [5,6]

    def __repr__(self):
        return f"Slot({self.day}, Slot {self.slot_number}, Periods {self.periods[0]}-{self.periods[-1]})"

# Represents a single scheduled class in the timetable
class ScheduledClass:
    def __init__(self, semester_id, course_id, faculty_ids, day, start_period, periods_count, is_lab):
        self.semester_id = semester_id
        self.course_id = course_id
        self.faculty_ids = faculty_ids # list of faculty IDs (1 for theory, 2 for lab)
        self.day = day
        self.start_period = start_period # 1 to 6
        self.periods_count = periods_count # e.g., 1 for theory, 2 for lab
        self.is_lab = is_lab

        # Will be set during processing for convenience in GA and display
        self.semester_obj = None
        self.course_obj = None
        self.faculty_objs = [] # List of faculty objects

    @property
    def end_period(self):
        return self.start_period + self.periods_count - 1

    def get_timeslot_range(self):
        """Returns a list of Timeslot objects for this scheduled class."""
        return [Timeslot(self.day, p) for p in range(self.start_period, self.end_period + 1)]

    def copy(self):
        """Creates a deep copy of this ScheduledClass instance."""
        new_sc = ScheduledClass(
            self.semester_id, self.course_id, list(self.faculty_ids), # Copy list of IDs
            self.day, self.start_period, self.periods_count, self.is_lab
        )
        new_sc.semester_obj = self.semester_obj
        new_sc.course_obj = self.course_obj
        new_sc.faculty_objs = list(self.faculty_objs) # Copy list of objects
        return new_sc

    def __repr__(self):
        course_info = self.course_obj.code if self.course_obj else f"Course_{self.course_id}"
        sem_info = self.semester_obj.semester_number if self.semester_obj else f"Sem_{self.semester_id}"
        faculty_info = ", ".join([f.name for f in self.faculty_objs]) if self.faculty_objs else f"Facs_{self.faculty_ids}"
        return f"ScheduledClass(Sem {sem_info}, {course_info}, Fac: {faculty_info}, Day: {self.day}, Periods: {self.start_period}-{self.end_period})"
