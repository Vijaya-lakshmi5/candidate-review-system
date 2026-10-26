
from app import app, db, User

with app.app_context():
    admin = User.query.filter_by(role="admin").first()

    if admin:
        admin.email = "admin@example.com"
        admin.set_password("VijiAdmin@2026!")
        db.session.commit()
        print("Admin password reset successfully.")
    else:
        print("Admin account not found.")
