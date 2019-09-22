import clr
clr.AddReference('SIPSorcery.SIP.Core')
from SIPSorcery.SIP import *

m_registrarSocket = "udp:127.0.0.1:7001"
m_regAgentSocket = "udp:127.0.0.1:7002"
m_notifierSocket = "udp:127.0.0.1:7003"
m_appServerSocket = "udp:192.168.11.50:7065"
m_proxySocketInternal = "udp:192.168.11.50:5060"
m_proxySocketLoopback = "udp:127.0.0.1:5060"

  #===== Utility functions to customise depending on deployment, such as single or mutliple server and private or public network. =====
 
def GetAppServer():
  return m_appServerSocket

def IsFromApplicationServer():
  return remoteEndPoint.ToString() == m_appServerSocket

def IsFromNotifierServer():
  return remoteEndPoint.ToString() == m_notifierSocket

  # Determines if a destination IP address is on the same local subnet or whether it's 
# on an external network.
#def IsLocalNetDestination(SIPEndPoint destinationAddress) :
def IsLocalNetDestination(destinationEP) :
  if destinationEP.Address.ToString().StartsWith("192.168.11."):
    return True
  else:
    return False

  #===== End of customisable utility functions =====

  #===== General utility functions =====

# Attempts to send a SIP request to an external user agent by first resolving the destination for the 
# request and then checking whether it is on the same subnet.
#def SendExternalRequest(SIPEndPoint receivedOn, SIPRequest req, String proxyBranch, IPAddress publicIP, bool sendTransparently):
def SendExternalRequest(receivedOn, req, proxyBranch, publicIP, sendTransparently):  
  #lookupResult = sys.Resolve(req) if (req.URI.Host != "asbw.alestravoip.com") else SIPDNSLookupResult(req.URI, SIPDNSLookupEndPoint(SIPEndPoint.ParseSIPEndPoint("sip:200.94.59.150"), 10000))
  lookupResult = sys.Resolve(req) if (req.URI.Host != "asbw.alestravoip.com") else sys.Resolve(SIPURI.ParseSIPURI("sip:200.94.59.150"))
  if lookupResult.Pending:
    # Do nothing.
    #sys.Log("DNS lookup pending.")
    pass
  elif lookupResult.LookupError != None or lookupResult.EndPointResults == None or lookupResult.EndPointResults.Count == 0:
    if req.Method.ToString() != "ACK":
      sys.Respond(req, SIPResponseStatusCodesEnum.DoesNotExistAnywhere, "Host " + req.URI.Host + " unresolvable")
  else:
    dest = lookupResult.EndPointResults[0].LookupEndPoint    
    if IsLocalNetDestination(dest):
      #sys.Log("Request destination " + dest.ToString() + " determined as local network.")
      if sendTransparently:
        sys.SendTransparent(dest, req, None) 
      else:
        sys.SendExternal(receivedOn, dest, req, proxyBranch, None) 
    else:
      #sys.Log("Request destination " + dest.ToString() + " determined as external network.")
      if sendTransparently:
        sys.SendTransparent(dest, req, publicIP) 
      else:
        sys.SendExternal(receivedOn, dest, req, proxyBranch, publicIP)

#def SendExternalResponse(SIPResponse resp, SIPEndPoint sendFromSIPEndPoint, IPAddress publicIP):
def SendExternalResponse(resp, sendFromSIPEndPoint, publicIP):
  dest = sys.Resolve(resp)
  #sys.Log("SendExternalResponse desination resolved to " + dest.ToString() + ".")
  if dest == None:
    sys.Log("The destination could not be resolved for a SIP response.")
    sys.Log(resp.ToString())
  elif IsLocalNetDestination(dest):
    sys.SendExternal(resp, sendFromSIPEndPoint, None)
  else:
    sys.SendExternal(resp, sendFromSIPEndPoint, publicIP)

  #===== End of general utility functions =====


