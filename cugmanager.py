#!/usr/bin/env python
from sqlalchemy import (Table, Column, Integer, String, DateTime, Date, 
                        ForeignKey, Text, Boolean, MetaData, 
                        and_, desc, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (backref, joinedload, subqueryload, sessionmaker,
                            relationship)
from ConfigParser import ConfigParser
from commands import getoutput as run
from hashlib import md5
from random import choice
import string
import getpass
import cmd
import os

config = ConfigParser()
config.read('cugmanager.conf')

Base = declarative_base()
engine = create_engine('sqlite:///database.db')
Session = sessionmaker(engine)

class VirtualMachine(Base):
    __tablename__ = 'vm'
    id = Column(Integer, primary_key=True)
    name = Column(Text, unique=True)
    ram = Column(Integer)
    disk = Column(Integer)
    address = Column(Text)
    netmask = Column(Text)
    router = Column(Text)
    passwd = Column(Text)
    upasswd = Column(Text)
    
    def start(self):
        run('sudo virsh start %s' % self.name)
    
    def stop(self):
        run('sudo virsh shutdown %s' % self.name)
    
    def restart(self):
        run('sudo virsh reboot %s' % self.name)
    
    def power(self):
        run('sudo virsh destroy %s' % self.name)
    
    def exists(self):
        if run('sudo virsh list --all | grep %s' % self.name) == '':
            return False
        else:
            return True
    
    def status(self):
        return run('sudo virsh domstate %s' % self.name).strip('\n')
    
    def check_password(self, password):
        h = md5()
        h.update(password)
        return self.upasswd == h.hexdigest()
    
    def update_password(self, password):
        h = md5()
        h.update(password)
        self.upasswd = h.hexdigest()
    
    def gen_upw(self):
        upw = self._genpwd(length=12)
        self.update_password(upw)
        return upw
    
    def _genpwd(self, length=8, chars=string.letters + string.digits):
        return ''.join([choice(chars) for i in range(length)])
    
    def delete(self):
        if self.exists():
            self.power()
            run('sudo virsh undefine %s' % self.name)
            run('sudo lvremove -f %s/%s' % (config.get('Settings', 'lvpath'), 
                                            self.name))
    
    def create(self, iso):
        if not self.exists():
            self.passwd = self._genpwd(length=12)
            opts = ['--autostart',
                    #'--vnc',
                    '--graphics vnc,password=%s' % self.passwd,
                    '--noautoconsole',
                    '--os-type=linux',
                    '--accelerate',
                    '--connect qemu:///system',
                    '-n %s' % self.name,
                    '--disk path=%s/%s,bus=virtio,cache=none' %\
                            (config.get('Settings', 'lvpath'), self.name),
                    '--network bridge=%s' % config.get('Settings', 'network'),
                    '--ram %s' % self.ram,
                    '--cdrom %s/%s' % (config.get('Settings', 'iso_path'), iso),
                   ]
            run('sudo lvcreate -L%sG -n %s %s' % (self.disk, 
                                             self.name, 
                                             config.get('Settings', 'vggroup')
                                            ))
            run('sudo /usr/local/bin/virt-install %s' % ' '.join(opts))
    
    def _iptables(self, allow=False):
        if self.console():
            rule = '-m state --state NEW -m tcp -p tcp --dport %s' % \
                    self.console()
            if allow:
                run('sudo iptables -D INPUT %s -j REJECT' % rule)
                #print run('iptables -A INPUT %s -j ACCEPT')
                return True
            else:
                #print run('iptables -D INPUT %s -j ACCEPT')
                run('sudo iptables -A INPUT %s -j REJECT' % rule)
                return True
        return False
    
    def enable_console(self):
        if self._iptables(allow=True):
            return True
        return False
    
    def disable_console(self):
        if self._iptables(allow=False):
            return True
        return False
    
    def console(self):
        display = run('sudo virsh vncdisplay %s' % self.name).strip('\n')\
                                                             .strip(':')
        if display is not '':
            return int(display) + 5900
        return False
        
        
VirtualMachine.metadata.create_all(engine)


class CLI(cmd.Cmd):
    prompt = 'cugkvm>'
    vm = None
    
    def __init__(self, vm):
        cmd.Cmd.__init__(self)
        self.vm = vm
        self.prompt = 'cugmanager[%s]> ' % self.vm.name
    
    def help_help(self):
        pass
    
    def do_start(self, s):
        '''start
        Start the virtual machine (Power ON)
        '''
        self.vm.start()
    
    def do_stop(self, s):
        '''stop
        Gracefully shuts the virtual machine down
        '''
        self.vm.stop()
    
    def do_power(self, s):
        '''power
        Forcefully turns the virtual machine off (Pulling the power)
        '''
        self.vm.power()
    
    def do_restart(self, s):
        '''restart
        Reboots the virtual machine gracefully
        '''
        self.vm.restart()
    
    def do_delete(self, s):
        '''delete
        Forcefully powers the virtual machine down and deletes the 
        configuration and disk.
        '''
        print 'WARNING: This will permanently erase the VM!'
        if raw_input('Continue? [yes/NO]: ').lower() == 'yes':
            print 'Deleting VM...'
            self.vm.delete()
        else:
            print 'Aborting deletion...'
    
    def do_create(self, iso):
        '''create ISO_IMAGE
        Will create a new virtual machine with the ISO specified if there is
        currently no VM definition set.
        '''
        if iso in self._get_isos():
            s = Session()
            self.vm.create(iso)
            s.merge(self.vm)
            s.commit()
            print 'Networking Information\n----------------------'
            print 'IP Address: %s' % self.vm.address
            print '   Netmask: %s' % self.vm.netmask
            print '   Gateway: %s' % self.vm.router
            print 'Nameserver: 4.2.2.2\n'
            self.do_console('')
        else:
            print '%s is not a valid ISO Image.' % s
    
    def do_status(self, s):
        '''status
        Returns the current running status of the virtual machine.
        '''
        print self.vm.status()
    
    def do_console(self, s):
        '''console
        Controls access to the VNC Console session
        
        OPTIONS:
        
        enable              Opens the console port & returns the connection
                            information
        
        disable             Closes the console port.
        
        <default>           Returns the connection information.
        '''
        d = {True: 'Success', False: 'Failed'}
        if self.vm.status() == 'running':
            if s.lower() == 'enable':
                print d[self.vm.enable_console()]
            if s.lower() == 'disable':
                print d[self.vm.disable_console()]
            else:
                print 'VNC Port: %s\nPassword: %s' % (self.vm.console(), 
                                                      self.vm.passwd)
                #print 'VNC Port: %s' % self.vm.console()
        else:
            print 'VM not running, please start the VM first.'
    
    def _get_isos(self):
        return os.listdir(config.get('Settings', 'iso_path'))
    
    def complete_create(self, text, line, begidx, endidx):
        if not text:
            return self._get_isos()
        else:
            return [s for s in self._get_isos() if s.startswith(text)]
    
    def do_exit(self, s):
        '''exit
        Exits cugmanager
        '''
        return True
    
    def do_updatepw(self, s):
        '''updatepw
        Updates the virtual machines\' login password. '''
        s = Session()
        opw = getpass.getpass('Current Password: ')
        if self.vm.check_password(opw):
            pw1 = getpass.getpass('New Password: ')
            pw2 = getpass.getpass('Confirm Password: ')
            if pw1 == pw2:
                self.vm.update_password(pw1)
                s.merge(self.vm)
                s.commit()
                print 'Password Updated.'
            else:
                print 'Password Mismatch.'
        else:
            print 'Old Password doesnt match whats on file.'
        s.close()

def login():
    #os.chdir(os.path.dirname(__file__))
    os.system('clear')
    count = 0
    s = Session()
    print 'CUGManager Login'
    while count < 3:
        name = raw_input('VM Name: ').strip()
        passwd = getpass.getpass()
        #try:
        vm = s.query(VirtualMachine).filter_by(name=name).one()
        if vm.check_password(passwd):
            CLI(vm).cmdloop()
            s.close()
            return True
        #except:
        #    pass
        count += 1
        print 'Invalid Password or VM name.\n'

if __name__ == '__main__':
    login()