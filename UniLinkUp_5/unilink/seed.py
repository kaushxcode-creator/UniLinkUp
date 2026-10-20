"""
seed.py
-------
Populates the database with sample data so the app isn't empty on first run:
 - ~15 aptitude/interview MCQ questions for the skill assessment module
 - one demo college + placement employee login + a few demo company drives
   (now with eligibility criteria: min CGPA, eligible branches/years, skills)
 - a broad list of real Indian colleges/universities so the registration
   dropdown isn't just a single entry — placement officers from any of these
   can also "join" their college instead of registering a brand-new one
   (see /college/register)

Run once, after installing requirements:
    python seed.py
Safe to re-run: every block below checks "if empty" before inserting.
"""

import re
import db as dbm
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

# A broad, realistic spread of Indian engineering colleges/universities so
# the "College / University" dropdown has real options to search through.
# (REVA University is seeded separately below, with full demo data.)
MORE_COLLEGES = [
    "Indian Institute of Technology Bombay",
    "Indian Institute of Technology Delhi",
    "Indian Institute of Technology Madras",
    "Indian Institute of Technology Kanpur",
    "Indian Institute of Technology Kharagpur",
    "Indian Institute of Technology Roorkee",
    "Indian Institute of Technology Guwahati",
    "Indian Institute of Technology Hyderabad",
    "Indian Institute of Technology (BHU) Varanasi",
    "Indian Institute of Technology Indore",
    "National Institute of Technology Karnataka, Surathkal",
    "National Institute of Technology Tiruchirappalli",
    "National Institute of Technology Warangal",
    "National Institute of Technology Rourkela",
    "National Institute of Technology Calicut",
    "National Institute of Technology Durgapur",
    "Visvesvaraya National Institute of Technology, Nagpur",
    "International Institute of Information Technology, Hyderabad",
    "International Institute of Information Technology, Bangalore",
    "Birla Institute of Technology and Science, Pilani",
    "Vellore Institute of Technology",
    "SRM Institute of Science and Technology",
    "Manipal Institute of Technology",
    "Delhi Technological University",
    "Netaji Subhas University of Technology",
    "Jadavpur University",
    "Anna University",
    "PES University",
    "RV College of Engineering",
    "BMS College of Engineering",
    "M S Ramaiah Institute of Technology",
    "Dayananda Sagar College of Engineering",
    "Bangalore Institute of Technology",
    "New Horizon College of Engineering",
    "Christ University",
    "Jain University",
    "Amity University",
    "Lovely Professional University",
    "Chandigarh University",
    "KIIT University",
    "SASTRA Deemed University",
    "Thapar Institute of Engineering and Technology",
    "PSG College of Technology",
    "Sri Sivasubramaniya Nadar College of Engineering",
    "College of Engineering, Pune",
    "Veermata Jijabai Technological Institute",
    "Sardar Vallabhbhai National Institute of Technology, Surat",
    "Malaviya National Institute of Technology, Jaipur",
    "Motilal Nehru National Institute of Technology, Allahabad",
    "Jawaharlal Nehru Technological University, Hyderabad",
    "Osmania University",
    "Guru Gobind Singh Indraprastha University",
]


def _slugify(name):
    slug = re.sub(r'[^a-z0-9]+', '', name.lower())
    return slug[:20] or 'college'

