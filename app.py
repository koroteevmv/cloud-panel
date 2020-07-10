import os
import subprocess

from flask import Flask, render_template, redirect

app = Flask(__name__)


@app.route('/')
def list_vms():
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

    # return str(vms)
    return render_template('vm_list.html',
                           vms=vms, user='koroteev', hostname='localhost')


@app.route('/launch/<string:id>')
def launch(id):
    port = 22002

    subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 delete ssh-forwarding', shell=True)
    subprocess.check_output(f'vboxmanage modifyvm {id} --natpf1 "ssh-forwarding,tcp,,{port},,22"', shell=True)
    subprocess.check_output(f'vboxmanage startvm --type headless {id}', shell=True)

    return redirect('/')


@app.route('/stop/<string:id>')
def stop(id):
    subprocess.check_output(f'vboxmanage controlvm {id} poweroff', shell=True)
    return redirect('/')


@app.route('/create_vm/')
def create_vm():
    images=[]
    return render_template('create.html', images=images)


@app.route('/delete/<string:id>')
def delete(id):
    subprocess.check_output(f'vboxmanage unregistervm {id}', shell=True)
    return redirect('/')


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