if isreq:
  
  #===== SIP Request Processing =====

  sys.Log(summary)
  req.Header.MaxForwards = req.Header.MaxForwards - 1

  if req.Header.UserAgent != None and req.Header.UserAgent.StartsWith("Cisco") and (req.Header.UserAgent.Contains("8.3") or req.Header.UserAgent.Contains("8.5")):
    req.Header.Vias.TopViaHeader.ViaParameters.Remove("rport")

  if sipMethod == "REGISTER":
    if remoteEndPoint.ToString() == m_regAgentSocket:
      # The registration agent has indicated where it wants the REGISTER request sent to by adding a Route header.
      # Remove the header in case it confuses the SIP Registrar the REGISTER is being sent to.
      route = req.Header.Routes.PopRoute()
      if route == None:
        sys.Log("Registration agent request was missing Route header.\n" + req.ToString())
      else:
        destRegistrar = route.ToSIPEndPoint()
        req.Header.Routes = None
        sys.Log("destination registrar " + destRegistrar.ToString() + ".");
        if destRegistrar.ToString() == "udp:10.6.34.9:5060": destRegistrar = SIPEndPoint.ParseSIPEndPoint("udp:200.94.59.150:5060")
        #req.Header.Contact[0] = "<sip:20010197220015678910@10.1.1.2:5061;transport=TLS;ob>"
        if destRegistrar.Address.ToString() == "147.235.185.150":
          sys.Log("Mangling Via header for joecope and his bezeq provider.")
          sys.SendTransparent(destRegistrar, req, IPAddress.Parse("10.1.1.5"))
        else:
          sys.SendTransparent(destRegistrar, req, publicip)
    else:
      sys.SendInternal(remoteEndPoint, localEndPoint, m_registrarSocket, req, proxyBranch, m_proxySocketLoopback)

  elif sipMethod == "SUBSCRIBE":
    if remoteEndPoint.ToString() == m_regAgentSocket:
      # The registration agent can initiate subscriptions for MWI.
      sys.Log("MWI Subscription from registration agent, send external.")
      SendExternalRequest(localEndPoint, req, proxyBranch, publicip, False)
    else:
      sys.Log("External SUBSCRIBE.");
      sys.SendInternal(remoteEndPoint, localEndPoint, m_notifierSocket, req, proxyBranch, m_proxySocketLoopback)

  elif sipMethod == "NOTIFY":
    if IsFromApplicationServer() or IsFromNotifierServer():
      # Request from a SIP Application or Notification server for an external user agent.
      SendExternalRequest(localEndPoint, req, proxyBranch, publicip, False)
    else:
      if req.Header.Event != None and req.Header.Event.StartsWith("refer"):
        # REFER notification for app server.
        sys.SendInternal(remoteEndPoint, localEndPoint, GetAppServer().ToString(), req, proxyBranch, m_proxySocketInternal)
      else:
        # A notification from an external notification server.
        sys.SendInternal(remoteEndPoint, localEndPoint, m_notifierSocket, req, proxyBranch, m_proxySocketLoopback)
  
  else:
    # All other requests are processed by the Application Server.
    if IsFromApplicationServer():
      # Request from a SIP Application Server for an external user agent.
      if req.Method.ToString() == "ACK" or req.Method.ToString() == "CANCEL" or req.Method.ToString() == "INVITE":
        SendExternalRequest(None, req, None, publicip, True)
      else:
        SendExternalRequest(localEndPoint, req, proxyBranch, publicip, False)
    else:
      # Request from an external user agent for an Application Server.

      dispatcherEndPoint = sys.DispatcherLookup(req)
      if dispatcherEndPoint != None:
        sys.SendInternal(remoteEndPoint, localEndPoint, dispatcherEndPoint.ToString(), req, proxyBranch, m_proxySocketInternal)
      else:
        #appServer = GetAppServer()
        appServer = SIPEndPoint.ParseSIPEndPoint("udp:127.0.0.1:5002") if req.Header.From.FromURI.User == "aaronpolycom" else GetAppServer()
        if appServer != None:
          sys.SendInternal(remoteEndPoint, localEndPoint, appServer.ToString(), req, proxyBranch, m_proxySocketInternal)
        else:
          sys.Respond(req, SIPResponseStatusCodesEnum.BadGateway, "No sipsorcery app servers available")

  #===== End SIP Request Processing =====

else:

  #===== SIP Response Processing =====

  #sys.Log(summary)
 
  if sipMethod == "REGISTER" and remoteEndPoint.ToString() == m_registrarSocket:
    # REGISTER response from SIP Registrar.
    sys.SendExternal(resp, outSocket)

  elif sipMethod == "REGISTER":
    # REGISTER response for SIP Registration Agent.
    sys.SendTransparent(remoteEndPoint, localEndPoint, resp, SIPEndPoint.ParseSIPEndPoint(m_proxySocketLoopback), m_regAgentSocket, topVia.Branch)

  elif sipMethod == "NOTIFY" or sipMethod == "SUBSCRIBE":
    if not IsFromNotifierServer() and not IsFromApplicationServer():
      # Responses for SIP Notifier Server.
      sys.SendInternal(remoteEndPoint, localEndPoint, resp, outSocket)
    else:
      # Subscribe and notify responses for external user agents.
      SendExternalResponse(resp, outSocket, publicip)

  else: 
    if IsFromApplicationServer():
      # Response from an Application Server for an external UA.
      SendExternalResponse(resp, outSocket, publicip)
    else:
      # Responses from external UAs for SIP Application Servers.
      if resp.Header.CSeqMethod.ToString() == "ACK" or resp.Header.CSeqMethod.ToString() == "CANCEL" or resp.Header.CSeqMethod.ToString() == "INVITE":
        dispatcherEndPoint = sys.DispatcherLookup(resp)
        if dispatcherEndPoint == None:
          dispatcherEndPoint = GetAppServer()
        sys.SendTransparent(remoteEndPoint, localEndPoint, resp, SIPEndPoint.ParseSIPEndPoint(m_proxySocketInternal), dispatcherEndPoint, topVia.Branch)
      else:
        sys.SendInternal(remoteEndPoint, localEndPoint, resp, SIPEndPoint.ParseSIPEndPoint(m_proxySocketInternal))

  #===== End SIP Response Processing =====