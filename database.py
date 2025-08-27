# database.py
import sqlite3
import bcrypt
import json # For serializing/deserializing timetable data as JSON
import base64 # For encoding/decoding JSON data as TEXT for BLOB
from models import (
    Department, Semester, Faculty, Course,
    TheoryMapping, LabMapping, FacultyPreference, ScheduledClass
)

DATABASE_NAME = "timetable.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables with user_id foreign key
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE (user_id, name),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS semesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            semester_number INTEGER NOT NULL,
            UNIQUE (user_id, semester_number),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            emp_id TEXT NOT NULL,
            department_id INTEGER,
            UNIQUE (user_id, emp_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            hours_per_week INTEGER NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('theory', 'lab')),
            UNIQUE (user_id, code),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS theory_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            semester_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            faculty_id INTEGER NOT NULL,
            UNIQUE (user_id, semester_id, course_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (semester_id) REFERENCES semesters (id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE,
            FOREIGN KEY (faculty_id) REFERENCES faculty (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lab_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            semester_id INTEGER NOT NULL,
            lab_course_id INTEGER NOT NULL,
            faculty_id_1 INTEGER NOT NULL,
            faculty_id_2 INTEGER NOT NULL,
            UNIQUE (user_id, semester_id, lab_course_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (semester_id) REFERENCES semesters (id) ON DELETE CASCADE,
            FOREIGN KEY (lab_course_id) REFERENCES courses (id) ON DELETE CASCADE,
            FOREIGN KEY (faculty_id_1) REFERENCES faculty (id) ON DELETE CASCADE,
            FOREIGN KEY (faculty_id_2) REFERENCES faculty (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faculty_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            faculty_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            period_start INTEGER NOT NULL,
            period_end INTEGER NOT NULL,
            preference_type TEXT NOT NULL CHECK (preference_type IN ('blocked', 'preferred')),
            UNIQUE (user_id, faculty_id, day, period_start, period_end),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (faculty_id) REFERENCES faculty (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_timetables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timetable_name TEXT NOT NULL,
            generated_on TEXT NOT NULL,
            timetable_data BLOB NOT NULL, -- Storing pickled/json data
            data_snapshot BLOB NOT NULL, -- Storing pickled/json data of all_data
            UNIQUE(user_id, timetable_name),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()

# --- User Management Functions ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def add_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed_pass = hash_password(password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_pass))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

# --- CRUD Functions for Departments ---
def add_department(user_id, name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO departments (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_departments(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM departments WHERE user_id = ?", (user_id,))
    departments = cursor.fetchall()
    conn.close()
    return departments

def update_department(user_id, dept_id, new_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE departments SET name = ? WHERE id = ? AND user_id = ?", (new_name, dept_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_department(user_id, dept_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM departments WHERE id = ? AND user_id = ?", (dept_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error as e:
        print(f"Error deleting department: {e}")
        return False
    finally:
        conn.close()

# --- CRUD Functions for Semesters ---
def add_semester(user_id, sem_num):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO semesters (user_id, semester_number) VALUES (?, ?)", (user_id, sem_num))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_semesters(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, semester_number FROM semesters WHERE user_id = ? ORDER BY semester_number", (user_id,))
    semesters = cursor.fetchall()
    conn.close()
    return semesters

def delete_semester(user_id, sem_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM semesters WHERE id = ? AND user_id = ?", (sem_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# --- CRUD Functions for Faculty ---
def add_faculty(user_id, name, emp_id, department_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO faculty (user_id, name, emp_id, department_id) VALUES (?, ?, ?, ?)", (user_id, name, emp_id, department_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_faculty(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.name, f.emp_id, d.name as department_name, f.department_id
        FROM faculty f
        JOIN departments d ON f.department_id = d.id
        WHERE f.user_id = ? AND d.user_id = ?
    """, (user_id, user_id))
    faculty = cursor.fetchall()
    conn.close()
    return faculty

def update_faculty(user_id, faculty_id, new_name, new_emp_id, new_department_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE faculty SET name = ?, emp_id = ?, department_id = ? WHERE id = ? AND user_id = ?",
                       (new_name, new_emp_id, new_department_id, faculty_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_faculty(user_id, faculty_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM faculty WHERE id = ? AND user_id = ?", (faculty_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# --- CRUD Functions for Courses ---
def add_course(user_id, code, name, hours_per_week, course_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO courses (user_id, code, name, hours_per_week, type) VALUES (?, ?, ?, ?, ?)",
                       (user_id, code, name, hours_per_week, course_type))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_courses(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name, hours_per_week, type FROM courses WHERE user_id = ?", (user_id,))
    courses = cursor.fetchall()
    conn.close()
    return courses

def get_theory_courses(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name, hours_per_week, type FROM courses WHERE user_id = ? AND type = 'theory'", (user_id,))
    courses = cursor.fetchall()
    conn.close()
    return courses

def get_lab_courses(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name, hours_per_week, type FROM courses WHERE user_id = ? AND type = 'lab'", (user_id,))
    courses = cursor.fetchall()
    conn.close()
    return courses

def update_course(user_id, course_id, new_code, new_name, new_hours_per_week, new_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE courses SET code = ?, name = ?, hours_per_week = ?, type = ? WHERE id = ? AND user_id = ?",
                       (new_code, new_name, new_hours_per_week, new_type, course_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_course(user_id, course_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM courses WHERE id = ? AND user_id = ?", (course_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# --- Mapping Functions ---
def add_theory_mapping(user_id, semester_id, course_id, faculty_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO theory_mappings (user_id, semester_id, course_id, faculty_id) VALUES (?, ?, ?, ?)",
                       (user_id, semester_id, course_id, faculty_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_theory_mappings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tm.id, s.semester_number, c.name AS course_name, c.code, f.name AS faculty_name
        FROM theory_mappings tm
        JOIN semesters s ON tm.semester_id = s.id
        JOIN courses c ON tm.course_id = c.id
        JOIN faculty f ON tm.faculty_id = f.id
        WHERE tm.user_id = ? AND s.user_id = ? AND c.user_id = ? AND f.user_id = ?
    """, (user_id, user_id, user_id, user_id))
    mappings = cursor.fetchall()
    conn.close()
    return mappings

def delete_theory_mapping(user_id, mapping_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM theory_mappings WHERE id = ? AND user_id = ?", (mapping_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def add_lab_mapping(user_id, semester_id, lab_course_id, faculty_id_1, faculty_id_2):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO lab_mappings (user_id, semester_id, lab_course_id, faculty_id_1, faculty_id_2) VALUES (?, ?, ?, ?, ?)",
                       (user_id, semester_id, lab_course_id, faculty_id_1, faculty_id_2))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_lab_mappings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT lm.id, s.semester_number, c.name AS lab_course_name, c.code, f1.name AS faculty_1_name, f2.name AS faculty_2_name
        FROM lab_mappings lm
        JOIN semesters s ON lm.semester_id = s.id
        JOIN courses c ON lm.lab_course_id = c.id
        JOIN faculty f1 ON lm.faculty_id_1 = f1.id
        JOIN faculty f2 ON lm.faculty_id_2 = f2.id
        WHERE lm.user_id = ? AND s.user_id = ? AND c.user_id = ? AND f1.user_id = ? AND f2.user_id = ?
    """, (user_id, user_id, user_id, user_id, user_id))
    mappings = cursor.fetchall()
    conn.close()
    return mappings

def delete_lab_mapping(user_id, mapping_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM lab_mappings WHERE id = ? AND user_id = ?", (mapping_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# --- Faculty Preferences Functions ---
def add_faculty_preference(user_id, faculty_id, day, period_start, period_end, pref_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO faculty_preferences (user_id, faculty_id, day, period_start, period_end, preference_type) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, faculty_id, day, period_start, period_end, pref_type)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_faculty_preferences(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fp.id, f.name AS faculty_name, fp.day, fp.period_start, fp.period_end, fp.preference_type
        FROM faculty_preferences fp
        JOIN faculty f ON fp.faculty_id = f.id
        WHERE fp.user_id = ? AND f.user_id = ?
    """, (user_id, user_id))
    preferences = cursor.fetchall()
    conn.close()
    return preferences

def get_faculty_preferences_by_faculty_id(user_id, faculty_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT day, period_start, period_end, preference_type
        FROM faculty_preferences
        WHERE user_id = ? AND faculty_id = ?
    """, (user_id, faculty_id))
    preferences = cursor.fetchall()
    conn.close()
    return preferences

def delete_faculty_preference(user_id, pref_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM faculty_preferences WHERE id = ? AND user_id = ?", (pref_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# --- Data Management for GA ---

def load_all_data(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    departments_raw = cursor.execute("SELECT id, name FROM departments WHERE user_id = ?", (user_id,)).fetchall()
    departments = {row['id']: Department(row['id'], row['name']) for row in departments_raw}

    semesters_raw = cursor.execute("SELECT id, semester_number FROM semesters WHERE user_id = ?", (user_id,)).fetchall()
    semesters = {row['id']: Semester(row['id'], row['semester_number']) for row in semesters_raw}

    faculty_raw = cursor.execute("SELECT id, name, emp_id, department_id FROM faculty WHERE user_id = ?", (user_id,)).fetchall()
    faculty = {}
    for row in faculty_raw:
        fac_obj = Faculty(row['id'], row['name'], row['emp_id'], row['department_id'])
        if row['department_id'] in departments:
            fac_obj.set_department(departments[row['department_id']])
        faculty[row['id']] = fac_obj

    courses_raw = cursor.execute("SELECT id, code, name, hours_per_week, type FROM courses WHERE user_id = ?", (user_id,)).fetchall()
    courses = {row['id']: Course(row['id'], row['code'], row['name'], row['hours_per_week'], row['type']) for row in courses_raw}

    theory_mappings_raw = cursor.execute("SELECT id, semester_id, course_id, faculty_id FROM theory_mappings WHERE user_id = ?", (user_id,)).fetchall()
    theory_mappings = []
    for row in theory_mappings_raw:
        tm_obj = TheoryMapping(row['id'], row['semester_id'], row['course_id'], row['faculty_id'])
        tm_obj.semester = semesters.get(row['semester_id'])
        tm_obj.course = courses.get(row['course_id'])
        tm_obj.faculty = faculty.get(row['faculty_id'])
        theory_mappings.append(tm_obj)

    lab_mappings_raw = cursor.execute("SELECT id, semester_id, lab_course_id, faculty_id_1, faculty_id_2 FROM lab_mappings WHERE user_id = ?", (user_id,)).fetchall()
    lab_mappings = []
    for row in lab_mappings_raw:
        lm_obj = LabMapping(row['id'], row['semester_id'], row['lab_course_id'], row['faculty_id_1'], row['faculty_id_2'])
        lm_obj.semester = semesters.get(row['semester_id'])
        lm_obj.lab_course = courses.get(row['lab_course_id'])
        lm_obj.faculty_1 = faculty.get(row['faculty_id_1'])
        lm_obj.faculty_2 = faculty.get(row['faculty_id_2'])
        lab_mappings.append(lm_obj)

    faculty_preferences_raw = cursor.execute("SELECT id, faculty_id, day, period_start, period_end, preference_type FROM faculty_preferences WHERE user_id = ?", (user_id,)).fetchall()
    faculty_preferences = []
    for row in faculty_preferences_raw:
        fp_obj = FacultyPreference(row['id'], row['faculty_id'], row['day'], row['period_start'], row['period_end'], row['preference_type'])
        fp_obj.faculty = faculty.get(row['faculty_id'])
        faculty_preferences.append(fp_obj)

    conn.close()

    return {
        "departments": list(departments.values()),
        "semesters": list(semesters.values()),
        "faculty": list(faculty.values()),
        "courses": list(courses.values()),
        "theory_mappings": theory_mappings,
        "lab_mappings": lab_mappings,
        "faculty_preferences": faculty_preferences,
        "departments_by_id": departments,
        "semesters_by_id": semesters,
        "faculty_by_id": faculty,
        "courses_by_id": courses,
    }

def get_classes_to_schedule(all_data):
    classes_to_schedule = []
    
    for tm in all_data['theory_mappings']:
        if tm.course and tm.faculty and tm.semester:
            for _ in range(tm.course.hours_per_week):
                sc = ScheduledClass(tm.semester.id, tm.course.id, [tm.faculty.id], None, None, 1, False)
                sc.semester_obj = tm.semester
                sc.course_obj = tm.course
                sc.faculty_objs = [tm.faculty]
                classes_to_schedule.append(sc)
        else:
            print(f"Warning: Incomplete data for theory mapping {tm.id}. Skipping.")

    for lm in all_data['lab_mappings']:
        if lm.lab_course and lm.faculty_1 and lm.faculty_2 and lm.semester:
            # Labs are treated as one 2-hour continuous block
            sc = ScheduledClass(lm.semester.id, lm.lab_course.id, [lm.faculty_1.id, lm.faculty_2.id], None, None, 2, True)
            sc.semester_obj = lm.semester
            sc.course_obj = lm.lab_course
            sc.faculty_objs = [lm.faculty_1, lm.faculty_2]
            classes_to_schedule.append(sc)
        else:
            print(f"Warning: Incomplete data for lab mapping {lm.id}. Skipping.")

    return classes_to_schedule

# --- Saved Timetable Functions ---

def convert_chromosome_to_dict(chromosome):
    """Converts a TimetableChromosome object to a dictionary for JSON serialization."""
    chromosome_dict = {
        "fitness": chromosome.fitness,
        "scheduled_classes": []
    }
    for sc in chromosome.scheduled_classes:
        sc_dict = {
            "semester_id": sc.semester_id,
            "course_id": sc.course_id,
            "faculty_ids": sc.faculty_ids,
            "day": sc.day,
            "start_period": sc.start_period,
            "periods_count": sc.periods_count,
            "is_lab": sc.is_lab,
        }
        chromosome_dict["scheduled_classes"].append(sc_dict)
    return chromosome_dict

def convert_dict_to_chromosome(chromosome_dict, all_data_snapshot):
    """Converts a dictionary back to a TimetableChromosome object."""
    scheduled_classes = []
    for sc_dict in chromosome_dict["scheduled_classes"]:
        sc = ScheduledClass(
            sc_dict["semester_id"],
            sc_dict["course_id"],
            sc_dict["faculty_ids"],
            sc_dict["day"],
            sc_dict["start_period"],
            sc_dict["periods_count"],
            sc_dict["is_lab"]
        )
        # Re-attach object references using the snapshot data
        sc.semester_obj = all_data_snapshot['semesters_by_id'].get(sc.semester_id)
        sc.course_obj = all_data_snapshot['courses_by_id'].get(sc.course_id)
        sc.faculty_objs = [all_data_snapshot['faculty_by_id'].get(fid) for fid in sc.faculty_ids if all_data_snapshot['faculty_by_id'].get(fid)]
        scheduled_classes.append(sc)
    
    from genetic_algorithm import TimetableChromosome # Import here to avoid circular dependency
    chromosome = TimetableChromosome(scheduled_classes)
    chromosome.fitness = chromosome_dict["fitness"]
    return chromosome

def add_saved_timetable(user_id, timetable_name, generated_on, timetable_chromosome, all_data_snapshot):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Convert objects to JSON-serializable format
        chromosome_json = json.dumps(convert_chromosome_to_dict(timetable_chromosome))
        all_data_json = json.dumps({
            "departments_by_id": {k: v.__dict__ for k,v in all_data_snapshot['departments_by_id'].items()},
            "semesters_by_id": {k: v.__dict__ for k,v in all_data_snapshot['semesters_by_id'].items()},
            "faculty_by_id": {k: v.__dict__ for k,v in all_data_snapshot['faculty_by_id'].items()},
            "courses_by_id": {k: v.__dict__ for k,v in all_data_snapshot['courses_by_id'].items()},
        })

        # Encode JSON strings to Base64 to store as BLOB (text in SQLite)
        encoded_chromosome_data = base64.b64encode(chromosome_json.encode('utf-8'))
        encoded_data_snapshot = base64.b64encode(all_data_json.encode('utf-8'))


        cursor.execute(
            "INSERT INTO saved_timetables (user_id, timetable_name, generated_on, timetable_data, data_snapshot) VALUES (?, ?, ?, ?, ?)",
            (user_id, timetable_name, generated_on, encoded_chromosome_data, encoded_data_snapshot)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Timetable name already exists for this user
    except Exception as e:
        print(f"Error saving timetable: {e}")
        return False
    finally:
        conn.close()

def get_saved_timetables(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, timetable_name, generated_on FROM saved_timetables WHERE user_id = ?", (user_id,))
    timetables = cursor.fetchall()
    conn.close()
    return timetables

def load_saved_timetable_data(user_id, timetable_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timetable_data, data_snapshot FROM saved_timetables WHERE id = ? AND user_id = ?", (timetable_id, user_id))
    row = cursor.fetchone()
    conn.close()

    if row:
        # Decode Base64 and load JSON
        chromosome_json = base64.b64decode(row['timetable_data']).decode('utf-8')
        data_snapshot_json = base64.b64decode(row['data_snapshot']).decode('utf-8')

        chromosome_dict = json.loads(chromosome_json)
        all_data_dict = json.loads(data_snapshot_json)

        # Reconstruct models from dictionary for snapshot
        reconstructed_data_snapshot = {
            "departments_by_id": {int(k): Department(**v) for k,v in all_data_dict['departments_by_id'].items()},
            "semesters_by_id": {int(k): Semester(**v) for k,v in all_data_dict['semesters_by_id'].items()},
            "faculty_by_id": {int(k): Faculty(**v) for k,v in all_data_dict['faculty_by_id'].items()},
            "courses_by_id": {int(k): Course(**v) for k,v in all_data_dict['courses_by_id'].items()},
        }
        
        # Build full faculty objects (set_department)
        for fac_id, fac_obj in reconstructed_data_snapshot['faculty_by_id'].items():
            if fac_obj.department_id in reconstructed_data_snapshot['departments_by_id']:
                fac_obj.set_department(reconstructed_data_snapshot['departments_by_id'][fac_obj.department_id])

        timetable_chromosome = convert_dict_to_chromosome(chromosome_dict, reconstructed_data_snapshot)

        return timetable_chromosome, reconstructed_data_snapshot
    return None, None

def delete_saved_timetable(user_id, timetable_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM saved_timetables WHERE id = ? AND user_id = ?", (timetable_id, user_id))
        conn.commit()
        return True if cursor.rowcount > 0 else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# --- Delete All User Data ---
def delete_all_user_data(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Tables with CASCADE DELETE set up. Deleting departments should cascade.
        # However, it's safer to explicitly delete everything to clear the slate
        # in case of any foreign key constraint issues.
        # Deleting from tables that depend on others first
        cursor.execute("DELETE FROM faculty_preferences WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM theory_mappings WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM lab_mappings WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM saved_timetables WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM faculty WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM courses WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM semesters WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM departments WHERE user_id = ?", (user_id,))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error deleting all user data: {e}")
        return False
    finally:
        conn.close()