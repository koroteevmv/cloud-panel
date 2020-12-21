import logging
import os
import subprocess
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


def get_machines(user):
    vms = subprocess.check_output('vboxmanage list vms', shell=True).decode('utf-8').split('\n')[:-1]
    vms = [tuple(vm.split(' ')) for vm in vms]
    vms = [{'name': name[1:-1],
            'id': id[1:-1]} for (name, id) in vms]

    running_vms = subprocess.check_output('vboxmanage list runningvms | cut -d " " -f 2', shell=True).decode(
        'utf-8').split('\n')[:-1]
    running_vms = [x[1:-1] for x in running_vms]

    for vm in vms:
        db_vm = db.session.query(Machine).filter(Machine.id_string == vm['id']).first()
        if not db_vm:
            db_vm = Machine(
                name=vm['name'],
                id_string=vm['id'],
                owner_id=db.session.query(User).filter(User.username == config.ADMIN_NAME).first().id
            )
            db.session.add(db_vm)
            db.session.commit()
        stream = os.popen(f'VBoxManage showvminfo {vm["id"]}')
        vm["desc"] = stream.read().replace('\n', '<br> \n')
        vm["running"] = vm['id'] in running_vms

        stream = os.popen(f'VBoxManage showvminfo {vm["id"]} | grep Rule | cut -d "=" -f 5')
        vm["port"] = stream.read().split(', ')[0][1:]

        vm['owner'] = db.session.query(User).filter(User.id == db_vm.owner_id).first().username
        if db_vm.image_id is not None:
            vm['username'] = db.session.query(Image).filter(Image.id == db_vm.image_id).first().username
        else:
            vm['username'] = config.DEFAULT_USERNAME

    # TODO пройтись по всем машинам в БД и удалить лишние.
    if user != config.ADMIN_NAME:
        vms = [vm for vm in vms if vm['owner'] == db.session.query(User).filter(User.username == user).first().username]

    return vms


def is_owned(vm_id, username):
    if username == config.ADMIN_NAME:
        logger.info(f"Ownership check. Admin rights. User - {username}")
        return True
    real_owner = db.session.query(Machine).filter(Machine.id_string == vm_id).first().owner_id
    real_owner = db.session.query(User).filter(User.id == real_owner).first().username
    logger.info(f"Ownership check. User - {username}, real owner - {real_owner}")
    return username == real_owner


def delete_machine(vm_id):
    db_machine = db.session.query(Machine).filter(Machine.id_string == vm_id).first()
    db.session.delete(db_machine)
    db.session.commit()


def get_images():
    images = [file for file in os.listdir(config.image_folder) if file.endswith('.ova')]
    for image in images:
        db_image = db.session.query(Image).filter(Image.filename == image).first()
        if not db_image:
            db_image = Image(
                filename=image, name=image, description='', username=config.DEFAULT_USERNAME,
            )
            db.session.add(db_image)
            db.session.commit()
    return db.session.query(Image).all()


def add_vm_to_db(image, name, user, id_string):
    print(image, name, user, id_string)
    machine = Machine(
        name=name,
        id_string=id_string,
        owner_id=db.session.query(User).filter(User.username == user).first().id,
        image_id=db.session.query(Image).filter(Image.name == image).first().id,
    )
    db.session.add(machine)
    db.session.commit()


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