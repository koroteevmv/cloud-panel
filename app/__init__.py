import logging
import uuid
from functools import wraps

import msal
from flask import Flask, session, redirect, url_for
from flask_login import LoginManager, current_user

logger = logging.getLogger('UI')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('./app.log')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


import config

app = Flask(__name__)
app.config.from_object(config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

from .models import db, User, Machine, Image


def _load_cache():
    cache = msal.SerializableTokenCache()
    if session.get("token_cache"):
        cache.deserialize(session["token_cache"])
    return cache


def _save_cache(cache):
    if cache.has_state_changed:
        session["token_cache"] = cache.serialize()


def _build_msal_app(cache=None, authority=None):
    return msal.ConfidentialClientApplication(
        config.CLIENT_ID, authority=authority or config.AUTHORITY,
        client_credential=config.CLIENT_SECRET, token_cache=cache)


def _build_auth_url(authority=None, scopes=None, state=None):
    return _build_msal_app(authority=authority).get_authorization_request_url(
        scopes or [],
        scopes or [],
        state=state or str(uuid.uuid4()),
        redirect_uri=url_for("authorized", _external=True))


def _get_token_from_cache(scope=None):
    cache = _load_cache()  # This web app maintains one cache per session
    cca = _build_msal_app(cache=cache)
    accounts = cca.get_accounts()
    if accounts:  # So all account(s) belong to the current signed-in user
        result = cca.acquire_token_silent(scope, account=accounts[0])
        _save_cache(cache)
        return result


def admin_required(func):
    @wraps(func)
    def login_wrapper(*args, **kwargs):
        if not session.get("user"):
            if not current_user.username == config.ADMIN_NAME:
                return redirect(url_for("login"))
        return func(*args, **kwargs)

    return login_wrapper

app.jinja_env.globals.update(_build_auth_url=_build_auth_url)  # Used in template

from . import views