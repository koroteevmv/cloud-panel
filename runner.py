from threading import Lock

from app import db, app, logger
from app.controller import get_images, rescan_machines
from app.models import User
from config import ADMIN_NAME
import logging

def rescan_db():
    db.create_all()
    if not db.session.query(User).filter(User.fullname == ADMIN_NAME).first():
        admin = User(
            fullname=ADMIN_NAME,
            email='koroteevmv@gmail.com',
            login_way='passwd',
            password_hash='pbkdf2:sha256:150000$BgkwVsF1$deb03f980b8d063888d4e7aa5af08333b8fbbbd6b159c5f8acf46f4c4e50594d'
        )
        db.session.add(admin)

    get_images()
    rescan_machines()
    db.session.commit()
    logging.info("Created new DB fixture")


rescan_db()


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
