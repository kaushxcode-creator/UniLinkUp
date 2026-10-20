"""
app.py
------
The main Flask application for UniLinkUp.

Run it with:
    python app.py

Then open  http://127.0.0.1:5000  in your browser.

HOW AUTH WORKS (kept intentionally simple):
- We do NOT use Flask-Login. Instead we store a couple of values directly
  in Flask's built-in `session` object (a signed cookie):
    session['role']       -> 'student' or 'employee'
    session['user_id']    -> the student's or employee's row id
    session['college_id'] -> the college the logged-in person belongs to
- Two small decorators (`student_login_required`, `employee_login_required`)
  guard the routes that should only be reachable after logging in.

HOW THE DATABASE WORKS:
- We use Python's built-in `sqlite3` module (see db.py) instead of an ORM,
  so the ONLY external package you need to `pip install` is Flask.
- `unilink.db` is a single file created automatically the first time
  you run the app -- no separate database server required.
"""

import os
import time
import secrets
from functools import wraps
from datetime import datetime, date
import random

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import db as dbm
import chatbot

# --------------------------------------------------------------------------
# App configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}
ALLOWED_RESUME_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
DEPARTMENTS = ['Computer Science', 'Information Science', 'Electronics & Communication',
                'Electrical & Electronics', 'AI & Machine Learning', 'Data Science',
                'Mechanical', 'Civil', 'MBA', 'MCA', 'Other']

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-secret-key-before-deploying'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB upload limit
dbm.init_app(app)

# Make sure every upload subfolder exists, even on a fresh clone where an
# empty directory may not have survived a zip/git transfer.
for _sub in ('certificates', 'documents', 'resumes', 'doubts', 'profile_pictures'):
    os.makedirs(os.path.join(UPLOAD_ROOT, _sub), exist_ok=True)


def allowed_file(filename, allowed=None):
    allowed = allowed or ALLOWED_EXTENSIONS
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


@app.template_filter('fmt_date')
def fmt_date(value, fmt='%d %b %Y'):
    """Jinja filter: turns an ISO date string ('2026-09-06') into '06 Sep 2026'."""
    d = parse_date(value)
    return d.strftime(fmt) if d else ''


# --------------------------------------------------------------------------
# Auth decorators & current-user helpers
# --------------------------------------------------------------------------
def student_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'student':
            flash('Please log in as a student to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def employee_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'employee':
            flash('Please log in with your college placement-cell account.', 'warning')
            return redirect(url_for('college_login'))
        return f(*args, **kwargs)
    return wrapper


def faculty_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'faculty':
            flash('Please log in with your faculty account.', 'warning')
            return redirect(url_for('faculty_login'))
        return f(*args, **kwargs)
    return wrapper


def company_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'company':
            flash('Please log in with your company account.', 'warning')
            return redirect(url_for('company_login'))
        return f(*args, **kwargs)
    return wrapper


def interviewer_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'interviewer':
            flash('Please log in with your interviewer account.', 'warning')
            return redirect(url_for('interviewer_login'))
        return f(*args, **kwargs)
    return wrapper


def current_interviewer():
    if session.get('role') == 'interviewer':
        return dbm.query_db("""SELECT i.*, c.name AS company_name FROM interviewers i
                               JOIN companies c ON c.id = i.company_id WHERE i.id = ?""",
                            (session['user_id'],), one=True)
    return None


def current_company():
    if session.get('role') == 'company':
        return dbm.query_db("SELECT * FROM companies WHERE id = ?", (session['user_id'],), one=True)
    return None


def current_student():
    if session.get('role') == 'student':
        return dbm.query_db("SELECT * FROM students WHERE id = ?", (session['user_id'],), one=True)
    return None


def current_employee():
    if session.get('role') == 'employee':
        return dbm.query_db("SELECT * FROM employees WHERE id = ?", (session['user_id'],), one=True)
    return None


def current_faculty():
    if session.get('role') == 'faculty':
        return dbm.query_db("SELECT * FROM faculty WHERE id = ?", (session['user_id'],), one=True)
    return None


def profile_completion(student):
    fields = [student['name'], student['srn'], student['section'], student['course'],
              student['year'], student['semester'], student['cgpa'], student['email']]
    filled = sum(1 for f in fields if f not in (None, ""))
    return round((filled / len(fields)) * 100)


def get_certificates(student_id):
    return dbm.query_db(
        "SELECT * FROM certificates WHERE student_id = ? ORDER BY uploaded_at DESC", (student_id,))


def get_documents(student_id):
    return dbm.query_db(
        "SELECT * FROM documents WHERE student_id = ? ORDER BY uploaded_at DESC", (student_id,))


def has_required_uploads(student_id):
    """A student must have at least one certificate AND one document on file
    before they're allowed to apply to any internship/job drive."""
    return bool(get_certificates(student_id)) and bool(get_documents(student_id))


def best_main_score(student_id):
    rows = dbm.query_db(
        "SELECT * FROM assessment_results WHERE student_id = ? AND mode = 'main' ORDER BY score DESC LIMIT 1",
        (student_id,), one=True)
    return rows


def best_test_score(student_id, test_id):
    return dbm.query_db(
        "SELECT * FROM faculty_test_attempts WHERE student_id = ? AND test_id = ? ORDER BY score DESC LIMIT 1",
        (student_id, test_id), one=True)


def overall_progress(student):
    profile_score = profile_completion(student) * 0.4
    main_attempt = best_main_score(student['id'])
    assessment_score = 30 if main_attempt else 0
    cert_count = len(dbm.query_db("SELECT id FROM certificates WHERE student_id = ?", (student['id'],)))
    cert_score = (min(cert_count, 3) / 3) * 30
    return round(profile_score + assessment_score + cert_score)


# --------------------------------------------------------------------------
# ELIGIBILITY MATCH ENGINE
# --------------------------------------------------------------------------
def _split_list(text):
    """'Python, SQL,  React' -> ['Python', 'SQL', 'React']. Handles None/''"""
    if not text:
        return []
    return [t.strip() for t in text.split(',') if t.strip()]


def eligibility_match(student, company):
    """Computes how good a fit a student is for a company's campus drive.

    Returns a dict with:
      percent  -- 0-100 overall fit score (soft signal, shown to both sides)
      eligible -- hard pass/fail against the company's stated CGPA/branch/year
                  criteria (this is what should gate "Apply Now" logically,
                  independent of the softer percent score)
      reasons  -- list of (label, ok, detail) tuples for a human-readable
                  breakdown, in the same order the score is built up
    """
    reasons = []
    points = 0.0

    # ---- CGPA: 30 pts ----
    min_cgpa = company['min_cgpa'] or 0
    student_cgpa = student['cgpa'] or 0
    if min_cgpa <= 0:
        cgpa_ok, cgpa_pts = True, 30.0
        reasons.append(('Minimum CGPA', True, f"No minimum set · you have {student_cgpa}"))
    else:
        cgpa_ok = student_cgpa >= min_cgpa
        cgpa_pts = 30.0 if cgpa_ok else max(0.0, 30.0 * (student_cgpa / min_cgpa))
        reasons.append(('Minimum CGPA', cgpa_ok, f"Needs {min_cgpa}+ · you have {student_cgpa}"))
    points += cgpa_pts

    # ---- Branch / course: 20 pts ----
    eligible_courses = _split_list(company['eligible_courses'] if 'eligible_courses' in company.keys() else None)
    student_course = (student['course'] or '').lower()
    if not eligible_courses:
        course_ok, course_pts = True, 20.0
        reasons.append(('Branch / Course', True, 'Open to all branches'))
    else:
        course_ok = any(ec.lower() in student_course or student_course in ec.lower()
                         for ec in eligible_courses if student_course)
        course_pts = 20.0 if course_ok else 0.0
        reasons.append(('Branch / Course', course_ok, f"Requires: {', '.join(eligible_courses)}"))
    points += course_pts

    # ---- Year: 15 pts ----
    eligible_years = _split_list(company['eligible_years'] if 'eligible_years' in company.keys() else None)
    student_year = (student['year'] or '').lower()
    if not eligible_years:
        year_ok, year_pts = True, 15.0
        reasons.append(('Year of Study', True, 'Open to all years'))
    else:
        year_ok = any(ey.lower() == student_year or ey.lower() in student_year for ey in eligible_years if student_year)
        year_pts = 15.0 if year_ok else 0.0
        reasons.append(('Year of Study', year_ok, f"Requires: {', '.join(eligible_years)}"))
    points += year_pts

    # ---- Required skills overlap: 25 pts ----
    required_skills = _split_list(company['required_skills'] if 'required_skills' in company.keys() else None)
    student_skills = _split_list(student['skills'] if 'skills' in student.keys() else None)
    student_skills_l = {s.lower() for s in student_skills}
    if not required_skills:
        skills_pts = 25.0
        reasons.append(('Skills', True, 'No specific skills listed for this drive'))
    else:
        matched = [s for s in required_skills if s.lower() in student_skills_l]
        frac = len(matched) / len(required_skills)
        skills_pts = 25.0 * frac
        reasons.append(('Skills', frac >= 0.5,
                         f"{len(matched)}/{len(required_skills)} required skills on your profile"
                         + (f" ({', '.join(matched)})" if matched else '')))
    points += skills_pts

    # ---- Skill assessment bonus: 10 pts ----
    # Drives posted through the Company portal can also set a minimum
    # assessment score (performance-based eligibility); that becomes a hard
    # requirement alongside CGPA / branch / year.
    min_assess = (company['min_assessment_pct'] if 'min_assessment_pct' in company.keys() else 0) or 0
    best = best_main_score(student['id'])
    assess_ok = True
    if best and best['total']:
        frac = best['score'] / best['total']
        assess_pts = 10.0 * frac
        pct = round(frac * 100)
        if min_assess:
            assess_ok = pct >= min_assess
            reasons.append(('Skill Assessment', assess_ok, f"Needs {min_assess}%+ · your best is {pct}%"))
        else:
            reasons.append(('Skill Assessment', frac >= 0.5, f"Best score {best['score']}/{best['total']}"))
    else:
        assess_pts = 0.0
        assess_ok = not min_assess
        reasons.append(('Skill Assessment', False,
                        (f"Needs {min_assess}%+ · " if min_assess else '')
                        + 'Not attempted yet — take it from the Skill Assessment tab'))
    points += assess_pts

    percent = round(min(points, 100.0))
    hard_eligible = cgpa_ok and course_ok and year_ok and assess_ok
    return {'percent': percent, 'eligible': hard_eligible, 'reasons': reasons}


# --------------------------------------------------------------------------
# SKILL GAP ANALYSIS — used by the student "Skill Enhancement" page.
# Compares a student's own skills against what's actually being asked for
# across every active drive at their college, so the gap is grounded in real
# demand rather than a generic checklist.
# --------------------------------------------------------------------------
def skill_gap_analysis(student):
    student_skills_l = {s.lower() for s in _split_list(student['skills'])}
    companies = []
    if student['college_id']:
        companies = dbm.query_db(
            "SELECT required_skills FROM company_visits WHERE college_id = ?", (student['college_id'],))

    demand = {}
    for c in companies:
        for skill in _split_list(c['required_skills']):
            key = skill.strip()
            if not key:
                continue
            demand[key.lower()] = demand.get(key.lower(), {'label': key, 'count': 0})
            demand[key.lower()]['count'] += 1

    gaps = sorted(
        (v for k, v in demand.items() if k not in student_skills_l),
        key=lambda v: v['count'], reverse=True)
    strengths = sorted(
        (v for k, v in demand.items() if k in student_skills_l),
        key=lambda v: v['count'], reverse=True)

    best = best_main_score(student['id'])
    if best and best['total']:
        frac = best['score'] / best['total']
        if frac >= 0.75:
            readiness = 'High'
        elif frac >= 0.45:
            readiness = 'Medium'
        else:
            readiness = 'Needs work'
    else:
        readiness = 'Not assessed yet'

    return {
        'gaps': gaps[:8],
        'strengths': strengths[:8],
        'readiness': readiness,
        'has_demand_data': bool(demand),
    }


def match_company_for_skill(college_id, skill):
    """Best-effort: which live company drive at this college actually asks
    for this skill? Used so a faculty member reviewing a slot request knows
    *why* a student needs it, not just that they do. Returns None (never
    fabricates a match) if no drive lists it."""
    if not college_id or not skill:
        return None
    companies = dbm.query_db(
        "SELECT company_name, required_skills FROM company_visits WHERE college_id = ?", (college_id,))
    skill_l = skill.strip().lower()
    for c in companies:
        if skill_l in {s.lower() for s in _split_list(c['required_skills'])}:
            return c['company_name']
    return None


def student_percentile(college_id, field, value):
    """What % of this student's own college peers they're ahead of on a
    numeric field (e.g. cgpa). Returns None if there's nothing to compare
    against yet (too few students) so the UI can hide the stat honestly
    instead of showing a meaningless 100%."""
    if value is None or not college_id:
        return None
    rows = dbm.query_db(
        f"SELECT {field} AS v FROM students WHERE college_id = ? AND {field} IS NOT NULL", (college_id,))
    values = [r['v'] for r in rows]
    if len(values) < 3:
        return None
    lower = sum(1 for v in values if v < value)
    return round((lower / len(values)) * 100)


# --------------------------------------------------------------------------
# RESUME ATS SCORER — a fully offline, heuristic readability/completeness
# checker. It does NOT call any external ATS product; it's a transparent,
# explainable checklist modeled on what real applicant-tracking systems and
# campus placement cells commonly screen for.
# --------------------------------------------------------------------------
ACTION_VERBS = [
    'developed', 'built', 'led', 'designed', 'implemented', 'created', 'managed',
    'improved', 'achieved', 'launched', 'optimized', 'automated', 'analyzed',
    'collaborated', 'delivered', 'reduced', 'increased', 'organized', 'mentored',
    'presented', 'researched', 'deployed', 'tested', 'coordinated',
]
SECTION_KEYWORDS = {
    'education': ['education', 'academic', 'qualification'],
    'experience': ['experience', 'internship', 'project', 'work history'],
    'skills': ['skills', 'technical skills', 'tech stack'],
    'extras': ['certification', 'achievement', 'award', 'activity', 'extracurricular'],
}


def extract_resume_text(filepath, ext):
    """Best-effort plain-text extraction. Returns '' (never raises) so a
    parsing failure degrades to a low score with a clear suggestion instead
    of a crash."""
    ext = ext.lower()
    try:
        if ext == 'txt':
            with open(filepath, 'r', errors='ignore') as f:
                return f.read()
        if ext == 'pdf':
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            return "\n".join((page.extract_text() or '') for page in reader.pages)
        if ext == 'docx':
            import docx
            doc = docx.Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ''
    return ''  # .doc (legacy binary) isn't parseable without extra tooling


def ats_score(text, student):
    """Returns (score 0-100, feedback: list[str]). Every point is tied to a
    concrete, human-readable reason so the feedback list doubles as the fix."""
    feedback = []
    score = 0
    text_l = (text or '').lower()

    if not text.strip():
        return 0, ["We couldn't read any text from this file — if it's a scanned/image PDF, "
                    "try exporting a text-based PDF from Word/Google Docs instead."]

    # Contact info — 15 pts
    import re
    has_email = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text))
    has_phone = bool(re.search(r'(\+?\d[\d\-\s]{8,}\d)', text))
    if has_email:
        score += 10
    else:
        feedback.append("Add a professional email address near the top so recruiters can reach you.")
    if has_phone:
        score += 5
    else:
        feedback.append("Add a phone number — many ATS tools flag resumes with no contact number.")

    # Section coverage — 40 pts (10 each)
    for section, keywords in SECTION_KEYWORDS.items():
        if any(k in text_l for k in keywords):
            score += 10
        else:
            nice = {'education': 'an Education section', 'experience': 'a Projects/Experience section',
                    'skills': 'a dedicated Skills section', 'extras': 'a Certifications/Achievements section'}
            feedback.append(f"Add {nice[section]} — its absence is one of the most common reasons ATS tools score a resume low.")

    # Skill keyword match vs the student's own profile skills — 20 pts
    student_skills = _split_list(student['skills'] if student and 'skills' in student.keys() else None)
    if student_skills:
        matched = [s for s in student_skills if s.lower() in text_l]
        frac = len(matched) / len(student_skills)
        score += round(20 * frac)
        missing = [s for s in student_skills if s.lower() not in text_l]
        if missing:
            feedback.append(f"These skills are on your UniLinkUp profile but not in your resume text — add them verbatim: {', '.join(missing[:6])}.")
    else:
        feedback.append("Add a Skills list to your profile first, so we can check it appears in your resume too.")

    # Action verbs — 10 pts
    verb_hits = sum(1 for v in ACTION_VERBS if v in text_l)
    if verb_hits >= 4:
        score += 10
    elif verb_hits >= 1:
        score += 5
        feedback.append("Start more bullet points with strong action verbs (Built, Led, Designed, Improved...) instead of passive phrasing.")
    else:
        feedback.append("Start your bullet points with action verbs (Built, Led, Designed, Improved...) — ATS tools weight these heavily.")

    # Length sanity — 10 pts
    word_count = len(text.split())
    if 250 <= word_count <= 1100:
        score += 10
    elif word_count < 250:
        feedback.append(f"Your resume is quite short ({word_count} words) — expand your project/internship bullet points with specifics and outcomes.")
    else:
        feedback.append(f"Your resume looks long ({word_count} words) — for a student resume, tighten it toward 1 page (roughly 400-700 words).")

    # Structure sanity (bullets / line breaks, not one wall of text) — 5 pts
    line_count = len([ln for ln in text.splitlines() if ln.strip()])
    if line_count >= 12:
        score += 5
    else:
        feedback.append("Break your content into clear bullet points/lines rather than dense paragraphs — ATS parsers and recruiters both prefer scannable formatting.")

    score = min(score, 100)
    if score >= 90:
        feedback.insert(0, "Strong resume — this is in the range recruiters and most ATS filters respond well to.")
    return score, feedback


# --------------------------------------------------------------------------
# RESUME BUILDER — turns a student's profile (name, CGPA, skills, college)
# plus their own added experience/project/achievement entries into an
# actual resume file, in whichever format they pick. All three builders
# below share the same grouped data so the TXT/DOCX/PDF versions always
# say the same thing.
# --------------------------------------------------------------------------
RESUME_ITEM_KINDS = ['experience', 'project', 'achievement']
RESUME_ITEM_LABELS = {'experience': 'Experience', 'project': 'Projects', 'achievement': 'Achievements'}


def _resume_data(student, items):
    grouped = {k: [] for k in RESUME_ITEM_KINDS}
    for it in items:
        if it['kind'] in grouped:
            grouped[it['kind']].append(it)
    college_name = None
    if student['college_id']:
        college = dbm.query_db("SELECT name FROM colleges WHERE id = ?", (student['college_id'],), one=True)
        college_name = college['name'] if college else None
    return grouped, college_name


def _resume_item_head(r):
    head = r['title']
    if r['organization']:
        head += f" — {r['organization']}"
    if r['duration']:
        head += f" ({r['duration']})"
    return head


def build_resume_text(student, items):
    grouped, college_name = _resume_data(student, items)
    lines = [student['name'], student['email']]
    edu_bits = [b for b in [student['course'], student['department'], student['year'], college_name] if b]
    if edu_bits:
        lines.append(" | ".join(edu_bits))
    if student['resume_summary']:
        lines += ["", "SUMMARY", student['resume_summary']]
    if student['skills']:
        lines += ["", "SKILLS", student['skills']]
    if student['cgpa']:
        lines += ["", "EDUCATION",
                  f"{college_name or ''} — {student['course'] or ''} ({student['department'] or ''}), CGPA {student['cgpa']}"]
    for kind in RESUME_ITEM_KINDS:
        rows = grouped[kind]
        if not rows:
            continue
        lines += ["", RESUME_ITEM_LABELS[kind].upper()]
        for r in rows:
            lines.append(_resume_item_head(r))
            if r['description']:
                lines.append(r['description'])
    return "\n".join(lines)


def build_resume_docx(path, student, items):
    import docx
    grouped, college_name = _resume_data(student, items)
    doc = docx.Document()
    doc.add_heading(student['name'], level=0)
    doc.add_paragraph(student['email'])
    edu_bits = [b for b in [student['course'], student['department'], student['year'], college_name] if b]
    if edu_bits:
        doc.add_paragraph(" | ".join(edu_bits))
    if student['resume_summary']:
        doc.add_heading('Summary', level=1)
        doc.add_paragraph(student['resume_summary'])
    if student['skills']:
        doc.add_heading('Skills', level=1)
        doc.add_paragraph(student['skills'])
    if student['cgpa']:
        doc.add_heading('Education', level=1)
        doc.add_paragraph(f"{college_name or ''} — {student['course'] or ''} ({student['department'] or ''}), CGPA {student['cgpa']}")
    for kind in RESUME_ITEM_KINDS:
        rows = grouped[kind]
        if not rows:
            continue
        doc.add_heading(RESUME_ITEM_LABELS[kind], level=1)
        for r in rows:
            p = doc.add_paragraph(style='List Bullet')
            p.add_run(_resume_item_head(r)).bold = True
            if r['description']:
                doc.add_paragraph(r['description'])
    doc.save(path)


def build_resume_pdf(path, student, items):
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    grouped, college_name = _resume_data(student, items)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ResumeTitle', parent=styles['Title'], fontSize=20, spaceAfter=2)
    h_style = ParagraphStyle('ResumeHeading', parent=styles['Heading2'], spaceBefore=12, spaceAfter=4)
    body = styles['BodyText']

    doc = SimpleDocTemplate(path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.7 * inch, rightMargin=0.7 * inch)
    story = [Paragraph(escape(student['name']), title_style), Paragraph(escape(student['email']), body)]
    edu_bits = [b for b in [student['course'], student['department'], student['year'], college_name] if b]
    if edu_bits:
        story.append(Paragraph(escape(" | ".join(edu_bits)), body))

    if student['resume_summary']:
        story += [Paragraph('Summary', h_style), Paragraph(escape(student['resume_summary']), body)]
    if student['skills']:
        story += [Paragraph('Skills', h_style), Paragraph(escape(student['skills']), body)]
    if student['cgpa']:
        story += [Paragraph('Education', h_style),
                  Paragraph(escape(f"{college_name or ''} — {student['course'] or ''} "
                                    f"({student['department'] or ''}), CGPA {student['cgpa']}"), body)]

    for kind in RESUME_ITEM_KINDS:
        rows = grouped[kind]
        if not rows:
            continue
        story.append(Paragraph(RESUME_ITEM_LABELS[kind], h_style))
        for r in rows:
            story.append(Paragraph(f"<b>{escape(_resume_item_head(r))}</b>", body))
            if r['description']:
                story.append(Paragraph(escape(r['description']), body))
            story.append(Spacer(1, 6))

    doc.build(story)


