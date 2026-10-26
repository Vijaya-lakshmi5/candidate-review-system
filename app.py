import os, io, secrets, smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-this-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///candidate_reviews.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)

def now_local():
    # Store naive local timestamps in this starter app; server timezone should be set to Asia/Kolkata.
    return datetime.now()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="candidate")  # admin or candidate
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(40), default="")
    assigned_task = db.Column(db.Text, default="")
    task_status = db.Column(db.String(30), default="Not Started")
    attendance_status = db.Column(db.String(30), default="Not Scheduled")
    review_status = db.Column(db.String(30), default="Waiting")
    last_review_at = db.Column(db.DateTime, nullable=True)
    next_review_at = db.Column(db.DateTime, nullable=True)
    task_deadline = db.Column(db.DateTime, nullable=True)
    meet_link = db.Column(db.String(500), default="")
    reviewer_feedback = db.Column(db.Text, default="")
    review_result = db.Column(db.String(100), default="")
    next_task = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=now_local)
    user = db.relationship("User", backref="candidate_record", uselist=False,
                           primaryjoin="Candidate.id==User.candidate_id")

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False, index=True)
    start_at = db.Column(db.DateTime, nullable=False, index=True)
    end_at = db.Column(db.DateTime, nullable=False, index=True)
    meet_link = db.Column(db.String(500), default="")
    status = db.Column(db.String(30), default="Scheduled")  # Scheduled, Completed, Absent, Cancelled
    attendance = db.Column(db.String(30), default="Pending")
    feedback = db.Column(db.Text, default="")
    result = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, default=now_local)
    candidate = db.relationship("Candidate", backref="reviews")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def send_email(to_email, subject, body):
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("MAIL_FROM") or username
    if not (host and username and password and sender):
        app.logger.warning("Email skipped: SMTP configuration is incomplete (recipient %s).", to_email)
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return True
    except Exception:
        app.logger.exception("Email delivery failed to %s", to_email)
        return False

def candidate_summary(c):
    when = c.next_review_at.strftime("%d %b %Y, %I:%M %p") if c.next_review_at else "Not scheduled"
    deadline = c.task_deadline.strftime("%d %b %Y, %I:%M %p") if c.task_deadline else "Not set"
    return f"""Hello {c.full_name},

Candidate ID: {c.candidate_code}
Review result: {c.review_result or 'Pending'}
Reviewer feedback: {c.reviewer_feedback or 'No feedback recorded'}
Current task: {c.assigned_task or 'Not assigned'}
Task status: {c.task_status}
Next task: {c.next_task or 'Not assigned'}
Task deadline: {deadline}
Next review: {when}
Google Meet link: {c.meet_link or 'Not available'}

Please contact the administrator if any detail needs correction.
"""

def notify_candidate(c, subject, extra=""):
    return send_email(c.email, subject, candidate_summary(c) + ("\n\n" + extra if extra else ""))

def create_admin_if_needed():
    if not User.query.filter_by(role="admin").first():
        email = os.getenv("ADMIN_EMAIL", "admin@example.com").strip().lower()
        password = os.getenv("ADMIN_PASSWORD", "ChangeThis-Immediately-123!")
        admin = User(name=os.getenv("ADMIN_NAME", "System Admin"), email=email, role="admin")
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        app.logger.warning("Initial admin created for %s. Change the password immediately.", email)

with app.app_context():
    db.create_all()
    create_admin_if_needed()

