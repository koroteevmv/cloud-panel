import glob
import os
import subprocess
from random import randint

from app import app
from flask import render_template, request, redirect, url_for, flash, make_response, session
# from flask_login import login_required, login_user,current_user, logout_user
# from .models import User, Post, Category, Feedback, db
# from .forms import ContactForm, LoginForm
# from .utils import send_mail


def get_list():
    vms = subprocess.check_output('vboxmanage list vms', shell=True).decode('utf-8').split('\n')[:-1]
    vms = [tuple(vm.split(' ')) for vm in vms]
    vms = [{'name': name[1:-1],
            'id': id[1:-1]} for (name, id) in vms]

    running_vms = subprocess.check_output('vboxmanage list runningvms | cut -d " " -f 2', shell=True).decode('utf-8').split('\n')[:-1]
    running_vms = [x[1:-1] for x in running_vms]

    for vm in vms:
        stream = os.popen(f'VBoxManage showvminfo {vm["id"]}')
        vm["desc"] = stream.read().replace('\n', '<br> \n')
        vm["running"] = vm['id'] in running_vms

        stream = os.popen(f'VBoxManage showvminfo {vm["id"]} | grep Rule | cut -d "=" -f 5')
        vm["port"] = stream.read().split(', ')[0][1:]

    return vms


@app.route('/')
def list_vms():
    vms = get_list()
    return render_template('vm_list.html',
                           vms=vms, user=app.config['USER'],
                           hostname=app.config['HOSTNAME'])


@app.route('/launch/<string:id>')
def launch(id):
    port = 22003

    vms = get_list()
    occupied_ports = set([vm['port'] for vm in vms])
    print(occupied_ports)

    while True:
        port = randint(app.config['LOW_PORT'], app.config['HIGH_PORT'])
        if port not in occupied_ports:
            break
    print(port)
    subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 "ssh-forwarding,tcp,,{port},,22"', shell=True)
    subprocess.check_output(f'vboxmanage startvm --type headless {id}', shell=True)

    return redirect('/')


@app.route('/stop/<string:id>')
def stop(id):
    subprocess.check_output(f'vboxmanage controlvm {id} poweroff', shell=True)
    try:
        subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 delete ssh-forwarding', shell=True)
    except:
        pass
    return redirect('/')


@app.route('/create_vm/', methods=['POST', 'GET'])
def create_vm():
    if request.method == 'POST':
        print(dict(request.form))
        filename = os.path.join(app.config['IMAGE_FOLDER'], request.form["image"])
        subprocess.check_output(f'vboxmanage import {request.form["image"]} --vsys 0 --vmname {request.form["name"]}', shell=True)
        subprocess.check_output(f'vboxmanage modifyvm {request.form["name"]} --nic1 nat', shell=True)

        return redirect('/')

    os.chdir(app.config['IMAGE_FOLDER'])
    images = [file for file in glob.glob("*.ova")]
    return render_template('create.html', images=images)


@app.route('/delete/<string:id>')
def delete(id):
    subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    return redirect('/')
