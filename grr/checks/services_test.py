#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for service state checks."""

from grr.lib import flags
from grr.lib import test_lib
from grr.lib.checks import checks_test_lib
from grr.lib.rdfvalues import client as rdf_client
from grr.parsers import linux_service_parser
from grr.parsers import linux_service_parser_test


class XinetdServiceStateTests(checks_test_lib.HostCheckTest):

  @classmethod
  def setUpClass(cls):
    cls.LoadCheck("services.yaml")
    cls.parser = linux_service_parser.LinuxXinetdParser().ParseMultiple

  def RunXinetdCheck(self,
                     chk_id,
                     svc,
                     disabled,
                     sym,
                     found,
                     xinetd=False,
                     should_detect=True):
    host_data = self.SetKnowledgeBase()
    cfgs = linux_service_parser_test.GenXinetd(svc, disabled)
    stats, files = linux_service_parser_test.GenTestData(cfgs, cfgs.values())
    data = list(self.parser(stats, files, None))

    # create entries on whether xinetd itself is setup to start or not
    if xinetd:
      cfgs = linux_service_parser_test.GenInit(
          "xinetd", "the extended Internet services daemon")
      stats, files = linux_service_parser_test.GenTestData(cfgs, cfgs.values())
      lsb_parser = linux_service_parser.LinuxLSBInitParser()
      data.extend(list(lsb_parser.ParseMultiple(stats, files, None)))

    host_data["LinuxServices"] = self.SetArtifactData(parsed=data)
    results = self.RunChecks(host_data)

    if should_detect:
      self.assertCheckDetectedAnom(chk_id, results, sym, found)
    else:
      self.assertCheckUndetected(chk_id, results)

  def testEmptyXinetdCheck(self):
    chk_id = "CIS-INETD-WITH-NO-SERVICES"
    sym = "Missing attribute: xinetd running with no xinetd-managed services."
    found = ["Expected state was not found"]

    # xinetd is running and the only service is disabled - there should be a hit
    self.RunXinetdCheck(
        chk_id, "finger", "yes", sym, found, xinetd=True, should_detect=True)

    # xinetd is running and there is a service enabled - no hit
    self.RunXinetdCheck(
        chk_id, "finger", "no", sym, found, xinetd=True, should_detect=False)
    # xinetd not running and the only service is disabled - no hit
    self.RunXinetdCheck(
        chk_id, "finger", "yes", sym, found, xinetd=False, should_detect=False)
    # xinetd not running and there is a service enabled - no hit
    self.RunXinetdCheck(
        chk_id, "finger", "no", sym, found, xinetd=False, should_detect=False)

  def testLegacyXinetdServicesCheck(self):
    chk_id = "CIS-SERVICE-LEGACY-SERVICE-ENABLED"
    sym = "Found: Legacy services are running."
    found = ["telnet is started by XINETD"]
    self.RunXinetdCheck(chk_id, "telnet", "no", sym, found)
    self.RunXinetdCheck(
        chk_id, "telnet", "yes", sym, found, should_detect=False)

  def testUnwantedServicesCheck(self):
    chk_id = "CIS-SERVICE-SHOULD-NOT-RUN"
    sym = "Found: Remote administration services are running."
    found = ["webmin is started by XINETD"]
    self.RunXinetdCheck(chk_id, "webmin", "no", sym, found)
    self.RunXinetdCheck(
        chk_id, "webmin", "yes", sym, found, should_detect=False)


class SysVInitStateTests(checks_test_lib.HostCheckTest):

  results = None

  @classmethod
  def setUpClass(cls):
    cls.LoadCheck("services.yaml")
    cls.parser = linux_service_parser.LinuxSysVInitParser().ParseMultiple

  def setUp(self, *args, **kwargs):
    super(SysVInitStateTests, self).setUp(*args, **kwargs)
    self.RunSysVChecks()

  def RunSysVChecks(self):
    host_data = self.SetKnowledgeBase()
    links = ["/etc/rc2.d/S50xinetd", "/etc/rc2.d/S60wu-ftpd",
             "/etc/rc2.d/S10ufw"]
    stats, files = linux_service_parser_test.GenTestData(
        links, [""] * len(links), st_mode=41471)
    parsed = list(self.parser(stats, files, None))
    host_data["LinuxServices"] = self.SetArtifactData(parsed=parsed)
    self.results = self.RunChecks(host_data)

  def testEmptyXinetdCheck(self):
    chk_id = "CIS-INETD-WITH-NO-SERVICES"
    sym = "Missing attribute: xinetd running with no xinetd-managed services."
    self.assertCheckDetectedAnom(chk_id, self.results, sym)

  def testLegacyServicesCheck(self):
    chk_id = "CIS-SERVICE-LEGACY-SERVICE-ENABLED"
    sym = "Found: Legacy services are running."
    found = ["wu-ftpd is started by INIT"]
    self.assertCheckDetectedAnom(chk_id, self.results, sym, found)

  def testRequiredServicesNotRunningCheck(self):
    chk_id = "CIS-SERVICE-SHOULD-RUN"
    sym = "Missing attribute: Sysstat is not started at boot time."
    self.assertCheckDetectedAnom(chk_id, self.results, sym)


