# AI-Powered Candidate Review and Task Scheduling Management System

## Features in this starter
- Flask web app with admin login and candidate portal access control
- SQLite database for candidate and review records
- Candidate add/edit/delete
- Excel/CSV import and Excel export
- Task status, deadline, review status and feedback tracking
- Review slot conflict checking
- Mark completed / absent; absent candidates are assigned a next available slot
- Email notifications over configured SMTP
- Optional AI-generated review-question/task-improvement drafts (human approval required)
- Responsive black-and-white interface

## Important integration status
- SMTP email sends real email when credentials are configured.
- Google Calendar/Meet event creation is NOT enabled in this starter. Scheduling stores a slot but does not claim a Meet URL exists. Add OAuth consent and Calendar API event creation before using Google Meet invitations.
- Candidate accounts are created with random initial passwords. This starter does not implement password reset/invitation onboarding; add that before allowing candidates to sign in.
- Schedule recurrence every two days is a policy rule, not an automatic recurring job yet. Admin selects future slots; absent candidates are assigned the next free slot.
- For production: use HTTPS, secure password onboarding/reset, rate limiting, backups, logging, database migrations, and a production WSGI server. Do not expose Flask debug mode.

## Run in VS Code or Antigravity
1. Install Python 3.11+.
2. Open this folder in the IDE.
3. Create a virtual environment:
   - Windows: `py -m venv .venv`
   - PowerShell: `.venv\\Scripts\\Activate.ps1`
4. Install: `python -m pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and change `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`.
6. Start: `python app.py`
7. Open `http://127.0.0.1:5000`.
8. Sign in with the admin email/password from `.env`.

## Excel import columns
Required headers: `candidate_id`, `full_name`, `email`.
Optional: `phone`, `assigned_task`, `task_status`, `next_task`, `task_deadline`.
Use a `.xlsx` or `.csv` file. Duplicate candidate IDs/emails are skipped.

## SMTP / Gmail setup
For Gmail, enable 2-Step Verification and create an App Password. Put the account in `SMTP_USERNAME` and the app password in `SMTP_PASSWORD`. Never use your normal Gmail password. Use a test recipient first.

## Google Calendar / Meet setup
1. Create/select a Google Cloud project.
2. Enable Google Calendar API.
3. Configure the OAuth consent screen and create OAuth Client credentials for a web/desktop app.
4. Download the OAuth client JSON as `credentials.json` into the project folder; keep it private and out of version control.
5. Implement the OAuth authorization-code flow for the calendar account and store tokens securely. The starter currently does not create Calendar events, because creating a real Meet link requires authorized Calendar API credentials and a valid conference request.
6. When implementing, create an event with `conferenceDataVersion=1`, a unique `conferenceData.createRequest.requestId`, start/end dateTime and timezone, and invite the candidate as an attendee. Save the returned `hangoutLink` and event ID to the database. Handle token expiry, duplicate retries, and API errors.

## AI setup
Add `OPENAI_API_KEY` and optionally `OPENAI_MODEL` to `.env`. The AI endpoint generates draft questions and suggestions only. A reviewer must verify any output; do not use AI alone to make hiring decisions.

## Security notes
- `.env`, credentials, and tokens must never be committed.
- The first admin is created once. If you change `.env` after the first run, the existing database admin password does not automatically change.
- This is a development starter, not a fully audited production deployment.