@app.route("/")
def home():
    return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "candidate":
        c = db.session.get(Candidate, current_user.candidate_id)
        if not c: abort(404)
        return redirect(url_for("candidate_portal", candidate_id=c.id))
    candidates = Candidate.query.order_by(Candidate.full_name).all()
    upcoming = Review.query.filter(Review.status == "Scheduled", Review.start_at >= now_local()).order_by(Review.start_at).limit(12).all()
    stats = {
        "total": Candidate.query.count(),
        "tasks_done": Candidate.query.filter_by(task_status="Completed").count(),
        "waiting": Candidate.query.filter_by(review_status="Waiting").count(),
        "reviewed": Candidate.query.filter_by(review_status="Completed").count(),
        "absent": Candidate.query.filter_by(attendance_status="Absent").count(),
        "overdue": Candidate.query.filter(Candidate.task_deadline < now_local(), Candidate.task_status != "Completed").count()
    }
    return render_template("dashboard.html", candidates=candidates, upcoming=upcoming, stats=stats)

@app.route("/candidates/new", methods=["GET", "POST"])
@admin_required
def candidate_new():
    if request.method == "POST":
        code = request.form.get("candidate_code", "").strip().upper()
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if not code or not name or not email:
            flash("Candidate ID, name, and email are required.", "error")
        elif Candidate.query.filter((Candidate.candidate_code == code) | (Candidate.email == email)).first():
            flash("Candidate ID or email already exists.", "error")
        else:
            c = Candidate(candidate_code=code, full_name=name, email=email,
                phone=request.form.get("phone", "").strip(),
                assigned_task=request.form.get("assigned_task", "").strip(),
                task_status=request.form.get("task_status", "Not Started"),
                next_task=request.form.get("next_task", "").strip())
            deadline = request.form.get("task_deadline", "")
            if deadline:
                c.task_deadline = datetime.fromisoformat(deadline)
            db.session.add(c); db.session.flush()
            user = User(name=name, email=email, role="candidate", candidate_id=c.id)
            # A random initial password is not disclosed by email. Admin must use password reset flow before production.
            user.set_password(secrets.token_urlsafe(18))
            db.session.add(user); db.session.commit()
            notify_candidate(c, "Your candidate portal has been created", "Ask the administrator for secure portal access.")
            flash("Candidate created. Candidate portal account was created; configure a secure password setup flow before production use.", "success")
            return redirect(url_for("dashboard"))
    return render_template("candidate.html", candidate=None)

@app.route("/candidates/<int:candidate_id>/edit", methods=["GET", "POST"])
@admin_required
def candidate_edit(candidate_id):
    c = db.session.get(Candidate, candidate_id) or abort(404)
    if request.method == "POST":
        c.full_name = request.form.get("full_name", "").strip()
        c.phone = request.form.get("phone", "").strip()
        c.assigned_task = request.form.get("assigned_task", "").strip()
        c.next_task = request.form.get("next_task", "").strip()
        c.task_status = request.form.get("task_status", "Not Started")
        raw_deadline = request.form.get("task_deadline", "")
        c.task_deadline = datetime.fromisoformat(raw_deadline) if raw_deadline else None
        db.session.commit()
        flash("Candidate details updated.", "success")
        return redirect(url_for("dashboard"))
    return render_template("candidate.html", candidate=c)

@app.route("/candidates/<int:candidate_id>/delete", methods=["POST"])
@admin_required
def candidate_delete(candidate_id):
    c = db.session.get(Candidate, candidate_id) or abort(404)
    User.query.filter_by(candidate_id=c.id).delete()
    Review.query.filter_by(candidate_id=c.id).delete()
    db.session.delete(c); db.session.commit()
    flash("Candidate deleted.", "success")
    return redirect(url_for("dashboard"))

