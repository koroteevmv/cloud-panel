from app import db, app
from app.models import Machine, Image, User
from config import ADMIN_NAME
import logging

def rescan_db():
    db.create_all()
    logging.warning("Created new DB fixture")
    if not db.session.query(User).filter(User.username == ADMIN_NAME).first():
        admin = User(
            username=ADMIN_NAME,
            email='koroteevmv@gmail.com',
            login_way='passwd',
            password_hash='pbkdf2:sha256:150000$BgkwVsF1$deb03f980b8d063888d4e7aa5af08333b8fbbbd6b159c5f8acf46f4c4e50594d'
        )
        db.session.add(admin)
    db.session.commit()
    logging.info("Created new DB fixture")


rescan_db()


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False, ssl_context='adhoc')
