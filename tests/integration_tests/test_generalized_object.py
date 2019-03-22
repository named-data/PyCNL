import random
import time

from pyndn import Name, Face, MetaInfo
from pyndn.util import Blob
from pyndn.util.common import Common
from pycnl import Namespace
from pycnl.generalized_object import ContentMetaInfo, GeneralizedObjectHandler

import facehelper


def startProducer(face, sequenceNumber):
    streamNamespace = Namespace(
        "/localhost/stream_prefix", facehelper.getDefaultKeyChain())
    streamNamespace.setFace(face, facehelper.errorOnRegisterFailed)
    sequenceNamespace = streamNamespace[str(sequenceNumber)]

    contentMetaInfo = ContentMetaInfo()
    contentMetaInfo.setContentType("ndnrtc4")
    contentMetaInfo.setTimestamp(Common.getNowMilliseconds())
    contentMetaInfo.setHasSegments(True)
    contentMetaInfo.setOther(Blob("Debug other"))
    sequenceNamespace["_meta"].serializeObject(contentMetaInfo.wireEncode())

    metaInfo = MetaInfo()
    metaInfo.setFinalBlockId(Name().appendSegment(1)[0])
    sequenceNamespace.setNewDataMetaInfo(metaInfo)
    sequenceNamespace[Name.Component.fromSegment(0)].serializeObject(
        Blob("Test"))
    sequenceNamespace[Name.Component.fromSegment(1)].serializeObject(
        Blob(" message " + str(sequenceNumber)))


def startConsumer(face, sequenceNumber, theReceivedObject):
    prefix = Name("/localhost/stream_prefix/%d" % sequenceNumber)
    prefixNamespace = Namespace(prefix)
    prefixNamespace.setFace(face)

    def onGeneralizedObject(contentMetaInfo, obj):
        facehelper.stopProcessEvents()
        theReceivedObject[0] = contentMetaInfo
        theReceivedObject[1] = obj

    prefixNamespace.setHandler(GeneralizedObjectHandler(
        onGeneralizedObject)).objectNeeded()


def test_generalized_object():
    sequenceNumber = random.randint(0, 99999999)

    faceP = Face()
    facehelper.setCommandSigningInfo(faceP)
    startProducer(faceP, sequenceNumber)

    theReceivedObject = [None, None]
    faceC = Face()
    startConsumer(faceC, sequenceNumber, theReceivedObject)

    facehelper.processEvents([faceP, faceC], duration=4.000)

    contentMetaInfo, obj = theReceivedObject
    assert contentMetaInfo is not None, "Object not received"
    assert contentMetaInfo.getContentType() == "ndnrtc4"
    assert str(obj) == "Test message %d" % sequenceNumber