@app.route("/candidates/import", methods=["POST"])
@admin_required
def import_candidates():
    upload = request.files.get("file")
    if not upload or not upload.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        flash("Upload an Excel (.xlsx) or CSV file.", "error"); return redirect(url_for("dashboard"))
    try:
        df = pd.read_csv(upload) if upload.filename.lower().endswith(".csv") else pd.read_excel(upload)
        df.columns = [str(x).strip().lower().replace(" ", "_") for x in df.columns]
        required = {"candidate_id", "full_name", "email"}
        if not required.issubset(df.columns):
            flash("Required columns: candidate_id, full_name, email. Optional: phone, assigned_task, task_status, next_task, task_deadline.", "error")
            return redirect(url_for("dashboard"))
        added, skipped = 0, 0
        for _, row in df.iterrows():
            code = str(row.get("candidate_id", "")).strip().upper()
            name = str(row.get("full_name", "")).strip()
            email = str(row.get("email", "")).strip().lower()
            if not code or code == "NAN" or not name or name == "NAN" or not email or email == "NAN":
                skipped += 1; continue
            if Candidate.query.filter((Candidate.candidate_code == code) | (Candidate.email == email)).first():
                skipped += 1; continue
            def val(key, default=""):
                x = row.get(key, default)
                return default if pd.isna(x) else str(x).strip()
            c = Candidate(candidate_code=code, full_name=name, email=email, phone=val("phone"),
                          assigned_task=val("assigned_task"), task_status=val("task_status", "Not Started") or "Not Started",
                          next_task=val("next_task"))
            deadline = val("task_deadline")
            if deadline:
                try: c.task_deadline = pd.to_datetime(deadline).to_pydatetime()
                except Exception: pass
            db.session.add(c); db.session.flush()
            u = User(name=name, email=email, role="candidate", candidate_id=c.id)
            u.set_password(secrets.token_urlsafe(24))
            db.session.add(u); added += 1
        db.session.commit()
        flash(f"Import finished: {added} added, {skipped} skipped. Set up secure candidate password onboarding before using candidate logins.", "success")
    except Exception:
        db.session.rollback()
        app.logger.exception("Candidate import failed")
        flash("Import failed. Check the file and required column names.", "error")
    return redirect(url_for("dashboard"))

@app.route("/candidates/export")
@admin_required
def export_candidates():
    rows = []
    for c in Candidate.query.order_by(Candidate.full_name).all():
        rows.append({"candidate_id": c.candidate_code, "full_name": c.full_name, "email": c.email, "phone": c.phone,
          "assigned_task": c.assigned_task, "task_status": c.task_status, "attendance_status": c.attendance_status,
          "review_status": c.review_status, "last_review_date": c.last_review_at, "next_review_date_time": c.next_review_at,
          "task_deadline": c.task_deadline, "meet_link": c.meet_link, "reviewer_feedback": c.reviewer_feedback,
          "review_result": c.review_result, "next_task": c.next_task})
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Candidates")
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="candidate_reviews.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/reviews/schedule/<int:candidate_id>", methods=["POST"])
@admin_required
def schedule_review(candidate_id):
    c = db.session.get(Candidate, candidate_id) or abort(404)
    if c.task_status != "Completed":
        flash("Mark the assigned task Completed before scheduling a review.", "error")
        return redirect(url_for("dashboard"))
    try:
        start = datetime.fromisoformat(request.form["start_at"])
        duration = int(request.form.get("duration", "30"))
        if start <= now_local() or duration < 10 or duration > 120:
            raise ValueError()
    except Exception:
        flash("Choose a future date/time and duration between 10 and 120 minutes.", "error")
        return redirect(url_for("dashboard"))
    end = start + timedelta(minutes=duration)
    conflict = Review.query.filter(Review.status == "Scheduled", Review.start_at < end, Review.end_at > start).first()
    if conflict:
        flash("That time overlaps another scheduled review. Choose another slot.", "error")
        return redirect(url_for("dashboard"))
    meet_link = ""
    # Google Meet integration is deliberately not faked: set up OAuth and Calendar API before adding event creation.
    review = Review(candidate_id=c.id, start_at=start, end_at=end, meet_link=meet_link)
    db.session.add(review)
    c.next_review_at, c.meet_link = start, meet_link
    c.review_status, c.attendance_status = "Scheduled", "Pending"
    db.session.commit()
    notify_candidate(c, "Candidate review scheduled", "Your review slot has been scheduled. Google Meet link will appear when Calendar integration is configured.")
    flash("Review slot scheduled and notification attempted. Configure Google Calendar OAuth to create a real Meet link.", "success")
    return redirect(url_for("dashboard"))