class ListeningServiceTests(checks_test_lib.HostCheckTest):

  @classmethod
  def setUpClass(cls):
    cls.LoadCheck("services.yaml")

  def GenHostData(self):
    # Create some host_data..
    host_data = self.SetKnowledgeBase()
    loop4 = self.AddListener("127.0.0.1", 6000)
    loop6 = self.AddListener("::1", 6000, "INET6")
    ext4 = self.AddListener("10.1.1.1", 6000)
    ext6 = self.AddListener("fc00::1", 6000, "INET6")
    x11 = rdf_client.Process(name="x11", pid=1233, connections=[loop4, loop6])
    xorg = rdf_client.Process(
        name="xorg", pid=1234, connections=[loop4, loop6, ext4, ext6])
    sshd = rdf_client.Process(
        name="sshd", pid=1235, connections=[loop4, loop6, ext4, ext6])
    # Note: ListProcessesGrr is a flow artifact, hence it needs to be of
    # raw context.
    host_data["ListProcessesGrr"] = self.SetArtifactData(raw=[x11, xorg, sshd])
    return host_data

  def testFindListeningServicesCheck(self):
    chk_id = "CIS-SERVICE-SHOULD-NOT-LISTEN"
    sym = "Found: Insecure services are accessible over the network."
    found = ["xorg (pid 1234) listens on 127.0.0.1,::1,10.1.1.1,fc00::1"]
    host_data = self.GenHostData()
    results = self.RunChecks(host_data)
    self.assertCheckDetectedAnom(chk_id, results, sym, found)

  def testFindNoRunningLogserver(self):
    chk_id = "CIS-SERVICE-LOGSERVER-RUNNING"
    sym = "Missing attribute: Logging software is not running."
    context = "RAW"
    found = ["Expected state was not found"]
    host_data = self.GenHostData()
    # Try it without rsyslog.
    results = self.RunChecks(host_data)
    self.assertCheckDetectedAnom(chk_id, results, sym, found)
    # Now rsyslog is running.
    logs = rdf_client.Process(name="rsyslogd", pid=1236)
    host_data["ListProcessesGrr"][context].append(logs)
    results = self.RunChecks(host_data)
    self.assertCheckUndetected(chk_id, results)
    # Check with some problematic real-world data.
    host_data = self.GenHostData()  # Reset the host_data.
    # Added a non-logger process. We expect to raise an anom.
    proc1 = rdf_client.Process(
        name="python",
        pid=10554,
        ppid=1,
        exe="/usr/bin/python",
        cmdline=["/usr/bin/python", "-E", "/usr/sbin/foo_agent",
                 "/etc/foo/conf.d/rsyslogd.conf", "/etc/foo/foobar.conf"])
    host_data["ListProcessesGrr"][context].append(proc1)
    results = self.RunChecks(host_data)
    self.assertCheckDetectedAnom(chk_id, results, sym, found)

    # Now added a logging service proc. We expect no anom. this time.
    proc2 = rdf_client.Process(
        name="rsyslogd",
        pid=10200,
        ppid=1,
        exe="/sbin/rsyslogd",
        cmdline=["/sbin/rsyslogd", "-i", "/var/run/rsyslogd.pid", "-m", "0"])
    host_data["ListProcessesGrr"][context].append(proc2)
    results = self.RunChecks(host_data)
    self.assertCheckUndetected(chk_id, results)

    # Add yet another non-logger process. We should still raise no anom.
    proc3 = rdf_client.Process(
        name="foobar",
        pid=31337,
        ppid=1,
        exe="/usr/local/bin/foobar",
        cmdline=["/usr/local/bin/foobar", "--test", "args"])
    host_data["ListProcessesGrr"][context].append(proc3)
    results = self.RunChecks(host_data)
    self.assertCheckUndetected(chk_id, results)


def main(argv):
  test_lib.GrrTestProgram(argv=argv)


if __name__ == "__main__":
  flags.StartMain(main)
