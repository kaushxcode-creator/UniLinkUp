"""
chatbot.py
----------
The brain behind UniLinkUp's floating "Ask UniLinkUp" assistant
(see static/js/chatbot.js for the widget and /api/chat in app.py for the
route that calls get_reply() below).

Design goals:

  Works completely offline, with zero external services and no API keys.
  A keyword-scored FAQ engine answers the common "how do I..." questions,
  and a handful of *dynamic* intents pull real numbers out of the
  student's / college's own data (eligibility %, progress, best score,
  how many students are eligible for a drive, etc.) so it never gives a
  generic answer when a real one is available.
"""
import re


# --------------------------------------------------------------------------
# Small talk / greetings
# --------------------------------------------------------------------------
GREETINGS = {'hi', 'hello', 'hey', 'hola', 'yo', 'hii', 'hiii'}
THANKS = {'thanks', 'thank you', 'thanks!', 'ty', 'thx', 'thank u'}
# Word-boundary matcher for THANKS — a plain `in` substring check would treat
# any message containing "ty" as thanks, which false-positives on ordinary
# words like "eligibility" or "university" and silently swallowed real
# questions (e.g. "how is eligibility % calculated") with a generic
# "Anytime!" reply instead of ever reaching the FAQ/dynamic engine below.
_THANKS_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(t) for t in THANKS) + r')\b')

