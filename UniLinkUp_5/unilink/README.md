# UniLinkUp — From Campus Learning to Career Launch

UniLinkUp is a full-stack campus placement portal connecting students,
faculty, colleges and companies. Students build a verified skill profile
with a profile picture, see a live Eligibility Match % for every campus
drive, get a real Skill Gap Analysis and an offline resume ATS score, build
a resume straight from their own profile data (or upload one) and download
it as PDF/DOCX/TXT, take timed skill assessments, and can book or request
1-on-1 and group mentor classes with faculty, ask academic doubts, message a
mentor directly, practice with flashcards, log private study hours, and see
real placed-peer stories; faculty offer time slots (approving or declining
student requests), run their own custom timed tests, answer doubts and
messages, and notify their students about classes; colleges track student
readiness and a combined student directory, manage drives, verify and share
student resumes with companies by email or link/Drive, and curate the Peer
Reference wall from one dashboard; an in-app
assistant answers common questions across all three roles.

---

## 1. Tech stack

| Layer          | Choice                          | Why |
|----------------|----------------------------------|-----|
| Language       | Python 3                         | Simple, widely supported |
| Web framework  | Flask                            | Lightweight, minimal boilerplate |
| Database       | SQLite via Python's built-in `sqlite3` | Zero setup — a single file, no separate database server |
| Frontend       | Server-rendered HTML + Jinja2 + Bootstrap 5 | No separate frontend build step; modern and fully responsive |
| Auth           | `werkzeug.security` password hashing + Flask `session` cookies | Simple and secure enough for this scale |
| File uploads   | Flask's built-in file handling  | Certificates/documents/resumes/profile pictures saved to `/uploads` |
| Resume parsing | `pypdf` (PDF) + `python-docx` (DOCX) | Extract resume text locally so the ATS scorer never needs an external API |
| Resume generation | `reportlab` (PDF) + `python-docx` (DOCX) + plain text | Build a downloadable resume from a student's own profile data, entirely offline |
| Resume email delivery | Python's built-in `smtplib` | Only sends for real if `SMTP_HOST` is configured (see §5); otherwise the share is honestly logged, never faked |
| Resume link/Drive sharing | Built-in shareable link (no setup), optionally real Google Drive via `google-api-python-client` | Always works out of the box; upgrades to a real Drive upload only if you configure a service account (see §5) |

**No external/paid services are used anywhere** — the ATS resume score is a
transparent, offline heuristic (see §5), not a call to a third-party API.

---

## 2. Project structure

```
unilink/
│
├── app.py                 # All routes / business logic (the "backend")
├── db.py                  # Tiny sqlite3 wrapper: schema + query helpers
├── chatbot.py              # Offline FAQ + data-aware assistant engine
├── seed.py                # Populates demo data (colleges, questions, drives)
├── requirements.txt
├── unilink.db              # Created automatically — the database file
│
├── templates/             # All HTML pages (Jinja2)
│   ├── base.html           # Shared layout + navigation
│   ├── index.html          # Public landing page
│   ├── about.html
│   ├── login.html / register_student.html
│   ├── college_login.html / register_college.html
│   ├── student_home.html   # Companies visiting campus
│   ├── profile.html        # Info, progress bar, snapshot, profile picture,
│   │                       #   certificates, documents, resume + ATS score,
│   │                       #   verification badge, share history
│   ├── resume_builder.html # Student: build a resume from profile data +
│   │                       #   experience/projects/achievements, export it
│   ├── college_resumes.html    # College: verify/reject a resume, share a
│   │                       #   verified one by email or as a shareable link
│   ├── shared_resume.html  # Public: the page a "share a link" URL opens to
│   ├── skill_enhancement.html  # Student: skill gap analysis, book/request a
│   │                       #   class, placed-peer stories
│   ├── ask_faculty.html    # Student: post a doubt + message a mentor
│   ├── message_thread.html # Shared: one student ↔ one faculty chat thread
│   ├── flashcards.html     # Student: tap-to-flip MCQ practice game
│   ├── learning_hours.html # Student: private self-study hour log
│   ├── assessment_home.html / assessment_take.html / assessment_result.html
│   ├── college_home.html   # Add/manage company drives
│   ├── college_peer_wall.html  # College: add/remove placed-student profiles
│   ├── student_tracker.html
│   ├── student_list.html   # College: student directory + placement readiness
│   │                       #   (progress bar, best score, certificates) together
│   ├── help.html            # Student: raise a support query
│   ├── college_helpdesk.html    # College: view/resolve student queries
│   ├── college_notifications.html  # College: compose + send notifications
│   ├── faculty_login.html / register_faculty.html
│   ├── faculty_home.html    # Faculty: upcoming classes, stats, notify students
│   ├── faculty_slots.html   # Faculty: offer slots, approve/decline requests
│   ├── faculty_progress.html  # Faculty: readiness of their own mentees
│   ├── faculty_tests.html   # Faculty: build a custom MCQ test
│   ├── faculty_test_results.html  # Faculty: see attempts on one test
│   └── faculty_doubts.html  # Faculty: answer doubts + reply to messages
│
├── static/
│   ├── css/style.css       # All custom styling
│   ├── js/                 # Searchable dropdown, entrance animations, chat
│   │                       #   widget, bell-icon notifications
│   └── img/                 # Illustrations + the original logo mark (own
│                             #   design — no third-party assets)
└── uploads/                # Uploaded certificates, documents, resumes &
    │                       #   profile pictures land here
    ├── certificates/
    ├── documents/
    ├── resumes/
    └── profile_pictures/
```

