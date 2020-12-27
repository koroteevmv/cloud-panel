import os
import subprocess
from random import randint

from werkzeug.utils import redirect

import config
from app import Machine, db, User, Image, app, admin_required, logger
from config import high_port, low_port


def get_machines(user):
    if user != config.ADMIN_NAME:
        user_id = db.session.query(User).filter(User.fullname == user).first().id
        return db.session.query(
            Machine.id_string,
            Machine.name,
            Machine.port,
            Machine.running,
            Machine.username,
            User.fullname
        ).join(User, Machine.owner_id == User.id).filter(Machine.owner_id == user_id).all()

    return db.session.query(
        Machine.id_string,
        Machine.name,
        Machine.port,
        Machine.running,
        Machine.username,
        User.fullname
    ).join(User, Machine.owner_id == User.id).all()


def rescan_machines():
    logger.debug("Rescan started")
    vms = subprocess.check_output('vboxmanage list vms', shell=True).decode('utf-8').split('\n')[:-1]
    vms = [tuple(vm.split(' ')) for vm in vms]
    vms = [{'name': name[1:-1],
            'id': id[1:-1]} for (name, id) in vms]

    for vm in vms:
        db_vm = db.session.query(Machine).filter(Machine.id_string == vm['id']).first()
        if not db_vm:
            logger.warning(f"During rescan new vm was found with name <{vm['name']}> and id <{vm['id']}>.")
            db_vm = Machine(
                name=vm['name'],
                id_string=vm['id'],
                owner_id=db.session.query(User).filter(User.fullname == config.ADMIN_NAME).first().id,
                running=False,
                username=config.DEFAULT_USERNAME,
            )
            db.session.add(db_vm)
            logger.debug(f"New vm named <{vm['name']}> has been added.")
            db.session.commit()

            port = get_port()
            logger.debug(f"Port <{port}> has been assigned to new vm named <{vm['name']}>.")

            try:
                subprocess.check_output(f'vboxmanage controlvm {vm["id"]} poweroff', shell=True)
            except:
                logger.error(f"Error stopping new vm id <{vm['id']}>.")

            try:
                subprocess.check_output(f'vboxmanage modifyvm {vm["id"]} --natpf1 delete ssh-forwarding', shell=True)
                logger.debug(f"Ssh-forwarding rule deleted for new vm named <{vm['name']}>.")
            except:
                logger.debug(f"Ssh-forwarding rule not deleted for new vm named <{vm['name']}>.")

            try:
                subprocess.check_output(f'vboxmanage modifyvm {vm["id"]} --natpf1 "ssh-forwarding,tcp,,{port},,22"',
                                        shell=True)
                logger.debug(f"Ssh-forwarding rule issued for new vm named <{vm['name']}>.")
            except:
                logger.error(f"Error ssh forwarding for new vm named <{vm['name']}>")

            db_vm.port=port
            logger.debug(f"New vm named <{vm['name']}> has been updated to use port <{port}>.")
            db.session.commit()


def is_owned(vm_id, username):
    if username == config.ADMIN_NAME:
        return True
    real_owner = db.session.query(Machine).filter(Machine.id_string == vm_id).first().owner_id
    real_owner = db.session.query(User).filter(User.id == real_owner).first().fullname
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


def is_unique(name):
    # TODO проверить уникальность имени
    return True


def get_port():
    """ Возвращает номер свободного порта. None если количество машин превысило размер пула портов.
    """
    vms = get_machines(user=config.ADMIN_NAME)

    if len(vms) >= high_port - low_port:
        return None

    occupied_ports = set([vm.port for vm in vms])
    # print(occupied_ports)

    while True:
        port = randint(low_port, high_port)
        if port not in occupied_ports:
            break
    return port


def is_disk_available():
    # TODO проверка, что места на диске хватает
    return True


@app.route('/delete_image/<string:id>')
@admin_required
def delete_image(id):
    # subprocess.check_output(f'vboxmanage unregistervm {id} --delete', shell=True)
    # TODO удалить запись об образе из БД
    return redirect('/settings/')


def is_ram_available():
    # TODO проверить, что свободной паямти хватает
    return True


def vm_launch(id):
    machine = db.session.query(Machine).filter(Machine.id_string == id).first()
    machine.running = True
    db.session.commit()


def vm_stop(id):
    machine = db.session.query(Machine).filter(Machine.id_string == id).first()
    machine.running = False
    db.session.commit()