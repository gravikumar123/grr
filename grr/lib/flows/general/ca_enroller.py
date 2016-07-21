#!/usr/bin/env python
"""A flow to enrol new clients."""



import logging
from grr.lib import aff4
from grr.lib import client_index
from grr.lib import flow
from grr.lib import queues
from grr.lib import rdfvalue
from grr.lib import utils
from grr.lib.aff4_objects import aff4_grr
from grr.lib.rdfvalues import client as rdf_client
from grr.lib.rdfvalues import crypto as rdf_crypto
from grr.lib.rdfvalues import structs as rdf_structs
from grr.proto import flows_pb2


class CAEnrolerArgs(rdf_structs.RDFProtoStruct):
  protobuf = flows_pb2.CAEnrolerArgs


class CAEnroler(flow.GRRFlow):
  """Enrol new clients."""

  args_type = CAEnrolerArgs

  @flow.StateHandler()
  def Start(self):
    """Sign the CSR from the client."""
    client = aff4.FACTORY.Create(
        self.client_id, aff4_grr.VFSGRRClient, mode="rw", token=self.token)

    if self.args.csr.type != rdf_crypto.Certificate.Type.CSR:
      raise IOError("Must be called with CSR")

    csr = rdf_crypto.CertificateSigningRequest(self.args.csr.pem)
    # Verify the CSR. This is not strictly necessary but doesn't harm either.
    try:
      csr.Verify(csr.GetPublicKey())
    except rdf_crypto.VerificationError:
      raise flow.FlowError("CSR for client %s did not verify: %s" %
                           (self.client_id, csr.AsPEM()))

    # Verify that the CN is of the correct form. The common name should refer
    # to a client URN.
    self.cn = rdf_client.ClientURN.FromPublicKey(csr.GetPublicKey())
    if self.cn != csr.GetCN():
      raise IOError("CSR CN %s does not match public key %s." %
                    (csr.GetCN(), self.cn))

    logging.info("Will sign CSR for: %s", self.cn)

    cert = rdf_crypto.RDFX509Cert.ClientCertFromCSR(csr)

    # This check is important to ensure that the client id reported in the
    # source of the enrollment request is the same as the one in the
    # certificate. We use the ClientURN to ensure this is also of the correct
    # form for a client name.
    if self.cn != self.client_id:
      raise flow.FlowError("Certificate name %s mismatch for client %s",
                           self.cn, self.client_id)

    # Set and write the certificate to the client record.
    client.Set(client.Schema.CERT, cert)
    client.Set(client.Schema.FIRST_SEEN, rdfvalue.RDFDatetime().Now())

    index = aff4.FACTORY.Create(
        client_index.MAIN_INDEX,
        aff4_type=client_index.ClientIndex,
        object_exists=True,
        mode="rw",
        token=self.token)
    index.AddClient(client)
    client.Close(sync=True)

    # Publish the client enrollment message.
    self.Publish("ClientEnrollment", self.client_id)

    self.Log("Enrolled %s successfully", self.client_id)


enrolment_cache = utils.FastStore(5000)


class Enroler(flow.WellKnownFlow):
  """Manage enrolment requests."""
  well_known_session_id = rdfvalue.SessionID(
      queue=queues.ENROLLMENT, flow_name="Enrol")

  def ProcessMessage(self, message):
    """Begins an enrollment flow for this client.

    Args:
        message: The Certificate sent by the client. Note that this
        message is not authenticated.
    """
    cert = rdf_crypto.Certificate(message.payload)

    queue = self.well_known_session_id.Queue()

    client_id = message.source

    # It makes no sense to enrol the same client multiple times, so we
    # eliminate duplicates. Note, that we can still enroll clients multiple
    # times due to cache expiration.
    try:
      enrolment_cache.Get(client_id)
      return
    except KeyError:
      enrolment_cache.Put(client_id, 1)

    # Create a new client object for this client.
    client = aff4.FACTORY.Create(
        client_id, aff4_grr.VFSGRRClient, mode="rw", token=self.token)

    # Only enroll this client if it has no certificate yet.
    if not client.Get(client.Schema.CERT):
      # Start the enrollment flow for this client.
      flow.GRRFlow.StartFlow(
          client_id=client_id,
          flow_name="CAEnroler",
          csr=cert,
          queue=queue,
          token=self.token)