# Make helper functions available inside every Jinja template automatically.
# ASSET_VERSION is appended as a "?v=..." query string on the CSS/JS <link>/
# <script> tags in base.html — it changes every time the app process starts,
# so a browser that cached an older style.css/notifications.js is forced to
# fetch the current one instead of silently reusing a stale cached copy.
ASSET_VERSION = str(int(time.time()))


@app.context_processor
def inject_globals():
    pending_requests = 0
    if session.get('role') == 'employee' and session.get('college_id'):
        row = dbm.query_db("SELECT COUNT(*) AS c FROM visit_requests WHERE college_id = ? AND status = 'pending'",
                           (session['college_id'],), one=True)
        pending_requests = row['c'] if row else 0
    return dict(current_student=current_student, current_employee=current_employee,
                current_faculty=current_faculty, current_company=current_company,
                current_interviewer=current_interviewer,
                pending_company_requests=pending_requests, ASSET_VERSION=ASSET_VERSION)


# --------------------------------------------------------------------------
# Public / landing routes
# --------------------------------------------------------------------------
@app.route('/')
def index():
    if session.get('role') == 'student':
        return redirect(url_for('student_home'))
    if session.get('role') == 'employee':
        return redirect(url_for('college_home'))
    if session.get('role') == 'faculty':
        return redirect(url_for('faculty_home'))
    if session.get('role') == 'company':
        return redirect(url_for('company_home'))
    if session.get('role') == 'interviewer':
        return redirect(url_for('interviewer_home'))

    stats = {
        'companies': len(dbm.query_db("SELECT id FROM companies")),
        'colleges': len(dbm.query_db("SELECT id FROM colleges")),
        'students': len(dbm.query_db("SELECT id FROM students")),
        'drives': len(dbm.query_db("SELECT id FROM company_visits")),
    }
    slides_dir = os.path.join(BASE_DIR, 'static', 'img', 'slides')
    slide_photos = set(os.listdir(slides_dir)) if os.path.isdir(slides_dir) else set()
    return render_template('index.html', stats=stats, slide_photos=slide_photos)


@app.route('/about')
def about():
    return render_template('about.html')


