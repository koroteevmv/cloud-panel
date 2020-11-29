import os
import subprocess
import uuid
from datetime import datetime
from functools import wraps
from random import randint

import msal
import requests
from flask import Flask, render_template, redirect, request, jsonify, flash
from flask import session, url_for
from flask_login import (
    LoginManager,
    login_user,
    logout_user, UserMixin, current_user, login_required,
)
# from flask_session import Session  # https://pythonhosted.org/Flask-Session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash,  check_password_hash
from wtforms import StringField, SubmitField, TextAreaField,  BooleanField, PasswordField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm

import app_config

app = Flask(__name__)

app.config.from_object(app_config)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sqlite_db'
app.config['SECRET_KEY'] = 'a really really really really long secret key'

# Session(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
db = SQLAlchemy(app)

# from werkzeug.middleware.proxy_fix import ProxyFix

# app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

image_folder = './images/'
low_port = 40000
high_port = 50000
user = 'user'
hostname = '77.37.204.9'


########################################################################################################################

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(user_id)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer(), primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    login_way = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(100), nullable=True)
    created_on = db.Column(db.DateTime(), default=datetime.utcnow)
    updated_on = db.Column(db.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return "<{}:{}>".format(self.id, self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # print(self.password_hash, password)
        return check_password_hash(self.password_hash, password)


db.create_all()


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField()


########################################################################################################################


@app.route("/login")
def login():
    session["state"] = str(uuid.uuid4())
    # Technically we could use empty list [] as scopes to do just sign in,
    # here we choose to also collect end user consent upfront
    auth_url = _build_auth_url(scopes=app_config.SCOPE, state=session["state"])
    return render_template("login.html", auth_url=auth_url, version=msal.__version__)


@app.route('/login_passwd/', methods=['post', 'get'])
def login_passwd():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.query(User).filter(User.username == form.username.data).first()
        print(user)
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('index'))

        flash("Неправильный логин/пароль", 'error')
        return redirect(url_for('login_passwd'))

    return render_template('login_passwd.html', form=form)


@app.route(app_config.REDIRECT_PATH)  # Its absolute URL must match your app's redirect_uri set in AAD
def authorized():
    if request.args.get('state') != session.get("state"):
        return redirect(url_for("index"))  # No-OP. Goes back to Index page
    if "error" in request.args:  # Authentication/Authorization failure
        return render_template("auth_error.html", result=request.args)
    if request.args.get('code'):
        cache = _load_cache()
        result = _build_msal_app(cache=cache).acquire_token_by_authorization_code(
            request.args['code'],
            scopes=app_config.SCOPE,  # Misspelled scope would cause an HTTP 400 error here
            redirect_uri=url_for("authorized", _external=True))
        if "error" in result:
            return render_template("auth_error.html", result=result)
        session["user"] = result.get("id_token_claims")
        _save_cache(cache)

    # print(session["user"])

    users_email = session["user"]["preferred_username"]
    users_name = ' '.join(session["user"]["name"].split(' ')[0:2])
    user = User(
        username=users_name, email=users_email, login_way='msft'
    )
    print(user)
    # Doesn't exist? Add it to the database.
    user_from_db = db.session.query(User).filter(User.username == users_name).first()
    if not user_from_db:
        db.session.add(user)
        db.session.commit()
        user_from_db = db.session.query(User).filter(User.username == users_name).first()
    elif user_from_db.login_way == 'msft':
        # print("Login w/ MSFT")
        pass
    else:
        print("Login w/ new MSFT")
        pass
    # Begin user session by logging the user in
    # print("111111", current_user)
    login_user(user_from_db, remember=True)
    # print("111111", current_user)
    return redirect(request.args.get('next') or url_for("index"))


@app.route("/logout")
def logout():
    session.clear()  # Wipe out user and its token cache from session
    logout_user()
    return redirect("/")
    # return redirect(  # Also logout from your tenant's web session
    #     app_config.AUTHORITY + "/oauth2/v2.0/logout" +
    #     "?post_logout_redirect_uri=" + url_for("index", _external=True))


@app.route("/graphcall")
def graphcall():
    token = _get_token_from_cache(app_config.SCOPE)
    if not token:
        return redirect(url_for("login"))
    graph_data = requests.get(  # Use token to call downstream service
        app_config.ENDPOINT,
        headers={'Authorization': 'Bearer ' + token['access_token']},
    ).json()
    return render_template('display.html', result=graph_data)


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
        app_config.CLIENT_ID, authority=authority or app_config.AUTHORITY,
        client_credential=app_config.CLIENT_SECRET, token_cache=cache)


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


