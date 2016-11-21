#!/usr/bin/python
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
'''
Refactor of the python mac build script to allow for easier transition between
library versions and products.  Instigated by the upgrade to PyQt5, PyInstaller 3.3
and using swift for the wrapper with elevator.

Date refactor initiated - 11/7/2016

@authors: Eric Ball, Roy Nielsen
'''
#--- Python specific libraries
import os
import re
import sys
import stat
import optparse
import traceback
import getpass
from glob import glob
from tempfile import mkdtemp
from time import time
from subprocess import Popen, STDOUT, PIPE, call
from shutil import rmtree, copy2
from ConfigParser import SafeConfigParser

# For setupRamdisk() and detachRamdisk()
sys.path.append("./ramdisk/")
from ramdisk.macRamdisk import RamDisk, detach
from ramdisk.lib.loggers import CyLogger
from ramdisk.lib.loggers import LogPriority as lp
from ramdisk.lib.get_libc import getLibc
from ramdisk.lib.run_commands import RunWith


#####
# Exception for when the conf file can't be grokked.
class ConfusingConfigurationError(Exception):
    """
    Meant for being thrown when the MacBuilder can't determine configuration
    information.

    @author: Roy Nielsen
    """
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class SoftwareBuilder():
    '''
    Class to manage the build process.  Initially used with the Stonix project
    on the Mac platform, will be used for others as well.
    '''
    def __init__(self,
                 options=optparse.Values({"compileGui": False, "version": "0",
                                          "clean": False, "test": False, "debug":False, "sig":False}),
                 ramdisk_size=1600):
        '''
        Initialization routine.
        @param: compileGui - bool to determine if the gui should be compiled 
                             or not
        @param: version - if passed in, the version to use for app and package
                          creation.
        @param: clean - bool to determine whether or not to clean artifacts 
                        from previous builds
        @param: test - Don't run the driver - specifically for unit testing
        @param: debug - bool to determine whether or not to log in debug mode
        @param: sig - signature to use for application and package signing
                      in the build process
        '''
        if isinstance(options.debug, bool) and options.debug:
            debug = 20
        else:
            debug = 40
        self.logger = CyLogger(level=debug)
        self.logger.initializeLogs()
        self.rw = RunWith(self.logger)
        
        self.ramdisk_size = ramdisk_size

        self.libc = getLibc()

        if options.sig:
            self.codesignSignature = options.sig

        # This script needs to be run from [stonixroot]/src/MacBuild; make sure
        # that is our current operating location
        cwd = os.getcwd()
        if not re.search("src/MacBuild$", cwd):
            print "This script needs to be run from src/MacBuild. Exiting..."
            exit(1)

        try:
            rmtree("/tmp/the_luggage")
        except OSError as e:
            if not e.errno == 2:
                raise
        if options.clean:
            self.clean()

        # If version was not included at command line, use hardcoded version
        # number
        if options.version == "0":
            self.APPVERSION = "0.9.5.0"
        else:
            self.APPVERSION = options.version

        self.compileGui = options.compileGui

        if not self._configParser():
            raise ConfusingConfigurationError("Cannot determine the correct configuration...")

        self.RSYNC = "/usr/bin/rsync"

        print " "
        print " "
        print "   ************************************************************"
        print "   ************************************************************"
        print "   ***** App Version: " + self.APPVERSION
        print "   ************************************************************"
        print "   ************************************************************"
        print " "
        print " "

        self.keyuser = raw_input("Keychain User: ")
        self.keypass = getpass.getpass("Keychain Password: ") 

        if not options.test:
            self.driver()

    #--------------------------------------------------------------------------
    # Private support methods

    def _setupRamdisk(self, size, mntpnt=""):
        ramdisk = RamDisk(str(size), mntpnt)

        if not ramdisk.success:
            print("Ramdisk setup failed...")
            raise Exception("Ramdisk setup failed...")

        return ramdisk.getDevice()

    def _detachRamdisk(self, device):
        if detach(device):
            print("Successfully detached disk: " + str(device).strip())
            return True
        else:
            print("Couldn't detach disk: " + str(device).strip())
            raise Exception("Cannot eject disk: " + str(device).strip())

    def _exit(self, ramdisk, luggage, exitcode=0):
        os.chdir(self.STONIX_ROOT)
        self._detachRamdisk(ramdisk)
        self._detachRamdisk(luggage)
        print traceback.format_exc()
        exit(exitcode)

    def _configSectionMap(self, section):
        '''
        Acquire values from the config file and store in a dictionary.

        @author: rsn
        '''
        dict1 = {}
        options = self.parser.options(section)
        for option in options:
            try:
                dict1[option] = self.parser.get(section, option)
                if dict1[option] == -1:
                    self.logger.log(lp.DEBUG, "skip: %s" % option)
            except:
                print("exception on %s!" % option)
                dict1[option] = None
        print dict1
        return dict1

    def _configParser(self):
        '''
        Parse config file and instanciate/initialize class variables from
        config file data.
        '''
        success = False
        # This script should be run from [stonixroot]/src/MacBuild. We must
        os.chdir("../..")
        self.STONIX_ROOT = os.getcwd()
        os.chdir("src/MacBuild")
        macbuild_root = os.getcwd()
        myconf = os.path.join(macbuild_root, 'build.conf')
        print myconf
        if os.path.isfile(myconf):
            self.parser = SafeConfigParser()
            candidates =  [myconf, 'not_a_real_conf.conf']
            found = self.parser.read(candidates)
            missing = set(candidates) - set(found)

            try:
                dict1 = {}
                for section in self.parser.sections():
                    dict1[section] = self._configSectionMap(section)
                print dict1
            except:
                self.STONIX = "stonix"
                self.STONIXICON = "stonix_icon"
                self.STONIXVERSION = self.APPVERSION
                self.STONIX4MAC = "stonix4mac"
                self.STONIX4MACICON = "stonix_icon"
                self.STONIX4MACVERSION = self.APPVERSION                
                #-- Internal libraries
                from buildlib import MacBuildLib
                self.mbl = MacBuildLib(self.logger)
                self.PYUIC = self.mbl.getpyuicpath()
                self.codesignVerbose = 'vvvv'
                self.codesignDeep = True
                self.doCodesign = False
            else:
                self.STONIX = dict1['stonix']['app']
                self.STONIXICON = dict1['stonix']['app_icon']
                self.STONIXVERSION = dict1['stonix']['app_version']
                self.STONIX4MAC = dict1['stonix']['wrapper']
                self.STONIX4MACICON = dict1['stonix']['wrapper_icon']
                self.STONIX4MACVERSION = dict1['stonix']['wrapper_version']
                self.PYUIC = dict1['libpaths']['pyuic']
                self.PYPATHS = dict1['libpaths']['pythonpath'].split(':')
                self.logger.log(lp.INFO, 'attempting to get codesigning information...')
                self.codesignVerbose = dict1['codesign']['verbose']
                if re.match('^True$', dict1['codesign']['ask']):
                    self.doCodesign = True
                else:
                    self.doCodesign = False
                if re.match('^True$', dict1['codesign']['deep']):
                    self.codesignDeep = True
                else:
                    self.codesignDeep = False
                self.logger.log(lp.INFO, "Grabbed codesign info...")
                for path in self.PYPATHS:
                    sys.path.append(path)
                #-- Internal libraries
                try:
                    from buildlib import MacBuildLib
                    self.mbl = MacBuildLib(self.logger, self.PYPATHS)
                except Exception, err:
                    raise
                self.logger.log(lp.INFO, "... macbuildlib loaded ...")
            finally:
                self.hiddenimports = self.mbl.getHiddenImports()
                self.logger.log(lp.DEBUG, "Hidden imports: " + str(self.hiddenimports))
                success = True

        return success

    def getOrdPass(self, passwd=''):
        '''
        Get the password translated to a direct ascii pattern of:
        
            "[\d+:]\d+"
        
        for use when in the need of passing it via self.rw.liftDown()
        
        #####
        # Prepare for transport of the password to the xcodebuild.py
        # builder.  This is not encryption, this is just encoding, using
        # similar to UTF encoding of various languages.
        # The standard python 'ord' function, to allow for special 
        # characters to be passed, that may be consumed by a shell in
        # the process of passing the password to the other python script.

        @param: password to translate
        
        @returns: translated password
        '''
        i = 0
        ordPass = ""
        for char in self.keypass:
            i += 1
            if i == 1:
                ordPass += str(ord(char))
            else:
                ordPass += ':' + str(ord(char))

        self.logger.log(lp.INFO, str(ordPass))
        return str(ordPass)

    #--------------------------------------------------------------------------
    # Main controller/driver for the class

    def driver(self):
        '''
        The driver orchestrates the build process.
        '''
        # Check that user building stonix has uid 0
        current_user, _ = self.mbl.checkBuildUser()

        #####
        # The driver needs to be run inside a try/except block to make sure to
        # call the tearDown method in case of an exception before exit.
        try:
            self.setUp()
            #####
            # Process Stonix
            self.preCompile(self.STONIX, self.tmphome + "/src/MacBuild/")
            # Compile the two apps...
            self.compile(self.STONIX, self.STONIXVERSION, self.STONIXICON,
                            self.tmphome + "/src/MacBuild/" + self.STONIX)

            self.postCompile(self.STONIX, self.tmphome + "/src/MacBuild/")

            #####
            # Process stonix4mac
            self.compile(self.STONIX4MAC, self.STONIX4MACVERSION,
                            self.STONIX4MACICON, self.tmphome + "/src/MacBuild/" + \
                            self.STONIX4MAC)
            #####
            # Create the installer
            self.makeInstaller(self.STONIX4MAC, self.STONIXVERSION, self.tmphome + \
                               "/src/MacBuild/")

        except (KeyboardInterrupt, SystemExit):
            print traceback.format_exc()
            self._exit(self.ramdisk, self.luggage, 130)
        except Exception:
            print traceback.format_exc()
            self._exit(self.ramdisk, self.luggage, 1)
        else:
            self.tearDown()

    #--------------------------------------------------------------------------
    # Interface support methods

    def setUp(self):
        '''
        Performing build setup for the whole process.
        '''
        success = False
        try:
            # Check that user building stonix has uid 0
            current_user, _ = self.mbl.checkBuildUser()
    
            # Create temp home directory for building with pyinstaller
            self.buildHome = os.getcwd()
            self.directory = os.environ["HOME"]
            self.tmphome = mkdtemp(prefix=current_user + ".")
            os.environ["HOME"] = self.tmphome
            os.chmod(self.tmphome, 0755)
    
            # Create a ramdisk and mount it to the tmphome
            self.ramdisk = self._setupRamdisk(self.ramdisk_size, self.tmphome)
            os.mkdir("/tmp/the_luggage")
            self.luggage = self._setupRamdisk(self.ramdisk_size,
                                        "/tmp/the_luggage")
            print "Device for tmp ramdisk is: " + self.ramdisk

            print "."
            print "."
            print "."

            rsync = [self.RSYNC, "-apv", "--exclude=\".svn\"",
                  "--exclude=\"*.tar.gz\"", "--exclude=\"*.dmg\"",
                  "../../src", self.tmphome]
            print str(rsync)

            print "."
            print "."
            print "."

            output = Popen(rsync, stdout=PIPE, stderr=STDOUT).communicate()[0]
            print "\t\trsync output: " + str(output)
        
            print "."
            print "."
            print "."

        except Exception, err:
            print traceback.format_exc()
            self.logger.log(lp.WARNING, "Problem setting up ramdisks, not likely to succeed...")
            raise err
        else:
            success = True
        return success

    def preCompile(self, appName, prepPath):
        '''
        '''
        success = False
        self.libc.sync()
        self.libc.sync()
        returnDir = os.getcwd()
        os.chdir(prepPath)
        self.libc.sync()
        self.libc.sync()
        try:
            if appName == 'stonix':
                # Copy src dir to /tmp/<username> so shutil doesn't freak about
                # long filenames.
                # ONLY seems to be a problem on Mavericks
                #####
                # Set the stonix version number correctly
                self.mbl.regexReplace(self.tmphome + "/src/stonix_resources/localize.py",
                                      r"^STONIXVERSION =.*$",
                                      r"STONIXVERSION = '" + self.APPVERSION + "'",
                                      backupname="../stonix_resources/localize.py.bak")
                #####
                # Make sure the "stonix" directory exists, so we can put
                # together and create the stonix.app
                if os.path.islink(self.tmphome + "/src/MacBuild/stonix"):
                    os.unlink(self.tmphome + "/src/MacBuild/stonix")
                if not os.path.isdir(self.tmphome + "/src/MacBuild/stonix"):
                    os.mkdir(self.tmphome + "/src/MacBuild/stonix")
                else:
                    #####
                    # Cannot use mkdtmp here because it will make the directory on
                    # the root filesystem instead of the ramdisk, then it will try
                    # to link across filesystems which won't work
                    tmpdir = self.tmphome + "/src/MacBuild/stonix." + str(time())
                    os.rename(self.tmphome + "/src/MacBuild/stonix", tmpdir)
                    os.mkdir(self.tmphome + "/src/MacBuild/stonix")

                #####
                # Set up stonix for a build
                copy2(self.tmphome + "/src/stonix.py", self.tmphome + "/src/MacBuild/stonix")
                
                rsync = [self.RSYNC, "-ap", "--exclude=\".svn\"",
                         "--exclude=\"*.tar.gz\"", "--exclude=\"*.dmg\"",
                         "--exclude=\".git*\"",
                         self.tmphome + "/src/stonix_resources",
                         self.tmphome + "/src/MacBuild/stonix"]
                output = Popen(rsync, stdout=PIPE, stderr=STDOUT).communicate()[0]
                print str(output)
            elif appName == 'stonix4mac':
                #####
                # No precompile currently needed
                pass
            os.chdir(returnDir)
        except:
            print traceback.format_exc()
            raise
        else:
            success = True            
        return success

    def compile(self, appName, appVersion, appIcon, appPath):
        '''
        Perform compile - to create an 'app' for the applications directory

        @param appName: Name of application as it should appear on OS X systems
        @param appVersion: Version of app being built
        @param appIcon: File name of icon for OS X app
        @param appPath: Path to [stonixroot]/src/MacBuild/[appName]

        @author: Eric Ball, Roy Nielsen
        '''
        print "Started compileApp with " + appName + ", " + appVersion + \
            ", " + appIcon
        try:
            returnDir = os.getcwd()
            os.chdir(appPath)

            #####
            # Determine compile type - ie: xcodebuild vs pyinstaller
            if appName == "stonix4mac":
                #####
                # Get a translated password
                ordPass = self.getOrdPass(self.keypass)

                os.chdir('..')
                buildDir = os.getcwd()
                print buildDir
                os.chdir(appPath)
                
                
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, "TMPHOME: " + str(self.tmphome))
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, ".")
                self.logger.log(lp.DEBUG, ".")
                
                #####
                # Run the xcodebuild script to build stonix4mac
                cmd = [self.tmphome + '/src/MacBuild/xcodebuild.py', '-p', ordPass, '-u', self.keyuser, '-a', appName, '-d', '--project_directory', self.tmphome]
                workingDir = os.getcwd()
                self.rw.setCommand(cmd)
                self.rw.liftDown(self.keyuser, workingDir)

            elif appName == "stonix":
                #####
                # Perform pyinstaller build
                if os.path.isdir(self.tmphome + "/src/MacBuild/stonix/build"):
                    rmtree(self.tmphome + "/src/MacBuild/stonix/build")
                if os.path.isdir(self.tmphome + "/src/MacBuild/stonix/dist"):
                    rmtree(self.tmphome + "/src/MacBuild/stonix/dist")
    
                self.logger.log(lp.DEBUG, "Hidden imports: " + str(self.hiddenimports))
    
                hdnimports = self.hiddenimports + ['ctypes', '_ctypes', 'ctypes._endian', 'decimal', 'numbers']
    
                # to compile a pyinstaller spec file for app creation:
                print "Creating a pyinstaller spec file for the project..."
                print self.mbl.pyinstMakespec([appName + ".py"], True, True, False,
                                              "../" + appIcon + ".icns",
                                              pathex=["stonix_resources/rules",
                                                      "stonix_resources", "/usr/lib"] + self.PYPATHS,
                                              specpath=os.getcwd(), hiddenimports=hdnimports)
                # to build:
                print "Building the app..."
                self.mbl.pyinstBuild(appName + ".spec", "private/tmp",
                                     appPath + "/dist", True, True)
    
                plist = self.tmphome + "/src/MacBuild/stonix" + "/dist/" + appName + ".app/Contents/Info.plist"
    
                # Change version string of the app
                print "Changing .app version string..."
                self.mbl.modplist(plist, "CFBundleShortVersionString", appVersion)
    
                # Change icon name in the app
                print "Changing .app icon..."
                self.mbl.modplist(plist, "CFBundleIconFile", appIcon + ".icns")
    
                # Copy icons to the resources directory
                copy2("../" + appIcon + ".icns",
                      "./dist/" + appName + ".app/Contents/Resources")
    
                # Change mode of Info.plist to 0755
                os.chmod(plist, 0o755)
        except Exception:
            raise

        print "compileApp with " + appName + ", " + appVersion + " Finished..."

    def postCompile(self, appName, prepPath):
        '''
        Perform post-compile processing.
        
        @author: Eric Ball, Roy Nielsen
        '''
        print "Started postCompile..."
        returnDir = os.getcwd()
        os.chdir(prepPath)
        try:
            if appName == 'stonix':
                self.logger.log(lp.DEBUG, "Starting stonix postCompile.")
                returnDir = os.getcwd()
                os.chdir(prepPath)
               #####
                # Copy stonix.app to the stonix4mac directory
                rsync = [self.RSYNC, "-avp", "--exclude=\".svn\"",
                         "--exclude=\"*.tar.gz\"", "--exclude=\"*.dmg\"",
                         "--exclude=\".git*\"", self.tmphome + \
                         "/src/MacBuild/stonix/dist/stonix.app", "./stonix4mac"]
                output = Popen(rsync, stdout=PIPE, stderr=STDOUT).communicate()[0]
                print output
                self.libc.sync()
            elif appName == 'stonix4mac':
                self.logger.log(lp.DEBUG, "Starting stonix4mac postCompile.")

            os.chdir(returnDir)
        except Exception:
            raise
        print "buildStonix4MacAppResources Finished..."


    def makeInstaller(self, appName, appVersion, appPath):
        '''
        Create an installer.  As of Nov 2016, use luggage to create a 
       <appName>.pkg

        @param appName: Name of application as it should appear on OS X systems
        @param appVersion: Version of app being built
        @param appPath: Path to [stonixroot]/src/MacBuild

        @authors: Eric Ball, Roy Nielsen
        '''
        #####
        # run make to create a pkg installer
        print "Started buildStonix4MacAppPkg..."
        try:
            returnDir = os.getcwd()
            os.chdir(appPath + "/" + appName)

            print "Putting new version into Makefile..."
            self.mbl.regexReplace("Makefile", r"PACKAGE_VERSION=",
                                  "PACKAGE_VERSION=" + appVersion)

            if not os.path.isdir(appPath + "/dmgs"):
                os.mkdir(appPath + "/dmgs")
            else:
                # Cannot use mkdtmp here because it will make the directory on
                # the root filesystem instead of the ramdisk, then it will try
                # to link across filesystems which won't work
                tmpdir = self.tmphome + "/src/MacBuild/dmgs." + str(time())
                os.rename(self.tmphome + "/src/MacBuild/stonix/dmgs", tmpdir)
                os.mkdir(self.tmphome + "/src/MacBuild/stonix/dmgs")

            print "Creating a .dmg file with a .pkg file inside for " + \
                "installation purposes..."
            #call(["make", "dmg", "PACKAGE_VERSION=" + appVersion,
            #      "USE_PKGBUILD=1"])
            makepkg = ["make", "pkg", "PACKAGE_VERSION=" + appVersion,
                  "USE_PKGBUILD=1"]
            output = Popen(makepkg, stdout=PIPE, stderr=STDOUT).communicate()[0]
            print output

            #####
            # Optional codesign
            self.libc.sync()
            self.libc.sync()
            if self.doCodesign:
                os.chdir('..')
                buildDir = os.getcwd()
                print buildDir
                #####
                # Get a translated password
                ordPass = self.getOrdPass(self.keypass)
                cmd = [self.tmphome + '/src/MacBuild/xcodebuild.py', '-c',
                       '-p', ordPass, '-u', self.keyuser, '-a', appName, '-d',
                       '-v', self.codesignVerbose,
                       '-s', '"' + self.codesignSignature + '"']

                workingDir = os.getcwd()

                #####
                # Run the xcodebuild script to codesign the mac installer package
                self.rw.setCommand(cmd)
                self.rw.liftDown(self.keyuser, workingDir)

                self.libc.sync()
                self.libc.sync()

            print "Moving dmg and pkg to the dmgs directory."
            #dmgname = appName + "-" + appVersion + ".dmg"
            #pkgname = appName + "-" + appVersion + ".pkg"
            #os.rename(dmgname, appPath + "/dmgs/" + dmgname)
            #os.rename(pkgname, appPath + "/dmgs/" + pkgname)

            os.chdir(returnDir)
        except Exception:
            raise
        print "buildStonix4MacAppPkg... Finished"

    def backup(self):
        '''
        '''
        pass

    def tearDown(self):
        '''
        Disconnect ramdisk, unloading data to pre-build location.
        '''
        self.mbl.chownR(self.keyuser, self.tmphome + "/src")

        # chmod so it's readable by everyone, writable by the group
        self.mbl.chmodR(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH |
                        stat.S_IWGRP, self.tmphome + "/src", "append")
        self.libc.sync()
        self.libc.sync()
        # Copy back to pseudo-build directory
        call([self.RSYNC, "-aqp", self.tmphome + "/src", self.buildHome])
        self.libc.sync()
        self.libc.sync()

        os.chdir(self.buildHome)
        #self._exit(self.ramdisk, self.luggage, 0)

if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option("-v", "--version", action="store", dest="version",
                      type="string", default="0",
                      help="Set the STONIX build version number",
                      metavar="version")
    parser.add_option("-g", "--gui", action="store_true",
                      dest="compileGui",
                      default=False,
                      help="If set, the PyQt files will be recompiled")
    parser.add_option("-c", "--clean", action="store_true", dest="clean",
                      default=False, help="Clean all artifacts from " +
                      "previous builds and exit")
    parser.add_option("-t", "--test", action="store_true", dest="test",
                      default=False, help="If run in testing mode, " +
                      "the driver method does not execute, allowing for " +
                      "unit testing of functions")
    parser.add_option("-d", "--debug", action="store_true", dest="debug",
                      default=False, help="debug mode, on or off.  Default off.")
    parser.add_option("-s", "--signature", action="store", dest="sig",
                      type="string", default="",
                      help="Codesign signature to sign with.",
                      metavar="sig")
    options, __ = parser.parse_args()
    stonix4mac = SoftwareBuilder(options)