---

## 3. How to run it

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate

# 2. Install the only dependency
pip install -r requirements.txt

# 3. Load demo data (colleges, one demo college with sample drives, and
#    assessment questions)
python seed.py

# 4. Run the app
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

### Demo logins already seeded for you
Every login page (Student, Faculty, College) shows its own demo credentials
in an info box with a **Use Demo Account** button that fills the form for
you — no need to remember these by hand:
- **Student:** `student@reva.edu.in` / `student123` (Demo Student, REVA
  University, profile pre-filled with CGPA and skills so eligibility match %
  and skill-gap analysis show real numbers immediately; the Resume Builder
  already has sample Experience/Project/Achievement entries and one
  generated resume that's already been verified by the demo college, plus a
  logged share to a demo company, so the full verify-and-share flow is
  visible without doing anything first)
- **Faculty mentor:** `faculty@reva.edu.in` / `faculty123` (Dr. Ramesh Iyer,
  REVA University, with 3 open class slots already offered — one a 5-seat
  group class)
- **College / Placement officer:** `officer@reva.edu.in` / `officer123`
  (college: "REVA University", with sample drives already added)
- **Company / Recruiter:** `hr@nimbustech.com` / `company123` (Nimbus
  Technologies, with two job drives, one approved REVA visit with a
  scheduled interview and two hiring-report entries, and one request still
  pending so the college can approve or reject it)

- **Interviewer:** `arjun@nimbustech.com` / `interviewer123` (Nimbus
  Technologies panel member — use the **Interviewer** tab on the Company
  login page; has open mock slots, a booked mock interview and a campus round
  with two candidates). A second interviewer, `meera@nimbustech.com`, uses
  the same password.
