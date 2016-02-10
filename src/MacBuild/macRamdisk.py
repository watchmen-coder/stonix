###############################################################################
#                                                                             #
# Copyright 2015.  Los Alamos National Security, LLC. This material was       #
# produced under U.S. Government contract DE-AC52-06NA25396 for Los Alamos    #
# National Laboratory (LANL), which is operated by Los Alamos National        #
# Security, LLC for the U.S. Department of Energy. The U.S. Government has    #
# rights to use, reproduce, and distribute this software.  NEITHER THE        #
# GOVERNMENT NOR LOS ALAMOS NATIONAL SECURITY, LLC MAKES ANY WARRANTY,        #
# EXPRESS OR IMPLIED, OR ASSUMES ANY LIABILITY FOR THE USE OF THIS SOFTWARE.  #
# If software is modified to produce derivative works, such modified software #
# should be clearly marked, so as not to confuse it with the version          #
# available from LANL.                                                        #
#                                                                             #
# Additionally, this program is free software; you can redistribute it and/or #
# modify it under the terms of the GNU General Public License as published by #
# the Free Software Foundation; either version 2 of the License, or (at your  #
# option) any later version. Accordingly, this program is distributed in the  #
# hope that it will be useful, but WITHOUT ANY WARRANTY; without even the     #
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    #
# See the GNU General Public License for more details.                        #
#                                                                             #
###############################################################################
"""
@author: Roy Nielsen
@change: 2016/02/03 ekkehard converted from log_message to print

"""
from __future__ import absolute_import
import os
import re
import sys
from tempfile import mkdtemp
from subprocess import Popen, PIPE, STDOUT

sys.path.append("../..")

from src.tests.lib.logdispatcher_lite import LogDispatcher, LogPriority
from src.stonix_resources.environment import Environment

LOGGER = LogDispatcher(Environment())

###############################################################################