# --------------------------------------------------------------------------
# Static FAQ knowledge base.
# Each entry: (keywords, answer). The engine scores every entry by how many
# of its keywords appear in the user's message and returns the best match.
# --------------------------------------------------------------------------
FAQ = [
    (['register', 'sign up', 'signup', 'create account', 'new account'],
     "To create a student account, go to **Student Register** from the top menu and fill in your "
     "Name, SRN, Course, Year, Semester, CGPA, email and password — then pick your college from the "
     "searchable dropdown so campus drives show up for you automatically. Placement officers register "
     "(or join an existing college) from **College Login → Register your institution**."),

    (['forgot password', 'reset password', 'lost password', "can't login", 'cannot login', 'wrong password'],
     "Click **Forgot password?** on the Login page. Students verify with their email + SRN; placement "
     "officers verify with their own email + their college's registered official email. Once verified, "
     "you can set a new password immediately — no email or admin needed."),

    (['apply', 'application', 'how do i apply', 'apply to a company', 'apply now'],
     "Open a company card on your **Home** page and click *Apply Now*. You'll need at least one "
     "certificate AND one document uploaded on your **Profile** page first — the button unlocks "
     "automatically once both are on file, and only while that drive's registration window is open."),

    (['certificate', 'document', 'upload'],
     "Head to **My Profile** — there are two upload widgets there, one for certificates and one for "
     "documents (resume, ID proof, etc.). Give each a short title and choose the file (PDF/Word/image, "
     "under 10 MB). You need at least one of each before you can apply to any drive."),

    (['assessment', 'practice test', 'mock test', 'quiz', 'mcq'],
     "The **Skill Assessment** tab has two modes: *Practice* (unlimited attempts, purely for your own "
     "prep, never saved to your record) and *Main* (one scored attempt at a time, saved permanently — "
     "your best Main score is what shows up on your profile and your college's dashboard)."),

    (['progress', 'progress bar', 'how is progress calculated', 'overall progress'],
     "Your overall Progress bar = 40% profile completeness + 30% for having attempted the Main "
     "assessment + 30% for certificates uploaded (capped at 3). Fill in every profile field, take the "
     "Main assessment, and upload a few certificates to push it up."),

    (['eligibility', 'eligible', 'match', 'match percentage', 'match %', 'am i eligible'],
     "Every company drive shows an **Eligibility Match %** — it blends your CGPA against the company's "
     "minimum, whether your branch/year fits their criteria, how many of their required skills are on "
     "your profile, and your best Skill Assessment score. Ask me *\"am I eligible for <company name>\"* "
     "and I'll pull your actual number."),

    (['drive', 'campus drive', 'add company', 'add a drive', 'announce'],
     "Placement officers add a drive from **College Home → Announce a Campus Drive**: company name, "
     "role, description, registration window, and now also the eligibility criteria (minimum CGPA, "
     "eligible branches, eligible years, required skills, package) so the match % can be computed for "
     "every student automatically."),

    (['college', 'university', 'not listed', 'my college', 'which colleges'],
     "Use the searchable dropdown on the registration form — start typing your college's name and it "
     "filters instantly. If it's genuinely not listed, a placement officer can register it from "
     "**College Login → Register your institution**, and then you'll be able to pick it."),

    (['tracker', 'who applied', 'applicants'],
     "**Student Tracker** (placement officer view) lists, for every drive, exactly which students "
     "applied and their eligibility match % for that specific company."),

    (['skill', 'skills', 'add skills', 'my skills'],
     "Add a comma-separated skills list on your **Profile** page (e.g. \"Python, SQL, React\") — it "
     "feeds directly into the eligibility match % for every company that lists required skills."),

    (['contact', 'support', 'help desk', 'human', 'real person', 'raise a query', 'raise a ticket'],
     "For anything I can't resolve, use the **Help** tab in the menu — fill in a subject and describe the "
     "problem, and it goes straight to your placement cell. Placement officers see every query on their "
     "**Help Desk** page and can mark it resolved."),

    (['notification', 'notifications', 'bell', 'reminder', 'announcement'],
     "The bell icon in the top menu shows notifications your placement cell has sent — manual updates or "
     "automatic reminders about a drive's registration deadline. Opening it marks them as read. Placement "
     "officers send these from **Notify Students** (pick specific students or select all) or with the "
     "one-click *Send Reminder* button next to any drive on the College Home page."),

    (['what is unilink', 'about unilink', 'what does this do', 'what is this'],
     "UniLinkUp connects students, colleges and companies: students build a verified skill profile "
     "and see an eligibility match % for every campus drive, colleges track readiness and placements in "
     "one dashboard, and companies get a pool of pre-matched, job-ready candidates."),

    (['skill enhancement', 'skill gap', 'where do i lack', 'weak skill', 'improve my skills'],
     "Open **Skill Enhancement** from the top menu. It compares your profile skills against the skills "
     "companies are actually asking for across drives at your college, and shows you exactly what to "
     "build next plus what's already working in your favor — then lets you book a 1-on-1 class with a "
     "faculty mentor for the gaps."),

    (['1-on-1', 'one on one', 'book a class', 'book appointment', 'book slot', 'mentor class', 'faculty class', 'join a class', 'group class'],
     "From **Skill Enhancement**, scroll to *Upcoming Classes You Can Join* and pick any open slot offered "
     "by a faculty mentor at your college. Some slots are one-on-one, others are group classes with a few "
     "seats — you'll see how many students have already joined, and you can join them. Cancel anytime under "
     "*Your Upcoming Classes*, which frees the seat for someone else."),

    (['request a class', 'request a slot', 'request a session', 'ask a mentor', 'request faculty'],
     "Also on **Skill Enhancement**, use *Request a Class* — pick a faculty mentor and the skill you want "
     "to learn (we'll flag which company drive actually needs it, if any) and send it. The mentor picks a "
     "time and approves or declines it; you'll see their answer right there under *Your Requests*."),

    (['approve request', 'decline request', 'pending request', 'student request'],
     "Faculty: pending requests show at the top of your **Slots** page, with the skill the student wants "
     "and — when it matches a live drive — which company needs it. Approve with a date/time (and an "
     "optional meeting link) to schedule it, or decline it — declining requires both a reason and a date "
     "for another class the student can join instead, so it's never a dead end."),

    (['cancel class', 'cancel a class', 'cancel booked class', 'cancel approved class', 'cancel my slot'],
     "Faculty: once a class already has students booked into it (including one created by approving a "
     "request), open **Slots** and use *Cancel Class* under that row — a reason is required, and every "
     "student booked into it is notified immediately with your reason via their notification bell."),

    (['create a test', 'make a test', 'faculty test', 'custom test', 'mcq test'],
     "Faculty: **Create Test** in your menu lets you build a custom MCQ test — title, a few questions each "
     "with 4 options and the correct one marked. It's instantly visible to students at your college under "
     "their **Skill Assessment** page, and you can see everyone's scores from the Results link."),

    (['doubt', 'ask a doubt', 'academic question', 'ask faculty'],
     "Post an academic question from **Ask Faculty** — pick your department, a subject and your question. "
     "Any faculty member in that department can answer it, and you'll see the reply right there."),

    (['message a faculty', 'chat with faculty', 'message mentor', 'dm faculty'],
     "Also on **Ask Faculty**, pick any mentor under *Message a Mentor* to start a direct chat — faculty "
     "reply from their own **Doubts & Messages** page."),

    (['flashcard', 'flash card', 'flip card', 'flashcard game'],
     "**Flashcards** (linked from Skill Assessment) is a quick tap-to-flip practice game — the question and "
     "options are on the front, the correct answer's on the back. Nothing's scored or saved, it's just for "
     "a fast refresher."),

    (['learning hours', 'study hours', 'log hours', 'track study time'],
     "**Learning Hours**, linked from your Profile snapshot, is a private log only you can see — note what "
     "you studied and how long, and it totals your hours for you."),

    (['peer reference', 'placed students', 'who got placed', 'success stories', 'alumni'],
     "The **Placed Peers** card on your Skill Enhancement page shows real profiles your placement cell has "
     "added — company, package, CGPA, skills and a line of advice from students who got placed, so you can "
     "see what actually worked. Placement officers add these from **Peer Wall**."),

    (['interview experience', 'interview questions', 'what was asked', 'interview rounds', 'interview prep'],
     "**Interview Experiences** (linked from Skill Enhancement) is a campus-only archive — students post a "
     "quick writeup right after their own interview at a real drive here: rounds, difficulty, what was "
     "actually asked, and tips for the next batch. Only from your own college, so it's about the exact "
     "recruiters who visit your campus, not a stranger's story from somewhere else."),

    (['notify my students', 'send class update', 'notify mentees', 'message my students'],
     "Faculty: use the *Notify Students* card on your **Home** page to send an update to everyone who's "
     "booked with you, or only the students in one specific class — it lands in their notification bell."),

    (['faculty login', 'faculty register', 'i am faculty', "i'm faculty", 'professor login', 'teacher login', 'mentor login'],
     "Faculty sign in from **Faculty Login** in the top menu, or register first from there if you're new "
     "— you'll join your college the same way a placement officer does. Once in, you get your own Home, "
     "Slots and Student Progress pages."),

    (['offer a slot', 'add a slot', 'create a slot', 'faculty slots', 'give students a slot'],
     "Faculty: go to **Slots** in your menu, fill in a date, start/end time and an optional topic, then "
     "*Add Slot*. It shows up immediately to students at your college on their Skill Enhancement page. "
     "You can remove any slot that's still open; once a student books it, it's locked until they cancel."),

    (['student progress', 'my mentees', 'who booked', 'my students'],
     "Faculty: the **Student Progress** page shows readiness for every student who has booked a class "
     "with you specifically — CGPA, best assessment score, certificates and overall progress, so you "
     "know where to focus the session."),

    (['resume', 'cv', 'ats', 'ats score', 'improve resume', '90 ats', 'resume score'],
     "Upload your resume on **My Profile**, under *Resume & ATS Score* (PDF, DOC, DOCX or TXT). You get "
     "an instant offline score out of 100 plus specific, actionable feedback — nothing is sent anywhere "
     "outside the app. Fix the listed points and re-upload any time to see your new score; aim to clear "
     "the contact info, section coverage, skill-match, action-verb and length checks for a 90+."),

    (['cgpa', 'percentile', 'snapshot', 'inspire', 'where do i stand'],
     "Your **Profile** page has a *Your Snapshot* card with your CGPA (and, once enough of your "
     "college's students have one on file, your CGPA percentile), skills listed, certificates, and best "
     "assessment score — a quick honest read on where you stand."),
]

