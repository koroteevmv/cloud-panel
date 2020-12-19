from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

from app import app

db = SQLAlchemy(app)


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer(), primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False)
    login_way = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(100), nullable=True)
    created_on = db.Column(db.DateTime(), default=datetime.utcnow)
    updated_on = db.Column(db.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)
    machines = db.relationship('Machine', backref='users', lazy=True)

    def __repr__(self):
        return "<{}:{}>".format(self.id, self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            print(self.password_hash, generate_password_hash(password), password)
            return False
        print(self.password_hash, generate_password_hash(password), password)
        return check_password_hash(self.password_hash, password)


class Image(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.Integer(), primary_key=True)
    filename = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    created_on = db.Column(db.DateTime(), default=datetime.utcnow)
    machines = db.relationship('Machine', backref='images', lazy=True)

    def __repr__(self):
        return f"{self.name}"


class Machine(db.Model):
    __tablename__ = 'machines'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    id_string = db.Column(db.String(1000), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    image_id = db.Column(db.Integer, db.ForeignKey('images.id'), nullable=True)

    def __repr__(self):
        return f"{self.name}"