app.jinja_env.globals.update(_build_auth_url=_build_auth_url)  # Used in template


########################################################################################################################


def get_list():
    vms = subprocess.check_output('vboxmanage list vms', shell=True).decode('utf-8').split('\n')[:-1]
    vms = [tuple(vm.split(' ')) for vm in vms]
    vms = [{'name': name[1:-1],
            'id': id[1:-1]} for (name, id) in vms]

    running_vms = subprocess.check_output('vboxmanage list runningvms | cut -d " " -f 2', shell=True).decode(
        'utf-8').split('\n')[:-1]
    running_vms = [x[1:-1] for x in running_vms]

    for vm in vms:
        stream = os.popen(f'VBoxManage showvminfo {vm["id"]}')
        vm["desc"] = stream.read().replace('\n', '<br> \n')
        vm["running"] = vm['id'] in running_vms

        stream = os.popen(f'VBoxManage showvminfo {vm["id"]} | grep Rule | cut -d "=" -f 5')
        vm["port"] = stream.read().split(', ')[0][1:]

    return vms


# def login_required(func):
#     @wraps(func)
#     def login_wrapper(*args, **kwargs):
#         if not session.get("user"):
#             return redirect(url_for("login"))
#         return func(*args, **kwargs)
#
#     return login_wrapper


def admin_required(func):
    @wraps(func)
    def login_wrapper(*args, **kwargs):
        if not session.get("user"):
            if not session["user"]["name"] == "Коротеев Михаил Викторович":
                return redirect(url_for("login"))
        return func(*args, **kwargs)

    return login_wrapper


@app.route("/")
@login_required
def index():
    vms = get_list()
    print("222", current_user.username)
    return render_template('vm_list.html',
                           vms=vms, vm_user=user, hostname=hostname,)


@app.route('/launch/<string:id>')
@login_required
def launch(id):
    port = 22003

    vms = get_list()
    occupied_ports = set([vm['port'] for vm in vms])
    print(occupied_ports)

    while True:
        port = randint(low_port, high_port)
        if port not in occupied_ports:
            break
    print(port)
    try:
        subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 "ssh-forwarding,tcp,,{port},,22"', shell=True)
        subprocess.check_output(f'vboxmanage startvm --type headless {id}', shell=True)
    except:
        subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 delete ssh-forwarding', shell=True)

    return redirect('/')


@app.route('/stop/<string:id>')
@login_required
def stop(id):
    subprocess.check_output(f'vboxmanage controlvm {id} poweroff', shell=True)
    try:
        subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 delete ssh-forwarding', shell=True)
    except:
        pass
    return redirect('/')


@app.route('/create_vm/', methods=['POST', 'GET'])
@login_required
def create_vm():
    if request.method == 'POST':
        # print(dict(request.form))
        print(os.getcwd(), image_folder, request.form["image"])
        filename = os.path.abspath(os.path.join(image_folder, request.form["image"]))
        subprocess.check_output(f'vboxmanage import {filename} --vsys 0 --vmname {request.form["name"]}', shell=True)
        subprocess.check_output(f'vboxmanage modifyvm {request.form["name"]} --nic1 nat', shell=True)

        return redirect('/')

    # TODO загрузка и скачивание образа

    if not os.path.isdir(image_folder):
        return redirect('/settings/')

    # os.chdir(image_folder)
    images = [file for file in os.listdir(image_folder) if file.endswith('.ova')]
    return render_template('create.html', images=images)


@app.route('/delete/<string:id>')
@login_required
def delete(id):
    subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    return redirect('/')


@app.route('/monitor/')
def monitor():
    import psutil
    vms = [vm for vm in get_list() if vm['running']]
    disk_per = psutil.disk_usage("/")[-1]
    return jsonify(cpu=psutil.cpu_percent(),
                   mem_per=psutil.virtual_memory().percent,
                   mem_total=psutil.virtual_memory().total,
                   running=len(vms),
                   disk_per=disk_per
                   )


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