DEFAULT_HELP = (
    "I can help with things like: registering or logging in, applying to a company drive, "
    "uploading certificates/documents, how the Skill Assessment works, how your Progress % or "
    "Eligibility Match % is calculated, Skill Enhancement (booking or requesting a mentor class), your "
    "resume's ATS score, Flashcards, Learning Hours, Peer References, Interview Experiences, and asking "
    "faculty a doubt or message. Try asking me something like *\"am I eligible for TCS?\"* or *\"how do I "
    "request a class?\"*"
)


def _score(message, keywords):
    return sum(1 for kw in keywords if kw in message)


def _best_faq(message):
    best_entry, best_score = None, 0
    for keywords, answer in FAQ:
        s = _score(message, keywords)
        if s > best_score:
            best_entry, best_score = answer, s
    return best_entry if best_score > 0 else None


# --------------------------------------------------------------------------
# Dynamic intents — answers computed from the live context passed in from
# app.py (the logged-in student's/employee's real data), not canned text.
# --------------------------------------------------------------------------
def _find_company(message, companies):
    """Very small fuzzy match: does any company's name (or a good chunk of
    it) appear in the user's message?"""
    message_l = message.lower()
    for c in companies:
        name = (c.get('company_name') or '').lower()
        if name and (name in message_l or any(part in message_l for part in name.split() if len(part) > 2)):
            return c
    return None


