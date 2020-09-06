import glob
import os
import subprocess
from random import randint

from flask import Flask, render_template, redirect, request, jsonify

app = Flask(__name__)


image_folder = '/home/koroteev/Documents'
low_port = 20000
high_port = 30000
user='koroteev'
hostname='localhost'


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
                           vms=vms, user=user, hostname=hostname)


@app.route('/launch/<string:id>')
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
        filename = os.path.join(image_folder, request.form["image"])
        subprocess.check_output(f'vboxmanage import {request.form["image"]} --vsys 0 --vmname {request.form["name"]}', shell=True)
        subprocess.check_output(f'vboxmanage modifyvm {request.form["name"]} --nic1 nat', shell=True)

        return redirect('/')

    if not os.path.isdir(image_folder):
        return redirect('/settings/')

    os.chdir(image_folder)
    images = [file for file in glob.glob("*.ova")]
    return render_template('create.html', images=images)


@app.route('/delete/<string:id>')
def delete(id):
    subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    return redirect('/')

@app.route('/monitor/')
def monitor():
    import psutil
    vms = [vm for vm in get_list()if vm['running']]
    return jsonify(cpu=psutil.cpu_percent(),
                   mem_per=psutil.virtual_memory().percent,
                   mem_total=psutil.virtual_memory().total,
                   running=len(vms), )


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