@app.route("/reviews/<int:review_id>/update", methods=["POST"])
@admin_required
def review_update(review_id):
    r = db.session.get(Review, review_id) or abort(404)
    c = r.candidate
    action = request.form.get("action")
    if action == "complete":
        r.status, r.attendance = "Completed", "Present"
        r.feedback = request.form.get("feedback", "").strip()
        r.result = request.form.get("result", "").strip()
        c.last_review_at = r.start_at
        c.review_status, c.attendance_status = "Completed", "Present"
        c.reviewer_feedback, c.review_result = r.feedback, r.result
        next_task = request.form.get("next_task", "").strip()
        if next_task: c.next_task = next_task
        db.session.commit()
        notify_candidate(c, "Review completed - summary and next schedule")
        flash("Review completed; summary email attempted.", "success")
    elif action == "absent":
        r.status, r.attendance = "Absent", "Absent"
        c.attendance_status, c.review_status = "Absent", "Waiting"
        db.session.commit()
        # Find next available slot in 30-minute intervals, starting at the next day.
        slot = max(now_local() + timedelta(days=1), r.end_at + timedelta(days=1))
        slot = slot.replace(hour=10, minute=0, second=0, microsecond=0)
        for _ in range(60):
            end = slot + timedelta(minutes=30)
            conflict = Review.query.filter(Review.status == "Scheduled", Review.start_at < end, Review.end_at > slot).first()
            if not conflict: break
            slot += timedelta(minutes=30)
            if slot.hour >= 17: slot = (slot + timedelta(days=1)).replace(hour=10, minute=0)
        nr = Review(candidate_id=c.id, start_at=slot, end_at=slot+timedelta(minutes=30))
        db.session.add(nr); c.next_review_at = slot; c.meet_link = ""; c.review_status = "Scheduled"
        db.session.commit()
        notify_candidate(c, "Missed review - new review schedule", "You were marked absent. A new review slot has been assigned.")
        flash("Candidate marked absent and moved to the next available slot. Calendar integration is needed for a Meet link.", "success")
    elif action == "cancel":
        r.status = "Cancelled"
        if c.next_review_at == r.start_at:
            c.next_review_at, c.meet_link, c.review_status = None, "", "Waiting"
        db.session.commit()
        flash("Review cancelled.", "success")
    return redirect(url_for("dashboard"))

@app.route("/candidate/<int:candidate_id>")
@login_required
def candidate_portal(candidate_id):
    c = db.session.get(Candidate, candidate_id) or abort(404)
    if current_user.role != "admin" and current_user.candidate_id != c.id:
        abort(403)
    reviews = Review.query.filter_by(candidate_id=c.id).order_by(Review.start_at.desc()).all()
    return render_template("review_summary.html", candidate=c, reviews=reviews)

@app.route("/ai/suggestions/<int:candidate_id>", methods=["POST"])
@admin_required
def ai_suggestions(candidate_id):
    c = db.session.get(Candidate, candidate_id) or abort(404)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        flash("AI is not configured. Add OPENAI_API_KEY to .env.", "error")
        return redirect(url_for("dashboard"))
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=f"Generate 5 review questions and 3 constructive task-improvement suggestions for this candidate task. Treat this as a draft for a human reviewer; do not score or make a hiring decision.\nTask: {c.assigned_task}\nStatus: {c.task_status}\nFeedback so far: {c.reviewer_feedback}"
        )
        flash("AI draft (review and approve before using): " + response.output_text[:1800], "success")
    except Exception:
        app.logger.exception("AI request failed")
        flash("AI request failed. Check the API key, model, and network.", "error")
    return redirect(url_for("dashboard"))

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
