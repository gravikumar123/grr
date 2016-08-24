#!/usr/bin/env python
"""Test for the flow state class."""



from grr.lib import rdfvalue
from grr.lib.rdfvalues import flows as rdf_flows
from grr.lib.rdfvalues import test_base


class FlowStateTest(test_base.RDFValueTestCase):

  rdfvalue_class = rdf_flows.FlowState

  def GenerateSample(self, number=0):
    res = rdf_flows.FlowState()
    res.Register("number", number)
    return res

  # Pickling has been deprecated so some tests won't work.
  def testComparisons(self):
    pass

  def testInitialization(self):
    pass

  def testHashability(self):
    pass

  def testSerialization(self):
    pass


class SessionIDTest(test_base.RDFValueTestCase):
  """Test SessionID."""

  rdfvalue_class = rdfvalue.SessionID

  def GenerateSample(self, number=0):
    id_str = "%08X" % (number % 2**32)
    return rdfvalue.SessionID(flow_name=id_str)

  def testSessionIDValidation(self):
    rdfvalue.SessionID(rdfvalue.RDFURN("aff4:/flows/A:12345678"))
    rdfvalue.SessionID(rdfvalue.RDFURN("aff4:/flows/A:TransferStore"))
    rdfvalue.SessionID(rdfvalue.RDFURN("aff4:/flows/DEBUG-user1:12345678"))
    rdfvalue.SessionID(rdfvalue.RDFURN("aff4:/flows/DEBUG-user1:12345678:hunt"))

  def testQueueGetterReturnsCorrectValues(self):
    s = rdfvalue.SessionID("A:12345678")
    self.assertEqual(s.Queue(), "A")

    s = rdfvalue.SessionID("DEBUG-user1:12345678:hunt")
    self.assertEqual(s.Queue(), "DEBUG-user1")

  def testFlowNameGetterReturnsCorrectValues(self):
    s = rdfvalue.SessionID("A:12345678")
    self.assertEqual(s.FlowName(), "12345678")

    s = rdfvalue.SessionID("DEBUG-user1:12345678:hunt")
    self.assertEqual(s.FlowName(), "12345678:hunt")

  def testBadStructure(self):
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/A:123456:1:"))
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/A:123456::"))
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/A:123456:"))
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/A:"))
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/:"))

  def testBadQueue(self):
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/A%b:12345678"))

  def testBadFlowID(self):
    self.assertRaises(rdfvalue.InitializeError, rdfvalue.SessionID,
                      rdfvalue.RDFURN("aff4:/flows/A:1234567G%sdf"))
