#!/usr/bin/env python
# encoding: utf-8
'''
admin.py

Created by Steven McGrath on 2012-03-23.
Copyright (c) 2012 __MyCompanyName__. All rights reserved.
'''

from ConfigParser import ConfigParser
import os
import sys
import getopt
import cugmanager


help_message = '''
The help message goes here.
'''


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    os.chdir(os.path.dirname(__file__))
    config = ConfigParser()
    config.read('cugmanager.conf')
    name = None
    action = None
    ram = config.getint('Defaults', 'ram')
    disk = config.getint('Defaults', 'disk')
    address = config.get('Defaults', 'address')
    netmask = config.get('Defaults', 'netmask')
    router = config.get('Defaults', 'router')
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], 'a:r:', 
                                       ['add=', 'remove=', 'ram=', 'disk=',
                                        'address=', 'netmask=', 'router=',
                                       ])
        except getopt.error, msg:
            raise Usage(msg)
    
        # option processing
        for option, value in opts:
            if option in ('-a', '--add'):
                action = 'add'
                name = value
            if option in ('-r', '--remove'):
                action = 'remove'
                name = value
            if option == '--ram':
                ram = int(value)
            if option == '--disk':
                disk = int(value)
            if option == '--address':
                address = value
            if option == '--netmask':
                netmask = value
            if option == '--router':
                router = value
    
    except Usage, err:
        print >> sys.stderr, sys.argv[0].split('/')[-1] + ': ' + str(err.msg)
        print >> sys.stderr, '\t for help use --help'
        return 2
    
    if name is not None and action is not None:
        s = cugmanager.Session()
        try:
            vm = s.query(cugmanager.VirtualMachine).filter_by(name=name).one()
        except:
            vm = None
        
        if action == 'remove':
            if vm is not None:
                print 'Powering off, deleting, and undefining the VM...'
                vm.delete()
                print 'Removing the VM allotment from the database...'
                s.delete(vm)
                s.commit()
                print 'Allotment removal complete.'
            else:
                print 'No VM by that name to remove.'
        if action == 'add':
            if vm == None:
                print 'Creating a new VM allotment based on the following:'
                print '       RAM: %4d MB' % ram
                print '      Disk: %3d GB' % disk
                print 'IP Address: %s' % address
                print '   NetMask: %s' % netmask
                print ' Router IP: %s' % router
                
                vm = cugmanager.VirtualMachine(name=name, ram=ram, disk=disk,
                                               address=address,
                                               netmask=netmask,
                                               router=router)
                upw = vm.gen_upw()
                s.add(vm)
                s.commit()
                
                print '\nLogin information for this VM will be:'
                print '   VM Name: %s' % vm.name
                print   'Password: %s' % upw
            else:
                print 'A VM Allotment by that name already exists!'                

if __name__ == '__main__':
    sys.exit(main())