- **Second student:** `aisha@reva.edu.in` / `student123` (applicant to the
  Nimbus drive, so the interviewer's campus round has someone to evaluate)

> Already have a `unilink.db` from an older version? Just run `python seed.py`
> again — new tables are created automatically and the demo company is added.

---

## 4. How the database is designed

Tables, created automatically by `db.py` the first time you run the app:

- `colleges` — name, established year, official email, password
- `employees` — placement-cell staff, linked to a college
- `students` — name, SRN, section, course, department, year, semester, CGPA, email, password, skills, linked
  college, an uploaded profile picture (shown on the profile page, falls back to an initial-letter avatar
  when none is set), and a short resume-builder summary line
- `company_visits` — company name, role, description, registration window, eligibility criteria (min CGPA, eligible courses/years, required skills, package), linked college
- `applications` — join table: which student applied to which company drive
- `certificates` / `documents` — uploaded files, linked to a student
- `questions` — the MCQ bank for skill assessment (category: aptitude / interview)
- `assessment_results` — every practice/main attempt's score, linked to a student
- `chat_messages` — a best-effort log of assistant conversations
- `support_tickets` — a student's Help Desk query (category, subject, message, open/resolved), linked to their college
- `notifications` — a message a college sends (manual, or an automatic drive reminder)
- `notification_recipients` — which students got a given notification, and whether they've read it
- `faculty` — mentor account, linked to a college (name, email, password, department, expertise, bio)
- `faculty_slots` — a time slot a faculty member offers (date, start/end time, topic, meeting link, seat
  capacity — 1 for one-on-one, more for a group class; status flips to `cancelled` with a mandatory
  reason when a faculty member cancels a class that already has students booked into it)
- `appointments` — a student's booking/enrollment in a slot (status: upcoming/cancelled, with a
  cancellation reason recorded when the faculty member — not the student — is the one who cancelled it);
  a slot stays bookable by other students until its seat capacity is reached
- `resumes` — every resume a student uploads *or* generates with the Resume Builder (`source`:
  `uploaded`/`builder`), with its computed ATS score and feedback, plus a mandatory verification workflow:
  `verification_status` (`pending`/`verified`/`rejected`), which college employee verified it and when, and
  and, when rejected, a mandatory `verification_note` (reason) and `verification_suggestion` (how to improve
  it) — a resume can only be shared with a company once verified;
  `share_token` is the unguessable id in its public `/shared-resume/<token>` link, minted the first time it's
  shared as a link and reused for every share after that
- `resume_items` — one row per Experience / Project / Achievement entry (`kind`) a student adds in the
  Resume Builder (title, organization, duration, description), pulled live into every resume they generate
- `resume_shares` — a log of every time a college shares a student's *verified* resume with a company, either
  by `method = 'email'` (company name/email, optional message, which employee sent it, `status`: `sent` when
  real SMTP delivery succeeded, `logged` when it didn't) or `method = 'drive'` (optional company name,
  `share_url` holding the link that was generated, `status`: `sent` for a real Google Drive upload, `logged`
  for the built-in fallback link — see §5) — visible on both the student's profile and the college's Resumes
  page
- `slot_requests` — a student's request for a class on a specific skill from a specific faculty member
  (skill, best-effort matched company, optional message, status: pending/approved/declined, the faculty's
  proposed date/time/meeting link, or — for a decline — a mandatory reason plus a mandatory alternate date
  for another class the student can join instead) — approving one creates a `faculty_slots` +
  `appointments` row automatically
- `faculty_tests` / `faculty_test_questions` / `faculty_test_attempts` — a custom MCQ test a faculty
  member builds (mirrors the shape of `questions`/`assessment_results` so the same take/submit flow can
  serve both), visible to every student at that faculty's college, with per-student attempt history
- `doubts` — a student's academic question tagged to a department (subject, message, an optional
  attached image, status: open/answered, which faculty answered it, their reply, and an optional
  attached image on the answer) — any faculty in that department can answer
- `messages` — a simple chat log between one student and one faculty member (sender role, body, read
  state) — a thread is just every row sharing that (student, faculty) pair
- `learning_logs` — a student's private self-reported study session (activity, hours, date, notes) —
  never surfaced to faculty or college accounts, only ever queried by `student_id = session['user_id']`
- `peer_references` — a placed student's profile a placement officer adds (company, role, package, CGPA,
  skills, projects, a line of advice), shown to current students at the same college
- `interview_experiences` — a student's own writeup posted right after an interview at a real drive
  (company, role, outcome, difficulty, rounds, the questions asked and tips), scoped to and visible only
  within their own college; the author can delete their own post

Students pick a college at registration so the college dashboards (tracker /
progress / student list) know which students belong to which college.

---

## 5. Feature overview

- **Navigation** — `templates/base.html` renders a different nav bar depending
  on the signed-in role: Home, Skill Assessment, My Profile, Skill
  Enhancement, Ask Faculty, Help, About Us and a notifications bell for
  students; Home, Slots, Student Progress, Create Test, Doubts & Messages and
  a bell (upcoming classes) for faculty; Home, Student Tracker, Students
  (directory + placement readiness together), Help Desk, Notify Students,
  Peer Wall, Resumes (verify/reject student resumes and share verified ones
  by email or as a shareable link) and a bell for colleges.
