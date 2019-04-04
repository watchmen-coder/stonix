###############################################################################
#                                                                             #
# Copyright 2015-2019.  Los Alamos National Security, LLC. This material was  #
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
Created on Oct 18, 2013

TCPWrappers is a library which provides simple access control and standardized
logging for supported applications which accept connections over a network.
Historically, TCP Wrapper was used to support inetd services. Now that inetd is
deprecated (see Section 3.2.1), TCP Wrapper supports only services which were
built to make use of the libwrap library.

@author: Breen Malmberg
@change: 02/13/2014 Ekkehard Implemented self.detailedresults flow
@change: 02/13/2014 Ekkehard Implemented isapplicable
@change: 04/18/2014 Ekkehard ci updates and ci fix method implementation
@change: 2015/04/17 dkennel updated for new isApplicable
@change: 2015/09/29 Eric Ball Fixed potential first-run failure
@change: 2015/10/08 Eric Ball Help text cleanup
@change: 2016/06/14 Eric Ball Rewrote most code
"""

from __future__ import absolute_import

import os
import re
import traceback
import socket

from ..rule import Rule
from ..logdispatcher import LogPriority
from ..stonixutilityfunctions import iterate

from ..localize import ALLOWNETS, HOSTSALLOWDEFAULT, HOSTSDENYDEFAULT


class TCPWrappers(Rule):
    """
    TCPWrappers is a library which provides simple access control and
    standardized logging for supported applications which accept connections
    over a network. Historically, TCPWrappers was used to support inetd
    services. Now that inetd is deprecated (see Section 3.2.1), TCPWrappers
    supports only services which were built to make use of the libwrap library.

    @author: Breen Malmberg
    """

    def __init__(self, config, environ, logger, statechglogger):
        """
        Constructor
        """

        Rule.__init__(self, config, environ, logger, statechglogger)
        self.config = config
        self.environ = environ
        self.logger = logger
        self.statechglogger = statechglogger
        self.rulenumber = 13
        self.rulename = 'TCPWrappers'
        self.formatDetailedResults("initialize")
        self.compliant = False
        self.mandatory = True
        self.sethelptext()
        self.rootrequired = True
        self.guidance = ['CIS', 'NSA(2.5.4)', '4434-7']
        self.applicable = {'type': 'white',
                           'family': ['linux']}

        # init CIs
        self.ci = self.initCi("bool",
                              "TCPWRAPPERS",
                              "To prevent TCP Wrappers from being " +
                              "configured on this system, set the " +
                              "value of TCPWrappers to False.",
                              True)

        datatype = "list"
        key = "ALLOWNETS"
        instructions = "Please enter a space-delimited list subnet ranges you wish to allow to " + \
            "connect via SSH and X-11 forwarding. To allow none, leave blank. Format for each subnet range = x.x.x.x/CIDR or x.x.x.x/y.y.y.y" + \
            " where y.y.y.y would be the subnet mask. We assume you know what you are doing if you edit the default values here!"
        default = ALLOWNETS

        self.allownetCI = self.initCi(datatype, key, instructions, default)

    def configure_allow_text(self):
        """
        Set up hosts.allow content for later output to file

        @author: Breen Malmberg
        """

        self.hosts_allow_contents = []
        subnets = self.allownetCI.getcurrvalue().split()

        if self.environ.getosname().lower() in ["rhel", "centos"]:
            if self.environ.getosmajorver() == 6:
                # convert all subnet formats to legacy format
                subnets = [self.convert_to_legacy(subnet) for subnet in subnets]

        # build the hosts.allow content by modifying the default content with
        # either the default ranges in localize.py or the user-specified ranges
        # from the CI
        splitstring = HOSTSALLOWDEFAULT.splitlines(True)
        for line in splitstring:
            if not re.search("{allownet}", line):
                self.hosts_allow_contents.append(line)
            else:
                for s in subnets:
                    self.hosts_allow_contents.append(re.sub("{allownet}", s, line))

    def convert_to_legacy(self, subnet):
        """
        converts modern tcp wrappers subnet specification to legacy (rhel 6, centos 6) format
        modern format = <servicename> : x.x.x.x/CIDR : <ALLOW|DENY>
        legacy format = <servicename> : x.x.x.x/y.y.y.y : <ALLOW|DENY>
        x.x.x.x = ip subnet spec, y.y.y.y = subnet mask

        @return: subnet
        @rtype: string
        """

        subnet = str(subnet)

        # check whether this is a valid ip subnet spec
        # (other things can be used in tcp wrappers like hostname, domain, etc.
        # and we don't want to try to do this manipulation on those types)
        try:
            socket.inet_aton(subnet)
        except:
            # will not try to manipulate anything that is not a valid ip subnet spec
            return subnet

        self.logger.log(LogPriority.DEBUG, "Converting " + str(subnet) + " from x.x.x.x/CIDR to legacy x.x.x.x/y.y.y.y format...")

        # CIDR number : subnet mask equivalent
        # (currently only supports 3 most common cases)
        conversion_matrix = {"/24": "/255.255.255.0",
                             "/16": "/255.255.0.0",
                             "/8": "/255.0.0.0"}

        # replace the cidr number with the subnet mask equivalent
        for case in conversion_matrix:
            subnet = re.sub(case, conversion_matrix[case], subnet)
            break

        return subnet

    def report(self):
        """
        Check for correct configuration of hosts.allow and hosts.deny

        @return: self.compliant
        @rtype: bool
        @author: Breen Malmberg
        """

        # if the REQUIRED constants from localize.py are not populated
        # then set the applicability of the rule to False
        # checkConsts logs a message saying the rule
        constlist = [ALLOWNETS, HOSTSALLOWDEFAULT, HOSTSDENYDEFAULT]
        if not self.checkConsts(constlist):
            self.compliant = False
            self.formatDetailedResults("report", self.compliant, self.detailedresults)
            self.logdispatch.log(LogPriority.INFO, self.detailedresults)
            return self.compliant

        try:

            self.detailedresults = ""
            self.compliant = True

            self.configure_allow_text()

            if not self.reportAllow():
                self.compliant = False

            if not self.reportDeny():
                self.compliant = False

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as err:
            self.compliant = False
            self.detailedresults += "\n" + str(traceback.format_exc())
            self.logdispatch.log(LogPriority.ERROR, self.detailedresults)
        self.formatDetailedResults("report", self.compliant, self.detailedresults)
        self.logdispatch.log(LogPriority.INFO, self.detailedresults)
        return self.compliant

    def reportAllow(self):
        """

        @return:
        """

        compliant = True
        allowfile = "/etc/hosts.allow"

        if not os.path.exists(allowfile):
            compliant = False
            self.detailedresults += "\nhosts.allow doesn't exist"
            return compliant

        f = open(allowfile, "r")
        contentlines = f.readlines()
        f.close()

        if contentlines != self.hosts_allow_contents:
            self.detailedresults += "\ncontents of hosts.allow are not correct"
            compliant = False

        return compliant

    def reportDeny(self):
        """

        @return:
        """

        compliant = False
        denyfile = "/etc/hosts.deny"

        if not os.path.exists(denyfile):
            compliant = False
            self.detailedresults += "\nhosts.deny doesn't exist"
            return compliant

        f = open(denyfile, "r")
        contentlines = f.readlines()
        f.close()

        if contentlines != HOSTSDENYDEFAULT.splitlines(True):
            self.detailedresults += "\ncontents of hosts.deny are not correct"
            compliant = False

        return compliant

    def fix(self):
        """
        Apply changes to hosts.allow and hosts.deny to correctly configure them

        @return: self.rulesuccess
        @rtype: bool
        @author: Breen Malmberg
        """

        # defaults
        self.iditerator = 0
        self.detailedresults = ""
        self.rulesuccess = True

        try:

            if not self.ci.getcurrvalue():
                return self.rulesuccess

            if not self.fixAllow():
                self.rulesuccess = False

            if not self.fixDeny():
                self.rulesuccess = False

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as err:
            self.rulesuccess = False
            self.detailedresults = self.detailedresults + "\n" + str(err) + \
                " - " + str(traceback.format_exc())
            self.logdispatch.log(LogPriority.ERROR, self.detailedresults)
        self.formatDetailedResults("fix", self.rulesuccess, self.detailedresults)
        self.logdispatch.log(LogPriority.INFO, self.detailedresults)
        return self.rulesuccess

    def fixAllow(self):
        """

        @return:
        """

        success = True
        allowfile = "/etc/hosts.allow"
        allowtmp = allowfile + ".stonixtmp"

        try:

            f = open(allowtmp, "w")
            f.writelines(self.hosts_allow_contents)
            f.close()

            self.iditerator += 1
            myid = iterate(self.iditerator, self.rulenumber)
            event = {"eventtype": "conf",
                     "filepath": allowfile}
            self.statechglogger.recordchgevent(myid, event)
            self.statechglogger.recordfilechange(allowfile, allowtmp, myid)

            os.rename(allowtmp, allowfile)
            os.chmod(allowfile, 0644)
            os.chown(allowfile, 0, 0)

            return success

        except IOError:
            success = False

        return success

    def fixDeny(self):
        """

        @return:
        """

        success = True
        denyfile = "/etc/hosts.deny"
        denytmp = denyfile + ".stonixtmp"

        try:

            f = open(denytmp, "w")
            f.write(HOSTSDENYDEFAULT)
            f.close()

            self.iditerator += 1
            myid = iterate(self.iditerator, self.rulenumber)
            event = {"eventtype": "conf",
                     "filepath": denyfile}
            self.statechglogger.recordchgevent(myid, event)
            self.statechglogger.recordfilechange(denyfile, denytmp, myid)

            os.rename(denytmp, denyfile)
            os.chmod(denyfile, 0644)
            os.chown(denyfile, 0, 0)

        except IOError:
            success = False

        return success
