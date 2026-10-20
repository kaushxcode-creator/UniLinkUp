"""
db.py
-----
A thin wrapper around Python's built-in `sqlite3` module.

Why raw sqlite3 instead of an ORM like SQLAlchemy?
This keeps the project's only dependency as Flask itself -- nothing else
needs to be pip-installed, which keeps setup fast on a machine with
limited internet access.

Usage pattern used throughout app.py:
    rows = query_db("SELECT * FROM students WHERE college_id = ?", (college_id,))
    row  = query_db("SELECT * FROM students WHERE id = ?", (student_id,), one=True)
    new_id = execute_db("INSERT INTO students (...) VALUES (...)", (...))
"""

import sqlite3
import os
from flask import g

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'unilink.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS colleges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    established_year INTEGER,
    official_email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    college_id INTEGER NOT NULL REFERENCES colleges(id)
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    srn TEXT UNIQUE NOT NULL,
    section TEXT,
    course TEXT,
    department TEXT,
    year TEXT,
    semester TEXT,
    cgpa REAL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    college_id INTEGER REFERENCES colleges(id),
    skills TEXT,
    profile_picture TEXT,
    resume_summary TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS company_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    role TEXT,
    description TEXT,
    reg_start TEXT NOT NULL,
    reg_end TEXT NOT NULL,
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    min_cgpa REAL DEFAULT 0,
    eligible_courses TEXT,
    eligible_years TEXT,
    required_skills TEXT,
    package_lpa TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    company_id INTEGER NOT NULL REFERENCES company_visits(id),
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, company_id)
);

CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessment_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    mode TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    taken_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    user_kind TEXT,
    user_id INTEGER,
    message TEXT NOT NULL,
    reply TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    category TEXT,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    employee_id INTEGER REFERENCES employees(id),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    kind TEXT DEFAULT 'manual',
    company_id INTEGER REFERENCES company_visits(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id INTEGER NOT NULL REFERENCES notifications(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    read_at TEXT
);

CREATE TABLE IF NOT EXISTS faculty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    department TEXT,
    expertise TEXT,
    bio TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS faculty_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id),
    slot_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    topic TEXT,
    status TEXT DEFAULT 'open',
    cancel_reason TEXT,
    cancelled_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id INTEGER NOT NULL REFERENCES faculty_slots(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    faculty_id INTEGER NOT NULL REFERENCES faculty(id),
    status TEXT DEFAULT 'upcoming',
    notes TEXT,
    cancel_reason TEXT,
    booked_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    ats_score INTEGER,
    ats_feedback TEXT,
    source TEXT DEFAULT 'uploaded',
    verification_status TEXT DEFAULT 'pending',
    verified_by INTEGER REFERENCES employees(id),
    verified_at TEXT,
    verification_note TEXT,
    verification_suggestion TEXT,
    share_token TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resume_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    organization TEXT,
    duration TEXT,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resume_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id INTEGER NOT NULL REFERENCES resumes(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    shared_by INTEGER NOT NULL REFERENCES employees(id),
    company_name TEXT,
    company_email TEXT NOT NULL,
    message TEXT,
    status TEXT DEFAULT 'logged',
    method TEXT DEFAULT 'email',
    share_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS slot_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    faculty_id INTEGER NOT NULL REFERENCES faculty(id),
    skill TEXT NOT NULL,
    company_name TEXT,
    message TEXT,
    status TEXT DEFAULT 'pending',
    proposed_date TEXT,
    proposed_start TEXT,
    proposed_end TEXT,
    meeting_link TEXT,
    decline_reason TEXT,
    alternate_date TEXT,
    resulting_slot_id INTEGER REFERENCES faculty_slots(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    responded_at TEXT
);

CREATE TABLE IF NOT EXISTS faculty_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id),
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    title TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS faculty_test_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL REFERENCES faculty_tests(id),
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS faculty_test_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL REFERENCES faculty_tests(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    taken_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doubts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    department TEXT,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    image_path TEXT,
    status TEXT DEFAULT 'open',
    faculty_id INTEGER REFERENCES faculty(id),
    answer TEXT,
    answer_image_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    faculty_id INTEGER NOT NULL REFERENCES faculty(id),
    sender_role TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    read_at TEXT
);

CREATE TABLE IF NOT EXISTS learning_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    activity TEXT NOT NULL,
    hours REAL NOT NULL,
    log_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS peer_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    added_by INTEGER REFERENCES employees(id),
    student_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    role TEXT,
    package_lpa TEXT,
    cgpa REAL,
    skills TEXT,
    projects TEXT,
    testimonial TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    company_name TEXT NOT NULL,
    role TEXT,
    outcome TEXT,
    difficulty TEXT,
    rounds TEXT,
    experience TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- COMPANY PORTAL
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    hr_name TEXT,
    phone TEXT,
    industry TEXT,
    website TEXT,
    location TEXT,
    about TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    title TEXT NOT NULL,
    job_type TEXT DEFAULT 'Full-time',
    description TEXT,
    location TEXT,
    package_lpa TEXT,
    openings INTEGER DEFAULT 1,
    min_cgpa REAL DEFAULT 0,
    eligible_courses TEXT,
    eligible_years TEXT,
    required_skills TEXT,
    min_assessment_pct INTEGER DEFAULT 0,
    last_date TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS visit_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    job_post_id INTEGER NOT NULL REFERENCES job_posts(id),
    college_id INTEGER NOT NULL REFERENCES colleges(id),
    proposed_date TEXT,
    message TEXT,
    status TEXT DEFAULT 'pending',
    college_note TEXT,
    responded_by INTEGER REFERENCES employees(id),
    responded_at TEXT,
    company_visit_id INTEGER REFERENCES company_visits(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    visit_request_id INTEGER NOT NULL REFERENCES visit_requests(id),
    round_name TEXT NOT NULL,
    interview_date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    mode TEXT DEFAULT 'On-campus',
    venue TEXT,
    meeting_link TEXT,
    panel TEXT,
    notes TEXT,
    status TEXT DEFAULT 'scheduled',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    visit_request_id INTEGER REFERENCES visit_requests(id),
    college_id INTEGER REFERENCES colleges(id),
    job_post_id INTEGER REFERENCES job_posts(id),
    schedule_id INTEGER REFERENCES interview_schedules(id),
    student_id INTEGER REFERENCES students(id),
    student_name TEXT NOT NULL,
    srn TEXT,
    student_email TEXT,
    phone TEXT,
    course TEXT,
    department TEXT,
    year TEXT,
    cgpa REAL,
    round_name TEXT,
    interview_date TEXT,
    interviewer TEXT,
    technical_rating INTEGER,
    communication_rating INTEGER,
    aptitude_rating INTEGER,
    result TEXT NOT NULL,
    package_offered TEXT,
    rejection_reason TEXT,
    remarks TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- INTERVIEWERS + MOCK INTERVIEWS
-- Interviewer accounts belong to a company and are created by its HR.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interviewers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    designation TEXT,
    expertise TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mock_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interviewer_id INTEGER NOT NULL REFERENCES interviewers(id),
    slot_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    focus TEXT DEFAULT 'Technical',
    topics TEXT,
    mode TEXT DEFAULT 'Online',
    meeting_link TEXT,
    venue TEXT,
    status TEXT DEFAULT 'open',
    cancel_reason TEXT,
    student_id INTEGER REFERENCES students(id),
    target_role TEXT,
    student_topics TEXT,
    student_note TEXT,
    booked_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mock_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id INTEGER UNIQUE NOT NULL REFERENCES mock_slots(id),
    interviewer_id INTEGER NOT NULL REFERENCES interviewers(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    technical INTEGER,
    communication INTEGER,
    problem_solving INTEGER,
    confidence INTEGER,
    verdict TEXT NOT NULL,
    strengths TEXT,
    improvements TEXT,
    resources TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# Columns added after the initial release. Kept separate from SCHEMA above so
# that an already-existing unilink.db (created before this feature set)
# gets upgraded automatically instead of silently missing the new fields.
MIGRATIONS = [
    ("students", "skills", "TEXT"),
    ("company_visits", "min_cgpa", "REAL DEFAULT 0"),
    ("company_visits", "eligible_courses", "TEXT"),
    ("company_visits", "eligible_years", "TEXT"),
    ("company_visits", "required_skills", "TEXT"),
    ("company_visits", "package_lpa", "TEXT"),
    ("students", "department", "TEXT"),
    ("faculty_slots", "meeting_link", "TEXT"),
    ("faculty_slots", "capacity", "INTEGER DEFAULT 1"),
    ("notifications", "faculty_id", "INTEGER REFERENCES faculty(id)"),
    ("slot_requests", "alternate_date", "TEXT"),
    ("doubts", "image_path", "TEXT"),
    ("doubts", "answer_image_path", "TEXT"),
    ("faculty_slots", "cancel_reason", "TEXT"),
    ("faculty_slots", "cancelled_at", "TEXT"),
    ("appointments", "cancel_reason", "TEXT"),
    ("students", "profile_picture", "TEXT"),
    ("students", "resume_summary", "TEXT"),
    ("resumes", "source", "TEXT DEFAULT 'uploaded'"),
    ("resumes", "verification_status", "TEXT DEFAULT 'pending'"),
    ("resumes", "verified_by", "INTEGER REFERENCES employees(id)"),
    ("resumes", "verified_at", "TEXT"),
    ("resumes", "verification_note", "TEXT"),
    ("resumes", "share_token", "TEXT"),
    ("resumes", "verification_suggestion", "TEXT"),
    ("resume_shares", "method", "TEXT DEFAULT 'email'"),
    ("resume_shares", "share_url", "TEXT"),
    # Company portal: a campus drive created by approving a company's visit
    # request remembers which company account / job post it came from.
    ("company_visits", "company_account_id", "INTEGER REFERENCES companies(id)"),
    ("company_visits", "job_post_id", "INTEGER REFERENCES job_posts(id)"),
    ("company_visits", "min_assessment_pct", "INTEGER DEFAULT 0"),
    # Interviewer portal: rounds can be assigned to an interviewer, and a
    # report remembers which interviewer filed it.
    ("interview_schedules", "interviewer_id", "INTEGER REFERENCES interviewers(id)"),
    ("interview_reports", "interviewer_id", "INTEGER REFERENCES interviewers(id)"),
]


def run_migrations():
    """Adds any columns introduced after the original schema to an existing
    database file. Safe to call on every startup -- each ADD COLUMN is
    skipped if the column is already present."""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    for table, column, coltype in MIGRATIONS:
        cur.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        if column not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    # Runs after the ALTER TABLEs above so share_token is guaranteed to exist
    # on both a brand-new database and one being upgraded from an older version.
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_resumes_share_token
            ON resumes(share_token) WHERE share_token IS NOT NULL
    """)
    conn.commit()
    conn.close()


def get_db():
    """Returns a per-request sqlite3 connection, cached on Flask's `g` object."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row      # lets us access columns by name, e.g. row['name']
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    """Registers the close_db function to run automatically after each request."""
    app.teardown_appcontext(close_db)


def init_db_schema():
    """Creates every table if it doesn't already exist. Safe to call every startup."""
    conn = sqlite3.connect(DATABASE)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    run_migrations()


def query_db(query, args=(), one=False):
    """Run a SELECT and return a list of sqlite3.Row objects (or a single one)."""
    cur = get_db().execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(query, args=()):
    """Run an INSERT/UPDATE/DELETE, commit it, and return the new row's id."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    new_id = cur.lastrowid
    cur.close()
    return new_id