# --------------------------------------------------------------------------
# STUDENT: register / login / logout
# --------------------------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    colleges = dbm.query_db("SELECT * FROM colleges ORDER BY name")

    if request.method == 'POST':
        form = request.form
        name = form.get('name', '').strip()
        srn = form.get('srn', '').strip()
        section = form.get('section', '').strip()
        course = form.get('course', '').strip()
        department = form.get('department', '').strip()
        year = form.get('year', '').strip()
        semester = form.get('semester', '').strip()
        cgpa = form.get('cgpa', '').strip()
        email = form.get('email', '').strip().lower()
        password = form.get('password', '')
        confirm_password = form.get('confirm_password', '')
        college_id = form.get('college_id') or None
        skills = form.get('skills', '').strip()

        if not all([name, srn, course, year, semester, cgpa, email, password]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('register_student.html', colleges=colleges, form=form)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register_student.html', colleges=colleges, form=form)

        if dbm.query_db("SELECT id FROM students WHERE email = ?", (email,), one=True):
            flash('An account with this email already exists.', 'danger')
            return render_template('register_student.html', colleges=colleges, form=form)

        if dbm.query_db("SELECT id FROM students WHERE srn = ?", (srn,), one=True):
            flash('An account with this SRN already exists.', 'danger')
            return render_template('register_student.html', colleges=colleges, form=form)

        try:
            cgpa_value = float(cgpa)
        except ValueError:
            flash('CGPA must be a number, e.g. 8.5', 'danger')
            return render_template('register_student.html', colleges=colleges, form=form)

        dbm.execute_db("""
            INSERT INTO students (name, srn, section, course, department, year, semester, cgpa, email, password_hash, college_id, skills)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, srn, section, course, department, year, semester, cgpa_value, email,
              generate_password_hash(password), int(college_id) if college_id else None, skills))

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register_student.html', colleges=colleges, form={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        student = dbm.query_db("SELECT * FROM students WHERE email = ?", (email,), one=True)
        if student and check_password_hash(student['password_hash'], password):
            session.clear()
            session['role'] = 'student'
            session['user_id'] = student['id']
            session['college_id'] = student['college_id']
            flash(f"Welcome back, {student['name']}!", 'success')
            return redirect(url_for('student_home'))

        flash('Incorrect email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# --------------------------------------------------------------------------
# FORGOT / RESET PASSWORD
# There's no email server configured on this build (kept fully offline, per
# the project's design), so instead of an emailed reset link we verify
# identity against a second piece of information already on file, then let
# the person set a new password immediately. A short-lived flag in the
# session (reset_role / reset_user_id) is what gates access to the actual
# reset form, so it can't be reached by guessing a URL alone.
# --------------------------------------------------------------------------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        srn = request.form.get('srn', '').strip()

        student = dbm.query_db(
            "SELECT * FROM students WHERE email = ? AND srn = ?", (email, srn), one=True)
        if student:
            session.clear()
            session['reset_role'] = 'student'
            session['reset_user_id'] = student['id']
            flash('Identity verified — choose a new password below.', 'success')
            return redirect(url_for('reset_password'))

        flash("We couldn't find a student account matching that email and SRN.", 'danger')

    return render_template('forgot_password.html')


@app.route('/college/forgot-password', methods=['GET', 'POST'])
def college_forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        college_email = request.form.get('college_email', '').strip().lower()

        employee = dbm.query_db("SELECT * FROM employees WHERE email = ?", (email,), one=True)
        college = dbm.query_db(
            "SELECT * FROM colleges WHERE official_email = ?", (college_email,), one=True)

        if employee and college and employee['college_id'] == college['id']:
            session.clear()
            session['reset_role'] = 'employee'
            session['reset_user_id'] = employee['id']
            flash('Identity verified — choose a new password below.', 'success')
            return redirect(url_for('reset_password'))

        flash("We couldn't verify those details against a placement-officer account.", 'danger')

    return render_template('college_forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    role = session.get('reset_role')
    user_id = session.get('reset_user_id')
    if role not in ('student', 'employee') or not user_id:
        flash('Please verify your identity first.', 'warning')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('reset_password.html', role=role)
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', role=role)

        table = 'students' if role == 'student' else 'employees'
        dbm.execute_db(f"UPDATE {table} SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(password), user_id))

        session.pop('reset_role', None)
        session.pop('reset_user_id', None)
        flash('Password updated — please log in.', 'success')
        return redirect(url_for('login') if role == 'student' else url_for('college_login'))

    return render_template('reset_password.html', role=role)


# --------------------------------------------------------------------------
# STUDENT PORTAL
# --------------------------------------------------------------------------
@app.route('/student/home')
@student_login_required
def student_home():
    student = current_student()
    today = date.today()

    companies = []
    if student['college_id']:
        companies = dbm.query_db(
            "SELECT * FROM company_visits WHERE college_id = ? ORDER BY reg_end ASC",
            (student['college_id'],))

    applied_rows = dbm.query_db(
        "SELECT company_id FROM applications WHERE student_id = ?", (student['id'],))
    applied_ids = {r['company_id'] for r in applied_rows}
    can_apply = has_required_uploads(student['id'])
    matches = {c['id']: eligibility_match(student, c) for c in companies}

    return render_template('student_home.html', student=student, companies=companies,
                            today=today, applied_ids=applied_ids, parse_date=parse_date,
                            can_apply=can_apply, matches=matches)


def _blocked_from_applying(student):
    """Shared eligibility gate for both the review page and the final submit.
    Returns a redirect response if the student is blocked, otherwise None."""
    if not has_required_uploads(student['id']):
        flash('Upload at least one certificate and one document before applying.', 'warning')
        return redirect(url_for('profile'))
    return None


@app.route('/student/apply/<int:company_id>')
@student_login_required
def apply_review(company_id):
    """Review page shown before a student confirms an application. Shows the
    student's key profile fields plus every certificate/document already on
    file, fetched automatically so nothing has to be re-entered or re-uploaded."""
    student = current_student()
    blocked = _blocked_from_applying(student)
    if blocked:
        return blocked

    company = dbm.query_db("SELECT * FROM company_visits WHERE id = ?", (company_id,), one=True)
    if not company:
        abort(404)
    if company['college_id'] != student['college_id']:
        abort(403)

    today = date.today()
    is_open = parse_date(company['reg_start']) <= today <= parse_date(company['reg_end'])
    already = dbm.query_db(
        "SELECT id FROM applications WHERE student_id = ? AND company_id = ?",
        (student['id'], company_id), one=True)
    match = eligibility_match(student, company)

    return render_template('apply_review.html', student=student, company=company,
                            certificates=get_certificates(student['id']),
                            documents=get_documents(student['id']),
                            is_open=is_open, already=already, match=match)


@app.route('/student/apply/<int:company_id>', methods=['POST'])
@student_login_required
def apply_to_company(company_id):
    student = current_student()
    blocked = _blocked_from_applying(student)
    if blocked:
        return blocked

    company = dbm.query_db("SELECT * FROM company_visits WHERE id = ?", (company_id,), one=True)
    if not company:
        abort(404)
    if company['college_id'] != student['college_id']:
        abort(403)

    today = date.today()
    if not (parse_date(company['reg_start']) <= today <= parse_date(company['reg_end'])):
        flash('Registration window for this company is not currently open.', 'warning')
        return redirect(url_for('student_home'))

    already = dbm.query_db(
        "SELECT id FROM applications WHERE student_id = ? AND company_id = ?",
        (student['id'], company_id), one=True)
    if already:
        flash('You have already applied to this company.', 'info')
    else:
        dbm.execute_db(
            "INSERT INTO applications (student_id, company_id) VALUES (?, ?)",
            (student['id'], company_id))
        flash(f"Applied to {company['company_name']} successfully!", 'success')

    return redirect(url_for('student_home'))


@app.route('/student/profile', methods=['GET', 'POST'])
@student_login_required
def profile():
    student = current_student()

    if request.method == 'POST':
        section = request.form.get('section', student['section'])
        course = request.form.get('course', student['course'])
        department = request.form.get('department', student['department'])
        year = request.form.get('year', student['year'])
        semester = request.form.get('semester', student['semester'])
        cgpa = request.form.get('cgpa')
        cgpa_value = student['cgpa']
        if cgpa:
            try:
                cgpa_value = float(cgpa)
            except ValueError:
                flash('CGPA must be numeric.', 'danger')
                return redirect(url_for('profile'))
        skills = request.form.get('skills', student['skills'] or '')

        dbm.execute_db("""
            UPDATE students SET section = ?, course = ?, department = ?, year = ?, semester = ?, cgpa = ?, skills = ?
            WHERE id = ?
        """, (section, course, department, year, semester, cgpa_value, skills, student['id']))
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))

    results = dbm.query_db(
        "SELECT * FROM assessment_results WHERE student_id = ? ORDER BY taken_at DESC",
        (student['id'],))
    certificates = dbm.query_db(
        "SELECT * FROM certificates WHERE student_id = ? ORDER BY uploaded_at DESC", (student['id'],))
    documents = dbm.query_db(
        "SELECT * FROM documents WHERE student_id = ? ORDER BY uploaded_at DESC", (student['id'],))
    resumes = dbm.query_db(
        "SELECT * FROM resumes WHERE student_id = ? ORDER BY uploaded_at DESC, id DESC", (student['id'],))
    latest_resume = resumes[0] if resumes else None
    latest_feedback = latest_resume['ats_feedback'].split('\n') if latest_resume and latest_resume['ats_feedback'] else []

    best = best_main_score(student['id'])
    learning_hours_total = dbm.query_db(
        "SELECT COALESCE(SUM(hours), 0) AS total FROM learning_logs WHERE student_id = ?",
        (student['id'],), one=True)['total']
    snapshot = {
        'cgpa_percentile': student_percentile(student['college_id'], 'cgpa', student['cgpa']),
        'skill_count': len(_split_list(student['skills'])),
        'certificate_count': len(certificates),
        'best_assessment': f"{best['score']}/{best['total']}" if best else None,
        'learning_hours': round(learning_hours_total, 1),
    }

    resume_shares = []
    if resumes:
        resume_ids = [r['id'] for r in resumes]
        placeholders = ','.join('?' for _ in resume_ids)
        resume_shares = dbm.query_db(
            f"SELECT * FROM resume_shares WHERE resume_id IN ({placeholders}) ORDER BY created_at DESC",
            resume_ids)

    return render_template('profile.html', student=student, results=results,
                            certificates=certificates, documents=documents,
                            resumes=resumes, latest_resume=latest_resume, latest_feedback=latest_feedback,
                            resume_shares=resume_shares,
                            snapshot=snapshot, progress=overall_progress(student))


@app.route('/student/upload/certificate', methods=['POST'])
@student_login_required
def upload_certificate():
    student = current_student()
    title = request.form.get('title', '').strip()
    file = request.files.get('file')

    if not title or not file or file.filename == '':
        flash('Please provide a title and choose a file.', 'danger')
        return redirect(url_for('profile'))
    if not allowed_file(file.filename):
        flash('Unsupported file type.', 'danger')
        return redirect(url_for('profile'))

    filename = secure_filename(f"{student['id']}_{datetime.utcnow().timestamp()}_{file.filename}")
    file.save(os.path.join(UPLOAD_ROOT, 'certificates', filename))
    dbm.execute_db(
        "INSERT INTO certificates (student_id, title, filename) VALUES (?, ?, ?)",
        (student['id'], title, filename))
    flash('Certificate uploaded.', 'success')
    return redirect(url_for('profile'))


@app.route('/student/upload/document', methods=['POST'])
@student_login_required
def upload_document():
    student = current_student()
    title = request.form.get('title', '').strip()
    file = request.files.get('file')

    if not title or not file or file.filename == '':
        flash('Please provide a title and choose a file.', 'danger')
        return redirect(url_for('profile'))
    if not allowed_file(file.filename):
        flash('Unsupported file type.', 'danger')
        return redirect(url_for('profile'))

    filename = secure_filename(f"{student['id']}_{datetime.utcnow().timestamp()}_{file.filename}")
    file.save(os.path.join(UPLOAD_ROOT, 'documents', filename))
    dbm.execute_db(
        "INSERT INTO documents (student_id, title, filename) VALUES (?, ?, ?)",
        (student['id'], title, filename))
    flash('Document uploaded.', 'success')
    return redirect(url_for('profile'))


@app.route('/student/upload/resume', methods=['POST'])
@student_login_required
def upload_resume():
    student = current_student()
    title = request.form.get('title', '').strip() or 'Resume'
    file = request.files.get('file')

    if not file or file.filename == '':
        flash('Please choose a file to upload.', 'danger')
        return redirect(url_for('profile'))
    if not allowed_file(file.filename, ALLOWED_RESUME_EXTENSIONS):
        flash('Please upload a PDF, DOC, DOCX, or TXT file.', 'danger')
        return redirect(url_for('profile'))

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f"{student['id']}_{datetime.utcnow().timestamp()}_{file.filename}")
    saved_path = os.path.join(UPLOAD_ROOT, 'resumes', filename)
    file.save(saved_path)

    text = extract_resume_text(saved_path, ext)
    score, feedback = ats_score(text, student)

    dbm.execute_db("""
        INSERT INTO resumes (student_id, title, filename, ats_score, ats_feedback)
        VALUES (?, ?, ?, ?, ?)
    """, (student['id'], title, filename, score, "\n".join(feedback)))

    flash(f'Resume uploaded — ATS readiness score: {score}/100.', 'success' if score >= 60 else 'info')
    return redirect(url_for('profile'))


@app.route('/student/upload/profile-picture', methods=['POST'])
@student_login_required
def upload_profile_picture():
    student = current_student()
    file = request.files.get('file')

    if not file or file.filename == '':
        flash('Please choose an image to upload.', 'danger')
        return redirect(url_for('profile'))
    if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
        flash('Please upload a PNG, JPG, JPEG or GIF image.', 'danger')
        return redirect(url_for('profile'))

    old_picture = student['profile_picture']
    filename = secure_filename(f"{student['id']}_{datetime.utcnow().timestamp()}_{file.filename}")
    file.save(os.path.join(UPLOAD_ROOT, 'profile_pictures', filename))
    dbm.execute_db("UPDATE students SET profile_picture = ? WHERE id = ?", (filename, student['id']))

    if old_picture:
        old_path = os.path.join(UPLOAD_ROOT, 'profile_pictures', old_picture)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    flash('Profile picture updated.', 'success')
    return redirect(url_for('profile'))


# --------------------------------------------------------------------------
# STUDENT: Resume Builder — pulls name/CGPA/skills/college straight from the
# profile, lets the student add experience/project/achievement entries and
# an editable summary, then generates an actual resume file (PDF/DOCX/TXT).
# The generated file is saved as a normal `resumes` row (so it gets an ATS
# score like any upload) with verification reset to pending, since it's a
# new document a college hasn't seen yet.
# --------------------------------------------------------------------------
@app.route('/student/resume-builder')
@student_login_required
def resume_builder():
    student = current_student()
    items = dbm.query_db(
        "SELECT * FROM resume_items WHERE student_id = ? ORDER BY kind, sort_order, id", (student['id'],))
    grouped = {k: [dict(r) for r in items if r['kind'] == k] for k in RESUME_ITEM_KINDS}
    return render_template('resume_builder.html', student=student, grouped=grouped,
                            labels=RESUME_ITEM_LABELS)


@app.route('/student/resume-builder/summary', methods=['POST'])
@student_login_required
def save_resume_summary():
    student = current_student()
    summary = request.form.get('summary', '').strip()
    dbm.execute_db("UPDATE students SET resume_summary = ? WHERE id = ?", (summary, student['id']))
    flash('Summary saved.', 'success')
    return redirect(url_for('resume_builder'))


@app.route('/student/resume-builder/items/add', methods=['POST'])
@student_login_required
def add_resume_item():
    student = current_student()
    kind = request.form.get('kind', '').strip()
    title = request.form.get('title', '').strip()
    organization = request.form.get('organization', '').strip()
    duration = request.form.get('duration', '').strip()
    description = request.form.get('description', '').strip()

    if kind not in RESUME_ITEM_KINDS or not title:
        flash('Please pick a section and give it a title.', 'danger')
        return redirect(url_for('resume_builder'))

    dbm.execute_db("""
        INSERT INTO resume_items (student_id, kind, title, organization, duration, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (student['id'], kind, title, organization, duration, description))
    flash(f'Added to {RESUME_ITEM_LABELS[kind]}.', 'success')
    return redirect(url_for('resume_builder'))


@app.route('/student/resume-builder/items/<int:item_id>/delete', methods=['POST'])
@student_login_required
def delete_resume_item(item_id):
    student = current_student()
    item = dbm.query_db("SELECT * FROM resume_items WHERE id = ?", (item_id,), one=True)
    if not item or item['student_id'] != student['id']:
        abort(404)
    dbm.execute_db("DELETE FROM resume_items WHERE id = ?", (item_id,))
    flash('Removed.', 'info')
    return redirect(url_for('resume_builder'))


@app.route('/student/resume-builder/generate', methods=['POST'])
@student_login_required
def generate_resume():
    student = current_student()
    fmt = request.form.get('format', 'pdf').strip().lower()
    if fmt not in ('pdf', 'docx', 'txt'):
        fmt = 'pdf'

    items = dbm.query_db("SELECT * FROM resume_items WHERE student_id = ? ORDER BY kind, sort_order, id",
                          (student['id'],))

    base_name = secure_filename(f"{student['id']}_{datetime.utcnow().timestamp()}_resume")
    filename = f"{base_name}.{fmt}"
    saved_path = os.path.join(UPLOAD_ROOT, 'resumes', filename)

    if fmt == 'txt':
        text = build_resume_text(student, items)
        with open(saved_path, 'w') as f:
            f.write(text)
    elif fmt == 'docx':
        build_resume_docx(saved_path, student, items)
        text = build_resume_text(student, items)  # for ATS scoring only
    else:
        build_resume_pdf(saved_path, student, items)
        text = build_resume_text(student, items)  # for ATS scoring only

    score, feedback = ats_score(text, student)
    dbm.execute_db("""
        INSERT INTO resumes (student_id, title, filename, ats_score, ats_feedback, source)
        VALUES (?, ?, ?, ?, ?, 'builder')
    """, (student['id'], 'Built Resume', filename, score, "\n".join(feedback)))

    flash(f'Resume generated ({fmt.upper()}) — ATS readiness score: {score}/100. '
          'It starts as unverified; ask your placement cell to verify it before it can be shared with a company.',
          'success' if score >= 60 else 'info')
    return redirect(url_for('profile'))


@app.route('/uploads/<subfolder>/<filename>')
def uploaded_file(subfolder, filename):
    if subfolder not in ('certificates', 'documents', 'resumes', 'doubts', 'profile_pictures'):
        abort(404)
    as_attachment = request.args.get('download') == '1'
    return send_from_directory(os.path.join(UPLOAD_ROOT, subfolder), filename, as_attachment=as_attachment)


# --------------------------------------------------------------------------
# STUDENT: Learning Hours — a private, self-reported log of study time.
# Visible only to the student themselves (not faculty or college staff) —
# it's a personal habit-tracker, not a performance metric anyone grades.
# --------------------------------------------------------------------------
@app.route('/student/learning-hours', methods=['GET', 'POST'])
@student_login_required
def learning_hours():
    student = current_student()

    if request.method == 'POST':
        activity = request.form.get('activity', '').strip()
        hours_raw = request.form.get('hours', '').strip()
        log_date = request.form.get('log_date') or date.today().isoformat()
        notes = request.form.get('notes', '').strip()

        try:
            hours = float(hours_raw)
        except ValueError:
            hours = None

        if not activity or not hours or hours <= 0:
            flash('Please describe what you studied and log a positive number of hours.', 'danger')
        else:
            dbm.execute_db("""
                INSERT INTO learning_logs (student_id, activity, hours, log_date, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (student['id'], activity, round(hours, 2), log_date, notes))
            flash('Logged — keep it up!', 'success')
        return redirect(url_for('learning_hours'))

    logs = dbm.query_db(
        "SELECT * FROM learning_logs WHERE student_id = ? ORDER BY log_date DESC, created_at DESC",
        (student['id'],))
    total_hours = round(sum(l['hours'] for l in logs), 1)
    this_week_hours = round(sum(
        l['hours'] for l in logs
        if parse_date(l['log_date']) and (date.today() - parse_date(l['log_date'])).days < 7
    ), 1)

    return render_template('learning_hours.html', logs=logs, total_hours=total_hours,
                            this_week_hours=this_week_hours, today=date.today().isoformat())


# --------------------------------------------------------------------------
# SKILL ASSESSMENT
# --------------------------------------------------------------------------
@app.route('/assessment')
@student_login_required
def assessment_home():
    student = current_student()
    faculty_tests = []
    if student['college_id']:
        rows = dbm.query_db("""
            SELECT faculty_tests.*, faculty.name AS faculty_name,
                   (SELECT COUNT(*) FROM faculty_test_questions WHERE test_id = faculty_tests.id) AS question_count
            FROM faculty_tests
            JOIN faculty ON faculty.id = faculty_tests.faculty_id
            WHERE faculty_tests.college_id = ?
            ORDER BY faculty_tests.created_at DESC
        """, (student['college_id'],))
        for t in rows:
            d = dict(t)
            best = best_test_score(student['id'], t['id'])
            d['best'] = dict(best) if best else None
            faculty_tests.append(d)
    return render_template('assessment_home.html', faculty_tests=faculty_tests)


def _start_assessment(mode, num_questions=10):
    all_rows = dbm.query_db("SELECT id FROM questions")
    all_ids = [r['id'] for r in all_rows]
    random.shuffle(all_ids)
    session['assessment_mode'] = mode
    session['assessment_question_ids'] = all_ids[:num_questions]
    session.pop('assessment_test_id', None)


@app.route('/assessment/practice/start')
@student_login_required
def start_practice():
    _start_assessment('practice')
    return redirect(url_for('take_assessment'))


@app.route('/assessment/main/start')
@student_login_required
def start_main():
    _start_assessment('main')
    return redirect(url_for('take_assessment'))


@app.route('/assessment/faculty-test/<int:test_id>/start')
@student_login_required
def start_faculty_test(test_id):
    student = current_student()
    test = dbm.query_db("SELECT * FROM faculty_tests WHERE id = ?", (test_id,), one=True)
    if not test or test['college_id'] != student['college_id']:
        abort(404)
    q_rows = dbm.query_db("SELECT id FROM faculty_test_questions WHERE test_id = ?", (test_id,))
    if not q_rows:
        flash('This test has no questions yet.', 'info')
        return redirect(url_for('assessment_home'))
    session['assessment_mode'] = 'faculty_test'
    session['assessment_test_id'] = test_id
    session['assessment_question_ids'] = [r['id'] for r in q_rows]
    return redirect(url_for('take_assessment'))


@app.route('/assessment/take')
@student_login_required
def take_assessment():
    ids = session.get('assessment_question_ids')
    mode = session.get('assessment_mode')
    if not ids:
        flash('Start an assessment first.', 'info')
        return redirect(url_for('assessment_home'))
    table = 'faculty_test_questions' if mode == 'faculty_test' else 'questions'
    placeholders = ','.join('?' for _ in ids)
    questions = dbm.query_db(f"SELECT * FROM {table} WHERE id IN ({placeholders})", ids)
    questions = sorted(questions, key=lambda q: ids.index(q['id']))
    return render_template('assessment_take.html', questions=questions, mode=mode)


@app.route('/assessment/submit', methods=['POST'])
@student_login_required
def submit_assessment():
    student = current_student()
    ids = session.get('assessment_question_ids', [])
    mode = session.get('assessment_mode', 'practice')
    test_id = session.get('assessment_test_id')
    table = 'faculty_test_questions' if mode == 'faculty_test' else 'questions'

    score = 0
    for qid in ids:
        question = dbm.query_db(f"SELECT * FROM {table} WHERE id = ?", (qid,), one=True)
        chosen = request.form.get(f'q{qid}')
        if question and chosen == question['correct_option']:
            score += 1

    test_title = None
    if mode == 'faculty_test' and test_id:
        dbm.execute_db(
            "INSERT INTO faculty_test_attempts (test_id, student_id, score, total) VALUES (?, ?, ?, ?)",
            (test_id, student['id'], score, len(ids)))
        test = dbm.query_db("SELECT title FROM faculty_tests WHERE id = ?", (test_id,), one=True)
        test_title = test['title'] if test else None
    else:
        dbm.execute_db(
            "INSERT INTO assessment_results (student_id, mode, score, total) VALUES (?, ?, ?, ?)",
            (student['id'], mode, score, len(ids)))

    session.pop('assessment_question_ids', None)
    session.pop('assessment_mode', None)
    session.pop('assessment_test_id', None)

    return render_template('assessment_result.html', score=score, total=len(ids), mode=mode, test_title=test_title)


# --------------------------------------------------------------------------
# STUDENT: Flashcards — a quick tap-to-flip MCQ practice game, reusing the
# same question bank as Practice/Main (nothing new to maintain), with zero
# scoring pressure — it's meant to be a fun, low-stakes refresher.
# --------------------------------------------------------------------------
@app.route('/flashcards')
@student_login_required
def flashcards():
    all_rows = dbm.query_db("SELECT id FROM questions")
    all_ids = [r['id'] for r in all_rows]
    random.shuffle(all_ids)
    picked_ids = all_ids[:12]
    placeholders = ','.join('?' for _ in picked_ids) if picked_ids else ''
    cards = []
    if picked_ids:
        rows = dbm.query_db(f"SELECT * FROM questions WHERE id IN ({placeholders})", picked_ids)
        by_id = {r['id']: r for r in rows}
        cards = [by_id[i] for i in picked_ids if i in by_id]
    return render_template('flashcards.html', cards=cards)


# --------------------------------------------------------------------------
# COLLEGE: register / login / logout
# --------------------------------------------------------------------------
@app.route('/college/register', methods=['GET', 'POST'])
def college_register():
    colleges = dbm.query_db("SELECT * FROM colleges ORDER BY name")

    if request.method == 'POST':
        form = request.form
        mode = form.get('mode', 'new')  # 'new' = register a brand-new college, 'join' = existing one

        emp_name = form.get('emp_name', '').strip()
        emp_email = form.get('emp_email', '').strip().lower()
        emp_password = form.get('emp_password', '')

        if mode == 'join':
            join_college_id = form.get('join_college_id') or None
            if not all([join_college_id, emp_name, emp_email, emp_password]):
                flash('Please pick your college and fill in your employee details.', 'danger')
                return render_template('register_college.html', form=form, colleges=colleges)

            college_row = dbm.query_db("SELECT id FROM colleges WHERE id = ?", (join_college_id,), one=True)
            if not college_row:
                flash('Please pick a valid college from the list.', 'danger')
                return render_template('register_college.html', form=form, colleges=colleges)

            if dbm.query_db("SELECT id FROM employees WHERE email = ?", (emp_email,), one=True):
                flash('This placement-officer email is already in use.', 'danger')
                return render_template('register_college.html', form=form, colleges=colleges)

            dbm.execute_db("""
                INSERT INTO employees (name, email, password_hash, college_id) VALUES (?, ?, ?, ?)
            """, (emp_name, emp_email, generate_password_hash(emp_password), int(join_college_id)))

            flash('You have been added as a placement-cell employee for your college. You can now log in.', 'success')
            return redirect(url_for('college_login'))

        # ---- mode == 'new': register a brand-new college ----
        name = form.get('name', '').strip()
        established_year = form.get('established_year', '').strip()
        official_email = form.get('official_email', '').strip().lower()
        password = form.get('password', '')
        confirm_password = form.get('confirm_password', '')

        if not all([name, established_year, official_email, password, emp_name, emp_email, emp_password]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('register_college.html', form=form, colleges=colleges)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register_college.html', form=form, colleges=colleges)

        if dbm.query_db("SELECT id FROM colleges WHERE official_email = ?", (official_email,), one=True):
            flash('This college is already registered.', 'danger')
            return render_template('register_college.html', form=form, colleges=colleges)

        if dbm.query_db("SELECT id FROM employees WHERE email = ?", (emp_email,), one=True):
            flash('This placement-officer email is already in use.', 'danger')
            return render_template('register_college.html', form=form, colleges=colleges)

        try:
            year_value = int(established_year)
        except ValueError:
            flash('Established year must be a number.', 'danger')
            return render_template('register_college.html', form=form, colleges=colleges)

        college_id = dbm.execute_db("""
            INSERT INTO colleges (name, established_year, official_email, password_hash)
            VALUES (?, ?, ?, ?)
        """, (name, year_value, official_email, generate_password_hash(password)))

        dbm.execute_db("""
            INSERT INTO employees (name, email, password_hash, college_id) VALUES (?, ?, ?, ?)
        """, (emp_name, emp_email, generate_password_hash(emp_password), college_id))

        flash('College registered successfully! Placement officer can now log in.', 'success')
        return redirect(url_for('college_login'))

    return render_template('register_college.html', form={}, colleges=colleges)


@app.route('/college/login', methods=['GET', 'POST'])
def college_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        employee = dbm.query_db("SELECT * FROM employees WHERE email = ?", (email,), one=True)
        if employee and check_password_hash(employee['password_hash'], password):
            session.clear()
            session['role'] = 'employee'
            session['user_id'] = employee['id']
            session['college_id'] = employee['college_id']
            flash(f"Welcome, {employee['name']}!", 'success')
            return redirect(url_for('college_home'))

        flash('Incorrect email or password.', 'danger')

    return render_template('college_login.html')


# --------------------------------------------------------------------------
# COLLEGE PORTAL
# --------------------------------------------------------------------------
@app.route('/college/home', methods=['GET', 'POST'])
@employee_login_required
def college_home():
    college_id = session['college_id']
    college = dbm.query_db("SELECT * FROM colleges WHERE id = ?", (college_id,), one=True)

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        role = request.form.get('role', '').strip()
        description = request.form.get('description', '').strip()
        reg_start = request.form.get('reg_start')
        reg_end = request.form.get('reg_end')
        package_lpa = request.form.get('package_lpa', '').strip()
        min_cgpa = request.form.get('min_cgpa', '').strip()
        eligible_courses = request.form.get('eligible_courses', '').strip()
        eligible_years = ','.join(request.form.getlist('eligible_years'))
        required_skills = request.form.get('required_skills', '').strip()

        if not all([company_name, reg_start, reg_end]):
            flash('Company name, start date and end date are required.', 'danger')
        else:
            try:
                min_cgpa_value = float(min_cgpa) if min_cgpa else 0
            except ValueError:
                min_cgpa_value = 0
            dbm.execute_db("""
                INSERT INTO company_visits
                    (company_name, role, description, reg_start, reg_end, college_id,
                     min_cgpa, eligible_courses, eligible_years, required_skills, package_lpa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_name, role, description, reg_start, reg_end, college_id,
                  min_cgpa_value, eligible_courses, eligible_years, required_skills, package_lpa))
            flash(f'{company_name} added to the campus drive list.', 'success')
        return redirect(url_for('college_home'))

    companies = dbm.query_db(
        "SELECT * FROM company_visits WHERE college_id = ? ORDER BY reg_start DESC", (college_id,))
    students = dbm.query_db("SELECT * FROM students WHERE college_id = ?", (college_id,))
    student_count = len(students)

    eligibility_overview = {}
    for c in companies:
        if students:
            scores = [eligibility_match(s, c) for s in students]
            eligible_count = sum(1 for m in scores if m['eligible'])
            avg_percent = round(sum(m['percent'] for m in scores) / len(scores))
        else:
            eligible_count, avg_percent = 0, 0
        eligibility_overview[c['id']] = {'eligible_count': eligible_count, 'avg_percent': avg_percent}

    return render_template('college_home.html', college=college, companies=companies,
                            student_count=student_count, eligibility_overview=eligibility_overview)


@app.route('/college/company/<int:company_id>/delete', methods=['POST'])
@employee_login_required
def delete_company(company_id):
    company = dbm.query_db("SELECT * FROM company_visits WHERE id = ?", (company_id,), one=True)
    if not company:
        abort(404)
    if company['college_id'] != session['college_id']:
        abort(403)
    dbm.execute_db("DELETE FROM applications WHERE company_id = ?", (company_id,))
    dbm.execute_db("UPDATE visit_requests SET company_visit_id = NULL WHERE company_visit_id = ?", (company_id,))
    dbm.execute_db("UPDATE notifications SET company_id = NULL WHERE company_id = ?", (company_id,))
    dbm.execute_db("DELETE FROM company_visits WHERE id = ?", (company_id,))
    flash('Company drive removed.', 'info')
    return redirect(url_for('college_home'))


@app.route('/college/tracker')
@employee_login_required
def student_tracker():
    college_id = session['college_id']
    companies = dbm.query_db(
        "SELECT * FROM company_visits WHERE college_id = ? ORDER BY reg_start DESC", (college_id,))
    tracker = []
    for c in companies:
        applicants = dbm.query_db("""
            SELECT students.* FROM students
            JOIN applications ON applications.student_id = students.id
            WHERE applications.company_id = ?
        """, (c['id'],))
        applicants_with_match = [(s, eligibility_match(s, c)) for s in applicants]
        tracker.append((c, applicants_with_match))
    return render_template('student_tracker.html', tracker=tracker)


def _categorize_students(rows):
    """Turns sqlite3.Row students into plain dicts with department/course
    normalized to 'Unspecified' when blank, so templates can group and
    filter on them without hitting None."""
    students = []
    for r in rows:
        d = dict(r)
        d['department'] = d.get('department') or 'Unspecified'
        d['course'] = d.get('course') or 'Unspecified'
        students.append(d)
    return students


@app.route('/college/students')
@employee_login_required
def student_list():
    """One combined section: the student directory (grouped by department
    then course, with Department/Course filters) and each student's
    placement readiness — best assessment score, certificate count, and
    overall progress bar — side by side in the same table, instead of two
    separate pages a placement officer had to flip between."""
    college_id = session['college_id']
    rows = dbm.query_db(
        "SELECT * FROM students WHERE college_id = ? ORDER BY department, course, name", (college_id,))
    students = _categorize_students(rows)
    for s in students:
        best = best_main_score(s['id'])
        cert_count = len(dbm.query_db("SELECT id FROM certificates WHERE student_id = ?", (s['id'],)))
        s['progress'] = overall_progress(s)
        s['best_score'] = f"{best['score']}/{best['total']}" if best else "Not attempted"
        s['certificates'] = cert_count
    departments = sorted({s['department'] for s in students})
    courses = sorted({s['course'] for s in students})
    return render_template('student_list.html', students=students,
                            departments=departments, courses=courses)


@app.route('/college/progress')
@employee_login_required
def student_progress():
    # Merged into the Students page (list + progress in one place) —
    # kept as a redirect so any old bookmark/link still lands somewhere useful.
    return redirect(url_for('student_list'))


# --------------------------------------------------------------------------
# HELP DESK — a student raises a query/problem, it goes straight to their
# own college's placement cell to answer.
# --------------------------------------------------------------------------
@app.route('/help', methods=['GET', 'POST'])
@student_login_required
def help_center():
    student = current_student()

    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not student['college_id']:
            flash('Add your college on the Profile page before contacting your placement cell.', 'warning')
            return redirect(url_for('help_center'))
        if not subject or not message:
            flash('Please add a subject and describe the problem.', 'danger')
            return redirect(url_for('help_center'))

        dbm.execute_db("""
            INSERT INTO support_tickets (student_id, college_id, category, subject, message)
            VALUES (?, ?, ?, ?, ?)
        """, (student['id'], student['college_id'], category, subject, message))
        flash('Your query has been sent to your placement cell.', 'success')
        return redirect(url_for('help_center'))

    tickets = dbm.query_db(
        "SELECT * FROM support_tickets WHERE student_id = ? ORDER BY created_at DESC", (student['id'],))
    return render_template('help.html', tickets=tickets)


@app.route('/college/helpdesk')
@employee_login_required
def college_helpdesk():
    college_id = session['college_id']
    tickets = dbm.query_db("""
        SELECT support_tickets.*, students.name AS student_name, students.srn AS student_srn,
               students.email AS student_email
        FROM support_tickets
        JOIN students ON students.id = support_tickets.student_id
        WHERE support_tickets.college_id = ?
        ORDER BY (support_tickets.status = 'open') DESC, support_tickets.created_at DESC
    """, (college_id,))
    return render_template('college_helpdesk.html', tickets=tickets)


@app.route('/college/helpdesk/<int:ticket_id>/resolve', methods=['POST'])
@employee_login_required
def resolve_ticket(ticket_id):
    ticket = dbm.query_db("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,), one=True)
    if not ticket:
        abort(404)
    if ticket['college_id'] != session['college_id']:
        abort(403)
    new_status = 'open' if ticket['status'] == 'resolved' else 'resolved'
    dbm.execute_db("UPDATE support_tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
    flash('Reopened.' if new_status == 'open' else 'Marked as resolved.', 'info')
    return redirect(url_for('college_helpdesk'))


# --------------------------------------------------------------------------
# NOTIFICATIONS — the college side can send a manual message to whichever
# students it selects, or a one-click reminder about a specific drive.
# --------------------------------------------------------------------------
@app.route('/college/notifications', methods=['GET', 'POST'])
@employee_login_required
def college_notifications():
    college_id = session['college_id']
    employee = current_employee()
    rows = dbm.query_db(
        "SELECT * FROM students WHERE college_id = ? ORDER BY department, course, name", (college_id,))
    students = _categorize_students(rows)
    departments = sorted({s['department'] for s in students})
    courses = sorted({s['course'] for s in students})

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        student_ids = request.form.getlist('student_ids')

        if not title or not message:
            flash('Please provide both a title and a message.', 'danger')
        elif not student_ids:
            flash('Select at least one student to notify.', 'danger')
        else:
            notif_id = dbm.execute_db("""
                INSERT INTO notifications (college_id, employee_id, title, message, kind)
                VALUES (?, ?, ?, ?, 'manual')
            """, (college_id, employee['id'], title, message))
            for sid in student_ids:
                dbm.execute_db(
                    "INSERT INTO notification_recipients (notification_id, student_id) VALUES (?, ?)",
                    (notif_id, int(sid)))
            flash(f'Notification sent to {len(student_ids)} student(s).', 'success')
        return redirect(url_for('college_notifications'))

    sent = dbm.query_db("""
        SELECT notifications.*,
               (SELECT COUNT(*) FROM notification_recipients WHERE notification_id = notifications.id) AS recipient_count,
               (SELECT COUNT(*) FROM notification_recipients WHERE notification_id = notifications.id AND read_at IS NOT NULL) AS read_count
        FROM notifications WHERE college_id = ? ORDER BY created_at DESC
    """, (college_id,))

    return render_template('college_notifications.html', students=students, sent=sent,
                            departments=departments, courses=courses)


@app.route('/college/notifications/remind/<int:company_id>', methods=['POST'])
@employee_login_required
def send_drive_reminder(company_id):
    college_id = session['college_id']
    employee = current_employee()
    company = dbm.query_db("SELECT * FROM company_visits WHERE id = ?", (company_id,), one=True)
    if not company:
        abort(404)
    if company['college_id'] != college_id:
        abort(403)

    pending_students = dbm.query_db("""
        SELECT * FROM students WHERE college_id = ? AND id NOT IN (
            SELECT student_id FROM applications WHERE company_id = ?
        )
    """, (college_id, company_id))

    if not pending_students:
        flash('Every student has already applied to this drive — no reminder needed.', 'info')
        return redirect(url_for('college_home'))

    reg_end_display = company['reg_end']
    parsed_end = parse_date(company['reg_end'])
    if parsed_end:
        reg_end_display = parsed_end.strftime('%d %b %Y')

    title = f"Reminder: {company['company_name']} registration closing soon"
    message = (f"The registration window for {company['company_name']}"
               f"{' (' + company['role'] + ')' if company['role'] else ''} closes on {reg_end_display}. "
               f"Apply now from your Home page if you haven't already!")

    notif_id = dbm.execute_db("""
        INSERT INTO notifications (college_id, employee_id, title, message, kind, company_id)
        VALUES (?, ?, ?, ?, 'drive_reminder', ?)
    """, (college_id, employee['id'], title, message, company_id))
    for s in pending_students:
        dbm.execute_db(
            "INSERT INTO notification_recipients (notification_id, student_id) VALUES (?, ?)",
            (notif_id, s['id']))

    flash(f"Reminder sent to {len(pending_students)} student(s) who haven't applied yet.", 'success')
    return redirect(url_for('college_home'))


# --------------------------------------------------------------------------
# COLLEGE: Peer Reference wall — placement-cell staff add a short profile of
# a placed student (CGPA, projects, skills, a line of advice) so current
# students have something concrete to aim for. Shown to students on their
# Skill Enhancement page.
# --------------------------------------------------------------------------
@app.route('/college/peer-wall', methods=['GET', 'POST'])
@employee_login_required
def college_peer_wall():
    college_id = session['college_id']
    employee = current_employee()

    if request.method == 'POST':
        student_name = request.form.get('student_name', '').strip()
        company_name = request.form.get('company_name', '').strip()
        role = request.form.get('role', '').strip()
        package_lpa = request.form.get('package_lpa', '').strip()
        cgpa = request.form.get('cgpa', '').strip()
        skills = request.form.get('skills', '').strip()
        projects = request.form.get('projects', '').strip()
        testimonial = request.form.get('testimonial', '').strip()

        if not student_name or not company_name:
            flash('At least the student\'s name and the company they were placed at are required.', 'danger')
        else:
            try:
                cgpa_value = float(cgpa) if cgpa else None
            except ValueError:
                cgpa_value = None
            dbm.execute_db("""
                INSERT INTO peer_references
                    (college_id, added_by, student_name, company_name, role, package_lpa, cgpa, skills, projects, testimonial)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (college_id, employee['id'], student_name, company_name, role, package_lpa,
                  cgpa_value, skills, projects, testimonial))
            flash(f'Added {student_name} to the Peer Reference wall.', 'success')
        return redirect(url_for('college_peer_wall'))

    entries = dbm.query_db(
        "SELECT * FROM peer_references WHERE college_id = ? ORDER BY created_at DESC", (college_id,))
    return render_template('college_peer_wall.html', entries=entries)


@app.route('/college/peer-wall/<int:entry_id>/delete', methods=['POST'])
@employee_login_required
def delete_peer_reference(entry_id):
    entry = dbm.query_db("SELECT * FROM peer_references WHERE id = ?", (entry_id,), one=True)
    if not entry:
        abort(404)
    if entry['college_id'] != session['college_id']:
        abort(403)
    dbm.execute_db("DELETE FROM peer_references WHERE id = ?", (entry_id,))
    flash('Removed.', 'info')
    return redirect(url_for('college_peer_wall'))


def try_send_resume_email(to_email, company_name, student, message, attachment_path, attachment_filename):
    """Best-effort real email delivery via SMTP, using credentials from
    environment variables (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    SMTP_FROM) if they're set. Returns True if an email was actually sent.
    UniLinkUp otherwise works fully offline with no external services, so
    when SMTP isn't configured this returns False rather than pretending to
    have sent something — the share is still logged either way."""
    host = os.environ.get('SMTP_HOST')
    if not host:
        return False
    try:
        import smtplib
        from email.message import EmailMessage
        port = int(os.environ.get('SMTP_PORT', '587'))
        user = os.environ.get('SMTP_USER')
        password = os.environ.get('SMTP_PASS')
        sender = os.environ.get('SMTP_FROM', user)

        msg = EmailMessage()
        msg['Subject'] = f"Resume — {student['name']}" + (f" for {company_name}" if company_name else "")
        msg['From'] = sender
        msg['To'] = to_email
        body = (message.strip() + "\n\n") if message.strip() else ""
        body += (f"Please find attached the verified resume for {student['name']} "
                 f"({student['email']}), shared via UniLinkUp.")
        msg.set_content(body)

        with open(attachment_path, 'rb') as f:
            data = f.read()
        ext = attachment_filename.rsplit('.', 1)[-1].lower()
        maintype, subtype = ('application', 'pdf') if ext == 'pdf' else \
            ('application', 'vnd.openxmlformats-officedocument.wordprocessingml.document') if ext == 'docx' else \
            ('text', 'plain')
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=attachment_filename)

        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


def try_upload_to_drive(file_path, filename):
    """Best-effort real upload to Google Drive, using a service account
    configured via environment variables (GOOGLE_SERVICE_ACCOUNT_FILE — path
    to that service account's JSON key, and GOOGLE_DRIVE_FOLDER_ID — a Drive
    folder shared with that service account's email). Returns a shareable
    'anyone with the link can view' URL on success, or None if Drive isn't
    configured (or the required libraries aren't installed) — same honest
    fall-back pattern as try_send_resume_email(): UniLinkUp never pretends a
    real upload happened when it didn't. See README for setup steps."""
    key_file = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE')
    folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
    if not key_file or not folder_id:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            key_file, scopes=['https://www.googleapis.com/auth/drive.file'])
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)

        media = MediaFileUpload(file_path, resumable=False)
        created = service.files().create(
            body={'name': filename, 'parents': [folder_id]},
            media_body=media, fields='id, webViewLink'
        ).execute()
        file_id = created.get('id')
        if not file_id:
            return None
        # Anyone with the link can view — this is what makes it usable as a
        # link to hand a company, the same way "Share" on a real Drive file works.
        service.permissions().create(fileId=file_id, body={'role': 'reader', 'type': 'anyone'}).execute()
        return created.get('webViewLink')
    except Exception:
        return None


def get_or_create_share_token(resume_id, existing_token):
    """A resume gets one stable, unguessable public token the first time it's
    shared as a link, reused for every share after that (so re-sharing the
    same resume doesn't invalidate a link already handed to a company)."""
    if existing_token:
        return existing_token
    token = secrets.token_urlsafe(24)
    dbm.execute_db("UPDATE resumes SET share_token = ? WHERE id = ?", (token, resume_id))
    return token


# --------------------------------------------------------------------------
# COLLEGE: verify a student's resume, and — only once verified — share it
# with a company, either by email or by generating a shareable link (a real
# Google Drive upload if GOOGLE_SERVICE_ACCOUNT_FILE/GOOGLE_DRIVE_FOLDER_ID
# are configured, otherwise a UniLinkUp-hosted link that works the same way
# a Drive link would — copy it into an email, WhatsApp, or your own Drive).
# Verification is mandatory before either kind of share: both share routes
# below refuse to run for anything that isn't verification_status='verified',
# on top of the UI only offering the Share forms for verified resumes.
# --------------------------------------------------------------------------
@app.route('/college/resumes')
@employee_login_required
def college_resumes():
    college_id = session['college_id']
    resumes = dbm.query_db("""
        SELECT resumes.*, students.name AS student_name, students.email AS student_email,
               students.course AS student_course, employees.name AS verified_by_name
        FROM resumes
        JOIN students ON students.id = resumes.student_id
        LEFT JOIN employees ON employees.id = resumes.verified_by
        WHERE students.college_id = ?
        ORDER BY (resumes.verification_status = 'pending') DESC, resumes.uploaded_at DESC, resumes.id DESC
    """, (college_id,))
    shares = dbm.query_db("""
        SELECT resume_shares.*, students.name AS student_name
        FROM resume_shares
        JOIN students ON students.id = resume_shares.student_id
        WHERE students.college_id = ?
        ORDER BY resume_shares.created_at DESC LIMIT 20
    """, (college_id,))
    return render_template('college_resumes.html', resumes=resumes, shares=shares)


@app.route('/college/resumes/<int:resume_id>/verify', methods=['POST'])
@employee_login_required
def verify_resume(resume_id):
    employee = current_employee()
    resume = dbm.query_db("""
        SELECT resumes.*, students.college_id AS student_college_id FROM resumes
        JOIN students ON students.id = resumes.student_id WHERE resumes.id = ?
    """, (resume_id,), one=True)
    if not resume or resume['student_college_id'] != employee['college_id']:
        abort(404)
    dbm.execute_db("""
        UPDATE resumes SET verification_status = 'verified', verified_by = ?, verified_at = CURRENT_TIMESTAMP,
               verification_note = NULL
        WHERE id = ?
    """, (employee['id'], resume_id))
    flash('Resume verified — it can now be shared with a company.', 'success')
    return redirect(url_for('college_resumes'))


@app.route('/college/resumes/<int:resume_id>/reject', methods=['POST'])
@employee_login_required
def reject_resume(resume_id):
    employee = current_employee()
    reason = request.form.get('reason', '').strip()
    suggestion = request.form.get('suggestion', '').strip()
    resume = dbm.query_db("""
        SELECT resumes.*, students.college_id AS student_college_id FROM resumes
        JOIN students ON students.id = resumes.student_id WHERE resumes.id = ?
    """, (resume_id,), one=True)
    if not resume or resume['student_college_id'] != employee['college_id']:
        abort(404)

    # Both fields are mandatory — a reject with no explanation or no concrete
    # way to improve leaves a student stuck, so the route refuses server-side
    # regardless of what the form submits, the same way the class-cancellation
    # and slot-decline flows require their own mandatory fields.
    if not reason or not suggestion:
        flash('Please provide both a reason for rejecting this resume and a suggestion for how to improve it.',
              'danger')
        return redirect(url_for('college_resumes'))

    dbm.execute_db("""
        UPDATE resumes SET verification_status = 'rejected', verified_by = ?, verified_at = CURRENT_TIMESTAMP,
               verification_note = ?, verification_suggestion = ?
        WHERE id = ?
    """, (employee['id'], reason, suggestion, resume_id))
    flash('Resume marked as rejected — the student will see your reason and suggestion.', 'info')
    return redirect(url_for('college_resumes'))


@app.route('/college/resumes/<int:resume_id>/share', methods=['POST'])
@employee_login_required
def share_resume(resume_id):
    employee = current_employee()
    resume = dbm.query_db("""
        SELECT resumes.*, students.college_id AS student_college_id, students.id AS student_id,
               students.name AS student_name, students.email AS student_email
        FROM resumes JOIN students ON students.id = resumes.student_id WHERE resumes.id = ?
    """, (resume_id,), one=True)
    if not resume or resume['student_college_id'] != employee['college_id']:
        abort(404)

    # Mandatory verification gate — a resume can never be shared unless a
    # placement officer has explicitly verified it first, regardless of
    # what the request contains.
    if resume['verification_status'] != 'verified':
        flash('This resume must be verified before it can be shared with a company.', 'danger')
        return redirect(url_for('college_resumes'))

    company_name = request.form.get('company_name', '').strip()
    company_email = request.form.get('company_email', '').strip()
    message = request.form.get('message', '').strip()
    if not company_email:
        flash("Please provide the company's email address.", 'danger')
        return redirect(url_for('college_resumes'))

    attachment_path = os.path.join(UPLOAD_ROOT, 'resumes', resume['filename'])
    sent = try_send_resume_email(company_email, company_name, resume, message,
                                  attachment_path, resume['filename'])
    status = 'sent' if sent else 'logged'

    dbm.execute_db("""
        INSERT INTO resume_shares (resume_id, student_id, shared_by, company_name, company_email, message, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (resume_id, resume['student_id'], employee['id'], company_name, company_email, message, status))

    if sent:
        flash(f"Resume emailed to {company_email}.", 'success')
    else:
        flash(f"Share recorded for {company_email}, but no SMTP server is configured so the email itself "
              "wasn't actually sent — see the README for how to configure SMTP_HOST/SMTP_USER/SMTP_PASS to "
              "enable real delivery.", 'warning')
    return redirect(url_for('college_resumes'))


@app.route('/college/resumes/<int:resume_id>/share-drive', methods=['POST'])
@employee_login_required
def share_resume_drive(resume_id):
    employee = current_employee()
    resume = dbm.query_db("""
        SELECT resumes.*, students.college_id AS student_college_id, students.id AS student_id,
               students.name AS student_name, students.email AS student_email
        FROM resumes JOIN students ON students.id = resumes.student_id WHERE resumes.id = ?
    """, (resume_id,), one=True)
    if not resume or resume['student_college_id'] != employee['college_id']:
        abort(404)

    # Same mandatory verification gate as emailing it — sharing a link is
    # still sharing, so it can't skip the rule either.
    if resume['verification_status'] != 'verified':
        flash('This resume must be verified before it can be shared with a company.', 'danger')
        return redirect(url_for('college_resumes'))

    company_name = request.form.get('company_name', '').strip()

    attachment_path = os.path.join(UPLOAD_ROOT, 'resumes', resume['filename'])
    drive_link = try_upload_to_drive(attachment_path, resume['filename'])
    if drive_link:
        status = 'sent'
        share_url = drive_link
    else:
        token = get_or_create_share_token(resume_id, resume['share_token'])
        share_url = url_for('shared_resume', token=token, _external=True)
        status = 'logged'

    dbm.execute_db("""
        INSERT INTO resume_shares (resume_id, student_id, shared_by, company_name, company_email,
                                    message, status, method, share_url)
        VALUES (?, ?, ?, ?, '', ?, ?, 'drive', ?)
    """, (resume_id, resume['student_id'], employee['id'], company_name,
          f"Shared as a link{' with ' + company_name if company_name else ''}.", status, share_url))

    if status == 'sent':
        flash(f"Uploaded to Google Drive and shared: {share_url}", 'success')
    else:
        flash(f"Google Drive isn't configured, so a shareable link was generated instead — copy it to send "
              f"however you like (email, WhatsApp, or paste into your own Drive folder): {share_url} "
              "See the README for how to configure GOOGLE_SERVICE_ACCOUNT_FILE/GOOGLE_DRIVE_FOLDER_ID for "
              "a real Drive upload.", 'warning')
    return redirect(url_for('college_resumes'))


@app.route('/shared-resume/<token>')
def shared_resume(token):
    """A public, unguessable link to one verified resume — no login required,
    the same way opening a Google Drive share link doesn't require an
    account. Only ever reachable via a token minted by share_resume_drive()
    above, which only ever runs on an already-verified resume."""
    resume = dbm.query_db("""
        SELECT resumes.*, students.name AS student_name, students.course AS student_course,
               colleges.name AS college_name
        FROM resumes
        JOIN students ON students.id = resumes.student_id
        LEFT JOIN colleges ON colleges.id = students.college_id
        WHERE resumes.share_token = ?
    """, (token,), one=True)
    if not resume:
        abort(404)
    return render_template('shared_resume.html', resume=resume, token=token)


@app.route('/shared-resume/<token>/file')
def shared_resume_file(token):
    resume = dbm.query_db("SELECT * FROM resumes WHERE share_token = ?", (token,), one=True)
    if not resume:
        abort(404)
    as_attachment = request.args.get('download') == '1'
    return send_from_directory(os.path.join(UPLOAD_ROOT, 'resumes'), resume['filename'],
                                as_attachment=as_attachment)


# --------------------------------------------------------------------------
# STUDENT: Interview Experience Archive — unlike a generic "interview
# experience" post on a public job board, every entry here is written by a
# student right after their own interview at *this specific college's* own
# drive, so juniors prepping for the same recurring recruiters get rounds,
# question types and difficulty that's actually relevant to them, not a
# stranger's account from a different city and hiring cycle.
# --------------------------------------------------------------------------
INTERVIEW_OUTCOMES = ['Selected', 'Not Selected', 'Awaiting Result']
INTERVIEW_DIFFICULTIES = ['Easy', 'Medium', 'Hard']


@app.route('/interview-experiences')
@student_login_required
def interview_experiences():
    student = current_student()
    experiences = []
    if student['college_id']:
        experiences = dbm.query_db("""
            SELECT interview_experiences.*, students.name AS student_name
            FROM interview_experiences
            JOIN students ON students.id = interview_experiences.student_id
            WHERE interview_experiences.college_id = ?
            ORDER BY interview_experiences.created_at DESC
        """, (student['college_id'],))
    return render_template('interview_experiences.html', student=student, experiences=experiences,
                            outcomes=INTERVIEW_OUTCOMES, difficulties=INTERVIEW_DIFFICULTIES)


@app.route('/interview-experiences/submit', methods=['POST'])
@student_login_required
def submit_interview_experience():
    student = current_student()
    if not student['college_id']:
        flash('Link a college to your profile before posting an interview experience.', 'danger')
        return redirect(url_for('interview_experiences'))

    company_name = request.form.get('company_name', '').strip()
    role = request.form.get('role', '').strip()
    outcome = request.form.get('outcome', '').strip()
    difficulty = request.form.get('difficulty', '').strip()
    rounds = request.form.get('rounds', '').strip()
    experience = request.form.get('experience', '').strip()

    if not company_name or not experience:
        flash('At least the company name and your writeup (questions asked, tips) are required.', 'danger')
        return redirect(url_for('interview_experiences'))

    dbm.execute_db("""
        INSERT INTO interview_experiences
            (student_id, college_id, company_name, role, outcome, difficulty, rounds, experience)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (student['id'], student['college_id'], company_name, role, outcome, difficulty, rounds, experience))
    flash('Thanks for sharing — juniors prepping for this company will see it.', 'success')
    return redirect(url_for('interview_experiences'))


@app.route('/interview-experiences/<int:exp_id>/delete', methods=['POST'])
@student_login_required
def delete_interview_experience(exp_id):
    student = current_student()
    exp = dbm.query_db("SELECT * FROM interview_experiences WHERE id = ?", (exp_id,), one=True)
    if not exp:
        abort(404)
    if exp['student_id'] != student['id']:
        abort(403)
    dbm.execute_db("DELETE FROM interview_experiences WHERE id = ?", (exp_id,))
    flash('Your post has been removed.', 'info')
    return redirect(url_for('interview_experiences'))


# --------------------------------------------------------------------------
# FACULTY: register / login — a faculty member always joins an existing
# college (colleges are registered by placement-cell staff, not faculty).
# --------------------------------------------------------------------------
@app.route('/faculty/register', methods=['GET', 'POST'])
def register_faculty():
    colleges = dbm.query_db("SELECT * FROM colleges ORDER BY name")

    if request.method == 'POST':
        form = request.form
        name = form.get('name', '').strip()
        email = form.get('email', '').strip().lower()
        password = form.get('password', '')
        confirm_password = form.get('confirm_password', '')
        college_id = form.get('college_id') or None
        department = form.get('department', '').strip()
        expertise = form.get('expertise', '').strip()
        bio = form.get('bio', '').strip()

        if not all([name, email, password, college_id]):
            flash('Please fill in all required fields and pick your college.', 'danger')
            return render_template('register_faculty.html', colleges=colleges, form=form)
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register_faculty.html', colleges=colleges, form=form)
        if dbm.query_db("SELECT id FROM faculty WHERE email = ?", (email,), one=True):
            flash('An account with this email already exists.', 'danger')
            return render_template('register_faculty.html', colleges=colleges, form=form)

        dbm.execute_db("""
            INSERT INTO faculty (name, email, password_hash, college_id, department, expertise, bio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, generate_password_hash(password), int(college_id), department, expertise, bio))

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('faculty_login'))

    return render_template('register_faculty.html', colleges=colleges, form={})


@app.route('/faculty/login', methods=['GET', 'POST'])
def faculty_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        faculty = dbm.query_db("SELECT * FROM faculty WHERE email = ?", (email,), one=True)
        if faculty and check_password_hash(faculty['password_hash'], password):
            session.clear()
            session['role'] = 'faculty'
            session['user_id'] = faculty['id']
            session['college_id'] = faculty['college_id']
            flash(f"Welcome, {faculty['name']}!", 'success')
            return redirect(url_for('faculty_home'))

        flash('Incorrect email or password.', 'danger')

    return render_template('faculty_login.html')


# --------------------------------------------------------------------------
# FACULTY PORTAL — a faculty member offers time slots, students book them as
# 1-on-1 mentoring appointments (see the student-facing Skill Enhancement
# section below for the booking side of this same feature).
# --------------------------------------------------------------------------
@app.route('/faculty/home')
@faculty_login_required
def faculty_home():
    faculty = current_faculty()
    upcoming = dbm.query_db("""
        SELECT appointments.*, faculty_slots.slot_date, faculty_slots.start_time, faculty_slots.end_time,
               faculty_slots.topic, faculty_slots.meeting_link, students.name AS student_name,
               students.course AS student_course
        FROM appointments
        JOIN faculty_slots ON faculty_slots.id = appointments.slot_id
        JOIN students ON students.id = appointments.student_id
        WHERE appointments.faculty_id = ? AND appointments.status = 'upcoming'
        ORDER BY faculty_slots.slot_date ASC, faculty_slots.start_time ASC
    """, (faculty['id'],))

    open_slot_count = dbm.query_db("""
        SELECT COUNT(*) AS c FROM faculty_slots
        WHERE faculty_id = ? AND status != 'cancelled' AND (
            SELECT COUNT(*) FROM appointments
            WHERE appointments.slot_id = faculty_slots.id AND appointments.status = 'upcoming'
        ) < COALESCE(capacity, 1)
    """, (faculty['id'],), one=True)
    mentee_count = dbm.query_db(
        "SELECT COUNT(DISTINCT student_id) AS c FROM appointments WHERE faculty_id = ? AND status = 'upcoming'",
        (faculty['id'],), one=True)
    pending_request_count = dbm.query_db(
        "SELECT COUNT(*) AS c FROM slot_requests WHERE faculty_id = ? AND status = 'pending'",
        (faculty['id'],), one=True)

    upcoming_classes = dbm.query_db("""
        SELECT DISTINCT faculty_slots.id, faculty_slots.slot_date, faculty_slots.start_time, faculty_slots.topic
        FROM faculty_slots
        JOIN appointments ON appointments.slot_id = faculty_slots.id AND appointments.status = 'upcoming'
        WHERE faculty_slots.faculty_id = ?
        ORDER BY faculty_slots.slot_date ASC, faculty_slots.start_time ASC
    """, (faculty['id'],))

    return render_template('faculty_home.html', faculty=faculty, upcoming=upcoming,
                            open_slot_count=open_slot_count['c'] if open_slot_count else 0,
                            mentee_count=mentee_count['c'] if mentee_count else 0,
                            pending_request_count=pending_request_count['c'] if pending_request_count else 0,
                            upcoming_classes=upcoming_classes)


@app.route('/faculty/notify', methods=['POST'])
@faculty_login_required
def faculty_notify():
    faculty = current_faculty()
    title = request.form.get('title', '').strip()
    message = request.form.get('message', '').strip()
    target = request.form.get('target', 'mentees')

    if not title or not message:
        flash('Please provide both a title and a message.', 'danger')
        return redirect(url_for('faculty_home'))

    if target == 'mentees':
        rows = dbm.query_db(
            "SELECT DISTINCT student_id FROM appointments WHERE faculty_id = ? AND status = 'upcoming'",
            (faculty['id'],))
    else:
        rows = []
        try:
            slot_id = int(target)
        except ValueError:
            slot_id = None
        if slot_id:
            slot = dbm.query_db("SELECT * FROM faculty_slots WHERE id = ?", (slot_id,), one=True)
            if slot and slot['faculty_id'] == faculty['id']:
                rows = dbm.query_db(
                    "SELECT DISTINCT student_id FROM appointments WHERE slot_id = ? AND status = 'upcoming'",
                    (slot_id,))

    if not rows:
        flash('No students to notify yet — once someone books a class with you, you can message them here.', 'info')
        return redirect(url_for('faculty_home'))

    notif_id = dbm.execute_db("""
        INSERT INTO notifications (college_id, faculty_id, title, message, kind)
        VALUES (?, ?, ?, ?, 'faculty_update')
    """, (faculty['college_id'], faculty['id'], title, message))
    for r in rows:
        dbm.execute_db(
            "INSERT INTO notification_recipients (notification_id, student_id) VALUES (?, ?)",
            (notif_id, r['student_id']))
    flash(f'Notification sent to {len(rows)} student(s).', 'success')
    return redirect(url_for('faculty_home'))


@app.route('/faculty/slots', methods=['GET', 'POST'])
@faculty_login_required
def faculty_slots():
    faculty = current_faculty()

    if request.method == 'POST':
        slot_date = request.form.get('slot_date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        topic = request.form.get('topic', '').strip()
        meeting_link = request.form.get('meeting_link', '').strip()
        capacity_raw = request.form.get('capacity', '1').strip()

        if not all([slot_date, start_time, end_time]):
            flash('Please provide a date, start time, and end time.', 'danger')
        elif end_time <= start_time:
            flash('End time must be after the start time.', 'danger')
        else:
            try:
                capacity = max(1, int(capacity_raw))
            except ValueError:
                capacity = 1
            dbm.execute_db("""
                INSERT INTO faculty_slots (faculty_id, slot_date, start_time, end_time, topic, meeting_link, capacity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (faculty['id'], slot_date, start_time, end_time, topic, meeting_link, capacity))
            flash('Slot added — students at your college can now book it.', 'success')
        return redirect(url_for('faculty_slots'))

    raw_slots = dbm.query_db("""
        SELECT faculty_slots.*,
               (SELECT COUNT(*) FROM appointments
                WHERE appointments.slot_id = faculty_slots.id AND appointments.status = 'upcoming') AS seats_taken
        FROM faculty_slots
        WHERE faculty_slots.faculty_id = ?
        ORDER BY faculty_slots.slot_date ASC, faculty_slots.start_time ASC
    """, (faculty['id'],))
    slots = []
    for s in raw_slots:
        booked = dbm.query_db("""
            SELECT students.name FROM appointments JOIN students ON students.id = appointments.student_id
            WHERE appointments.slot_id = ? AND appointments.status = 'upcoming'
        """, (s['id'],))
        d = dict(s)
        d['capacity'] = s['capacity'] or 1
        d['student_names'] = [r['name'] for r in booked]
        slots.append(d)

    pending_requests = dbm.query_db("""
        SELECT slot_requests.*, students.name AS student_name, students.course AS student_course,
               students.year AS student_year, students.department AS student_department
        FROM slot_requests
        JOIN students ON students.id = slot_requests.student_id
        WHERE slot_requests.faculty_id = ? AND slot_requests.status = 'pending'
        ORDER BY slot_requests.created_at ASC
    """, (faculty['id'],))
    handled_requests = dbm.query_db("""
        SELECT slot_requests.*, students.name AS student_name
        FROM slot_requests
        JOIN students ON students.id = slot_requests.student_id
        WHERE slot_requests.faculty_id = ? AND slot_requests.status != 'pending'
        ORDER BY slot_requests.responded_at DESC LIMIT 10
    """, (faculty['id'],))

    return render_template('faculty_slots.html', faculty=faculty, slots=slots,
                            pending_requests=pending_requests, handled_requests=handled_requests,
                            today=date.today().isoformat())


@app.route('/faculty/slots/<int:slot_id>/delete', methods=['POST'])
@faculty_login_required
def delete_faculty_slot(slot_id):
    faculty = current_faculty()
    slot = dbm.query_db("SELECT * FROM faculty_slots WHERE id = ?", (slot_id,), one=True)
    if not slot or slot['faculty_id'] != faculty['id']:
        abort(404)
    seats_taken = dbm.query_db(
        "SELECT COUNT(*) AS c FROM appointments WHERE slot_id = ? AND status = 'upcoming'",
        (slot_id,), one=True)['c']
    if seats_taken > 0:
        flash('One or more students are booked into this slot — cancel the class instead (below) to notify them and free up the slot.', 'warning')
    else:
        dbm.execute_db("DELETE FROM faculty_slots WHERE id = ?", (slot_id,))
        flash('Slot removed.', 'info')
    return redirect(url_for('faculty_slots'))


@app.route('/faculty/slots/<int:slot_id>/cancel', methods=['POST'])
@faculty_login_required
def cancel_faculty_slot(slot_id):
    """Cancel a class that already has students booked into it — including
    one created by approving a slot request — and require a reason, which
    is pushed to every affected student as a notification (reusing the same
    notifications/notification_recipients infrastructure as Notify Students)
    so a cancellation is never silent."""
    faculty = current_faculty()
    slot = dbm.query_db("SELECT * FROM faculty_slots WHERE id = ?", (slot_id,), one=True)
    if not slot or slot['faculty_id'] != faculty['id']:
        abort(404)

    reason = request.form.get('cancel_reason', '').strip()
    if not reason:
        flash('Please give a reason for cancelling this class — students booked into it will see it.', 'danger')
        return redirect(url_for('faculty_slots'))

    booked = dbm.query_db(
        "SELECT student_id FROM appointments WHERE slot_id = ? AND status = 'upcoming'", (slot_id,))
    if not booked:
        flash('No one is booked into this slot — use Remove instead.', 'info')
        return redirect(url_for('faculty_slots'))

    dbm.execute_db("""
        UPDATE appointments SET status = 'cancelled', cancel_reason = ?
        WHERE slot_id = ? AND status = 'upcoming'
    """, (reason, slot_id))
    dbm.execute_db("""
        UPDATE faculty_slots SET status = 'cancelled', cancel_reason = ?, cancelled_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (reason, slot_id))

    when = f"{slot['slot_date']} at {slot['start_time']}" if slot['slot_date'] else "your upcoming class"
    topic = f" ({slot['topic']})" if slot['topic'] else ""
    notif_id = dbm.execute_db("""
        INSERT INTO notifications (college_id, faculty_id, title, message, kind)
        VALUES (?, ?, ?, ?, 'class_cancelled')
    """, (faculty['college_id'], faculty['id'], "Class Cancelled",
          f"Your class on {when}{topic} with {faculty['name']} has been cancelled. Reason: {reason}"))
    for r in booked:
        dbm.execute_db(
            "INSERT INTO notification_recipients (notification_id, student_id) VALUES (?, ?)",
            (notif_id, r['student_id']))

    flash(f'Class cancelled — {len(booked)} student(s) have been notified with your reason.', 'info')
    return redirect(url_for('faculty_slots'))


@app.route('/faculty/slots/requests/<int:request_id>/approve', methods=['POST'])
@faculty_login_required
def approve_slot_request(request_id):
    faculty = current_faculty()
    req = dbm.query_db("SELECT * FROM slot_requests WHERE id = ?", (request_id,), one=True)
    if not req or req['faculty_id'] != faculty['id']:
        abort(404)
    if req['status'] != 'pending':
        flash('This request has already been handled.', 'info')
        return redirect(url_for('faculty_slots'))

    slot_date = request.form.get('proposed_date')
    start_time = request.form.get('proposed_start')
    end_time = request.form.get('proposed_end')
    meeting_link = request.form.get('meeting_link', '').strip()

    if not all([slot_date, start_time, end_time]):
        flash('Give a date, start time and end time to approve this request.', 'danger')
        return redirect(url_for('faculty_slots'))
    if end_time <= start_time:
        flash('End time must be after the start time.', 'danger')
        return redirect(url_for('faculty_slots'))

    topic = req['skill'] + (f" (for {req['company_name']})" if req['company_name'] else '')
    slot_id = dbm.execute_db("""
        INSERT INTO faculty_slots (faculty_id, slot_date, start_time, end_time, topic, status, meeting_link, capacity)
        VALUES (?, ?, ?, ?, ?, 'booked', ?, 1)
    """, (faculty['id'], slot_date, start_time, end_time, topic, meeting_link))
    dbm.execute_db(
        "INSERT INTO appointments (slot_id, student_id, faculty_id) VALUES (?, ?, ?)",
        (slot_id, req['student_id'], faculty['id']))
    dbm.execute_db("""
        UPDATE slot_requests SET status = 'approved', proposed_date = ?, proposed_start = ?, proposed_end = ?,
               meeting_link = ?, resulting_slot_id = ?, responded_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (slot_date, start_time, end_time, meeting_link, slot_id, request_id))
    flash('Request approved — the class has been scheduled and booked for the student.', 'success')
    return redirect(url_for('faculty_slots'))


@app.route('/faculty/slots/requests/<int:request_id>/decline', methods=['POST'])
@faculty_login_required
def decline_slot_request(request_id):
    faculty = current_faculty()
    req = dbm.query_db("SELECT * FROM slot_requests WHERE id = ?", (request_id,), one=True)
    if not req or req['faculty_id'] != faculty['id']:
        abort(404)
    if req['status'] != 'pending':
        flash('This request has already been handled.', 'info')
        return redirect(url_for('faculty_slots'))

    reason = request.form.get('decline_reason', '').strip()
    alternate_date = request.form.get('alternate_date', '').strip()

    if not reason or not alternate_date:
        flash('To decline a request you must give a reason and a date for another class the student can join.', 'danger')
        return redirect(url_for('faculty_slots'))

    dbm.execute_db("""
        UPDATE slot_requests SET status = 'declined', decline_reason = ?, alternate_date = ?,
               responded_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (reason, alternate_date, request_id))
    flash('Request declined — the student has been shown your reason and the alternate date.', 'info')
    return redirect(url_for('faculty_slots'))


@app.route('/faculty/progress')
@faculty_login_required
def faculty_progress():
    """Progress overview for this faculty member's own mentees (students who
    have booked at least one appointment with them) — not the whole college,
    so it stays focused on the students they're actually mentoring."""
    faculty = current_faculty()
    rows = dbm.query_db("""
        SELECT DISTINCT students.* FROM students
        JOIN appointments ON appointments.student_id = students.id
        WHERE appointments.faculty_id = ?
        ORDER BY students.name
    """, (faculty['id'],))

    data = []
    for s in rows:
        best = best_main_score(s['id'])
        cert_count = len(dbm.query_db("SELECT id FROM certificates WHERE student_id = ?", (s['id'],)))
        data.append({
            'student': s,
            'progress': overall_progress(s),
            'best_score': f"{best['score']}/{best['total']}" if best else "Not attempted",
            'certificates': cert_count,
        })
    return render_template('faculty_progress.html', faculty=faculty, data=data)


# --------------------------------------------------------------------------
# FACULTY: create a custom MCQ test — students at the same college see it
# under Skill Assessment (see assessment_home() / start_faculty_test()).
# --------------------------------------------------------------------------
@app.route('/faculty/tests', methods=['GET', 'POST'])
@faculty_login_required
def faculty_tests():
    faculty = current_faculty()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        q_texts = request.form.getlist('question_text[]')
        opt_a = request.form.getlist('option_a[]')
        opt_b = request.form.getlist('option_b[]')
        opt_c = request.form.getlist('option_c[]')
        opt_d = request.form.getlist('option_d[]')
        corrects = request.form.getlist('correct[]')

        rows_to_insert = []
        for i in range(len(q_texts)):
            qt = q_texts[i].strip()
            a = opt_a[i].strip() if i < len(opt_a) else ''
            b = opt_b[i].strip() if i < len(opt_b) else ''
            c = opt_c[i].strip() if i < len(opt_c) else ''
            d = opt_d[i].strip() if i < len(opt_d) else ''
            corr = corrects[i].strip().upper() if i < len(corrects) else ''
            if qt and a and b and c and d and corr in ('A', 'B', 'C', 'D'):
                rows_to_insert.append((qt, a, b, c, d, corr))

        if not title:
            flash('Give the test a title.', 'danger')
        elif not rows_to_insert:
            flash('Add at least one complete question — text, all 4 options, and the correct option marked.', 'danger')
        else:
            test_id = dbm.execute_db("""
                INSERT INTO faculty_tests (faculty_id, college_id, title, description)
                VALUES (?, ?, ?, ?)
            """, (faculty['id'], faculty['college_id'], title, description))
            for qt, a, b, c, d, corr in rows_to_insert:
                dbm.execute_db("""
                    INSERT INTO faculty_test_questions
                        (test_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (test_id, qt, a, b, c, d, corr))
            flash(f'Test "{title}" created with {len(rows_to_insert)} question(s) — students at your college can now take it.', 'success')
        return redirect(url_for('faculty_tests'))

    tests = dbm.query_db("""
        SELECT faculty_tests.*,
               (SELECT COUNT(*) FROM faculty_test_questions WHERE test_id = faculty_tests.id) AS question_count,
               (SELECT COUNT(*) FROM faculty_test_attempts WHERE test_id = faculty_tests.id) AS attempt_count
        FROM faculty_tests WHERE faculty_id = ? ORDER BY created_at DESC
    """, (faculty['id'],))
    return render_template('faculty_tests.html', faculty=faculty, tests=tests)


@app.route('/faculty/tests/<int:test_id>/delete', methods=['POST'])
@faculty_login_required
def delete_faculty_test(test_id):
    faculty = current_faculty()
    test = dbm.query_db("SELECT * FROM faculty_tests WHERE id = ?", (test_id,), one=True)
    if not test or test['faculty_id'] != faculty['id']:
        abort(404)
    dbm.execute_db("DELETE FROM faculty_test_attempts WHERE test_id = ?", (test_id,))
    dbm.execute_db("DELETE FROM faculty_test_questions WHERE test_id = ?", (test_id,))
    dbm.execute_db("DELETE FROM faculty_tests WHERE id = ?", (test_id,))
    flash('Test removed.', 'info')
    return redirect(url_for('faculty_tests'))


@app.route('/faculty/tests/<int:test_id>/results')
@faculty_login_required
def faculty_test_results(test_id):
    faculty = current_faculty()
    test = dbm.query_db("SELECT * FROM faculty_tests WHERE id = ?", (test_id,), one=True)
    if not test or test['faculty_id'] != faculty['id']:
        abort(404)
    attempts = dbm.query_db("""
        SELECT faculty_test_attempts.*, students.name AS student_name, students.course AS student_course
        FROM faculty_test_attempts
        JOIN students ON students.id = faculty_test_attempts.student_id
        WHERE faculty_test_attempts.test_id = ?
        ORDER BY faculty_test_attempts.taken_at DESC
    """, (test_id,))
    return render_template('faculty_test_results.html', faculty=faculty, test=test, attempts=attempts)


# --------------------------------------------------------------------------
# STUDENT: Skill Enhancement — skill-gap analysis + browse/book a 1-on-1
# mentoring slot with a faculty member at the student's own college.
# --------------------------------------------------------------------------
@app.route('/skill-enhancement')
@student_login_required
def skill_enhancement():
    student = current_student()
    analysis = skill_gap_analysis(student)

    open_slots = []
    faculty_list = []
    my_requests = []
    peer_refs = []
    if student['college_id']:
        raw_slots = dbm.query_db("""
            SELECT faculty_slots.*, faculty.name AS faculty_name, faculty.department AS faculty_department,
                   faculty.expertise AS faculty_expertise,
                   (SELECT COUNT(*) FROM appointments
                    WHERE appointments.slot_id = faculty_slots.id AND appointments.status = 'upcoming') AS seats_taken
            FROM faculty_slots
            JOIN faculty ON faculty.id = faculty_slots.faculty_id
            WHERE faculty.college_id = ? AND faculty_slots.status != 'cancelled'
            ORDER BY faculty_slots.slot_date ASC, faculty_slots.start_time ASC
        """, (student['college_id'],))
        my_slot_ids = {a['slot_id'] for a in dbm.query_db(
            "SELECT slot_id FROM appointments WHERE student_id = ? AND status = 'upcoming'", (student['id'],))}
        for s in raw_slots:
            capacity = s['capacity'] or 1
            already_joined = s['id'] in my_slot_ids
            if s['seats_taken'] < capacity or already_joined:
                d = dict(s)
                d['capacity'] = capacity
                d['already_joined'] = already_joined
                open_slots.append(d)

        faculty_list = dbm.query_db(
            "SELECT * FROM faculty WHERE college_id = ? ORDER BY name", (student['college_id'],))
        peer_refs = dbm.query_db(
            "SELECT * FROM peer_references WHERE college_id = ? ORDER BY created_at DESC LIMIT 6",
            (student['college_id'],))

    my_appointments = dbm.query_db("""
        SELECT appointments.*, faculty_slots.slot_date, faculty_slots.start_time, faculty_slots.end_time,
               faculty_slots.topic, faculty_slots.meeting_link, faculty.name AS faculty_name
        FROM appointments
        JOIN faculty_slots ON faculty_slots.id = appointments.slot_id
        JOIN faculty ON faculty.id = appointments.faculty_id
        WHERE appointments.student_id = ? AND appointments.status = 'upcoming'
        ORDER BY faculty_slots.slot_date ASC, faculty_slots.start_time ASC
    """, (student['id'],))

    my_requests = dbm.query_db("""
        SELECT slot_requests.*, faculty.name AS faculty_name
        FROM slot_requests JOIN faculty ON faculty.id = slot_requests.faculty_id
        WHERE slot_requests.student_id = ? ORDER BY slot_requests.created_at DESC LIMIT 10
    """, (student['id'],))

    return render_template('skill_enhancement.html', student=student, analysis=analysis,
                            open_slots=open_slots, my_appointments=my_appointments,
                            faculty_list=faculty_list, my_requests=my_requests, peer_refs=peer_refs)


@app.route('/skill-enhancement/request', methods=['POST'])
@student_login_required
def request_slot():
    student = current_student()
    faculty_id = request.form.get('faculty_id')
    skill = request.form.get('skill_custom', '').strip() or request.form.get('skill_select', '').strip()
    message = request.form.get('message', '').strip()

    if not faculty_id or not skill:
        flash('Pick a faculty mentor and tell them which skill you want to learn.', 'danger')
        return redirect(url_for('skill_enhancement'))

    faculty = dbm.query_db("SELECT * FROM faculty WHERE id = ?", (faculty_id,), one=True)
    if not faculty or faculty['college_id'] != student['college_id']:
        abort(403)

    company_name = match_company_for_skill(student['college_id'], skill)
    dbm.execute_db("""
        INSERT INTO slot_requests (student_id, faculty_id, skill, company_name, message)
        VALUES (?, ?, ?, ?, ?)
    """, (student['id'], int(faculty_id), skill, company_name, message))
    flash(f"Request sent to {faculty['name']} — you'll see their response here once they reply.", 'success')
    return redirect(url_for('skill_enhancement'))


@app.route('/skill-enhancement/book/<int:slot_id>', methods=['POST'])
@student_login_required
def book_slot(slot_id):
    student = current_student()
    slot = dbm.query_db("SELECT * FROM faculty_slots WHERE id = ?", (slot_id,), one=True)
    if not slot:
        abort(404)
    faculty = dbm.query_db("SELECT * FROM faculty WHERE id = ?", (slot['faculty_id'],), one=True)
    if not faculty or faculty['college_id'] != student['college_id']:
        abort(403)
    if slot['status'] == 'cancelled':
        flash('This class was cancelled by the faculty member.', 'warning')
        return redirect(url_for('skill_enhancement'))

    already = dbm.query_db(
        "SELECT id FROM appointments WHERE slot_id = ? AND student_id = ? AND status = 'upcoming'",
        (slot_id, student['id']), one=True)
    if already:
        flash("You're already enrolled in this class.", 'info')
        return redirect(url_for('skill_enhancement'))

    seats_taken = dbm.query_db(
        "SELECT COUNT(*) AS c FROM appointments WHERE slot_id = ? AND status = 'upcoming'",
        (slot_id,), one=True)['c']
    if seats_taken >= (slot['capacity'] or 1):
        flash('Sorry, that class just filled up.', 'warning')
        return redirect(url_for('skill_enhancement'))

    dbm.execute_db(
        "INSERT INTO appointments (slot_id, student_id, faculty_id) VALUES (?, ?, ?)",
        (slot_id, student['id'], slot['faculty_id']))
    flash(f"Booked! {faculty['name']} will see you on {slot['slot_date']} at {slot['start_time']}.", 'success')
    return redirect(url_for('skill_enhancement'))


@app.route('/skill-enhancement/cancel/<int:appointment_id>', methods=['POST'])
@student_login_required
def cancel_appointment(appointment_id):
    student = current_student()
    appt = dbm.query_db("SELECT * FROM appointments WHERE id = ?", (appointment_id,), one=True)
    if not appt or appt['student_id'] != student['id']:
        abort(404)
    dbm.execute_db("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appointment_id,))
    flash('Appointment cancelled — the seat is open for other students again.', 'info')
    return redirect(url_for('skill_enhancement'))


# --------------------------------------------------------------------------
# DOUBTS — a student posts a question tagged to a department; any faculty
# member in that department can answer it. Separate from the college Help
# Desk (support_tickets), which is for placement/admin issues, not academics.
# --------------------------------------------------------------------------
@app.route('/ask-faculty')
@student_login_required
def ask_faculty():
    student = current_student()
    my_doubts = dbm.query_db("""
        SELECT doubts.*, faculty.name AS faculty_name FROM doubts
        LEFT JOIN faculty ON faculty.id = doubts.faculty_id
        WHERE doubts.student_id = ? ORDER BY doubts.created_at DESC
    """, (student['id'],))

    faculty_list = []
    threads = []
    if student['college_id']:
        faculty_list = dbm.query_db(
            "SELECT * FROM faculty WHERE college_id = ? ORDER BY name", (student['college_id'],))
        raw = dbm.query_db("""
            SELECT * FROM (
                SELECT faculty.id AS faculty_id, faculty.name AS faculty_name,
                       (SELECT COUNT(*) FROM messages
                        WHERE messages.student_id = ? AND messages.faculty_id = faculty.id) AS message_count,
                       (SELECT COUNT(*) FROM messages
                        WHERE messages.student_id = ? AND messages.faculty_id = faculty.id
                          AND messages.sender_role = 'faculty' AND messages.read_at IS NULL) AS unread
                FROM faculty WHERE faculty.college_id = ?
            ) WHERE message_count > 0
            ORDER BY unread DESC, message_count DESC
        """, (student['id'], student['id'], student['college_id']))
        threads = [dict(r) for r in raw]

    return render_template('ask_faculty.html', my_doubts=my_doubts, faculty_list=faculty_list,
                            threads=threads, departments=DEPARTMENTS, student=student)


@app.route('/doubts/ask', methods=['POST'])
@student_login_required
def submit_doubt():
    student = current_student()
    department = request.form.get('department', '').strip() or student['department']
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()
    file = request.files.get('image')

    if not subject or not message:
        flash('Please fill in a subject and your question.', 'danger')
        return redirect(url_for('ask_faculty'))

    image_path = None
    if file and file.filename:
        if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            flash('That attachment needs to be an image (PNG, JPG, JPEG or GIF).', 'danger')
            return redirect(url_for('ask_faculty'))
        image_path = secure_filename(f"q_{student['id']}_{datetime.utcnow().timestamp()}_{file.filename}")
        file.save(os.path.join(UPLOAD_ROOT, 'doubts', image_path))

    dbm.execute_db(
        "INSERT INTO doubts (student_id, department, subject, message, image_path) VALUES (?, ?, ?, ?, ?)",
        (student['id'], department, subject, message, image_path))
    flash('Your doubt has been posted — a faculty member from that department will answer soon.', 'success')
    return redirect(url_for('ask_faculty'))


@app.route('/faculty/doubts')
@faculty_login_required
def faculty_doubts():
    faculty = current_faculty()
    open_doubts = dbm.query_db("""
        SELECT doubts.*, students.name AS student_name FROM doubts
        JOIN students ON students.id = doubts.student_id
        WHERE students.college_id = ? AND doubts.status = 'open'
          AND (doubts.department = ? OR doubts.department IS NULL OR doubts.department = '')
        ORDER BY doubts.created_at ASC
    """, (faculty['college_id'], faculty['department']))
    answered_by_me = dbm.query_db("""
        SELECT doubts.*, students.name AS student_name FROM doubts
        JOIN students ON students.id = doubts.student_id
        WHERE doubts.faculty_id = ? ORDER BY doubts.answered_at DESC LIMIT 10
    """, (faculty['id'],))
    threads = dbm.query_db("""
        SELECT * FROM (
            SELECT students.id AS student_id, students.name AS student_name,
                   (SELECT COUNT(*) FROM messages
                    WHERE messages.faculty_id = ? AND messages.student_id = students.id) AS message_count,
                   (SELECT COUNT(*) FROM messages
                    WHERE messages.faculty_id = ? AND messages.student_id = students.id
                      AND messages.sender_role = 'student' AND messages.read_at IS NULL) AS unread
            FROM students WHERE students.college_id = ?
        ) WHERE message_count > 0
        ORDER BY unread DESC, message_count DESC
    """, (faculty['id'], faculty['id'], faculty['college_id']))

    return render_template('faculty_doubts.html', faculty=faculty, open_doubts=open_doubts,
                            answered_by_me=answered_by_me, threads=threads)


@app.route('/doubts/<int:doubt_id>/answer', methods=['POST'])
@faculty_login_required
def answer_doubt(doubt_id):
    faculty = current_faculty()
    doubt = dbm.query_db("SELECT * FROM doubts WHERE id = ?", (doubt_id,), one=True)
    if not doubt:
        abort(404)
    student = dbm.query_db("SELECT * FROM students WHERE id = ?", (doubt['student_id'],), one=True)
    same_college = student and student['college_id'] == faculty['college_id']
    same_department = not doubt['department'] or doubt['department'] == faculty['department']
    if not same_college or not same_department:
        abort(403)

    answer = request.form.get('answer', '').strip()
    file = request.files.get('image')

    if not answer:
        flash('Please write an answer before submitting.', 'danger')
        return redirect(url_for('faculty_doubts'))

    answer_image_path = None
    if file and file.filename:
        if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            flash('That attachment needs to be an image (PNG, JPG, JPEG or GIF).', 'danger')
            return redirect(url_for('faculty_doubts'))
        answer_image_path = secure_filename(f"a_{faculty['id']}_{datetime.utcnow().timestamp()}_{file.filename}")
        file.save(os.path.join(UPLOAD_ROOT, 'doubts', answer_image_path))

    dbm.execute_db("""
        UPDATE doubts SET answer = ?, answer_image_path = ?, faculty_id = ?, status = 'answered',
               answered_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (answer, answer_image_path, faculty['id'], doubt_id))
    flash('Answer posted.', 'success')
    return redirect(url_for('faculty_doubts'))


# --------------------------------------------------------------------------
# MESSAGES — a lightweight chat thread between one student and one faculty
# member. `other_id` means the faculty's id when a student is viewing, or
# the student's id when a faculty member is viewing.
# --------------------------------------------------------------------------
@app.route('/messages/<int:other_id>', methods=['GET', 'POST'])
def message_thread(other_id):
    role = session.get('role')
    if role == 'student':
        student = current_student()
        faculty = dbm.query_db("SELECT * FROM faculty WHERE id = ?", (other_id,), one=True)
        if not student or not faculty or faculty['college_id'] != student['college_id']:
            abort(404)
        student_id, faculty_id, other_name = student['id'], faculty['id'], faculty['name']
    elif role == 'faculty':
        faculty = current_faculty()
        student = dbm.query_db("SELECT * FROM students WHERE id = ?", (other_id,), one=True)
        if not faculty or not student or student['college_id'] != faculty['college_id']:
            abort(404)
        student_id, faculty_id, other_name = student['id'], faculty['id'], student['name']
    else:
        flash('Please log in to send messages.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if body:
            dbm.execute_db(
                "INSERT INTO messages (student_id, faculty_id, sender_role, body) VALUES (?, ?, ?, ?)",
                (student_id, faculty_id, role, body))
        return redirect(url_for('message_thread', other_id=other_id))

    dbm.execute_db("""
        UPDATE messages SET read_at = CURRENT_TIMESTAMP
        WHERE student_id = ? AND faculty_id = ? AND sender_role != ? AND read_at IS NULL
    """, (student_id, faculty_id, role))

    thread = dbm.query_db(
        "SELECT * FROM messages WHERE student_id = ? AND faculty_id = ? ORDER BY created_at ASC",
        (student_id, faculty_id))

    return render_template('message_thread.html', thread=thread, other_name=other_name,
                            my_role=role, other_id=other_id)


# --------------------------------------------------------------------------
# Bell icon — small JSON API polled by static/js/notifications.js
# --------------------------------------------------------------------------
@app.route('/api/notifications/summary')
def api_notifications_summary():
    if session.get('role') == 'student':
        student = current_student()
        if not student:
            return jsonify({'count': 0, 'items': []})
        unread = dbm.query_db(
            "SELECT COUNT(*) AS c FROM notification_recipients WHERE student_id = ? AND read_at IS NULL",
            (student['id'],), one=True)
        rows = dbm.query_db("""
            SELECT notifications.id, notifications.title, notifications.message,
                   notifications.created_at, notification_recipients.read_at
            FROM notification_recipients
            JOIN notifications ON notifications.id = notification_recipients.notification_id
            WHERE notification_recipients.student_id = ?
            ORDER BY notifications.created_at DESC LIMIT 8
        """, (student['id'],))
        items = [{
            'id': r['id'], 'title': r['title'], 'message': r['message'],
            'created_at': r['created_at'], 'unread': r['read_at'] is None,
        } for r in rows]
        return jsonify({'count': unread['c'] if unread else 0, 'items': items})

    if session.get('role') == 'employee':
        college_id = session['college_id']
        open_count = dbm.query_db(
            "SELECT COUNT(*) AS c FROM support_tickets WHERE college_id = ? AND status = 'open'",
            (college_id,), one=True)
        rows = dbm.query_db("""
            SELECT support_tickets.id, support_tickets.subject, support_tickets.message,
                   support_tickets.status, support_tickets.created_at, students.name AS student_name
            FROM support_tickets
            JOIN students ON students.id = support_tickets.student_id
            WHERE support_tickets.college_id = ?
            ORDER BY support_tickets.created_at DESC LIMIT 8
        """, (college_id,))
        items = [{
            'id': r['id'], 'title': f"{r['student_name']}: {r['subject']}", 'message': r['message'],
            'created_at': r['created_at'], 'unread': r['status'] == 'open',
        } for r in rows]
        return jsonify({'count': open_count['c'] if open_count else 0, 'items': items})

    if session.get('role') == 'faculty':
        faculty = current_faculty()
        if not faculty:
            return jsonify({'count': 0, 'items': []})
        rows = dbm.query_db("""
            SELECT appointments.id, faculty_slots.slot_date, faculty_slots.start_time,
                   faculty_slots.topic, students.name AS student_name
            FROM appointments
            JOIN faculty_slots ON faculty_slots.id = appointments.slot_id
            JOIN students ON students.id = appointments.student_id
            WHERE appointments.faculty_id = ? AND appointments.status = 'upcoming'
            ORDER BY faculty_slots.slot_date ASC, faculty_slots.start_time ASC LIMIT 8
        """, (faculty['id'],))
        items = [{
            'id': r['id'], 'title': f"Class with {r['student_name']}",
            'message': f"{r['slot_date']} · {r['start_time']}" + (f" · {r['topic']}" if r['topic'] else ''),
            'created_at': r['slot_date'], 'unread': False,
        } for r in rows]
        return jsonify({'count': len(items), 'items': items})

    return jsonify({'count': 0, 'items': []})


@app.route('/api/notifications/mark_read', methods=['POST'])
@student_login_required
def api_notifications_mark_read():
    student = current_student()
    dbm.execute_db("""
        UPDATE notification_recipients SET read_at = CURRENT_TIMESTAMP
        WHERE student_id = ? AND read_at IS NULL
    """, (student['id'],))
    return jsonify({'ok': True})


# --------------------------------------------------------------------------
# AI ASSISTANT (floating chat widget — see static/js/chatbot.js)
# --------------------------------------------------------------------------
@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    history = data.get('history') or []

    if not message:
        return jsonify({'reply': "Ask me anything — registering, applying to a drive, "
                                  "your eligibility %, assessments, or your progress!"})

    context = {'role': 'guest'}
    student = current_student()
    employee = current_employee()

    if student:
        context['role'] = 'student'
        context['student'] = student
        context['progress'] = overall_progress(student)
        context['can_apply'] = has_required_uploads(student['id'])

        companies = []
        if student['college_id']:
            companies = dbm.query_db(
                "SELECT * FROM company_visits WHERE college_id = ? ORDER BY reg_end ASC",
                (student['college_id'],))
        context['companies'] = [dict(c) for c in companies]
        context['matches'] = {c['company_name']: eligibility_match(student, c) for c in companies}

        applied_rows = dbm.query_db(
            "SELECT company_id FROM applications WHERE student_id = ?", (student['id'],))
        context['applied_count'] = len(applied_rows)

        results = dbm.query_db(
            "SELECT * FROM assessment_results WHERE student_id = ? ORDER BY taken_at DESC", (student['id'],))
        context['assessment_attempts'] = len(results)
        best = best_main_score(student['id'])
        context['best_main'] = dict(best) if best else None

    elif employee:
        context['role'] = 'employee'
        context['employee'] = employee
        college_id = session['college_id']
        college = dbm.query_db("SELECT * FROM colleges WHERE id = ?", (college_id,), one=True)
        context['college'] = dict(college) if college else None

        companies = dbm.query_db(
            "SELECT * FROM company_visits WHERE college_id = ? ORDER BY reg_start DESC", (college_id,))
        context['companies'] = [dict(c) for c in companies]

        students = dbm.query_db("SELECT * FROM students WHERE college_id = ?", (college_id,))
        context['student_count'] = len(students)

        overview = {}
        for c in companies:
            if students:
                scores = [eligibility_match(s, c) for s in students]
                overview[c['company_name']] = {
                    'eligible_count': sum(1 for m in scores if m['eligible']),
                    'avg_percent': round(sum(m['percent'] for m in scores) / len(scores)),
                    'total': len(students),
                }
        context['eligibility_overview'] = overview

    else:
        faculty = current_faculty()
        if faculty:
            context['role'] = 'faculty'
            context['faculty'] = faculty
            upcoming_count = dbm.query_db(
                "SELECT COUNT(*) AS c FROM appointments WHERE faculty_id = ? AND status = 'upcoming'",
                (faculty['id'],), one=True)
            open_slot_count = dbm.query_db("""
                SELECT COUNT(*) AS c FROM faculty_slots
                WHERE faculty_id = ? AND status != 'cancelled' AND (
                    SELECT COUNT(*) FROM appointments
                    WHERE appointments.slot_id = faculty_slots.id AND appointments.status = 'upcoming'
                ) < COALESCE(capacity, 1)
            """, (faculty['id'],), one=True)
            mentee_count = dbm.query_db(
                "SELECT COUNT(DISTINCT student_id) AS c FROM appointments WHERE faculty_id = ? AND status = 'upcoming'",
                (faculty['id'],), one=True)
            pending_request_count = dbm.query_db(
                "SELECT COUNT(*) AS c FROM slot_requests WHERE faculty_id = ? AND status = 'pending'",
                (faculty['id'],), one=True)
            context['upcoming_count'] = upcoming_count['c'] if upcoming_count else 0
            context['open_slot_count'] = open_slot_count['c'] if open_slot_count else 0
            context['mentee_count'] = mentee_count['c'] if mentee_count else 0
            context['pending_request_count'] = pending_request_count['c'] if pending_request_count else 0

    reply = chatbot.get_reply(message, context, history=history)

    try:
        dbm.execute_db(
            "INSERT INTO chat_messages (role, user_kind, user_id, message, reply) VALUES (?, ?, ?, ?, ?)",
            ('user', context['role'], session.get('user_id'), message, reply))
    except Exception:
        pass  # logging chat history is best-effort only

    return jsonify({'reply': reply})


# ==========================================================================
# PORTAL CHOOSER — the "Login / Register" button lands here; pick a role.
# ==========================================================================
@app.route('/portal')
def choose_portal():
    return render_template('portal.html')


# ==========================================================================
# COMPANY PORTAL
#   Job Drive Post  -> company creates job posts with performance-based
#                      eligibility (CGPA, branch, year, skills, min assessment %)
#   College List    -> browse colleges, see how many students qualify,
#                      send a campus-visit request to the placement cell
#   Interview Schedules -> plan rounds for visits the college approved
#   Hiring Reports  -> record every interview (student details, ratings,
#                      selected / not selected + reason, remarks) and view
#                      the summary report
# ==========================================================================
INTERVIEW_RESULTS = ['Selected', 'Not Selected', 'On Hold']


def _student_assessment_pct(student_id):
    best = best_main_score(student_id)
    if best and best['total']:
        return round(best['score'] * 100 / best['total'])
    return None


def _college_performance(college_id, job=None):
    """Aggregate student-performance numbers for one college. If a job post is
    given, also counts how many students meet its eligibility rules."""
    students = dbm.query_db("SELECT * FROM students WHERE college_id = ?", (college_id,))
    cgpas = [s['cgpa'] for s in students if s['cgpa'] is not None]
    assess = [p for p in (_student_assessment_pct(s['id']) for s in students) if p is not None]
    out = {
        'students': len(students),
        'avg_cgpa': round(sum(cgpas) / len(cgpas), 2) if cgpas else None,
        'avg_assessment': round(sum(assess) / len(assess)) if assess else None,
        'assessed': len(assess),
        'eligible': None,
        'avg_match': None,
    }
    if job is not None and students:
        matches = [eligibility_match(s, job) for s in students]
        out['eligible'] = sum(1 for m in matches if m['eligible'])
        out['avg_match'] = round(sum(m['percent'] for m in matches) / len(matches))
    elif job is not None:
        out['eligible'] = 0
    return out


def _company_visit_requests(company_id):
    return dbm.query_db("""
        SELECT vr.*, c.name AS college_name, jp.title AS job_title, jp.job_type, jp.package_lpa
        FROM visit_requests vr
        JOIN colleges c ON c.id = vr.college_id
        JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE vr.company_id = ?
        ORDER BY vr.created_at DESC
    """, (company_id,))


def _drive_applicants(visit_request):
    """Students who applied to the campus drive created for an approved visit."""
    if not visit_request['company_visit_id']:
        return []
    return dbm.query_db("""
        SELECT s.* FROM applications a JOIN students s ON s.id = a.student_id
        WHERE a.company_id = ? ORDER BY s.name
    """, (visit_request['company_visit_id'],))


@app.route('/company/register', methods=['GET', 'POST'])
def company_register():
    if request.method == 'POST':
        form = request.form
        name = form.get('name', '').strip()
        email = form.get('email', '').strip().lower()
        password = form.get('password', '')
        confirm = form.get('confirm_password', '')
        hr_name = form.get('hr_name', '').strip()
        if not all([name, email, password, hr_name]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('register_company.html', form=form)
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('register_company.html', form=form)
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register_company.html', form=form)
        if dbm.query_db("SELECT id FROM companies WHERE email = ?", (email,), one=True):
            flash('A company account with this email already exists.', 'danger')
            return render_template('register_company.html', form=form)
        dbm.execute_db("""
            INSERT INTO companies (name, email, password_hash, hr_name, phone, industry, website, location, about)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, email, generate_password_hash(password), hr_name, form.get('phone', '').strip(),
              form.get('industry', '').strip(), form.get('website', '').strip(),
              form.get('location', '').strip(), form.get('about', '').strip()))
        flash('Company registered! Please log in.', 'success')
        return redirect(url_for('company_login'))
    return render_template('register_company.html', form={})


@app.route('/company/login', methods=['GET', 'POST'])
def company_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        company = dbm.query_db("SELECT * FROM companies WHERE email = ?", (email,), one=True)
        if company and check_password_hash(company['password_hash'], password):
            session.clear()
            session['role'] = 'company'
            session['user_id'] = company['id']
            flash(f"Welcome, {company['name']}!", 'success')
            return redirect(url_for('company_home'))
        flash('Incorrect email or password.', 'danger')
    return render_template('company_login.html')


@app.route('/company/home')
@company_login_required
def company_home():
    company = current_company()
    cid = company['id']
    jobs = dbm.query_db("SELECT * FROM job_posts WHERE company_id = ? ORDER BY created_at DESC", (cid,))
    requests_ = _company_visit_requests(cid)
    today = date.today().isoformat()
    upcoming = dbm.query_db("""
        SELECT s.*, c.name AS college_name, jp.title AS job_title
        FROM interview_schedules s
        JOIN visit_requests vr ON vr.id = s.visit_request_id
        JOIN colleges c ON c.id = vr.college_id
        JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE s.company_id = ? AND s.status = 'scheduled' AND s.interview_date >= ?
        ORDER BY s.interview_date, s.start_time LIMIT 5
    """, (cid, today))
    reports = dbm.query_db("SELECT result FROM interview_reports WHERE company_id = ?", (cid,))
    stats = {
        'jobs': len([j for j in jobs if j['status'] == 'open']),
        'pending': len([r for r in requests_ if r['status'] == 'pending']),
        'approved': len([r for r in requests_ if r['status'] == 'approved']),
        'interviews': len(reports),
        'selected': len([r for r in reports if r['result'] == 'Selected']),
    }
    return render_template('company_home.html', company=company, stats=stats,
                           requests=requests_[:6], upcoming=upcoming, jobs=jobs[:4])


@app.route('/company/jobs', methods=['GET', 'POST'])
@company_login_required
def company_jobs():
    company = current_company()
    if request.method == 'POST':
        f = request.form
        title = f.get('title', '').strip()
        if not title:
            flash('Job title is required.', 'danger')
            return redirect(url_for('company_jobs'))

        def _num(v, cast, default=0):
            try:
                return cast(v) if v not in (None, '') else default
            except ValueError:
                return default

        dbm.execute_db("""
            INSERT INTO job_posts (company_id, title, job_type, description, location, package_lpa, openings,
                                   min_cgpa, eligible_courses, eligible_years, required_skills,
                                   min_assessment_pct, last_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (company['id'], title, f.get('job_type', 'Full-time'), f.get('description', '').strip(),
              f.get('location', '').strip(), f.get('package_lpa', '').strip(),
              _num(f.get('openings'), int, 1), _num(f.get('min_cgpa'), float, 0),
              f.get('eligible_courses', '').strip(), ','.join(f.getlist('eligible_years')),
              f.get('required_skills', '').strip(),
              max(0, min(100, _num(f.get('min_assessment_pct'), int, 0))),
              f.get('last_date') or None))
        flash(f'Job drive "{title}" posted. Now pick colleges from the College List to request a campus visit.',
              'success')
        return redirect(url_for('company_jobs'))

    jobs = dbm.query_db("SELECT * FROM job_posts WHERE company_id = ? ORDER BY created_at DESC", (company['id'],))
    req_counts = {}
    for r in _company_visit_requests(company['id']):
        d = req_counts.setdefault(r['job_post_id'], {'pending': 0, 'approved': 0, 'rejected': 0})
        d[r['status']] = d.get(r['status'], 0) + 1
    return render_template('company_jobs.html', company=company, jobs=jobs, req_counts=req_counts)


@app.route('/company/jobs/<int:job_id>/toggle', methods=['POST'])
@company_login_required
def toggle_job_post(job_id):
    job = dbm.query_db("SELECT * FROM job_posts WHERE id = ?", (job_id,), one=True)
    if not job or job['company_id'] != session['user_id']:
        abort(404)
    new_status = 'closed' if job['status'] == 'open' else 'open'
    dbm.execute_db("UPDATE job_posts SET status = ? WHERE id = ?", (new_status, job_id))
    flash(f'Job drive marked {new_status}.', 'info')
    return redirect(url_for('company_jobs'))


@app.route('/company/jobs/<int:job_id>/delete', methods=['POST'])
@company_login_required
def delete_job_post(job_id):
    job = dbm.query_db("SELECT * FROM job_posts WHERE id = ?", (job_id,), one=True)
    if not job or job['company_id'] != session['user_id']:
        abort(404)
    used = dbm.query_db("SELECT id FROM visit_requests WHERE job_post_id = ? AND status = 'approved'", (job_id,))
    if used:
        flash('This job already has an approved campus visit — close it instead of deleting.', 'warning')
        return redirect(url_for('company_jobs'))
    dbm.execute_db("DELETE FROM visit_requests WHERE job_post_id = ?", (job_id,))
    dbm.execute_db("DELETE FROM job_posts WHERE id = ?", (job_id,))
    flash('Job drive deleted.', 'info')
    return redirect(url_for('company_jobs'))


@app.route('/company/colleges')
@company_login_required
def company_colleges():
    company = current_company()
    jobs = dbm.query_db("SELECT * FROM job_posts WHERE company_id = ? AND status = 'open' ORDER BY created_at DESC",
                        (company['id'],))
    job = None
    job_id = request.args.get('job', type=int)
    if job_id:
        job = next((j for j in jobs if j['id'] == job_id), None)
    elif jobs:
        job = jobs[0]

    q = request.args.get('q', '').strip()
    # Default: only colleges that actually have students on UniLinkUp.
    only_active = ('1' in request.args.getlist('active')) if 'active' in request.args else True
    colleges = dbm.query_db("SELECT * FROM colleges ORDER BY name")
    if q:
        colleges = [c for c in colleges if q.lower() in c['name'].lower()]

    existing = {}
    for r in _company_visit_requests(company['id']):
        if job and r['job_post_id'] == job['id']:
            existing[r['college_id']] = r

    rows = []
    for c in colleges:
        perf = _college_performance(c['id'], job)
        if only_active and not perf['students']:
            continue
        rows.append({'college': c, 'perf': perf, 'request': existing.get(c['id'])})
    # Colleges with eligible students first, then by number of students.
    rows.sort(key=lambda r: (-(r['perf']['eligible'] or 0), -r['perf']['students'], r['college']['name']))
    return render_template('company_colleges.html', company=company, jobs=jobs, job=job, rows=rows,
                           q=q, only_active=only_active, today=date.today().isoformat())


@app.route('/company/colleges/<int:college_id>')
@company_login_required
def company_college_detail(college_id):
    company = current_company()
    college = dbm.query_db("SELECT * FROM colleges WHERE id = ?", (college_id,), one=True)
    if not college:
        abort(404)
    jobs = dbm.query_db("SELECT * FROM job_posts WHERE company_id = ? ORDER BY created_at DESC", (company['id'],))
    job_id = request.args.get('job', type=int)
    job = next((j for j in jobs if j['id'] == job_id), None) if job_id else (jobs[0] if jobs else None)
    perf = _college_performance(college_id, job)

    # Student-level detail is only shared once this college has approved a
    # visit from this company; before that the company sees aggregates only.
    approved = dbm.query_db("""SELECT id FROM visit_requests WHERE company_id = ? AND college_id = ?
                               AND status = 'approved'""", (company['id'], college_id))
    students = []
    by_dept = {}
    for s in dbm.query_db("SELECT * FROM students WHERE college_id = ?", (college_id,)):
        m = eligibility_match(s, job) if job else None
        dept = s['department'] or s['course'] or 'Other'
        d = by_dept.setdefault(dept, {'total': 0, 'eligible': 0})
        d['total'] += 1
        if m and m['eligible']:
            d['eligible'] += 1
        students.append({'s': s, 'match': m, 'assess': _student_assessment_pct(s['id'])})
    students.sort(key=lambda x: -(x['match']['percent'] if x['match'] else 0))
    reqs = [r for r in _company_visit_requests(company['id']) if r['college_id'] == college_id]
    return render_template('company_college_detail.html', company=company, college=college, jobs=jobs,
                           job=job, perf=perf, students=students if approved else [],
                           can_see_students=bool(approved), by_dept=by_dept, reqs=reqs,
                           today=date.today().isoformat())


@app.route('/company/colleges/<int:college_id>/request', methods=['POST'])
@company_login_required
def request_college_visit(college_id):
    company = current_company()
    college = dbm.query_db("SELECT * FROM colleges WHERE id = ?", (college_id,), one=True)
    job_id = request.form.get('job_post_id', type=int)
    job = dbm.query_db("SELECT * FROM job_posts WHERE id = ? AND company_id = ?", (job_id, company['id']), one=True)
    if not college or not job:
        flash('Pick a valid college and job drive.', 'danger')
        return redirect(url_for('company_colleges'))
    dup = dbm.query_db("""SELECT id FROM visit_requests WHERE company_id = ? AND college_id = ? AND job_post_id = ?
                          AND status IN ('pending','approved')""", (company['id'], college_id, job_id), one=True)
    if dup:
        flash(f'You already have an active request to {college["name"]} for this job.', 'warning')
    else:
        dbm.execute_db("""
            INSERT INTO visit_requests (company_id, job_post_id, college_id, proposed_date, message)
            VALUES (?, ?, ?, ?, ?)
        """, (company['id'], job_id, college_id, request.form.get('proposed_date') or None,
              request.form.get('message', '').strip()))
        flash(f'Visit request sent to {college["name"]}. Their placement cell will approve or reject it.', 'success')
    nxt = request.form.get('next')
    if nxt and nxt.startswith('/company/'):
        return redirect(nxt)
    return redirect(url_for('company_colleges', job=job_id))


@app.route('/company/requests/<int:req_id>/withdraw', methods=['POST'])
@company_login_required
def withdraw_visit_request(req_id):
    r = dbm.query_db("SELECT * FROM visit_requests WHERE id = ?", (req_id,), one=True)
    if not r or r['company_id'] != session['user_id']:
        abort(404)
    if r['status'] == 'pending':
        dbm.execute_db("UPDATE visit_requests SET status = 'withdrawn' WHERE id = ?", (req_id,))
        flash('Request withdrawn.', 'info')
    return redirect(request.referrer or url_for('company_home'))


@app.route('/company/interviews', methods=['GET', 'POST'])
@company_login_required
def company_interviews():
    company = current_company()
    visits = [r for r in _company_visit_requests(company['id']) if r['status'] == 'approved']
    if request.method == 'POST':
        f = request.form
        vr_id = f.get('visit_request_id', type=int)
        if not any(v['id'] == vr_id for v in visits):
            flash('Pick an approved campus visit.', 'danger')
            return redirect(url_for('company_interviews'))
        if not f.get('round_name', '').strip() or not f.get('interview_date'):
            flash('Round name and date are required.', 'danger')
            return redirect(url_for('company_interviews'))
        dbm.execute_db("""
            INSERT INTO interview_schedules (company_id, visit_request_id, round_name, interview_date, start_time,
                                             end_time, mode, venue, meeting_link, panel, notes, interviewer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (company['id'], vr_id, f.get('round_name').strip(), f.get('interview_date'),
              f.get('start_time') or None, f.get('end_time') or None, f.get('mode', 'On-campus'),
              f.get('venue', '').strip(), f.get('meeting_link', '').strip(), f.get('panel', '').strip(),
              f.get('notes', '').strip(), _own_interviewer_id(company['id'], f.get('interviewer_id', type=int))))
        flash('Interview round scheduled.', 'success')
        return redirect(url_for('company_interviews'))

    schedules = dbm.query_db("""
        SELECT s.*, c.name AS college_name, jp.title AS job_title, vr.company_visit_id,
               (SELECT COUNT(*) FROM interview_reports r WHERE r.schedule_id = s.id) AS report_count,
               iv.name AS interviewer_name
        FROM interview_schedules s
        LEFT JOIN interviewers iv ON iv.id = s.interviewer_id
        JOIN visit_requests vr ON vr.id = s.visit_request_id
        JOIN colleges c ON c.id = vr.college_id
        JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE s.company_id = ?
        ORDER BY s.interview_date DESC, s.start_time
    """, (company['id'],))
    today = date.today().isoformat()
    upcoming = [s for s in schedules if s['status'] == 'scheduled' and s['interview_date'] >= today]
    upcoming.sort(key=lambda s: (s['interview_date'], s['start_time'] or ''))
    past = [s for s in schedules if s not in upcoming]
    applicants = {v['id']: len(_drive_applicants(v)) for v in visits}
    interviewers = dbm.query_db("SELECT * FROM interviewers WHERE company_id = ? AND is_active = 1 ORDER BY name",
                                (company['id'],))
    return render_template('company_interviews.html', company=company, visits=visits, upcoming=upcoming,
                           past=past, applicants=applicants, today=today, interviewers=interviewers)


@app.route('/company/interviews/<int:sid>/status', methods=['POST'])
@company_login_required
def update_interview_status(sid):
    s = dbm.query_db("SELECT * FROM interview_schedules WHERE id = ?", (sid,), one=True)
    if not s or s['company_id'] != session['user_id']:
        abort(404)
    status = request.form.get('status')
    if status in ('scheduled', 'completed', 'cancelled'):
        dbm.execute_db("UPDATE interview_schedules SET status = ? WHERE id = ?", (status, sid))
        flash(f'Interview marked {status}.', 'info')
    return redirect(url_for('company_interviews'))


def _report_filters(company_id):
    clauses, args = ["r.company_id = ?"], [company_id]
    vr = request.args.get('visit', type=int)
    res = request.args.get('result', '')
    if vr:
        clauses.append("r.visit_request_id = ?")
        args.append(vr)
    if res in INTERVIEW_RESULTS:
        clauses.append("r.result = ?")
        args.append(res)
    return dbm.query_db(f"""
        SELECT r.*, c.name AS college_name, jp.title AS job_title
        FROM interview_reports r
        LEFT JOIN colleges c ON c.id = r.college_id
        LEFT JOIN job_posts jp ON jp.id = r.job_post_id
        WHERE {' AND '.join(clauses)}
        ORDER BY r.interview_date DESC, r.created_at DESC
    """, tuple(args))


@app.route('/company/reports', methods=['GET', 'POST'])
@company_login_required
def company_reports():
    company = current_company()
    visits = [r for r in _company_visit_requests(company['id']) if r['status'] == 'approved']

    if request.method == 'POST':
        f = request.form
        vr_id = f.get('visit_request_id', type=int)
        visit = next((v for v in visits if v['id'] == vr_id), None)
        name = f.get('student_name', '').strip()
        result = f.get('result', '')
        reason = f.get('rejection_reason', '').strip()
        if not visit:
            flash('Pick the campus drive this interview belongs to.', 'danger')
            return redirect(url_for('company_reports'))
        if not name or result not in INTERVIEW_RESULTS:
            flash('Student name and interview result are required.', 'danger')
            return redirect(url_for('company_reports'))
        if result == 'Not Selected' and not reason:
            flash('Please enter the reason the student was not selected.', 'danger')
            return redirect(url_for('company_reports'))

        def _rating(key):
            v = f.get(key, type=int)
            return v if v and 1 <= v <= 5 else None

        def _cgpa():
            try:
                return float(f.get('cgpa')) if f.get('cgpa') else None
            except ValueError:
                return None

        student_id = f.get('student_id', type=int)
        if student_id:
            valid = dbm.query_db("SELECT id FROM students WHERE id = ? AND college_id = ?",
                                 (student_id, visit['college_id']), one=True)
            student_id = student_id if valid else None
        schedule_id = f.get('schedule_id', type=int)
        sched = dbm.query_db("SELECT * FROM interview_schedules WHERE id = ? AND visit_request_id = ?",
                             (schedule_id, vr_id), one=True) if schedule_id else None
        schedule_id = sched['id'] if sched else None
        round_name = f.get('round_name', '').strip() or (sched['round_name'] if sched else '')
        interview_date = f.get('interview_date') or (sched['interview_date'] if sched else date.today().isoformat())

        dbm.execute_db("""
            INSERT INTO interview_reports
                (company_id, visit_request_id, college_id, job_post_id, schedule_id, student_id, student_name, srn,
                 student_email, phone, course, department, year, cgpa, round_name, interview_date, interviewer,
                 technical_rating, communication_rating, aptitude_rating, result, package_offered,
                 rejection_reason, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (company['id'], vr_id, visit['college_id'], visit['job_post_id'], schedule_id, student_id, name,
              f.get('srn', '').strip(), f.get('student_email', '').strip(), f.get('phone', '').strip(),
              f.get('course', '').strip(), f.get('department', '').strip(), f.get('year', '').strip(), _cgpa(),
              round_name, interview_date,
              f.get('interviewer', '').strip(), _rating('technical_rating'), _rating('communication_rating'),
              _rating('aptitude_rating'), result, f.get('package_offered', '').strip() if result == 'Selected' else '',
              reason if result != 'Selected' else '', f.get('remarks', '').strip()))
        flash(f'Interview report saved for {name} ({result}).', 'success')
        return redirect(url_for('company_reports', visit=vr_id))

    reports = _report_filters(company['id'])
    all_reports = dbm.query_db("""
        SELECT r.*, c.name AS college_name, jp.title AS job_title FROM interview_reports r
        LEFT JOIN colleges c ON c.id = r.college_id LEFT JOIN job_posts jp ON jp.id = r.job_post_id
        WHERE r.company_id = ?""", (company['id'],))
    summary = {
        'total': len(all_reports),
        'selected': sum(1 for r in all_reports if r['result'] == 'Selected'),
        'rejected': sum(1 for r in all_reports if r['result'] == 'Not Selected'),
        'hold': sum(1 for r in all_reports if r['result'] == 'On Hold'),
    }
    summary['rate'] = round(summary['selected'] * 100 / summary['total']) if summary['total'] else 0

    by_drive = {}
    for r in all_reports:
        key = (r['college_name'] or '—', r['job_title'] or '—')
        d = by_drive.setdefault(key, {'total': 0, 'Selected': 0, 'Not Selected': 0, 'On Hold': 0})
        d['total'] += 1
        d[r['result']] = d.get(r['result'], 0) + 1

    # Pre-fill data for the form: each approved drive's applicants and rounds.
    drive_data = {}
    for v in visits:
        drive_data[v['id']] = {
            'applicants': [{'id': s['id'], 'name': s['name'], 'srn': s['srn'], 'email': s['email'],
                            'course': s['course'] or '', 'department': s['department'] or '',
                            'year': s['year'] or '', 'cgpa': s['cgpa']} for s in _drive_applicants(v)],
            'rounds': [{'id': s['id'], 'name': s['round_name'], 'date': s['interview_date'],
                        'panel': s['panel'] or ''}
                       for s in dbm.query_db("SELECT * FROM interview_schedules WHERE visit_request_id = ? "
                                             "ORDER BY interview_date", (v['id'],))],
        }
    return render_template('company_reports.html', company=company, visits=visits, reports=reports,
                           summary=summary, by_drive=by_drive, drive_data=drive_data,
                           results=INTERVIEW_RESULTS, sel_visit=request.args.get('visit', type=int),
                           sel_result=request.args.get('result', ''), today=date.today().isoformat())


@app.route('/company/reports/export.csv')
@company_login_required
def export_company_reports():
    import csv
    import io
    rows = _report_filters(session['user_id'])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'College', 'Job', 'Round', 'Student', 'SRN', 'Email', 'Phone', 'Course', 'Department',
                'Year', 'CGPA', 'Interviewer', 'Technical', 'Communication', 'Aptitude', 'Result',
                'Package Offered', 'Reason Not Selected', 'Remarks'])
    for r in rows:
        w.writerow([r['interview_date'], r['college_name'], r['job_title'], r['round_name'], r['student_name'],
                    r['srn'], r['student_email'], r['phone'], r['course'], r['department'], r['year'], r['cgpa'],
                    r['interviewer'], r['technical_rating'], r['communication_rating'], r['aptitude_rating'],
                    r['result'], r['package_offered'], r['rejection_reason'], r['remarks']])
    from flask import Response
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=hiring_report.csv'})


@app.route('/company/reports/<int:rid>/delete', methods=['POST'])
@company_login_required
def delete_interview_report(rid):
    r = dbm.query_db("SELECT * FROM interview_reports WHERE id = ?", (rid,), one=True)
    if not r or r['company_id'] != session['user_id']:
        abort(404)
    dbm.execute_db("DELETE FROM interview_reports WHERE id = ?", (rid,))
    flash('Report deleted.', 'info')
    return redirect(url_for('company_reports'))


# ==========================================================================
# COLLEGE: company visit requests (approve / reject) + hiring outcomes
# ==========================================================================
@app.route('/college/company-requests')
@employee_login_required
def college_company_requests():
    college_id = session['college_id']
    reqs = dbm.query_db("""
        SELECT vr.*, co.name AS company_name, co.industry, co.website, co.location AS company_location,
               co.hr_name, co.email AS company_email, co.phone AS company_phone, co.about,
               jp.title AS job_title, jp.job_type, jp.description AS job_description, jp.location AS job_location,
               jp.package_lpa, jp.openings, jp.min_cgpa, jp.eligible_courses, jp.eligible_years,
               jp.required_skills, jp.min_assessment_pct, jp.last_date
        FROM visit_requests vr
        JOIN companies co ON co.id = vr.company_id
        JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE vr.college_id = ? AND vr.status != 'withdrawn'
        ORDER BY CASE vr.status WHEN 'pending' THEN 0 ELSE 1 END, vr.created_at DESC
    """, (college_id,))
    students = dbm.query_db("SELECT * FROM students WHERE college_id = ?", (college_id,))
    eligible = {}
    for r in reqs:
        job = dbm.query_db("SELECT * FROM job_posts WHERE id = ?", (r['job_post_id'],), one=True)
        eligible[r['id']] = sum(1 for s in students if eligibility_match(s, job)['eligible'])
    reports = dbm.query_db("""
        SELECT r.*, co.name AS company_name, jp.title AS job_title
        FROM interview_reports r
        JOIN companies co ON co.id = r.company_id
        LEFT JOIN job_posts jp ON jp.id = r.job_post_id
        WHERE r.college_id = ? ORDER BY r.interview_date DESC
    """, (college_id,))
    return render_template('college_company_requests.html', reqs=reqs, eligible=eligible,
                           student_count=len(students), reports=reports, today=date.today())


@app.route('/college/company-requests/<int:req_id>/approve', methods=['POST'])
@employee_login_required
def approve_company_request(req_id):
    r = dbm.query_db("SELECT * FROM visit_requests WHERE id = ?", (req_id,), one=True)
    if not r or r['college_id'] != session['college_id']:
        abort(404)
    if r['status'] != 'pending':
        flash('This request has already been answered.', 'warning')
        return redirect(url_for('college_company_requests'))
    job = dbm.query_db("SELECT * FROM job_posts WHERE id = ?", (r['job_post_id'],), one=True)
    company = dbm.query_db("SELECT * FROM companies WHERE id = ?", (r['company_id'],), one=True)
    today = date.today()
    reg_start = request.form.get('reg_start') or today.isoformat()
    reg_end = request.form.get('reg_end') or job['last_date'] or r['proposed_date'] or today.isoformat()
    if reg_end < reg_start:
        flash('Registration end date must be on or after the start date.', 'danger')
        return redirect(url_for('college_company_requests'))
    # Approving publishes a normal campus drive, so students immediately see it
    # (with their Eligibility Match %) on their home page and can apply.
    visit_id = dbm.execute_db("""
        INSERT INTO company_visits (company_name, role, description, reg_start, reg_end, college_id, min_cgpa,
                                    eligible_courses, eligible_years, required_skills, package_lpa,
                                    company_account_id, job_post_id, min_assessment_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (company['name'], job['title'], job['description'], reg_start, reg_end, r['college_id'],
          job['min_cgpa'] or 0, job['eligible_courses'], job['eligible_years'], job['required_skills'],
          job['package_lpa'], company['id'], job['id'], job['min_assessment_pct'] or 0))
    dbm.execute_db("""
        UPDATE visit_requests SET status = 'approved', college_note = ?, responded_by = ?,
               responded_at = CURRENT_TIMESTAMP, company_visit_id = ? WHERE id = ?
    """, (request.form.get('note', '').strip(), session['user_id'], visit_id, req_id))
    flash(f'Approved {company["name"]}. The drive is now live for your students.', 'success')
    return redirect(url_for('college_company_requests'))


@app.route('/college/company-requests/<int:req_id>/reject', methods=['POST'])
@employee_login_required
def reject_company_request(req_id):
    r = dbm.query_db("SELECT * FROM visit_requests WHERE id = ?", (req_id,), one=True)
    if not r or r['college_id'] != session['college_id']:
        abort(404)
    if r['status'] != 'pending':
        flash('This request has already been answered.', 'warning')
        return redirect(url_for('college_company_requests'))
    note = request.form.get('note', '').strip()
    if not note:
        flash('Please give the company a reason for rejecting.', 'danger')
        return redirect(url_for('college_company_requests'))
    dbm.execute_db("""
        UPDATE visit_requests SET status = 'rejected', college_note = ?, responded_by = ?,
               responded_at = CURRENT_TIMESTAMP WHERE id = ?
    """, (note, session['user_id'], req_id))
    flash('Request rejected and the company has been informed.', 'info')
    return redirect(url_for('college_company_requests'))


# ==========================================================================
# INTERVIEWERS & MOCK INTERVIEWS
#   - A company's HR creates interviewer accounts (Company portal -> Interviewers).
#   - Interviewers log in from the second tab of the Company login page.
#   - Interviewers see a BLIND profile of each student: name, skills, branch,
#     year, projects, certifications and assessment score only. College name,
#     CGPA, SRN, email, phone and photo are never shown, to avoid partiality.
#   - Students book mock interviews from the "Mock Interview" tab and get
#     written feedback afterwards.
# ==========================================================================
MOCK_FOCUS = ['Technical', 'HR', 'Behavioural', 'Mixed']
MOCK_VERDICTS = ['Ready for interviews', 'Almost ready', 'Needs more practice']
MAX_UPCOMING_MOCKS = 2


def _own_interviewer_id(company_id, interviewer_id):
    """Returns interviewer_id only if it belongs to this company and is active."""
    if not interviewer_id:
        return None
    row = dbm.query_db("SELECT id FROM interviewers WHERE id = ? AND company_id = ? AND is_active = 1",
                       (interviewer_id, company_id), one=True)
    return row['id'] if row else None


def blind_profile(student_id):
    """The only student details an interviewer is allowed to see."""
    s = dbm.query_db("SELECT * FROM students WHERE id = ?", (student_id,), one=True)
    if not s:
        return None
    projects = dbm.query_db("""SELECT title, description FROM resume_items
                               WHERE student_id = ? AND kind = 'project' ORDER BY sort_order, id""", (student_id,))
    achievements = dbm.query_db("""SELECT title FROM resume_items
                                   WHERE student_id = ? AND kind = 'achievement' ORDER BY sort_order, id""",
                                (student_id,))
    certs = dbm.query_db("SELECT title FROM certificates WHERE student_id = ? ORDER BY uploaded_at DESC", (student_id,))
    return {
        'id': s['id'],
        'name': s['name'],
        'skills': _split_list(s['skills']),
        'course': s['course'] or '',
        'department': s['department'] or '',
        'year': s['year'] or '',
        'projects': [dict(p) for p in projects],
        'achievements': [a['title'] for a in achievements],
        'certifications': [c['title'] for c in certs],
        'assessment': _student_assessment_pct(s['id']),
    }


# ---------------- Company: manage interviewers ----------------
@app.route('/company/interviewers', methods=['GET', 'POST'])
@company_login_required
def company_interviewers():
    company = current_company()
    if request.method == 'POST':
        f = request.form
        name = f.get('name', '').strip()
        email = f.get('email', '').strip().lower()
        password = f.get('password', '')
        if not all([name, email, password]):
            flash('Name, email and a temporary password are required.', 'danger')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        elif dbm.query_db("SELECT id FROM interviewers WHERE email = ?", (email,), one=True):
            flash('An interviewer with this email already exists.', 'danger')
        else:
            dbm.execute_db("""
                INSERT INTO interviewers (company_id, name, email, password_hash, designation, expertise)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (company['id'], name, email, generate_password_hash(password),
                  f.get('designation', '').strip(), f.get('expertise', '').strip()))
            flash(f'Interviewer account created for {name}. Share the email and password with them — '
                  f'they log in from the Interviewer tab of the Company login page.', 'success')
        return redirect(url_for('company_interviewers'))

    interviewers = dbm.query_db("""
        SELECT i.*,
          (SELECT COUNT(*) FROM mock_slots m WHERE m.interviewer_id = i.id AND m.status = 'completed') AS mocks_done,
          (SELECT COUNT(*) FROM mock_slots m WHERE m.interviewer_id = i.id AND m.status = 'booked') AS mocks_booked,
          (SELECT COUNT(*) FROM interview_schedules s WHERE s.interviewer_id = i.id) AS rounds,
          (SELECT COUNT(*) FROM interview_reports r WHERE r.interviewer_id = i.id) AS evaluations
        FROM interviewers i WHERE i.company_id = ? ORDER BY i.is_active DESC, i.name
    """, (company['id'],))
    return render_template('company_interviewers.html', company=company, interviewers=interviewers)


@app.route('/company/interviewers/<int:iid>/toggle', methods=['POST'])
@company_login_required
def toggle_interviewer(iid):
    iv = dbm.query_db("SELECT * FROM interviewers WHERE id = ?", (iid,), one=True)
    if not iv or iv['company_id'] != session['user_id']:
        abort(404)
    dbm.execute_db("UPDATE interviewers SET is_active = ? WHERE id = ?", (0 if iv['is_active'] else 1, iid))
    flash(f"{iv['name']} {'deactivated' if iv['is_active'] else 'reactivated'}.", 'info')
    return redirect(url_for('company_interviewers'))


@app.route('/company/interviewers/<int:iid>/password', methods=['POST'])
@company_login_required
def reset_interviewer_password(iid):
    iv = dbm.query_db("SELECT * FROM interviewers WHERE id = ?", (iid,), one=True)
    if not iv or iv['company_id'] != session['user_id']:
        abort(404)
    pw = request.form.get('password', '')
    if len(pw) < 6:
        flash('New password must be at least 6 characters.', 'danger')
    else:
        dbm.execute_db("UPDATE interviewers SET password_hash = ? WHERE id = ?", (generate_password_hash(pw), iid))
        flash(f"Password updated for {iv['name']}.", 'success')
    return redirect(url_for('company_interviewers'))


@app.route('/company/interviews/<int:sid>/assign', methods=['POST'])
@company_login_required
def assign_interviewer(sid):
    s = dbm.query_db("SELECT * FROM interview_schedules WHERE id = ?", (sid,), one=True)
    if not s or s['company_id'] != session['user_id']:
        abort(404)
    iid = _own_interviewer_id(session['user_id'], request.form.get('interviewer_id', type=int))
    dbm.execute_db("UPDATE interview_schedules SET interviewer_id = ? WHERE id = ?", (iid, sid))
    flash('Interviewer assigned.' if iid else 'Interviewer removed from this round.', 'info')
    return redirect(url_for('company_interviews'))


# ---------------- Interviewer: login ----------------
@app.route('/company/interviewer/login', methods=['GET', 'POST'])
def interviewer_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        iv = dbm.query_db("SELECT * FROM interviewers WHERE email = ?", (email,), one=True)
        if iv and check_password_hash(iv['password_hash'], password):
            if not iv['is_active']:
                flash('Your interviewer account has been deactivated by your company.', 'danger')
            else:
                session.clear()
                session['role'] = 'interviewer'
                session['user_id'] = iv['id']
                session['company_id'] = iv['company_id']
                flash(f"Welcome, {iv['name']}!", 'success')
                return redirect(url_for('interviewer_home'))
        else:
            flash('Incorrect email or password.', 'danger')
    return render_template('company_login.html', active_tab='interviewer')


# ---------------- Interviewer: portal ----------------
@app.route('/interviewer/home')
@interviewer_login_required
def interviewer_home():
    iv = current_interviewer()
    today = date.today().isoformat()
    booked = dbm.query_db("""SELECT * FROM mock_slots WHERE interviewer_id = ? AND status = 'booked'
                             ORDER BY slot_date, start_time""", (iv['id'],))
    open_slots = dbm.query_db("""SELECT * FROM mock_slots WHERE interviewer_id = ? AND status = 'open'
                                 AND slot_date >= ? ORDER BY slot_date, start_time""", (iv['id'], today))
    rounds = dbm.query_db("""
        SELECT s.*, jp.title AS job_title FROM interview_schedules s
        JOIN visit_requests vr ON vr.id = s.visit_request_id JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE s.interviewer_id = ? AND s.status = 'scheduled' ORDER BY s.interview_date
    """, (iv['id'],))
    stats = {
        'booked': len(booked),
        'open': len(open_slots),
        'done': dbm.query_db("SELECT COUNT(*) AS c FROM mock_slots WHERE interviewer_id = ? AND status = 'completed'",
                             (iv['id'],), one=True)['c'],
        'rounds': len(rounds),
    }
    profiles = {m['id']: blind_profile(m['student_id']) for m in booked}
    return render_template('interviewer_home.html', iv=iv, booked=booked, open_slots=open_slots,
                           rounds=rounds, stats=stats, profiles=profiles, today=today)


@app.route('/interviewer/mock', methods=['GET', 'POST'])
@interviewer_login_required
def interviewer_mock():
    iv = current_interviewer()
    if request.method == 'POST':
        f = request.form
        slot_date, start = f.get('slot_date'), f.get('start_time')
        if not slot_date or not start:
            flash('Date and start time are required.', 'danger')
        elif slot_date < date.today().isoformat():
            flash('Pick a date from today onwards.', 'danger')
        else:
            focus = f.get('focus') if f.get('focus') in MOCK_FOCUS else 'Technical'
            repeat = max(1, min(4, f.get('repeat', type=int) or 1))
            d0 = parse_date(slot_date)
            from datetime import timedelta
            for k in range(repeat):
                dbm.execute_db("""
                    INSERT INTO mock_slots (interviewer_id, slot_date, start_time, end_time, focus, topics, mode,
                                            meeting_link, venue)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (iv['id'], (d0 + timedelta(days=7 * k)).isoformat(), start, f.get('end_time') or None, focus,
                      f.get('topics', '').strip(), f.get('mode', 'Online'), f.get('meeting_link', '').strip(),
                      f.get('venue', '').strip()))
            flash(f'{repeat} mock interview slot{"s" if repeat > 1 else ""} published for students.', 'success')
        return redirect(url_for('interviewer_mock'))

    slots = dbm.query_db("""
        SELECT m.*, fb.verdict FROM mock_slots m LEFT JOIN mock_feedback fb ON fb.slot_id = m.id
        WHERE m.interviewer_id = ? ORDER BY m.slot_date DESC, m.start_time
    """, (iv['id'],))
    today = date.today().isoformat()
    groups = {
        'booked': sorted([m for m in slots if m['status'] == 'booked'], key=lambda m: (m['slot_date'], m['start_time'])),
        'open': sorted([m for m in slots if m['status'] == 'open' and m['slot_date'] >= today],
                       key=lambda m: (m['slot_date'], m['start_time'])),
        'past': [m for m in slots if m['status'] in ('completed', 'cancelled', 'no-show')
                 or (m['status'] == 'open' and m['slot_date'] < today)],
    }
    profiles = {m['id']: blind_profile(m['student_id']) for m in slots if m['student_id']}
    return render_template('interviewer_mock.html', iv=iv, groups=groups, profiles=profiles,
                           focus_options=MOCK_FOCUS, today=today)


def _my_slot(slot_id):
    m = dbm.query_db("SELECT * FROM mock_slots WHERE id = ?", (slot_id,), one=True)
    if not m or m['interviewer_id'] != session['user_id']:
        abort(404)
    return m


@app.route('/interviewer/mock/<int:slot_id>/cancel', methods=['POST'])
@interviewer_login_required
def interviewer_cancel_slot(slot_id):
    m = _my_slot(slot_id)
    if m['status'] not in ('open', 'booked'):
        flash('This slot can no longer be cancelled.', 'warning')
    else:
        reason = request.form.get('reason', '').strip()
        if m['status'] == 'booked' and not reason:
            flash('A student has booked this slot — please give them a reason.', 'danger')
            return redirect(url_for('interviewer_mock'))
        dbm.execute_db("UPDATE mock_slots SET status = 'cancelled', cancel_reason = ? WHERE id = ?", (reason, slot_id))
        flash('Slot cancelled.', 'info')
    return redirect(url_for('interviewer_mock'))


@app.route('/interviewer/mock/<int:slot_id>', methods=['GET', 'POST'])
@interviewer_login_required
def interviewer_mock_session(slot_id):
    iv = current_interviewer()
    m = _my_slot(slot_id)
    if not m['student_id']:
        flash('Nobody has booked this slot yet.', 'warning')
        return redirect(url_for('interviewer_mock'))
    feedback = dbm.query_db("SELECT * FROM mock_feedback WHERE slot_id = ?", (slot_id,), one=True)

    if request.method == 'POST':
        f = request.form
        if f.get('action') == 'no-show':
            if m['status'] == 'booked':
                dbm.execute_db("UPDATE mock_slots SET status = 'no-show' WHERE id = ?", (slot_id,))
                flash('Marked as no-show.', 'info')
            return redirect(url_for('interviewer_mock'))
        if feedback:
            flash('Feedback was already submitted for this mock interview.', 'warning')
            return redirect(url_for('interviewer_mock_session', slot_id=slot_id))
        verdict = f.get('verdict')
        if verdict not in MOCK_VERDICTS:
            flash('Choose an overall verdict.', 'danger')
            return redirect(url_for('interviewer_mock_session', slot_id=slot_id))
        if not f.get('improvements', '').strip():
            flash('Tell the student at least one thing to improve.', 'danger')
            return redirect(url_for('interviewer_mock_session', slot_id=slot_id))

        def _r(k):
            v = f.get(k, type=int)
            return v if v and 1 <= v <= 5 else None
        dbm.execute_db("""
            INSERT INTO mock_feedback (slot_id, interviewer_id, student_id, technical, communication, problem_solving,
                                       confidence, verdict, strengths, improvements, resources)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (slot_id, iv['id'], m['student_id'], _r('technical'), _r('communication'), _r('problem_solving'),
              _r('confidence'), verdict, f.get('strengths', '').strip(), f.get('improvements', '').strip(),
              f.get('resources', '').strip()))
        dbm.execute_db("UPDATE mock_slots SET status = 'completed' WHERE id = ?", (slot_id,))
        flash('Feedback sent to the student.', 'success')
        return redirect(url_for('interviewer_mock'))

    history = dbm.query_db("""
        SELECT fb.verdict, m.slot_date, m.focus FROM mock_feedback fb JOIN mock_slots m ON m.id = fb.slot_id
        WHERE fb.student_id = ? AND fb.slot_id != ? ORDER BY m.slot_date DESC
    """, (m['student_id'], slot_id))
    return render_template('interviewer_mock_session.html', iv=iv, m=m, p=blind_profile(m['student_id']),
                           feedback=feedback, history=history, verdicts=MOCK_VERDICTS)


@app.route('/interviewer/campus')
@interviewer_login_required
def interviewer_campus():
    iv = current_interviewer()
    rounds = dbm.query_db("""
        SELECT s.*, jp.title AS job_title, jp.required_skills, vr.company_visit_id,
               (SELECT COUNT(*) FROM interview_reports r WHERE r.schedule_id = s.id) AS evaluated
        FROM interview_schedules s
        JOIN visit_requests vr ON vr.id = s.visit_request_id JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE s.interviewer_id = ? ORDER BY s.interview_date DESC
    """, (iv['id'],))
    counts = {}
    for r in rounds:
        counts[r['id']] = len(dbm.query_db("SELECT id FROM applications WHERE company_id = ?",
                                           (r['company_visit_id'],))) if r['company_visit_id'] else 0
    return render_template('interviewer_campus.html', iv=iv, rounds=rounds, counts=counts)


@app.route('/interviewer/campus/<int:sid>', methods=['GET', 'POST'])
@interviewer_login_required
def interviewer_round(sid):
    iv = current_interviewer()
    s = dbm.query_db("""
        SELECT s.*, jp.title AS job_title, jp.required_skills, jp.id AS job_post_id, vr.company_visit_id,
               vr.college_id, vr.id AS vr_id
        FROM interview_schedules s
        JOIN visit_requests vr ON vr.id = s.visit_request_id JOIN job_posts jp ON jp.id = vr.job_post_id
        WHERE s.id = ?""", (sid,), one=True)
    if not s or s['interviewer_id'] != iv['id']:
        abort(404)
    applicant_ids = [r['student_id'] for r in dbm.query_db(
        "SELECT student_id FROM applications WHERE company_id = ?", (s['company_visit_id'],))] \
        if s['company_visit_id'] else []

    if request.method == 'POST':
        f = request.form
        sid_ = f.get('student_id', type=int)
        result = f.get('result')
        reason = f.get('rejection_reason', '').strip()
        if sid_ not in applicant_ids:
            flash('Pick a candidate from this round.', 'danger')
        elif result not in INTERVIEW_RESULTS:
            flash('Choose a result.', 'danger')
        elif result == 'Not Selected' and not reason:
            flash('Please enter the reason the candidate was not selected.', 'danger')
        elif dbm.query_db("SELECT id FROM interview_reports WHERE schedule_id = ? AND student_id = ?",
                          (sid, sid_), one=True):
            flash('You have already evaluated this candidate in this round.', 'warning')
        else:
            st = dbm.query_db("SELECT * FROM students WHERE id = ?", (sid_,), one=True)

            def _r(k):
                v = f.get(k, type=int)
                return v if v and 1 <= v <= 5 else None
            # The company's hiring report gets the full student record; the
            # interviewer only ever saw the blind profile.
            dbm.execute_db("""
                INSERT INTO interview_reports
                    (company_id, visit_request_id, college_id, job_post_id, schedule_id, student_id, student_name,
                     srn, student_email, course, department, year, cgpa, round_name, interview_date, interviewer,
                     technical_rating, communication_rating, aptitude_rating, result, package_offered,
                     rejection_reason, remarks, interviewer_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (iv['company_id'], s['vr_id'], s['college_id'], s['job_post_id'], sid, st['id'], st['name'],
                  st['srn'], st['email'], st['course'], st['department'], st['year'], st['cgpa'], s['round_name'],
                  s['interview_date'], iv['name'], _r('technical_rating'), _r('communication_rating'),
                  _r('aptitude_rating'), result, '', reason if result != 'Selected' else '',
                  f.get('remarks', '').strip(), iv['id']))
            flash(f"Evaluation saved for {st['name']}. It now appears in your company's hiring report.", 'success')
        return redirect(url_for('interviewer_round', sid=sid))

    done = {r['student_id']: r for r in dbm.query_db(
        "SELECT * FROM interview_reports WHERE schedule_id = ? AND student_id IS NOT NULL", (sid,))}
    candidates = [blind_profile(x) for x in applicant_ids]
    candidates = [c for c in candidates if c]
    candidates.sort(key=lambda c: (c['id'] in done, c['name']))
    return render_template('interviewer_round.html', iv=iv, s=s, candidates=candidates, done=done,
                           required=_split_list(s['required_skills']), results=INTERVIEW_RESULTS)


# ---------------- Student: Mock Interview tab ----------------
@app.route('/mock-interview')
@student_login_required
def mock_interview():
    student = current_student()
    today = date.today().isoformat()
    focus = request.args.get('focus', '')
    q = """
        SELECT m.*, i.name AS interviewer_name, i.designation, i.expertise, c.name AS company_name
        FROM mock_slots m JOIN interviewers i ON i.id = m.interviewer_id JOIN companies c ON c.id = i.company_id
        WHERE m.status = 'open' AND m.slot_date >= ? AND i.is_active = 1
    """
    args = [today]
    if focus in MOCK_FOCUS:
        q += " AND m.focus = ?"
        args.append(focus)
    open_slots = dbm.query_db(q + " ORDER BY m.slot_date, m.start_time", tuple(args))
    mine = dbm.query_db("""
        SELECT m.*, i.name AS interviewer_name, i.designation, c.name AS company_name, fb.id AS fb_id,
               fb.technical, fb.communication, fb.problem_solving, fb.confidence, fb.verdict, fb.strengths,
               fb.improvements, fb.resources
        FROM mock_slots m JOIN interviewers i ON i.id = m.interviewer_id JOIN companies c ON c.id = i.company_id
        LEFT JOIN mock_feedback fb ON fb.slot_id = m.id
        WHERE m.student_id = ? ORDER BY m.slot_date DESC, m.start_time DESC
    """, (student['id'],))
    upcoming = [m for m in mine if m['status'] == 'booked']
    upcoming.sort(key=lambda m: (m['slot_date'], m['start_time']))
    past = [m for m in mine if m['status'] != 'booked']
    rated = [m for m in past if m['fb_id']]
    avg = {}
    for k in ('technical', 'communication', 'problem_solving', 'confidence'):
        vals = [m[k] for m in rated if m[k]]
        avg[k] = round(sum(vals) / len(vals), 1) if vals else None
    return render_template('mock_interview.html', student=student, open_slots=open_slots, upcoming=upcoming,
                           past=past, avg=avg, completed=len(rated), focus=focus, focus_options=MOCK_FOCUS,
                           preview=blind_profile(student['id']), can_book=len(upcoming) < MAX_UPCOMING_MOCKS,
                           max_upcoming=MAX_UPCOMING_MOCKS)


@app.route('/mock-interview/<int:slot_id>/book', methods=['POST'])
@student_login_required
def book_mock(slot_id):
    student = current_student()
    upcoming = dbm.query_db("SELECT id FROM mock_slots WHERE student_id = ? AND status = 'booked'", (student['id'],))
    if len(upcoming) >= MAX_UPCOMING_MOCKS:
        flash(f'You can have at most {MAX_UPCOMING_MOCKS} upcoming mock interviews. Finish or cancel one first.',
              'warning')
        return redirect(url_for('mock_interview'))
    target_role = request.form.get('target_role', '').strip()
    if not target_role:
        flash('Tell the interviewer which role you are preparing for.', 'danger')
        return redirect(url_for('mock_interview'))
    # Atomic claim: only succeeds if the slot is still open.
    db = dbm.get_db()
    cur = db.execute("""
        UPDATE mock_slots SET status = 'booked', student_id = ?, target_role = ?, student_topics = ?,
               student_note = ?, booked_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'open' AND slot_date >= ?
    """, (student['id'], target_role, request.form.get('student_topics', '').strip(),
          request.form.get('student_note', '').strip(), slot_id, date.today().isoformat()))
    db.commit()
    if cur.rowcount:
        flash('Mock interview booked! The join details are in "My upcoming mock interviews".', 'success')
    else:
        flash('Sorry, that slot was just taken. Pick another one.', 'warning')
    return redirect(url_for('mock_interview'))


@app.route('/mock-interview/<int:slot_id>/cancel', methods=['POST'])
@student_login_required
def cancel_mock(slot_id):
    m = dbm.query_db("SELECT * FROM mock_slots WHERE id = ?", (slot_id,), one=True)
    if not m or m['student_id'] != session['user_id']:
        abort(404)
    if m['status'] == 'booked':
        dbm.execute_db("""UPDATE mock_slots SET status = 'open', student_id = NULL, target_role = NULL,
                          student_topics = NULL, student_note = NULL, booked_at = NULL WHERE id = ?""", (slot_id,))
        flash('Booking cancelled — the slot is open for others again.', 'info')
    return redirect(url_for('mock_interview'))


# --------------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------------
if __name__ == '__main__':
    dbm.init_db_schema()
    app.run(debug=True)