QUESTIONS = [
    ("aptitude", "Two fathers and two sons went fishing and caught 3 fish total, one each. How?",
     "One fish was caught by an outsider", "One son was a pet",
     "There were only 3 people: grandfather, son, grandson", "It's impossible", "C"),
    ("aptitude", "If a train travels 60 km in 45 minutes, what is its speed in km/h?",
     "60 km/h", "80 km/h", "90 km/h", "75 km/h", "B"),
    ("aptitude", "Find the next number in the series: 2, 6, 12, 20, 30, ?",
     "36", "40", "42", "44", "C"),
    ("aptitude", "A shopkeeper marks up an item by 25% and gives a 20% discount. What is his net profit/loss %?",
     "5% profit", "No profit no loss", "5% loss", "10% profit", "B"),
    ("aptitude", "If CODE is written as DPEF, how is WORD written?",
     "XPSE", "XQSE", "XPSF", "XPTE", "A"),
    ("aptitude", "A can do a piece of work in 10 days, B in 15 days. Working together, how many days will they take?",
     "5 days", "6 days", "8 days", "12 days", "B"),
    ("aptitude", "What is the missing number: 5, 10, 20, 40, ?",
     "60", "70", "80", "90", "C"),
    ("aptitude", "Pointing to a photo, Ravi said, 'She is the daughter of my grandfather's only son.' Who is she to Ravi?",
     "Sister", "Cousin", "Mother", "Aunt", "A"),
    ("interview", "Which data structure uses FIFO (First In First Out) order?",
     "Stack", "Queue", "Tree", "Graph", "B"),
    ("interview", "What does SQL stand for?",
     "Structured Query Language", "Simple Query Logic",
     "Sequential Query Language", "Structured Question Language", "A"),
    ("interview", "In Git, which command creates a new branch?",
     "git branch <name>", "git checkout -new <name>",
     "git new <name>", "git create <name>", "A"),
    ("interview", "What is the time complexity of binary search on a sorted array?",
     "O(n)", "O(n log n)", "O(log n)", "O(1)", "C"),
    ("interview", "Which HTTP method is typically used to update an existing resource?",
     "GET", "POST", "PUT", "DELETE", "C"),
    ("interview", "In Python, which keyword is used to define a function?",
     "func", "def", "function", "lambda only", "B"),
    ("interview", "What does 'CSS' stand for in web development?",
     "Cascading Style Sheets", "Computer Style Sheets",
     "Creative Style System", "Cascading Style System", "A"),
    ("interview", "How should you handle a disagreement in a team project?",
     "Ignore it and do it your way",
     "Escalate immediately to a manager without discussion",
     "Listen to the other perspective, discuss trade-offs, and agree on a data-informed decision",
     "Let the more senior person decide without discussion", "C"),
]


