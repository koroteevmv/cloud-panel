import os
import subprocess
import time
import uuid

import msal
import requests
from flask import render_template, jsonify, redirect, request, session, url_for, flash
from flask_login import login_required, current_user, login_user, logout_user

import config
from app import app, admin_required, logger, login_manager, db, User, _build_auth_url, _load_cache, _build_msal_app, \
    _save_cache, _get_token_from_cache, Image, Machine
from app.controller import get_machines, is_owned, delete_machine, get_images, is_unique, \
    get_port, is_disk_available, is_ram_available, vm_launch, vm_stop
from app.forms import LoginForm
from config import HOSTNAME, image_folder


@app.route("/")
@login_required
def index():
    vms = get_machines(current_user.fullname)
    print(vms)
    return render_template('vm_list.html',
                           vms=vms, admin=(current_user.fullname == config.ADMIN_NAME), hostname=HOSTNAME, )

@app.route("/settings/")
@admin_required
def settings():
    images = get_images()
    # TODO загрузка и скачивание образа
    return render_template('settings.html', images=images)


@app.route('/launch/<string:id>')
@login_required
def launch(id):
    if not is_owned(vm_id=id, username=current_user.fullname):
        logger.warning(f"User <{current_user.fullname}> tried to launch someone's vm id <{id}>")
        return redirect("/")

    if not is_ram_available():
        logger.warning(f"No free ram available to start new VM.")
        return redirect("/")

    try:
        subprocess.check_output(f'vboxmanage startvm --type headless {id}', shell=True)
    except:
        logger.error(f"Error starting vm id <{id}> by user <{current_user.fullname}>")
        return redirect("/")

    vm_launch(id)
    logger.info(f"Started vm id <{id}> by user <{current_user.fullname}>")
    return redirect('/')


@app.route('/stop/<string:id>')
@login_required
def stop(id):
    if not is_owned(vm_id=id, username=current_user.fullname):
        return redirect("/")
    try:
        subprocess.check_output(f'vboxmanage controlvm {id} poweroff', shell=True)
    except:
        logger.error(f"Error stopping vm id <{id}> by user <{current_user.fullname}>")
        return redirect('/')

    vm_stop(id)
    logger.info(f"Stopped vm id <{id}> by user <{current_user.fullname}>")
    return redirect('/')


@app.route('/create_vm/', methods=['POST', 'GET'])
@login_required
def create_vm():
    if request.method == 'POST':
        name = request.form["name"]
        user = current_user.fullname

        logger.warning(f"User <{user}> has issued a request top create a vm named <{name}>")

        if not is_unique(name):
            logger.warning(f"Error creating vm named {name}. The name is not unique")
            return redirect("/create_vm/")
        
        filename = os.path.abspath(os.path.join(image_folder, request.form["image"]))
        try:
            subprocess.check_output(f'vboxmanage import {filename} --vsys 0 --vmname {request.form["name"]}', shell=True)
            logger.info(f"Imported vm named <{name}> by <{user}>.")
        except:
            logger.error(f"Error importing vm named <{name}> by <{user}>.")
            return redirect("/create_vm/")

        try:
            subprocess.check_output(f'vboxmanage modifyvm {request.form["name"]} --nic1 nat', shell=True)
            logger.info(f"Setted up NAT vm named <{name}> by <{user}>.")
        except:
            logger.error(f"Error modyfying vm named <{name}> by <{user}>. Error setting network adapter to NAT")
            return redirect("/create_vm/")

        vms = subprocess.check_output('vboxmanage list vms', shell=True).decode('utf-8').split('\n')[:-1]
        vms = [tuple(vm.split(' ')) for vm in vms]
        print(vms[::-1])
        id = [(id[1:-1]) for (name, id) in vms if name[1:-1] == request.form["name"]]
        print(id)
        if len(id) != 1:
            logger.error(f"Smth wrong with registering vm named <{name}> created by <{user}>")
            return redirect('/')

        port = get_port()
        logger.debug(f"Port <{port}> has been assigned to vm named <{name}> created by <{user}>")
        if port is None:
            logger.warning(f"Error creating vm named {name}. No free ports left")
            return redirect("/create_vm/")

        # time.sleep(5)
        try:
            subprocess.check_output(f'vboxmanage modifyvm {id[0]} --natpf1 delete ssh-forwarding', shell=True)
            logger.debug(f"Ssh-forwarding rule deleted for new vm named <{name}>.")
        except:
            logger.debug(f"Ssh-forwarding rule not deleted for new vm named <{name}>.")

        try:
            subprocess.check_output(f'vboxmanage modifyvm {id[0]} --natpf1 "ssh-forwarding,tcp,,{port},,22"', shell=True)
            logger.debug(f"Ssh-forwarding rule issued for new vm named <{name}>.")
        except:
            logger.error(f"Error ssh forwarding for vm named <{name}> created by <{user}>")
            return redirect("/")

        logger.debug(f"New VM named <{name}> created successfully by <{user}>")

        machine = Machine(
            name=request.form["name"],
            id_string=id[0],
            owner_id=db.session.query(User).filter(User.fullname == user).first().id,
            image_id=db.session.query(Image).filter(Image.name == request.form["image"]).first().id,
            port=port,
            username=db.session.query(Image).filter(Image.name == request.form["image"]).first().username,
            running=False
        )
        db.session.add(machine)
        db.session.commit()
        return redirect('/')

    if not is_disk_available():
        logger.warning(f"Not enough disk space for a new machine")
        return redirect("/")
    if not os.path.isdir(image_folder):
        return redirect('/settings/')
    images = [file for file in os.listdir(image_folder) if file.endswith('.ova')]
    return render_template('create.html', images=images)