def _dynamic_reply(message, context):
    message_l = message.lower()
    role = context.get('role', 'guest')

    # A "how is X calculated / what goes into X" question wants the general
    # explanation from the static FAQ, never a live number — without this,
    # "how is eligibility % calculated" contains "elig" and would otherwise
    # be caught by the eligibility branch below and answered with the
    # student's actual match numbers instead of how the figure is derived.
    is_howto = any(w in message_l for w in
                   ('how is', 'how are', 'how does', 'how do you', 'how you calculate',
                    'formula', 'calculat', 'compute', 'what goes into', 'what is factored'))

    # ---- Eligibility questions (student) ----
    if role == 'student' and not is_howto and any(k in message_l for k in ('elig', 'match', 'chance', 'qualify')):
        companies = context.get('companies') or []
        matches = context.get('matches') or {}
        company = _find_company(message, companies)
        if company:
            m = matches.get(company['company_name'])
            if m:
                verdict = "You meet the hard eligibility criteria ✅" if m['eligible'] else \
                          "You don't yet meet one or more hard criteria ⚠️"
                lines = [f"**{company['company_name']}** — {m['percent']}% match. {verdict}"]
                for label, ok, detail in m['reasons']:
                    lines.append(f"{'✔️' if ok else '✖️'} {label}: {detail}")
                return "\n".join(lines)
        if matches:
            ranked = sorted(matches.items(), key=lambda kv: kv[1]['percent'], reverse=True)
            lines = ["Here's your match % for every drive at your college:"]
            for name, m in ranked[:8]:
                lines.append(f"• {name}: {m['percent']}% {'(eligible)' if m['eligible'] else ''}")
            return "\n".join(lines)
        return ("I don't see any company drives for your college yet, so there's nothing to "
                "match against right now — check back once your placement cell announces one.")

    # ---- Eligibility / overview questions (employee) ----
    if role == 'employee' and not is_howto and any(k in message_l for k in ('elig', 'match', 'how many')):
        overview = context.get('eligibility_overview') or {}
        companies = context.get('companies') or []
        company = _find_company(message, companies)
        if company and company['company_name'] in overview:
            o = overview[company['company_name']]
            return (f"For **{company['company_name']}**: {o['eligible_count']} of {o['total']} students "
                    f"currently meet the hard eligibility criteria, with an average match score of "
                    f"{o['avg_percent']}% across your whole student list.")
        if overview:
            lines = ["Eligibility overview across your active drives:"]
            for name, o in overview.items():
                lines.append(f"• {name}: {o['eligible_count']}/{o['total']} eligible · avg {o['avg_percent']}% match")
            return "\n".join(lines)

    # ---- Progress ----
    if role == 'student' and 'progress' in message_l:
        return (f"Your overall progress is **{context.get('progress', 0)}%** "
                f"(40% profile completeness + 30% for a Main assessment attempt + 30% for certificates, "
                f"capped at 3).")

    # ---- Assessment score ----
    if role == 'student' and any(k in message_l for k in ('score', 'best attempt', 'how did i do')):
        best = context.get('best_main')
        if best:
            return f"Your best Main assessment score is **{best['score']}/{best['total']}**."
        return "You haven't attempted the Main skill assessment yet — head to the Skill Assessment tab to take it."

    # ---- Can I apply? ----
    if role == 'student' and 'can i apply' in message_l:
        if context.get('can_apply'):
            return "Yes — you've already got at least one certificate and one document on file, so Apply Now is unlocked for any open drive."
        return "Not yet — upload at least one certificate AND one document on your Profile page first, then Apply Now unlocks."

    # ---- How many students (employee) ----
    if role == 'employee' and 'how many student' in message_l:
        return f"You currently have **{context.get('student_count', 0)}** students registered under your college."

    # ---- Faculty: upcoming classes / slots / mentees ----
    if role == 'faculty':
        if any(k in message_l for k in ('upcoming', 'my class', 'my classes', 'next class')):
            n = context.get('upcoming_count', 0)
            if n:
                return f"You have **{n}** upcoming class{'es' if n != 1 else ''} booked — check **Home** for the full schedule."
            return "You don't have any classes booked yet. Once you offer a few open slots, students at your college can book them."
        if any(k in message_l for k in ('open slot', 'my slots', 'slots do i have', 'how many slot')):
            n = context.get('open_slot_count', 0)
            return f"You currently have **{n}** open slot{'s' if n != 1 else ''} students can book. Add more from the **Slots** page."
        if any(k in message_l for k in ('mentee', 'how many student', 'students mentored', 'my students')):
            n = context.get('mentee_count', 0)
            return f"You're currently mentoring **{n}** student{'s' if n != 1 else ''} — see their readiness on **Student Progress**."
        if any(k in message_l for k in ('pending request', 'requests do i have', 'new request')):
            n = context.get('pending_request_count', 0)
            if n:
                return f"You have **{n}** pending class request{'s' if n != 1 else ''} — review them at the top of your **Slots** page."
            return "No pending requests right now."

    return None