def run():
    dbm.init_db_schema()
    import sqlite3
    conn = sqlite3.connect(dbm.DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM questions")
    if cur.fetchone()['c'] == 0:
        for cat, q, a, b, c, d, correct in QUESTIONS:
            cur.execute("""
                INSERT INTO questions (category, question_text, option_a, option_b, option_c, option_d, correct_option)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cat, q, a, b, c, d, correct))
        print(f"Seeded {len(QUESTIONS)} assessment questions.")

    cur.execute("SELECT COUNT(*) AS c FROM colleges")
    if cur.fetchone()['c'] == 0:
        cur.execute("""
            INSERT INTO colleges (name, established_year, official_email, password_hash)
            VALUES (?, ?, ?, ?)
        """, ("REVA University", 2012, "placements@reva.edu.in", generate_password_hash("college123")))
        college_id = cur.lastrowid

        cur.execute("""
            INSERT INTO employees (name, email, password_hash, college_id) VALUES (?, ?, ?, ?)
        """, ("Placement Officer", "officer@reva.edu.in", generate_password_hash("officer123"), college_id))

        today = date.today()
        cur.execute("""
            INSERT INTO company_visits
                (company_name, role, description, reg_start, reg_end, college_id,
                 min_cgpa, eligible_courses, eligible_years, required_skills, package_lpa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("TCS", "Software Engineer Trainee",
              "On-campus drive for final year CSE/ISE students.",
              today.isoformat(), (today + timedelta(days=10)).isoformat(), college_id,
              6.0, "CSE, ISE, AIML", "4th Year",
              "Python, SQL, Data Structures", "3.6 LPA"))

        cur.execute("""
            INSERT INTO company_visits
                (company_name, role, description, reg_start, reg_end, college_id,
                 min_cgpa, eligible_courses, eligible_years, required_skills, package_lpa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Infosys", "Systems Engineer",
              "Open to all branches, CGPA 6.5+.",
              (today - timedelta(days=2)).isoformat(), (today + timedelta(days=5)).isoformat(), college_id,
              6.5, "", "3rd Year, 4th Year",
              "Java, Problem Solving", "4.0 LPA"))

        cur.execute("""
            INSERT INTO company_visits
                (company_name, role, description, reg_start, reg_end, college_id,
                 min_cgpa, eligible_courses, eligible_years, required_skills, package_lpa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Wipro", "Cloud & DevOps Intern",
              "Short-term paid internship, hands-on with CI/CD pipelines.",
              (today - timedelta(days=1)).isoformat(), (today + timedelta(days=14)).isoformat(), college_id,
              7.0, "CSE, ISE, ECE", "3rd Year, 4th Year",
              "Python, Git, Cloud, Linux", "25,000/month stipend"))

        cur.execute("""
            INSERT INTO faculty (name, email, password_hash, college_id, department, expertise, bio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Dr. Ramesh Iyer", "faculty@reva.edu.in", generate_password_hash("faculty123"), college_id,
              "Computer Science", "Data Structures, DBMS, Mock Interviews",
              "15 years teaching CS fundamentals; runs weekly mock-interview slots for final years."))
        faculty_id = cur.lastrowid

        cur.execute("""
            INSERT INTO faculty_slots (faculty_id, slot_date, start_time, end_time, topic, status)
            VALUES (?, ?, ?, ?, ?, 'open')
        """, (faculty_id, (today + timedelta(days=3)).isoformat(), "10:00", "10:30", "Mock Interview Practice"))
        cur.execute("""
            INSERT INTO faculty_slots (faculty_id, slot_date, start_time, end_time, topic, status)
            VALUES (?, ?, ?, ?, ?, 'open')
        """, (faculty_id, (today + timedelta(days=4)).isoformat(), "15:00", "15:30", "Data Structures Doubt Clearing"))
        cur.execute("""
            INSERT INTO faculty_slots (faculty_id, slot_date, start_time, end_time, topic, status, meeting_link, capacity)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
        """, (faculty_id, (today + timedelta(days=5)).isoformat(), "17:00", "17:45",
              "Group Session: Cracking Coding Interviews", "https://meet.google.com/demo-group-session", 5))

        cur.execute("""
            INSERT INTO peer_references
                (college_id, added_by, student_name, company_name, role, package_lpa, cgpa, skills, projects, testimonial)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (college_id, None, "Ananya Rao", "TCS", "Software Engineer Trainee", "3.6 LPA", 8.7,
              "Python, SQL, Data Structures",
              "Built a campus event-management web app; contributed to an open-source CLI tool.",
              "Consistency beat cramming — I practiced 45 minutes of DSA daily for two months before the drive."))

        # A ready-to-use demo student, so a visitor can log straight into a
        # populated account (skills + CGPA already filled in, so eligibility
        # match % and skill-gap analysis show real numbers immediately)
        # instead of registering from scratch just to look around.
        cur.execute("""
            INSERT INTO students
                (name, srn, section, course, department, year, semester, cgpa, email, password_hash,
                 college_id, skills)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Demo Student", "DEMO2026CS001", "A", "CSE", "Computer Science", "4th Year", "7",
              7.8, "student@reva.edu.in", generate_password_hash("student123"), college_id,
              "Python, SQL, Git"))

        print("Seeded demo college 'REVA University' "
              "(placement login: officer@reva.edu.in / officer123) with 3 sample drives.")
        print("Seeded demo faculty 'Dr. Ramesh Iyer' "
              "(faculty login: faculty@reva.edu.in / faculty123) with 3 open slots (one a 5-seat group class) "
              "and a sample Peer Reference wall entry.")
        print("Seeded demo student 'Demo Student' (student login: student@reva.edu.in / student123).")

    # ---- Broad list of real colleges/universities for the dropdown ----
    cur.execute("SELECT COUNT(*) AS c FROM colleges")
    existing_count = cur.fetchone()['c']
    if existing_count <= 1:  # only REVA present so far
        used_slugs = set()
        added = 0
        for name in MORE_COLLEGES:
            slug = _slugify(name)
            candidate = slug
            n = 1
            while candidate in used_slugs:
                n += 1
                candidate = f"{slug}{n}"
            used_slugs.add(candidate)
            email = f"placements@{candidate}.edu.in"

            cur.execute("SELECT id FROM colleges WHERE official_email = ?", (email,))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO colleges (name, established_year, official_email, password_hash)
                VALUES (?, ?, ?, ?)
            """, (name, None, email, generate_password_hash("collegeportal123")))
            added += 1
        print(f"Seeded {added} additional colleges/universities for the registration dropdown.")

    # ---- Demo company account (Company portal) ----
    cur.execute("SELECT COUNT(*) AS c FROM companies")
    if cur.fetchone()['c'] == 0:
        today = date.today()
        cur.execute("""
            INSERT INTO companies (name, email, password_hash, hr_name, phone, industry, website, location, about)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Nimbus Technologies", "hr@nimbustech.com", generate_password_hash("company123"),
              "Priya Menon", "+91 98450 00000", "IT Services & Consulting", "https://nimbustech.example",
              "Bengaluru", "A product engineering company building cloud and data platforms for mid-size businesses."))
        company_id = cur.lastrowid

        cur.execute("""
            INSERT INTO job_posts (company_id, title, job_type, description, location, package_lpa, openings,
                                   min_cgpa, eligible_courses, eligible_years, required_skills, min_assessment_pct, last_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (company_id, "Associate Software Engineer", "Full-time",
              "Work on backend services in Python and SQL. Two technical rounds and one HR round.",
              "Bengaluru", "6.5 LPA", 10, 7.0, "CSE, ISE, AIML", "4th Year",
              "Python, SQL, Data Structures", 50, (today + timedelta(days=30)).isoformat()))
        job_full = cur.lastrowid
        cur.execute("""
            INSERT INTO job_posts (company_id, title, job_type, description, location, package_lpa, openings,
                                   min_cgpa, eligible_courses, eligible_years, required_skills, min_assessment_pct, last_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (company_id, "Data Analyst Intern", "Internship",
              "Six-month paid internship with the analytics team; SQL and dashboards.",
              "Remote / Bengaluru", "30,000/month stipend", 5, 6.5, "", "3rd Year, 4th Year",
              "SQL, Python, Excel", 0, (today + timedelta(days=20)).isoformat()))
        job_intern = cur.lastrowid

        cur.execute("SELECT id FROM colleges WHERE name = 'REVA University'")
        reva = cur.fetchone()
        if reva:
            reva_id = reva['id']
            # A pending request, so the placement cell has something to approve or reject.
            cur.execute("""
                INSERT INTO visit_requests (company_id, job_post_id, college_id, proposed_date, message, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (company_id, job_full, reva_id, (today + timedelta(days=14)).isoformat(),
                  "We'd like to run an on-campus drive for final-year CSE/ISE/AIML students."))

            # An already-approved visit with a live drive, a schedule and two reports.
            cur.execute("""
                INSERT INTO company_visits
                    (company_name, role, description, reg_start, reg_end, college_id, min_cgpa,
                     eligible_courses, eligible_years, required_skills, package_lpa,
                     company_account_id, job_post_id, min_assessment_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("Nimbus Technologies", "Data Analyst Intern",
                  "Six-month paid internship with the analytics team; SQL and dashboards.",
                  today.isoformat(), (today + timedelta(days=12)).isoformat(), reva_id, 6.5, "",
                  "3rd Year, 4th Year", "SQL, Python, Excel", "30,000/month stipend",
                  company_id, job_intern, 0))
            visit_id = cur.lastrowid
            cur.execute("""
                INSERT INTO visit_requests (company_id, job_post_id, college_id, proposed_date, message, status,
                                            college_note, responded_at, company_visit_id)
                VALUES (?, ?, ?, ?, ?, 'approved', ?, CURRENT_TIMESTAMP, ?)
            """, (company_id, job_intern, reva_id, (today + timedelta(days=7)).isoformat(),
                  "Internship drive for 3rd and 4th year students of all branches.",
                  "Approved — seminar hall B is reserved for you.", visit_id))
            req_id = cur.lastrowid
            cur.execute("""
                INSERT INTO interview_schedules (company_id, visit_request_id, round_name, interview_date,
                                                 start_time, end_time, mode, venue, panel, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, req_id, "Technical Interview", (today + timedelta(days=7)).isoformat(),
                  "10:00", "13:00", "On-campus", "Seminar Hall B, Block C", "Arjun Rao, Meera Shah",
                  "Carry a printed resume and college ID card."))
            sched_id = cur.lastrowid

            cur.execute("SELECT * FROM students WHERE email = 'student@reva.edu.in'")
            demo = cur.fetchone()
            if demo:
                cur.execute("""
                    INSERT INTO interview_reports
                        (company_id, visit_request_id, college_id, job_post_id, schedule_id, student_id,
                         student_name, srn, student_email, course, department, year, cgpa, round_name,
                         interview_date, interviewer, technical_rating, communication_rating, aptitude_rating,
                         result, package_offered, rejection_reason, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (company_id, req_id, reva_id, job_intern, sched_id, demo['id'], demo['name'], demo['srn'],
                      demo['email'], demo['course'], demo['department'], demo['year'], demo['cgpa'],
                      "Technical Interview", today.isoformat(), "Arjun Rao", 4, 4, 3, "Selected",
                      "30,000/month stipend", None,
                      "Strong SQL fundamentals, wrote clean joins and window functions. Good communication."))
            cur.execute("""
                INSERT INTO interview_reports
                    (company_id, visit_request_id, college_id, job_post_id, schedule_id, student_name, srn,
                     student_email, course, department, year, cgpa, round_name, interview_date, interviewer,
                     technical_rating, communication_rating, aptitude_rating, result, rejection_reason, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, req_id, reva_id, job_intern, sched_id, "Rahul Verma", "R21CS114",
                  "rahul.v@reva.edu.in", "ISE", "Information Science", "3rd Year", 7.1,
                  "Technical Interview", today.isoformat(), "Meera Shah", 2, 3, 3, "Not Selected",
                  "Could not write basic GROUP BY queries; Python fundamentals need work.",
                  "Encouraged to re-apply next cycle after practising SQL aggregation."))
        print("Seeded demo company 'Nimbus Technologies' (company login: hr@nimbustech.com / company123).")

    # ---- Demo interviewer + mock interviews (Interviewer portal) ----
    cur.execute("SELECT COUNT(*) AS c FROM interviewers")
    cur2 = conn.cursor()
    nimbus = cur2.execute("SELECT id FROM companies WHERE email = 'hr@nimbustech.com'").fetchone()
    if cur.fetchone()['c'] == 0 and nimbus:
        today = date.today()
        cur.execute("""
            INSERT INTO interviewers (company_id, name, email, password_hash, designation, expertise)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nimbus['id'], "Arjun Rao", "arjun@nimbustech.com", generate_password_hash("interviewer123"),
              "Senior Software Engineer", "Python, SQL, System Design"))
        iv = cur.lastrowid
        cur.execute("""
            INSERT INTO interviewers (company_id, name, email, password_hash, designation, expertise)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nimbus['id'], "Meera Shah", "meera@nimbustech.com", generate_password_hash("interviewer123"),
              "HR Business Partner", "HR, Behavioural, Communication"))
        iv2 = cur.lastrowid

        # Assign the existing campus round to Arjun
        cur.execute("UPDATE interview_schedules SET interviewer_id = ? WHERE company_id = ?", (iv, nimbus['id']))

        slots = [
            (iv, (today + timedelta(days=2)).isoformat(), "16:00", "16:45", "Technical", "DSA, SQL joins", "Online",
             "https://meet.google.com/demo-mock-1"),
            (iv, (today + timedelta(days=4)).isoformat(), "11:00", "11:45", "Technical", "Python, OOP", "Online",
             "https://meet.google.com/demo-mock-2"),
            (iv2, (today + timedelta(days=3)).isoformat(), "15:00", "15:30", "HR", "Tell me about yourself, strengths",
             "Online", "https://meet.google.com/demo-mock-3"),
            (iv2, (today + timedelta(days=6)).isoformat(), "10:00", "10:30", "Behavioural", "STAR answers, teamwork",
             "Online", "https://meet.google.com/demo-mock-4"),
        ]
        for s in slots:
            cur.execute("""
                INSERT INTO mock_slots (interviewer_id, slot_date, start_time, end_time, focus, topics, mode, meeting_link)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, s)

        demo = cur2.execute("SELECT id FROM students WHERE email = 'student@reva.edu.in'").fetchone()
        if demo:
            # One upcoming booking and one completed mock with feedback for the demo student.
            cur.execute("""
                INSERT INTO mock_slots (interviewer_id, slot_date, start_time, end_time, focus, topics, mode,
                                        meeting_link, status, student_id, target_role, student_topics, booked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'booked', ?, ?, ?, CURRENT_TIMESTAMP)
            """, (iv, (today + timedelta(days=1)).isoformat(), "17:00", "17:45", "Technical", "Mixed DSA round",
                  "Online", "https://meet.google.com/demo-mock-5", demo['id'], "Backend Developer",
                  "Arrays, hashing, SQL"))
            cur.execute("""
                INSERT INTO mock_slots (interviewer_id, slot_date, start_time, end_time, focus, topics, mode,
                                        meeting_link, status, student_id, target_role, student_topics, booked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, CURRENT_TIMESTAMP)
            """, (iv2, (today - timedelta(days=3)).isoformat(), "15:00", "15:30", "HR", "HR basics", "Online",
                  "https://meet.google.com/demo-mock-6", demo['id'], "Data Analyst", "Introduction, career goals"))
            done = cur.lastrowid
            cur.execute("""
                INSERT INTO mock_feedback (slot_id, interviewer_id, student_id, technical, communication,
                                           problem_solving, confidence, verdict, strengths, improvements, resources)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (done, iv2, demo['id'], 3, 4, 3, 3, "Almost ready",
                  "Clear self-introduction; good examples from your college project.",
                  "Answers ran long — keep each under 2 minutes. Prepare a sharper answer to 'why this role'.",
                  "Practise 5 STAR stories; record yourself once and watch it back."))
        print("Seeded demo interviewers (interviewer login: arjun@nimbustech.com / interviewer123) "
              "and sample mock-interview slots.")

    # ---- A second demo student who applied to the approved Nimbus drive, so the
    #      interviewer's campus round has a candidate to evaluate ----
    cur.execute("SELECT id FROM students WHERE email = 'aisha@reva.edu.in'")
    reva = cur2.execute("SELECT id FROM colleges WHERE name = 'REVA University'").fetchone()
    drive = cur2.execute("""SELECT company_visit_id FROM visit_requests
                            WHERE status = 'approved' AND company_visit_id IS NOT NULL LIMIT 1""").fetchone()
    if not cur.fetchone() and reva and drive:
        cur.execute("""
            INSERT INTO students (name, srn, section, course, department, year, semester, cgpa, email, password_hash,
                                  college_id, skills)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Aisha Khan", "R22IS045", "B", "ISE", "Information Science", "3rd Year", "5", 8.4,
              "aisha@reva.edu.in", generate_password_hash("student123"), reva['id'],
              "SQL, Python, Excel, Power BI, Statistics"))
        aisha = cur.lastrowid
        cur.execute("""INSERT INTO resume_items (student_id, kind, title, organization, duration, description)
                       VALUES (?, 'project', ?, ?, ?, ?)""",
                    (aisha, "Retail Sales Dashboard", "Course project", "2026",
                     "Power BI dashboard over 2 years of sales data with SQL-based ETL."))
        cur.execute("INSERT OR IGNORE INTO applications (student_id, company_id) VALUES (?, ?)",
                    (aisha, drive['company_visit_id']))
        demo = cur2.execute("SELECT id FROM students WHERE email = 'student@reva.edu.in'").fetchone()
        if demo:
            cur.execute("INSERT OR IGNORE INTO applications (student_id, company_id) VALUES (?, ?)",
                        (demo['id'], drive['company_visit_id']))
        print("Seeded demo student 'Aisha Khan' (aisha@reva.edu.in / student123) as an applicant to the Nimbus drive.")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == '__main__':
    run()