@app.route('/delete/<string:id>')
@login_required
def delete(id):
    if not is_owned(vm_id=id, username=current_user.fullname):
        logger.warn(f"Try deleting vm id <{id}> by <{current_user.fullname}>")
        return redirect("/")
    try:
        subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    except:
        logger.error(f"Error deleting vm id <{id}> by <{current_user.fullname}>")

    logger.warning(f"Deleted vm id <{id}> by <{current_user.fullname}>")
    delete_machine(vm_id=id)
    time.sleep(4.0)
    return redirect('/')


@app.route('/monitor/')
@login_required
def monitor():
    import psutil
    vms = [vm for vm in get_machines(user=current_user.fullname) if vm.running]
    disk_per = psutil.disk_usage("/")[-1]
    return jsonify(cpu=psutil.cpu_percent(),
                   mem_per=psutil.virtual_memory().percent,
                   mem_total=psutil.virtual_memory().total,
                   running=len(vms),
                   disk_per=disk_per
                   )


@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(user_id)


@app.route("/login")
def login():
    session["state"] = str(uuid.uuid4())
    auth_url = _build_auth_url(scopes=config.SCOPE, state=session["state"])
    return render_template("login.html", auth_url=auth_url, version=msal.__version__)


@app.route('/login_passwd/', methods=['post', 'get'])
def login_passwd():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.query(User).filter(User.fullname == form.username.data).first()
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
        fullname=users_name, email=users_email, login_way='msft'
    )

    # Doesn't exist? Add it to the database.
    user_from_db = db.session.query(User).filter(User.fullname == users_name).first()
    if not user_from_db:
        db.session.add(user)
        db.session.commit()
        user_from_db = db.session.query(User).filter(User.fullname == users_name).first()
        logger.warning(f"New user login via MSFT attempt: {session['user']}")
    elif user_from_db.login_way == 'msft':
        logger.info(f"User login via MSFT attempt: {session['user']}")
    else:
        logger.warning(f"User login via MSFT attempt: {session['user']}. This is it's first login via MSFT")
    login_user(user_from_db, remember=True)
    return redirect(request.args.get('next') or url_for("index"))


@app.route("/logout")
def logout():
    logger.info(f'User "{current_user.fullname}" logged out')
    session.clear()  # Wipe out user and its token cache from session
    logout_user()
    return redirect("/")


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