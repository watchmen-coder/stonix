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
Created on Aug 23, 2016

@author: dwalker
'''
from __future__ import absolute_import
import traceback
import os
import re
from ..rule import Rule
from ..logdispatcher import LogPriority
from ..stonixutilityfunctions import iterate
from ..KVEditorStonix import KVEditorStonix


class STIGConfigureProfileManagement(Rule):
    '''
    Deploy Passcode Policy configuration profiles for OS X Yosemite 10.10
    '''
    def __init__(self, config, environ, logdispatch, statechglogger):
        '''
        Constructor
        '''
        Rule.__init__(self, config, environ, logdispatch, statechglogger)

        self.logger = logdispatch
        self.rulenumber = 361
        self.rulename = "STIGConfigureProfileManagement"
        self.formatDetailedResults("initialize")
        self.helptext = "STIGConfigureProfileManagement rule configures the " + \
            "Mac OSX operating system's password policy according to LANL " + \
            "standards and practices."
        self.rootrequired = True
        self.applicable = {'type': 'white',
                           'os': {'Mac OS X': ['10.10', 'r', '10.11']}}
        datatype = "bool"
        key = "STIGPASSCODECONFIG"
        instructions = "To disable the installation of the password " + \
            "profile set the value of STIGPASSCODECONFIG to False"
        default = True
        self.pwci = self.initCi(datatype, key, instructions, default)
        
        datatype = "bool"
        key = "STIGSECURITYCONFIG"
        instructions = "To disable the installation of the security " + \
            "profile set the value of SECURITYCONFIG to False"
        default = True
        self.sci = self.initCi(datatype, key, instructions, default)
        self.iditerator = 0
        if re.search("10\.10.*", self.environ.getosver()):
#         self.pwprofile = "/Applications/stonix4mac.app/Contents/" + \
#                          "Resources/stonix.app/Contents/MacOS/" + \
#                          "stonix_resources/files/" + \
#                          "U_Apple_OS_X_10-10_Workstation_V1R2_STIG_Passcode_Policy.mobileconfig"
#         self.secprofile = "/Applications/stonix4mac.app/Contents/" + \
#                           "Resources/stonix.app/Contents/MacOS/" + \
#                           "stonix_resources/files/" + \
#                           "U_Apple_OS_X_10-10_Workstation_V1R2_STIG_Security_Privacy_Policy.mobileconfig"
            '''These directories for testing purposes only'''
            self.pwprofile = "/home/dwalker/src/" + \
                "stonix_resources/files/" + \
                "U_Apple_OS_X_10-10_Workstation_V1R2_STIG_Passcode_Policy.mobileconfig"
            self.secprofile = "/home/dwalker/src/" + \
                "stonix_resources/files/" + \
                "U_Apple_OS_X_10-10_Workstation_V1R2_STIG_Security_Privacy_Policy.mobileconfig"
        elif re.search("10\.11\.*", self.environ.getosver()):
#             self.pwprofile = "/Applications/stonix4mac.app/Contents/" + \
#                          "Resources/stonix.app/Contents/MacOS/" + \
#                          "stonix_resources/files/" + \
#                          "U_Apple_OS_X_10-11_V1R1_STIG_Passcode_Policy.mobileconfig"
#             self.secprofile = "/Applications/stonix4mac.app/Contents/" + \
#                           "Resources/stonix.app/Contents/MacOS/" + \
#                           "stonix_resources/files/" + \
#                           "U_Apple_OS_X_10-11_V1R1_STIG_Security_and_Privacy_Policy.mobileconfig"
            '''These directories for testing purposes only'''
            self.pwprofile = "/home/dwalker/src/" + \
                         "stonix_resources/files/" + \
                         "U_Apple_OS_X_10-11_V1R1_STIG_Passcode_Policy.mobileconfig"
            self.secprofile = "/home/dwalker/src/" + \
                          "stonix_resources/files/" + \
                          "U_Apple_OS_X_10-11_V1R1_STIG_Security_and_Privacy_Policy.mobileconfig"

    def report(self):
        '''
        @since: 3/9/2016
        @author: dwalker
        first item in dictionary - identifier (multiple can exist)
            first item in second nested dictionary - key identifier within
                opening braces in output
            first item in nested list is the expected value after the = in
                output (usually a number, in quotes "1"
            second item in nested list is accepted datatype of value after
                the = ("bool", "int")
            third item in nested list (if int) is whether the allowable value
                is allowed to be more or less and still be ok
                "more", "less"
                '''
        try:
            compliant = True
            self.detailedresults = ""
            self.pweditor, self.seceditor = "", ""
            self.pwprofiledict = {"com.apple.mobiledevice.passwordpolicy":
                                  {"allowSimple": ["0", "bool"],
                                   "forcePIN": ["1", "bool"],
                                   "maxFailedAttempts": ["4", "int", "less"],
                                   "maxPINAgeInDays": ["180", "int", "more"],
                                   "minComplexChars": ["1", "int", "more"],
                                   "minLength": ["14", "int", "more"],
                                   "minutesUntilFailedLoginReset":
                                   ["15", "int", "more"],
                                   "pinHistory": ["5", "int", "more"],
                                   "requireAlphanumeric": ["1", "bool"]}}
            self.spprofiledict = {"com.apple.screensaver": "",
                                  "com.apple.loginwindow": "",
                                  "com.apple.systempolicy.managed": "",
                                  "com.apple.SubmitDiagInfo": "",
                                  "com.apple.preference.security": "",
                                  "com.apple.MCX": "",
                                  "com.apple.applicationaccess": "",
                                  "com.apple.systempolicy.control": ""}

            self.pweditor = KVEditorStonix(self.statechglogger, self.logger,
                                               "profiles", self.pwprofile, "",
                                               self.pwprofiledict, "", "")
            self.seceditor = KVEditorStonix(self.statechglogger, self.logger,
                                             "profiles", self.secprofile, "",
                                             self.spprofiledict, "", "")
            '''Run the system_proflier command'''
            if not self.pweditor.report():
                self.detailedresults += "password profile is either uninstalled or weak\n"
                compliant = False
            if not self.seceditor.report():
                self.detailedresults += "security profile is either uninstalled or weak\n"
                compliant = False
            self.compliant = compliant
        except (KeyboardInterrupt, SystemExit):
            # User initiated exit
            raise
        except Exception:
            self.rulesuccess = False
            self.detailedresults += "\n" + traceback.format_exc()
            self.logdispatch.log(LogPriority.ERROR, self.detailedresults)
        self.formatDetailedResults("report", self.compliant,
                                   self.detailedresults)
        self.logdispatch.log(LogPriority.INFO, self.detailedresults)
        return self.compliant

###############################################################################

    def fix(self):
        try:
            if not self.pwci.getcurrvalue() and not self.sci.getcurrvalue():
                return
            self.detailedresults = ""

            self.iditerator = 0
            eventlist = self.statechglogger.findrulechanges(self.rulenumber)
            for event in eventlist:
                self.statechglogger.deleteentry(event)
            success = True
            profileexist = True
            if self.neededprofiles:
                for profilepath in self.profpaths:
                    if not os.path.exists(profilepath):
                        profileexist = False
                        break
                if not profileexist:
                    self.detailedresults += "You need profiles installed " + \
                        "but you don't have all the necessary profiles\n"
                    success = False
                else:
                    for profile in self.neededprofiles:
                        cmd = ["/usr/bin/profiles", "-I", "-F", profile]
                        if self.ch.executeCommand(cmd):
                            self.iditerator += 1
                            myid = iterate(self.iditerator, self.rulenumber)
                            undocmd = ["/usr/bin/profiles", "-R", "-F",
                                       profile]
                            event = {"eventtype": "comm",
                                     "command": undocmd}
                            self.statechglogger.recordchgevent(myid, event)
                        else:
                            success = False
            self.rulesuccess = success
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.rulesuccess = False
            self.detailedresults += "\n" + traceback.format_exc()
            self.logdispatch.log(LogPriority.ERROR, self.detailedresults)
        self.formatDetailedResults("fix", self.rulesuccess,
                                   self.detailedresults)
        self.logdispatch.log(LogPriority.INFO, self.detailedresults)
        return self.rulesuccess
