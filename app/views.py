import os
import subprocess
import time
import uuid
import logging
from random import randint

import msal
import requests
from flask import render_template, jsonify, redirect, request, url_for, session, flash
from flask_login import login_required, current_user, logout_user, login_user

import config
from app import app, get_machines, _load_cache, _build_msal_app, _save_cache, _build_auth_url, \
    _get_token_from_cache, db, login_manager, admin_required, get_images, add_vm_to_db, is_owned, delete_machine
from app.forms import LoginForm
from app.models import User
from config import DEFAULT_USERNAME, HOSTNAME, image_folder, high_port, low_port


logger = logging.getLogger('UI')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('./app.log')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(user_id)


@app.route("/login")
def login():
    session["state"] = str(uuid.uuid4())
    # Technically we could use empty list [] as scopes to do just sign in,
    # here we choose to also collect end user consent upfront
    auth_url = _build_auth_url(scopes=config.SCOPE, state=session["state"])
    return render_template("login.html", auth_url=auth_url, version=msal.__version__)


@app.route('/login_passwd/', methods=['post', 'get'])
def login_passwd():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.query(User).filter(User.username == form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            logger.info(f"User login via passwd success. Login: '{form.username.data}', passwd: '{form.password.data}'")
            return redirect(url_for('index'))
        flash("Неправильный логин/пароль", 'error')
        logger.warning(f"User login via passwd fail. Login: '{form.username.data}', passwd: '{form.password.data}'")
        return redirect(url_for('login_passwd'))

    return render_template('login_passwd.html', form=form)


@app.route(config.REDIRECT_PATH)  # Its absolute URL must match your app's redirect_uri set in AAD
def authorized():
    if request.args.get('state') != session.get("state"):
        return redirect(url_for("index"))  # No-OP. Goes back to Index page
    if "error" in request.args:  # Authentication/Authorization failure
        return render_template("auth_error.html", result=request.args)
    if request.args.get('code'):
        cache = _load_cache()
        result = _build_msal_app(cache=cache).acquire_token_by_authorization_code(
            request.args['code'],
            scopes=config.SCOPE,  # Misspelled scope would cause an HTTP 400 error here
            redirect_uri=url_for("authorized", _external=True))
        if "error" in result:
            return render_template("auth_error.html", result=result)
        session["user"] = result.get("id_token_claims")
        _save_cache(cache)

    users_email = session["user"]["preferred_username"]
    users_name = ' '.join(session["user"]["name"].split(' ')[0:2])
    user = User(
        username=users_name, email=users_email, login_way='msft'
    )

    # Doesn't exist? Add it to the database.
    user_from_db = db.session.query(User).filter(User.username == users_name).first()
    if not user_from_db:
        db.session.add(user)
        db.session.commit()
        user_from_db = db.session.query(User).filter(User.username == users_name).first()
        logger.warning(f"New user login via MSFT attempt: {session['user']}")
    elif user_from_db.login_way == 'msft':
        logger.info(f"User login via MSFT attempt: {session['user']}")
    else:
        logger.warning(f"User login via MSFT attempt: {session['user']}. This is it's first login via MSFT")
    login_user(user_from_db, remember=True)
    return redirect(request.args.get('next') or url_for("index"))


@app.route("/logout")
def logout():
    logger.info(f'User "{current_user.username}" logged out')
    session.clear()  # Wipe out user and its token cache from session
    logout_user()
    return redirect("/")
    # return redirect(  # Also logout from your tenant's web session
    #     app_config.AUTHORITY + "/oauth2/v2.0/logout" +
    #     "?post_logout_redirect_uri=" + url_for("index", _external=True))


@app.route("/graphcall")
def graphcall():
    token = _get_token_from_cache(config.SCOPE)
    if not token:
        return redirect(url_for("login"))
    graph_data = requests.get(  # Use token to call downstream service
        config.ENDPOINT,
        headers={'Authorization': 'Bearer ' + token['access_token']},
    ).json()
    return render_template('display.html', result=graph_data)


@app.route("/")
@login_required
def index():
    vms = get_machines(current_user.username)
    return render_template('vm_list.html',
                           vms=vms, admin=(current_user.username == config.ADMIN_NAME), hostname=HOSTNAME, )

@app.route("/settings/")
@admin_required
def settings():
    images = get_images()
    # TODO загрузка и скачивание образа
    return render_template('settings.html', images=images)


@app.route('/launch/<string:id>')
@login_required
def launch(id):
    if not is_owned(vm_id=id, username=current_user.username):
        return redirect("/")
    # TODO проверить, что свободной паямти хватает
    port = 22003

    vms = get_machines(user=current_user.username)
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
        subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 "ssh-forwarding,tcp,,{port},,22"', shell=True)
        subprocess.check_output(f'vboxmanage startvm --type headless {id}', shell=True)

    return redirect('/')


@app.route('/stop/<string:id>')
@login_required
def stop(id):
    if not is_owned(vm_id=id, username=current_user.username):
        return redirect("/")
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
        # TODO проверить уникальность имени
        filename = os.path.abspath(os.path.join(image_folder, request.form["image"]))
        subprocess.check_output(f'vboxmanage import {filename} --vsys 0 --vmname {request.form["name"]}', shell=True)
        subprocess.check_output(f'vboxmanage modifyvm {request.form["name"]} --nic1 nat', shell=True)
        vms = subprocess.check_output('vboxmanage list vms', shell=True).decode('utf-8').split('\n')[:-1]
        vms = [tuple(vm.split(' ')) for vm in vms]
        id = [(id[1:-1]) for (name, id) in vms if name[1:-1] == request.form["name"]]
        if len(id) != 1:
            return redirect('/')
        logger.debug(id)
        add_vm_to_db(image=request.form["image"], name=request.form["name"], user=current_user.username, id_string=id[0])
        return redirect('/')

    # TODO проверка, что места на диске хватает
    if not os.path.isdir(image_folder):
        return redirect('/settings/')
    images = [file for file in os.listdir(image_folder) if file.endswith('.ova')]
    return render_template('create.html', images=images)


@app.route('/delete/<string:id>')
@login_required
def delete(id):
    if not is_owned(vm_id=id, username=current_user.username):
        return redirect("/")
    subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    delete_machine(vm_id=id)
    time.sleep(4.0)
    return redirect('/')


@app.route('/delete_image/<string:id>')
@admin_required
def delete_image(id):
    # subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    # TODO удалить запись об образе из БД
    return redirect('/settings/')


@app.route('/monitor/')
@login_required
def monitor():
    import psutil
    vms = [vm for vm in get_machines(user=current_user.username) if vm['running']]
    disk_per = psutil.disk_usage("/")[-1]
    return jsonify(cpu=psutil.cpu_percent(),
                   mem_per=psutil.virtual_memory().percent,
                   mem_total=psutil.virtual_memory().total,
                   running=len(vms),
                   disk_per=disk_per
                   )