- **Logo** — an original two-ring "link" mark drawn as inline SVG
  (`static/img/logo-mark.svg`, also used as the favicon) — no third-party
  icon set or stock artwork, so it's free to reuse and re-theme.
- **Help & Support** — a student can raise a query from **Help** (category +
  subject + description); it lands on their placement cell's **Help Desk**
  page, which lists every query (newest / unresolved first) and can mark one
  resolved or reopen it. A "Need help?" shortcut also sits right on the
  student's own Home page, and the public landing page calls the feature out
  too, so it isn't only reachable from the nav bar.
- **Notifications** — a college can message its students two ways: a
  one-click **Send Reminder** button next to any drive on College Home
  (auto-targets only the students who haven't applied yet), or a full
  **Notify Students** composer. The composer groups every student by
  **Department** and then **Course** with a "Select department" shortcut per
  group, plus Department/Course filter dropdowns and Select/Deselect
  visible — so a message can go to, say, only "Computer Science" or only
  "B.Tech CSE" students. Both paths land in the recipient's notification bell.
- **Notification bell** — every logged-in page shows a bell icon that polls
  `/api/notifications/summary`. For students it lists notifications from
  their college and clears the unread badge once opened; for college staff
  it lists open Help Desk queries and links straight to the Help Desk.
- **Forgot password** — no email server is configured on this build, so
  identity is verified against a second fact already on file instead of an
  emailed link: students confirm their email + SRN, placement officers
  confirm their own email + their college's registered official email. Once
  verified, a one-time session flag (`reset_role` / `reset_user_id`, cleared
  the moment the password is changed) unlocks a **Set a New Password**
  form — see `forgot_password()` / `college_forgot_password()` /
  `reset_password()` in `app.py`.
- **Student registration** — Name, SRN, Section, Course, Department, Year,
  Semester, CGPA, Skills, Mail ID, Password, and a searchable College
  dropdown. Department is a fixed dropdown (Computer Science, Information
  Science, Mechanical, MBA, etc.) kept separate from the free-text Course
  field (e.g. "B.Tech CSE") so students can be grouped and targeted by
  either axis.
- **Companies visiting campus** — `student_home.html` reads `company_visits`
  for the student's linked college and shows company name, description,
  registration window, package, and a live Eligibility Match % — with
  "Apply Now" disabled automatically once the window closes.
- **Eligibility Match %** — every drive can carry eligibility criteria (min
  CGPA, eligible branches/years, required skills). `eligibility_match()` in
  `app.py` blends those against a student's profile and best assessment score
  into a 0–100% score plus a hard eligible/not-eligible verdict, shown as a
  color-coded ring with a line-by-line breakdown to both the student and the
  college (per-applicant on the Student Tracker, and a per-drive summary on
  the College Home page).
- **Skill assessment** — a question bank of aptitude + interview questions.
  - **Practice session:** unlimited attempts, scored instantly but not
    counted toward the official record.
  - **Main assessment:** one scored attempt at a time, saved permanently —
    the best score shows up on the student's profile and the college's
    dashboard.
  - **Faculty-created tests** (see below) use the exact same take/submit page.
  - **Timed:** every one of those three — Practice, Main, and a faculty's own
    custom test — gives 90 seconds per question (a visible `mm:ss` countdown
    that turns red under 30 seconds and auto-submits whatever's answered so
    far when it hits zero). **Flashcards are deliberately excluded** — they're
    an untimed, tap-to-flip practice tool, not a scored test.
- **My Profile** — all filled-in info, an editable section (course/year/
  semester/CGPA/skills), a **profile picture** upload (shown as a circular
  photo at the top of the page, or an initial-letter avatar until one is
  set), a **Your Snapshot** card, certificate upload + list, document upload
  + list, a **Resume & ATS Score** card, and assessment history and overall
  progress bar.
  - Progress formula (see `overall_progress()` in `app.py`): 40% profile
    completeness + 30% for having attempted the main assessment + 30% for
    certificates uploaded (capped at 3).
  - **Your Snapshot** (`student_percentile()` in `app.py`) — CGPA plus an
    honest CGPA percentile within the student's own college (only shown once
    at least 3 peers have a CGPA on file, so it never claims a meaningless
    "ahead of 100%"), skills listed, certificates on file, and best
    assessment score — a quick, data-backed reason to keep the profile up to
    date.
  - **Resume & ATS Score** (`extract_resume_text()` + `ats_score()` in
    `app.py`) — upload a PDF/DOC/DOCX/TXT resume and get an instant, fully
    offline score out of 100, broken down across contact info, section
    coverage (education/experience/skills), how many of the student's own
    profile skills actually appear in the resume text, action-verb usage,
    length, and formatting — each deduction comes with a concrete, actionable
    tip so a student can work toward 90+. Every re-upload is scored fresh and
    kept in a "Previous Uploads" history. A verification badge (Verified /
    Rejected / Awaiting verification) sits right above it — see **Resume
    Builder & verification** below.