class RamDisk(object) :
    """
    Class to manage a ramdisk
    
    utilizes commands I've used to manage ramdisks
    
    Size passed in must be passed in as 1Mb chunks
    
    @author: Roy Nielsen
    """
    def __init__(self, size=0, mountpoint="") :
        """
        Constructor
        """
        self.logger = LOGGER
        self.version = "0.9.4"
        #####
        # Calculating the size of ramdisk in 1Mb chunks     
        self.diskSize = str(int(size) * 1024 * 1024 / 512)
        self.volumename = mountpoint

        self.hdiutil = "/usr/bin/hdiutil"
        self.diskutil = "/usr/sbin/diskutil"

        if mountpoint:
            self.logger.log(LogPriority.INFO, "\n\n\n\tMOUNTPOINT: " + str(mountpoint) + "\n\n\n")
            self.mntPoint = mountpoint
        else:
            self.mntPoint = ""

        self.myRamdiskDev = ""
        
        success = True

        if size == 0 :
            success  = False
        if not self.__isMemoryAvailable() :
            success = False
            self.logger.log(LogPriority.INFO, "Physical memory not available to create ramdisk.")

        if success :

            if self.volumename :
                #####
                # eventually have checking to make sure that directory doesn't already exist.
                self.logger.log(LogPriority.INFO, "Attempting to use mount point of: " + str(mountpoint))
                self.mntPoint = mountpoint
            else :
                self.logger.log(LogPriority.INFO, "Attempting to acquire a radomized mount point. . .")
                if not self.__getRandomizedMountpoint() :
                    success = False

            if success:
                if not self.__create():
                    success = False
                    self.logger.log(LogPriority.INFO, "Create appears to have failed..")
                else:
                    if not self.__mount():
                        success = False
                        self.logger.log(LogPriority.INFO, "Mount appears to have failed..")
                    else:
                        if not self.__remove_journal():
                            success = False
                            self.logger.log(LogPriority.INFO, "Remove journal appears to have failed..")

        self.success = success
        self.logger.log(LogPriority.INFO, "Success: " + str(self.success))
        self.logger.log(LogPriority.INFO, "Mount point: " + str(self.mntPoint))
        self.logger.log(LogPriority.INFO, "Device: " + str(self.myRamdiskDev))

    ###########################################################################

    def get_data(self):
        """
        Getter for mount data, and if the mounting of a ramdisk was successful
        """
        self.logger.log(LogPriority.INFO, "Success: " + str(self.success))
        self.logger.log(LogPriority.INFO, "Mount point: " + str(self.mntPoint))
        self.logger.log(LogPriority.INFO, "Device: " + str(self.myRamdiskDev))
        return (self.success, str(self.mntPoint), str(self.myRamdiskDev))

    ###########################################################################

    def __getRandomizedMountpoint(self) :
        """
        Create a randomized (secure) mount point - per python's implementation
        of mkdtemp - a way to make an unguessable directory on the system
        
        @author: Roy Nielsen
        """
        success = False
        try :
            self.mntPoint = mkdtemp()
        except Exception, err :
            self.logger.log(LogPriority.INFO, "Exception trying to create temporary directory")
        else :
            success = True
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in __get_randomizedMountpoint: " + str(self.mntPoint))            
        return success
    
    ###########################################################################

    def __create(self) :
        """
        Create a ramdisk device
        
        @author: Roy Nielsen
        """
        retval = None
        reterr = None
        success = False
        cmd = [self.hdiutil, "attach", "-nomount", "ram://" + self.diskSize]
        retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        self.logger.log(LogPriority.INFO, "retval: " + str(retval))
        self.logger.log(LogPriority.INFO,"reterr: " + str(reterr))
        if reterr:
            success = False
            raise Exception("Error trying to create ramdisk(" + str(reterr).strip() + ")")
        else:
            self.myRamdiskDev = retval.strip()
            self.logger.log(LogPriority.INFO,"Device: \"" + str(self.myRamdiskDev) + "\"")
            success = True
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in __create")            
        return success
    
    ###########################################################################

    def __mount(self) :
        """
        Mount the disk
        
        @author: Roy Nielsen
        """
        success = False
        success = self.__attach()
        return success

    ###########################################################################

    def __attach(self):
        """
        Attach the device so it can be formatted
        
        @author: Roy Nielsen
        """
        success = False
        if self.__partition():
            success = True
        
        
        # eraseVolume format name device
            if self.mntPoint:
                #####
                # "Mac" unmount (not eject)
                cmd = [self.diskutil, "unmount", self.myRamdiskDev + "s1"]
                retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
                if not reterr:
                    success = True
                
                if success:
                    #####
                    # remount to self.mntPoint                
                    cmd = [self.diskutil, "mount", "-mountPoint", self.mntPoint, self.myRamdiskDev + "s1"]
                    retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
                    if not reterr:
                        success = True
            self.logger.log(LogPriority.INFO, "*******************************************")
            self.logger.log(LogPriority.INFO, r"retval:   " + str(retval).strip())
            self.logger.log(LogPriority.INFO, r"reterr:   " + str(reterr).strip())
            self.logger.log(LogPriority.INFO, r"mntPoint: " + str(self.mntPoint).strip())
            self.logger.log(LogPriority.INFO, r"device:   " + str(self.myRamdiskDev).strip())
            self.logger.log(LogPriority.INFO, "*******************************************")
            self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in __mount")
        return success

    ###########################################################################

    def __remove_journal(self) :
        """
        Having a journal in ramdisk makes very little sense.  Remove the journal
        after creating the ramdisk device
        
        cmd = ["/usr/sbin/diskutil", "disableJournal", "force", myRamdiskDev]
        
        using "force" doesn't work on a mounted filesystem, without it, the command
        will work on a mounted file system

        @author: Roy Nielsen
        """
        success = False
        cmd = [self.diskutil, "disableJournal", self.myRamdiskDev + "s1"]
        retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        if not reterr:
            success = True
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in __remove_journal")
        return success
    
    ###########################################################################

    def unmount(self) :
        """
        Unmount the disk - same functionality as __eject on the mac
        
        @author: Roy Nielsen
        """
        success = False
        if self.__eject() :
            success = True
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in unmount")
        return success

    ###########################################################################

    def eject(self) :
        """
        Eject the ramdisk
        Detach (on the mac) is a better solution than unmount and eject 
        separately.. Besides unmounting the disk, it also stops any processes 
        related to the mntPoint
        """
        success = False
        cmd = [self.hdiutil, "detach", self.myRamdiskDev]
        retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        if not reterr:
            success = True
        self.logger.log(LogPriority.INFO, "*******************************************")
        self.logger.log(LogPriority.INFO, "retval: \"" + str(retval).strip() + "\"")
        self.logger.log(LogPriority.INFO, "reterr: \"" + str(reterr).strip() + "\"")
        self.logger.log(LogPriority.INFO, "*******************************************")
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in eject")
        return success
        
    ###########################################################################

    def __format(self) :
        """
        Format the ramdisk
        
        @author: Roy Nielsen
        """
        success = False
        cmd = ["/sbin/newfs_hfs", "-v", "ramdisk", self.myRamdiskDev]
        retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        if not reterr:
            success = True
        self.logger.log(LogPriority.INFO, "*******************************************")
        self.logger.log(LogPriority.INFO, "retval: \"" + str(retval).strip() + "\"")
        self.logger.log(LogPriority.INFO, "reterr: \"" + str(reterr).strip() + "\"")
        self.logger.log(LogPriority.INFO, "*******************************************")
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in __format")
        return success
        
    ###########################################################################

    def __partition(self) :
        """
        Not implemented on the Mac
        
        """
        success=False
        size = int(self.diskSize)/(2*1024)
        cmd = [self.diskutil, "partitionDisk", self.myRamdiskDev, str(1), "MBR", "HFS+", "ramdisk", str(size) + "M"]
        retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        if not reterr:
            success = True
        self.logger.log(LogPriority.INFO, "*******************************************")
        self.logger.log(LogPriority.INFO, "retval: \"\"\"" + str(retval).strip() + "\"\"\"")
        self.logger.log(LogPriority.INFO, "reterr: \"" + str(reterr).strip() + "\"")
        self.logger.log(LogPriority.INFO, "*******************************************")
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in __format")
        return success

    ###########################################################################

    def __isMemoryAvailable(self) :
        """
        Check to make sure there is plenty of memory of the size passed in 
        before creating the ramdisk

        Best method to do this on the Mac is to get the output of "top -l 1"
        and re.search("unused\.$", line)
        
        @author: Roy Nielsen
        """
        #mem_free = psutil.phymem_usage()[2]

        #print "Memory free = " + str(mem_free)
        success = False
        self.free = 0
        cmd = ["/usr/bin/top", "-l", "1"]
        pipe = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        size = None
        freeMagnitude = None
         
        if pipe:
            while True:
                myout = pipe.stdout.readline()
                #print myout + "\n"
                if myout == '' and pipe.poll() != None:
                    break
                
                line = myout.split()
                
                # Get the last item in the list
                found = line[-1]
                almost_size = line[:-1]
                size = almost_size[-1]
                
                self.logger.log(LogPriority.INFO, "size: " + str(size))
                self.logger.log(LogPriority.INFO, "found: " + str(found))
                
                if re.search("unused", found) or re.search("free", found):
                    break
            if size:
                sizeCompile = re.compile("(\d+)(\w+)")
                    
                split_size = sizeCompile.search(size)
                freeNumber = split_size.group(1)
                freeMagnitude = split_size.group(2)

                self.logger.log(LogPriority.INFO, "freeNumber: " + str(freeNumber))
                self.logger.log(LogPriority.INFO, "freeMagnitude: " + str(freeMagnitude))

                if re.match("^\d+$", freeNumber.strip()):
                    if re.match("^\w$", freeMagnitude.strip()):
                        success = True
                        if freeMagnitude:    
                            if re.search("G", freeMagnitude.strip()):
                                self.free = 1024 * int(freeNumber)
                                self.free = str(self.free)
                            elif re.search("M", freeMagnitude.strip()):
                                self.free = freeNumber
                
        return success
        
    ###########################################################################

    def _runcmd(self, cmd, err_message) :
        """
        Run the command
        
        @author Roy Nielsen
        """
        success = False
        try :
            retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        except Exception, err :
            self.logger.log(LogPriority.INFO, err_message + str(err))
        else :
            success = True
        self.logger.log(LogPriority.INFO, "Success: " + str(success) + " in _runcmd")
        return success

    ###########################################################################

    def getDevice(self):
        """
        Getter for the device name the ramdisk is using

        @author: Roy Nielsen
        """
        return self.myRamdiskDev

    ###########################################################################

    def setDevice(self, device=None):
        """
        Setter for the device so it can be ejected.
        
        @author: Roy Nielsen
        """
        if device:
            self.myRamdiskDev = device
        else:
            raise Exception("Problem trying to set the device..")
            
    ###########################################################################

    def getVersion(self):
        """
        Getter for the version of the ramdisk

        @author: Roy Nielsen
        """
        return self.version


###############################################################################

def detach(device=" ", message_level="normal"):
    """
    Eject the ramdisk
    Detach (on the mac) is a better solution than unmount and eject 
    separately.. Besides unmounting the disk, it also stops any processes 
    related to the mntPoint

    @author: Roy Nielsen
    """
    success = False
    if not re.match("^\s*$", device):
        cmd = ["/usr/bin/hdiutil", "detach", device]
        retval, reterr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        if not reterr:
            success = True

        LOGGER.log(LogPriority.INFO, "*******************************************")
        LOGGER.log(LogPriority.INFO, "retval: " + re.escape(str(retval).strip("\"")))
        LOGGER.log(LogPriority.INFO, "reterr: " + re.escape(str(reterr).strip("\"")))
        LOGGER.log(LogPriority.INFO, "*******************************************")
        LOGGER.log(LogPriority.INFO, "Success: " + str(success) + " in eject")
    else:
        raise Exception("Cannot eject a device with an empty name..")
    return success

