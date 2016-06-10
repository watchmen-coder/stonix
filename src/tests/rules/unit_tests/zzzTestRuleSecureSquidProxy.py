#!/usr/bin/env python
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
This is a Unit Test for Rule SetTFTPD
Created on Jun 8, 2016

@author: dwalker
'''

from __future__ import absolute_import
import unittest
import sys

sys.path.append("../../../..")
from src.tests.lib.RuleTestTemplate import RuleTest
from src.stonix_resources.CommandHelper import CommandHelper
from src.stonix_resources.stonixutilityfunctions import iterate, setPerms, checkPerms
from src.stonix_resources.stonixutilityfunctions import resetsecon, readFile, writeFile, createFile
from src.stonix_resources.pkghelper import Pkghelper
from src.tests.lib.logdispatcher_mock import LogPriority
from src.stonix_resources.rules.SecureSquidProxy import SecureSquidProxy
from shutil import copyfile
import os
import re

class zzzTestRuleSecureSquidProxy(RuleTest):

    def setUp(self):
        RuleTest.setUp(self)
        self.rule = SecureSquidProxy(self.config,
                                        self.environ,
                                        self.logdispatch,
                                        self.statechglogger)
        self.rulename = self.rule.rulename
        self.rulenumber = self.rule.rulenumber
        self.ch = CommandHelper(self.logdispatch)
        self.ph = Pkghelper(self.logdispatch, self.environ)
        self.fileexisted = True

    def tearDown(self):
        pass

    def runTest(self):
        self.simpleRuleTest()

    def setConditionsForRule(self):
        '''
        Configure system for the unit test
        @param self: essential if you override this definition
        @return: boolean - If successful True; If failure False
        @author: dwalker
        '''
        success = True
        if self.ph.check("squid"):
            if self.ph.manager == "apt-get":
                self.squidfile = "/etc/squid3/squid.conf"
            else:
                self.squidfile = "/etc/squid/squid.conf"
            self.backup = self.squidfile + ".original"
            if checkPerms(self.squidfile, [0, 0, 420], self.logdispatch):
                if not setPerms(self.squidfile, [0, 0, 416], self.logdispatch):
                    success = False
            self.data1 = {"ftp_passive": "on",
                          "ftp_sanitycheck": "on",
                          "check_hostnames": "on",
                          "request_header_max_size": "20 KB",
                          "reply_header_max_size": "20 KB",
                          "cache_effective_user": "squid",
                          "cache_effective_group": "squid",
                          "ignore_unknown_nameservers": "on",
                          "allow_underscore": "off",
                          "httpd_suppress_version_string": "on",
                          "forwarded_for": "off",
                          "log_mime_hdrs": "on",
                          "http_access": "deny to_localhost"}

            #make sure these aren't in the file
            self.denied = ["acl Safe_ports port 70",
                           "acl Safe_ports port 210",
                           "acl Safe_ports port 280",
                           "acl Safe_ports port 488",
                           "acl Safe_ports port 591",
                           "acl Safe_ports port 777"]
            print "about to begin\n"
            if not os.path.exists(self.squidfile):
                print "squid file doesn't exist, creating it...\n"
                self.fileexisted = False
                createFile(self.squidfile, self.logdispatch)
            else:
                print "copying the file for backup\n"
                copyfile(self.squidfile, self.backup)
            tempstring = ""
            contents = readFile(self.squidfile, self.logdispatch)
            if contents:
                print "there are contents!\n"
                print "they are: " + str(contents)
                for line in contents:
                    if re.search("^ftp_passive", line.strip()):
                        '''Delete this line'''
                        continue
                    else:
                        tempstring += line
            else:
                print "file was blank"
            print "messing up the file\n\n"
            '''insert line with incorrect value'''
            tempstring += "request_header_max_size 64 KB\n"
            '''insert line with no value'''
            tempstring += "ignore_unknown_nameservers\n"
            '''insert these two lines we don't want in there'''
            tempstring += "acl Safe_ports port 70\nacl Safe_ports port 210\n"
            if not writeFile(self.squidfile, tempstring, self.logdispatch):
                success = False
        return success

    def checkReportForRule(self, pCompliance, pRuleSuccess):
        '''
        check on whether report was correct
        @param self: essential if you override this definition
        @param pCompliance: the self.iscompliant value of rule
        @param pRuleSuccess: did report run successfully
        @return: boolean - If successful True; If failure False
        @author: ekkehard j. koch
        '''
        self.logdispatch.log(LogPriority.DEBUG, "pCompliance = " + \
                             str(pCompliance) + ".")
        self.logdispatch.log(LogPriority.DEBUG, "pRuleSuccess = " + \
                             str(pRuleSuccess) + ".")
        success = True
        return success

    def checkFixForRule(self, pRuleSuccess):
        '''
        check on whether fix was correct
        @param self: essential if you override this definition
        @param pRuleSuccess: did report run successfully
        @return: boolean - If successful True; If failure False
        @author: ekkehard j. koch
        '''
        self.logdispatch.log(LogPriority.DEBUG, "pRuleSuccess = " + \
                             str(pRuleSuccess) + ".")
        success = True
        if not self.fileexisted:
            os.remove(self.path)
        return success

    def checkUndoForRule(self, pRuleSuccess):
        '''
        check on whether undo was correct
        @param self: essential if you override this definition
        @param pRuleSuccess: did report run successfully
        @return: boolean - If successful True; If failure False
        @author: ekkehard j. koch
        '''
        self.logdispatch.log(LogPriority.DEBUG, "pRuleSuccess = " + \
                             str(pRuleSuccess) + ".")
        success = True
        return success

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()