- **Resume Builder** (`/student/resume-builder`) — rather than only accepting
  an uploaded file, a student can build a resume straight from their own
  data: name, email, course/department/CGPA and skills are pulled live from
  their profile (edit the profile and the next resume picks it up
  automatically), plus an editable professional-summary line and any number
  of **Experience**, **Project**, and **Achievement** entries they add and
  remove themselves. Generating it produces a real file — **PDF**
  (`reportlab`), **Word `.docx`** (`python-docx`), or **plain `.txt`** — and
  also runs it straight through the same offline ATS scorer as an uploaded
  resume, so builder-made and uploaded resumes are scored identically and
  live in the same "Previous Uploads" list. Every resume — uploaded or
  built — starts out **unverified**.
- **Resume verification & sharing (mandatory gate)** — a resume cannot be
  shared with a company until a placement officer explicitly verifies it
  from the college's **Resumes** page. Verifying stamps a visible sign on
  *both* portals: the student sees "Verified by your placement cell" right
  on their profile, and the college's Resumes list shows the same badge plus
  who verified it and when. **Rejecting requires two mandatory fields** — a
  reason the resume was rejected and a concrete suggestion for how to
  improve it — enforced server-side (`reject_resume()` in `app.py`) so a
  rejection can never leave a student with nothing actionable; both show up
  on the student's own profile and on the college's Resumes list. Only once
  a resume is verified does the college's UI
  even offer the **Share with a company** forms — and both share routes
  below independently re-check verification status server-side and refuse a
  pending or rejected resume regardless of what's submitted, so the rule
  can't be bypassed from the browser. A college can share a verified resume
  two ways, picked from tabs on the same form:
  - **Email it** (company name + email + optional message) — sent for real
    only if `SMTP_HOST` (and friends) are configured in the environment; if
    not, the share is still recorded honestly with `status = 'logged'`
    rather than the app pretending an email went out. To enable real
    delivery, set `SMTP_HOST`, `SMTP_PORT` (defaults to 587), `SMTP_USER`,
    `SMTP_PASS`, and `SMTP_FROM` before running `python app.py`.
  - **Share a link / Drive** (optional company name, for your own records)
    — generates a link the college can copy and hand to a company however
    they like (paste into an email, WhatsApp, or their own Drive folder). If
    `GOOGLE_SERVICE_ACCOUNT_FILE` (path to a Google Cloud service account's
    JSON key) and `GOOGLE_DRIVE_FOLDER_ID` (a Drive folder shared with that
    service account's email, with Editor access) are both configured, the
    resume is actually uploaded to that Drive folder and the real Drive
    "anyone with the link" URL is shared (`status = 'sent'`). Otherwise it
    falls back to a UniLinkUp-hosted link (`/shared-resume/<token>`) that
    works the same way — open it with no login and view or download the
    resume — and the share is recorded as `status = 'logged'` so it's clear
    no real Drive upload happened. Setting up the optional real upload needs
    the `google-api-python-client` and `google-auth` packages (`pip install
    google-api-python-client google-auth`) — they aren't required for the
    rest of the app and aren't in `requirements.txt` by default.

  Every share — either method — shows up in a "Shared With Companies" list
  on the student's own profile and a "Recent Shares" list on the college's
  Resumes page, each row honestly labeled Sent / Logged / Uploaded to Drive
  / Link generated.
- **Skill Enhancement** — `skill_gap_analysis()` in `app.py` compares a
  student's own skills against the `required_skills` actually being asked
  for across every live company drive at their college (never a generic or
  invented checklist), ranks the biggest gaps and existing strengths, and
  derives a coarse assessment-readiness badge. From the same page a student
  can:
  - **Join an open class** — every slot shows how many seats are taken out
    of its capacity; a one-seat slot is a private 1-on-1, a multi-seat slot
    is a group class other students can see filling up and join too.
  - **Request a class** — pick a faculty mentor and the skill they want to
    learn (optionally pre-filled from their own skill gaps); `app.py`'s
    `match_company_for_skill()` best-effort-matches it to a live company
    drive that actually asks for that skill, so the faculty member sees
    *why* the student needs it, not just that they do. The faculty then
    approves it with a date/time/meeting link (creating a slot + booking
    automatically) or declines it — declining requires both a reason and a
    date for another class the student can join instead, so a decline is
    never a dead end. Both outcomes show up on the student's own Skill
    Enhancement page.
  - **See Placed Peers** — real profiles from the college's Peer Reference
    wall (below), so "get inspired" is backed by actual stories, not
    fabricated ones.
- **Faculty role** — a third login alongside Student and College.
  - **Register/Login** — a faculty member joins an existing college (like a
    placement officer) with name, department, expertise and an optional bio.
  - **Home** — upcoming classes, open slot count, mentee count, pending
    request count, and a **Notify Students** form to message everyone who's
    booked with them, or only the students in one specific class.
  - **Slots** — pending class requests to approve/decline sit at the top;
    below, offer a new slot (date, start/end time, optional topic, seat
    capacity, optional meeting link) that instantly becomes bookable by
    students at the same college; remove any slot with zero bookings, or
    **Cancel Class** on one that already has students booked into it
    (including one created by approving a request) — a reason is required,
    and every booked student is immediately notified with it.
  - **Student Progress** — readiness (CGPA/year/course, best assessment
    score, certificates, overall progress) scoped to only the students who
    have actually booked a class with that faculty member, not the whole
    college roster.
  - **Create Test** — build a custom MCQ test (title + any number of
    questions, each with 4 options and the correct one marked) that's
    instantly visible to every student at the same college under their own
    Skill Assessment page; a Results link shows every attempt and score.
  - **Doubts & Messages** — open academic doubts from their own department
    (any question a student hasn't tagged to a department falls back to
    visible-to-all), with a reply form that can optionally attach an image
    (e.g. an annotated screenshot of the fix); plus every direct-message
    conversation a student has started with them.
- **Ask Faculty** (student) — post an academic doubt (department + subject +
  question), optionally attaching an image (e.g. a screenshot of the
  problem), that any faculty member in that department can answer, and see
  every doubt's status, reply, and any image the faculty attached with their
  answer; or start a direct message thread with any faculty mentor at the
  same college — replies show up in both the "Recent Conversations" list
  here and the mentor's own Doubts & Messages page.
- **Flashcards** — reuses the same `questions` bank as Skill Assessment (no
  separate content to maintain): a set of 12 random questions rendered as
  tap-to-flip cards, front shows the question and options, back reveals the
  correct answer. Purely for practice — nothing is scored or saved, and a
  "New Set" button reshuffles.
- **Learning Hours** — a private log (`learning_logs`, linked from the
  Profile Snapshot) where a student notes what they studied and for how
  long; a total and a "last 7 days" figure are computed on the fly. Every
  query is scoped to `session['user_id']`, so this page is never reachable
  by — or visible to — faculty or college accounts.
- **Peer Reference wall** — a placement officer adds a short profile of a
  placed student from **Peer Wall** (company, role, package, CGPA, skills,
  projects, a line of advice); it immediately shows up on every current
  student's Skill Enhancement page as real, concrete proof of what's
  possible, not invented statistics.
- **Interview Experience Archive** — linked from Skill Enhancement, a
  campus-only board where a student posts a structured writeup right after
  their own interview (company, role, outcome, difficulty, rounds, the
  actual questions asked, and tips), visible only to other students at the
  same college. Unlike a generic interview-experience post on a public job
  board, every entry here is about the exact recruiters who visit *this*
  campus, so it stays genuinely relevant to the juniors reading it — and a
  student can remove their own post at any time.
- **College registration** — register a brand-new college, or join one
  already on the list, plus the first placement-officer login.
- **College login** — any placement-cell employee logs in with their
  official email + password.
- **College home dashboard** — add a company drive (name, role, description,
  registration window, eligibility criteria, package) and see/remove
  existing ones, each with an eligibility overview across your students.
- **Student Tracker** — for each drive, a live list of which students
  applied and their eligibility match %.
- **Students** — the student directory and each student's placement
  readiness in one section, instead of two separate pages: every registered
  student grouped by Department and then Course (with Department/Course
  filter dropdowns to narrow the view), each row also showing their best
  assessment score, certificate count, and overall progress bar.
- **In-app assistant** — a floating chat widget (`chatbot.py` +
  `/api/chat` + `static/js/chatbot.js`) answers common questions and pulls
  real numbers from the database for questions like *"am I eligible for
  TCS?"*, *"how do I improve my resume score?"* or (as faculty) *"how many
  students am I mentoring?"* — fully offline, no external services or API
  keys required, and now role-aware for students, faculty and colleges alike.

---

### What's new in v5 — Mock Interviews & Interviewer login (blind mode)

**Two logins inside the Company login page.** `/company/login` now has a
sliding **Company | Interviewer** switch. HR and recruiters use the Company
tab, and interview panel members use the Interviewer tab
(`/company/interviewer/login`). Each tab has its own form, illustration and
demo account.

**Company portal → Interviewers.** HR creates interviewer logins (name, work
email, designation, topics, temporary password), resets passwords and
deactivates accounts. Each person's mocks, campus rounds and evaluations are
counted. In **Interview Schedules**, every round can be assigned to an
interviewer.

**Interviewer portal (blind mode).** To prevent partiality, interviewers
only ever see a student's **name, skills, branch, year, projects,
certifications, achievements and assessment score**. College name, CGPA,
SRN, email, phone and photo are never sent to interviewer pages.
- **Mock Interviews**: open slots (Technical / HR / Behavioural / Mixed,
  online or in person, optionally repeated weekly), see who booked, run the
  session and send feedback: four star ratings, a verdict (Ready / Almost
  ready / Needs more practice), what went well, what to improve, and what to
  practise next. Interviewers can also mark a no-show or cancel with a
  reason.
- **Campus Interviews**: assigned rounds list the drive's applicants as
  blind profiles, with the job's required skills highlighted. The
  interviewer's evaluation (ratings, result, reason, remarks) is saved into
  the company's Hiring Report with the student's full details filled in on
  the server.

**Student portal → Mock Interview** (new navbar tab; Help and About Us moved
under **More**)
- Browse open slots from industry interviewers, filter by focus, and book
  with your target role and topics (up to 2 upcoming bookings at a time).
- Join link, cancel, a history of every session, and feedback with average
  ratings across all your mocks.
- A **What the interviewer sees** card shows exactly the blind profile
  interviewers get.

New tables: `interviewers`, `mock_slots`, `mock_feedback`.
`interview_schedules` and `interview_reports` gained `interviewer_id`.

### What's new in v4 — animated landing page, portal chooser & Company portal

**Landing page (`/`)**
- An intro splash plays once per browser session (logo draws itself, letters
  drop in, the screen splits open).
- The hero answers **"What is UniLinkUp?"** with a 6-slide slideshow
  (auto-play with progress dots, arrows, keyboard arrows, swipe on phones,
  pauses on hover). Slides use the illustrations in `static/img/`; drop real
  photos into `static/img/slides/` (see the README there) and they replace
  the illustrations automatically.
- A live "network" canvas, typed rotating words, count-up stats, tilt cards,
  a self-drawing "How it works" timeline, a feature marquee and a glowing CTA.
- Everything respects the operating system's *reduce motion* setting.

**Login / Register (top-left button → `/portal`)**
- Four animated cards — **Student, Faculty, College, Company** — each with a
  short description of what the portal is for, plus Login and Register.
- Picking one plays a transition into that role's login page. Every login
  and register page now shares an animated shell in the role's colour, a
  sliding **Login | Register** switch and a "Change portal" link.
- The navbar's **Portals** menu and every login page link to the new
  **Company Login** too.

**Company portal** (`/company/...`, role `company`)
- **Job Drive Post** — create job drives with eligibility based on student
  performance: minimum CGPA, branches, years, required skills and a minimum
  skill-assessment score. Close, reopen or delete drives.
- **College List** — every college with its number of students, average CGPA,
  average assessment score and how many students are eligible for the chosen
  job. Send a campus-visit request from the list or the college's page.
  Individual student records are only shown after the college approves.
- **Interview Schedules** — plan rounds (date, time, on-campus/online, venue,
  link, panel, instructions) for approved visits; mark them completed or
  cancelled.
- **Hiring Reports** — a form for every interview: pick the drive and round,
  pick an applicant to auto-fill their details (or type them), rate
  technical / communication / aptitude, choose **Selected / Not selected /
  On hold**, give the package or the reason they weren't selected, and add
  remarks. The report shows selection rate, results per campus drive and
  every record, with filters, CSV export and print.

**College portal**
- New **Company Requests** tab (with a pending-count badge): see the company,
  the job, its eligibility rules and how many of your students qualify, then
  **approve** (choose the registration window — the drive is published to
  students immediately with their Eligibility Match %) or **reject** with a
  reason the company can see. Companies' hiring results for your students
  are listed on the same page.
- Notify Students, Peer Wall and Help Desk moved under **More** to keep the
  navbar on one line.

New tables: `companies`, `job_posts`, `visit_requests`,
`interview_schedules`, `interview_reports`. `company_visits` gained
`company_account_id`, `job_post_id` and `min_assessment_pct` (added
automatically on start-up).

---

## 6. Ideas for further development

- Add your college's real name/logo to the navbar and landing page.
- Swap the demo `SECRET_KEY` for a random one (use `python -c "import secrets; print(secrets.token_hex(16))"`).
- **Rejection feedback:** let a placement officer mark an application
  "Rejected" with a free-text reason, shown to the student on their tracker.
- **Short-term paid internships:** reuse `company_visits` with an
  `internship` flag and a `duration_weeks` field (a `stipend`-style field
  already exists via `package_lpa`).
- **Leaderboards & badges:** rank students by best assessment score per
  college, with a shareable badge on the profile page.
- **Faculty calendar sync / reminders:** email or notification-bell reminders
  a few hours before a booked class, and an .ics export for faculty slots.
- **Richer ATS scoring:** parse resume sections more precisely (dates,
  quantified impact) and compare against a specific job description's
  keywords, not just the student's own profile skills.
- **Live chat:** the Messages feature currently reloads the page per send —
  swap in polling (like the notification bell) or WebSockets for a real-time
  feel.
- **Bell integration for doubts/messages:** fold unread doubt replies and
  new messages into the existing notification bell instead of only showing
  on the Ask Faculty / Doubts & Messages pages.
- **Calendar export:** an `.ics` download for an approved class request or
  any booked slot, so it lands on a student's or faculty member's own
  calendar app.
- Swap SQLite for PostgreSQL if you expect concurrent writes at scale.
- Move file uploads to cloud storage (S3 / Firebase) instead of local disk.
- Add HTTPS + a production WSGI server (gunicorn) + a process manager.
- Add automated tests (`pytest` + Flask's test client).

---

## 7. Style guide

Colors and fonts follow a fixed palette (dark teal `#0d2b2f`, accent teal
`#14b391`, accent orange `#e8823c`, Poppins font) defined at the top of
`static/css/style.css` — change the CSS custom properties there to re-theme
the whole app.