def get_reply(message, context=None, history=None):
    context = context or {}
    history = history or []
    message_stripped = message.strip()
    message_l = message_stripped.lower()

    if message_l in GREETINGS or message_l.rstrip('!.') in GREETINGS:
        name = None
        if context.get('role') == 'student':
            name = context.get('student', {}).get('name') if isinstance(context.get('student'), dict) else context['student']['name']
        elif context.get('role') == 'employee':
            name = context.get('employee', {}).get('name') if isinstance(context.get('employee'), dict) else context['employee']['name']
        elif context.get('role') == 'faculty':
            name = context.get('faculty', {}).get('name') if isinstance(context.get('faculty'), dict) else context['faculty']['name']
        greeting = f"Hey {name.split()[0]}! 👋" if name else "Hey there! 👋"
        return f"{greeting} I'm the UniLinkUp assistant. {DEFAULT_HELP}"

    if _THANKS_PATTERN.search(message_l):
        return "Anytime! Let me know if anything else comes up. 🙂"

    # 1. Dynamic, data-backed intents (eligibility %, progress %, scores...).
    dynamic = _dynamic_reply(message_stripped, context)
    if dynamic:
        return dynamic

    # 2. Static FAQ, keyword-scored.
    faq = _best_faq(message_l)
    if faq:
        return faq

    return ("I'm not totally sure about that one. " + DEFAULT_HELP)
