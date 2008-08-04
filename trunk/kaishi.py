#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# P2P framework for simple, non-anonymous network
# building from known nodes
#
# tslocum@gmail.com
# http://www.tj9991.com
# http://code.google.com/p/kaishi/

__author__ = 'Trevor "tj9991" Slocum'
__license__ = 'GNU GPL v3'

import datetime
import md5
import time
import base64
import sys
import os
import urllib
import zlib
import struct
import StringIO
import pickle
import thread
import socket

class P2PClient(object):
  def __init__(self):
    socket.setdefaulttimeout(5)
    self.debug = False
    self.nicks = {}
    self.pings = {}
    self.peers = []
    self.uidlist = []
    self.provider = 'http://vector.cluenet.org/~tj9991/provider.php'

    print '----------------------------------------'
    print 'kaishi pre-release alpha'
    print 'If you are unfamiliar with kaishi, please type /help'
    print '----------------------------------------'
    print 'Initializing Peer-to-Peer network interfaces...'

    self.host = urllib.urlopen('http://www.showmyip.com/simple/').read()
    self.port = 44545
    self.irc_port = 44546
    self.irc_address = '127.0.0.1:' + str(self.irc_port)
    self.peerid = self.host + ':' + str(self.port)
    
    if len(sys.argv) > 1:
      self.host, self.port = peerIDToTuple(sys.argv[1])
      self.port = int(self.port)
      self.peers = [self.host + ':' + str(self.port)]
      
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.bind(('', self.port))
    
    print 'Entering main network loop...'
    
    thread.start_new_thread(self.receiveData, ())
    thread.start_new_thread(self.pingAllPeers, ())
    thread.start_new_thread(self.pingProvider, ())

    print 'Requesting known nodes from IP provider...'
    
    self.fetchPeersFromProvider()

    print 'Now available for connections on the kaishi network as ' + self.peerid
    print 'Type /irc to start the local IRC server, and then connect to ' + self.irc_address
    print '----------------------------------------'
    
    self.getInput()

  def sendData(self, identifier, message, **kwargs):
    args = {'uid': None,
            'origin': self.peerid,
            'to': None,
            'bounce': True}
    args.update(kwargs)

    if not args['uid']:
      uid = makeID(message)
      self.debugMessage('Making uid for ' + message)
    else:
      uid = args['uid']
    self.uidlist.append(uid)
    if args['bounce']:
      bounce = '1'
    else:
      bounce = '0'
    
    data = identifier + ':' + bounce + ':' + uid + ':' + base64.encodestring(args['origin']) + ':' + message

    data = zlib.compress(unicode(data), 9)
    
    if args['to']:
      try:
        self.socket.sendto(data, peerIDToTuple(args['to']))
      except:
        self.dropPeer(args['to'])
        return False
      return True
    else:
      for peer in self.peers:
        try:
          self.socket.sendto(data, peerIDToTuple(peer))
        except:
          self.dropPeer(peer)
          return False
      return True

  def receiveData(self):
    while 1:
      data = None
      try:
        data, address = self.socket.recvfrom(65536)
        data = zlib.decompress(data)
        sender_peerid = address[0] + ':' + str(address[1])
        identifier, bounce, uid, origin, message = data.split(':', 4)
        peerid = base64.decodestring(origin)
      except socket.timeout:
        pass
      except:
        self.debugMessage('Failed to establish a connection.')
        pass
      
      if data and uid not in self.uidlist:
        if peerid not in self.peers and identifier != 'JOIN' and identifier != 'DROP':
          self.addPeer(peerid)
          self.debugMessage('Adding ' + peerid + ' from outside message')
          
        if identifier == 'MSG':
          self.printChatMessage(peerid, message)
        elif identifier == 'ACTION':
          self.printChatMessage(peerid, message, True)
        elif identifier == 'JOIN': # a user requests that they join the network
          if peerid not in self.peers:
            self.addPeer(peerid)
            self.setPeerNickname(peerid, message) # add the nick sent in the JOIN message
            if self.getPeerNickname(self.peerid) != self.peerid:
              self.sendData('NICK', self.getPeerNickname(self.peerid), to=peerid, bounce=False) # send them our nick
              self.debugMessage('Sent NICK to ' + self.getPeerNickname(peerid))
            else:
              self.debugMessage('Did not send NICK to ' + self.getPeerNickname(peerid))
            self.sendData('PEERS', self.makePeerList(), to=peerid, bounce=False)
            print message + ' has joined the network.'
        elif identifier == 'PEERS': # list of connected peers
          peers = pickle.loads(message)
          for peer, peer_nick in peers.items():
            self.addPeer(peer)
            self.setPeerNickname(peer, peer_nick)
          self.debugMessage('Got peerlist from ' + peerid)
        elif identifier == 'DROP':
          print self.getPeerNickname(peerid) + ' has dropped from the network.'
          self.dropPeer(peerid)
        elif identifier == 'PING':
          if peerid in self.pings:
            self.pings.update({peerid: time.time()})
          self.debugMessage('Got PING from ' + peerid)
        elif identifier == 'NICK':
          print '* ' + self.getPeerNickname(peerid) + ' is now known as ' + message
          self.userNick(self.getPeerNickname(peerid), message)
          self.setPeerNickname(peerid, message)
        else:
          self.debugMessage('Unhandled: ' + identifier + ' ' + message)

        if bounce == '1':
          self.sendData(identifier, message, uid=uid, origin=peerid)
      elif data:
        self.debugMessage('Not rerouting data: ' + data)
        
  def getInput(self):
    while 1:
      try:
        data = raw_input('>')
        if data != '':
          if data.startswith('/'):
            if data == '/q' or data == '/quit' or data == '/exit':
              self.gracefulExit()
            elif data == '/provider':
              self.getPeersFromProvider()
            elif data == '/irc':
              self.startIRC()
              print 'IRC server started at ' + self.irc_address
            elif data == '/local' or data == '/myid':
              print self.peerid + ' (Displayed as ' + self.getPeerNickname(self.peerid) + ')'
            elif data.startswith('/peers') or data.startswith('/peerlist'):
              self.callSpecialFunction('peers')
            elif data.startswith('/add') or data.startswith('/addpeer'):
              command, peerid = data.split(' ')
              if self.addPeer(peerid):
                print 'Successfully added peer.'
              else:
                print 'Unable to establish connection with peer.'
            elif data.startswith('/nick'):
             command, nick = data.split(' ', 1)
             self.callSpecialFunction('nick', nick)
            elif data.startswith('/clearpeers'):
              self.callSpecialFunction('clearpeers')
            elif data.startswith('/me') or data.startswith('/action'):
             command, action = data.split(' ', 1)
             self.sendData('ACTION', action)
            elif data.startswith('/debug'):
              self.debug = True
            elif data == '/help':
              print 'Commands: /local /peers /addpeer /provider /clearpeers /nick /help /quit'
            else:
              print 'Unknown command.  Message discarded.'
          else:
            self.sendData('MSG', data)
            
      except KeyboardInterrupt:
        self.gracefulExit()
  
  def callSpecialFunction(self, function, data=''):
    if function == 'peers':
      self.printMessage(str(len(self.peers)) + ' other peers in current scope.')
      for peerid in self.peers:
        self.printMessage(self.getPeerNickname(peerid))
    elif function == 'clearpeers':
      for peerid in self.peers:
        self.dropPeer(peerid)
      self.printMessage('Cleared peer list.')
    elif function == 'nick':
      if 'kaishi' not in data:
        self.setPeerNickname(self.peerid, data)
        self.sendData('NICK', data)
        self.printMessage('You are now known as ' + data)
      
  def addPeer(self, peerid):
    result = False
    if not peerid in self.peers and peerid != self.peerid:
      self.peers.append(peerid)
      result = self.sendData('JOIN', self.getPeerNickname(self.peerid)) # send our nickname in the message of JOIN
      self.debugMessage('Added peer: ' + self.getPeerNickname(peerid))
      if result:
        self.userJoin(self.getPeerNickname(peerid))
      else:
        self.dropPeer(peerid)
    return result

  def dropPeer(self, peerid):
    if peerid in self.peers and peerid != self.peerid:
      del self.peers[self.peers.index(peerid)]
      self.userPart(self.getPeerNickname(peerid))
      self.debugMessage(self.getPeerNickname(peerid) + ' has dropped from network')
        
  def getAllPeersExcept(self, exclude_peerid):
    peers = []
    for peerid in self.peers:
      if peerid != exclude_peerid:
        peers.append(peerid)
    return peers

  def getPeerNickname(self, peerid):
    if peerid in self.nicks:
      return self.nicks[peerid]
    else:
      return peerid

  def setPeerNickname(self, peerid, nickname):
    self.nicks.update({peerid: nickname})
    self.debugMessage('Set nickname for ' + peerid + ' to ' + nickname)

  def sendDropNotice(self):
    self.sendData('DROP', 'DROP')

  def pingAllPeers(self):
    for peerid in self.peers:
      if peerid in self.pings:
        if time.time() - self.pings[peerid] >= 20:
          self.dropPeer(peerid)
          self.debugMessage('Dropping ' + self.getPeerNickname(peerid) + ' (no ping responses for 20 seconds)')
      else:
        self.pings.update({peerid: time.time()})
      self.sendData('PING', 'PING', to=peerid, bounce=False)
    time.sleep(15)
    thread.start_new_thread(self.pingAllPeers, ())

  def pingProvider(self):
    time.sleep(60)
    urllib.urlopen(self.provider).read()
    thread.start_new_thread(self.pingProvider, ())
    
  def makePeerList(self):
    peers = {}
    for peerid in self.peers:
      peers.update({peerid: self.getPeerNickname(peerid)})
    
    return pickle.dumps(peers)

  def fetchPeersFromProvider(self):
    self.debugMessage('Fetching peers from provider')
    added_nodes = 0
    known_nodes = urllib.urlopen(self.provider).read()
    if known_nodes != '':
      known_nodes = known_nodes.split('\n')
      for known_node in known_nodes:
        if known_node != '':
          added_nodes += 1
          self.addPeer(known_node)
          self.debugMessage('Added ' + known_node + ' from provider')
    self.printMessage('Found ' + str(added_nodes) + ' nodes on the provider.')
  
  def startIRC(self):
    self.irc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.irc_socket.bind(('', self.irc_port))
    self.irc_socket.listen(1)
    thread.start_new_thread(self.handleIRC, ())
    
  def handleIRC(self):
    while 1:
      try:
        self.irc_connection, address = self.irc_socket.accept()
        break
      except socket.timeout:
        pass
      
    self.rawMSG('NOTICE AUTH :connected to the local kaishi irc server.')
    self.clientMSG(001, 'kaishi')
    self.rawMSG('JOIN #kaishi')
    self.rawMSG('353 kaishi = #kaishi :kaishi')
    self.rawMSG('366 kaishi #kaishi :End of /NAMES list')
    for peerid in self.peers:
      self.userJoin(self.getPeerNickname(peerid))
    while 1:
      try:
        data = self.irc_connection.recv(1024)
        if data:
          data = unicode(data).encode('utf-8')
          if data.startswith('PRIVMSG #kaishi :'):
            data = data[17:]
            if ord(data[0]) == 1:
              data = data[8:len(data)-2]
              self.sendData('ACTION', data)
            else:
              self.sendData('MSG', data)
          elif data.startswith('PEERS') or data.startswith('PEERLIST'):
            self.callSpecialFunction('peers')
          elif data.startswith('CLEARPEERS'):
            self.callSpecialFunction('clearpeers')
          elif data.startswith('NICK :'):
            nick = data[6:]
            self.callSpecialFunction('nick', nick)
        else:
          break
      except:
        pass
      
  def rawMSG(self, message):
    try:
      self.irc_connection.send(':kaishi!kaishi@127.0.0.1 ' + message + '\n')
    except:
      pass

  def userMSG(self, user, message, action=False):
    try:
      if action:
        message = chr(1) + 'ACTION ' + message + chr(1)
      self.irc_connection.send(':' + user + '!' + user + '@127.0.0.1 PRIVMSG #kaishi :' + message + '\n')
    except:
      pass

  def userJoin(self, user):
    try:
      self.irc_connection.send(':' + user + '!' + user + '@127.0.0.1 JOIN #kaishi\n')
    except:
      pass

  def userPart(self, user):
    try:
      self.irc_connection.send(':' + user + '!' + user + '@127.0.0.1 PART #kaishi\n')
    except:
      pass

  def userNick(self, user, newnick):
    try:
      self.irc_connection.send(':' + user + '!' + user + '@127.0.0.1 NICK ' + newnick + '\n')
    except:
      pass

  def clientMSG(self, code, message):
    try:
      self.irc_connection.send(':kaishi!kaishi@127.0.0.1 ' + str(code) + ' ' + message + '\n')
    except:
      pass
    
  def printChatMessage(self, peerid, message, action=False):
    if not action:
      print '\n<' + self.getPeerNickname(peerid) + '> ' + message
      self.userMSG(self.getPeerNickname(peerid), message)
    else:
      print '\n* ' + self.getPeerNickname(peerid) + ' ' + message
      self.userMSG(self.getPeerNickname(peerid), message, True)
    
  def printMessage(self, message):
    print message
    self.userMSG('KAISHI', message)
    
  def debugMessage(self, message):
    if self.debug:
      print message

  def gracefulExit(self):
    self.sendDropNotice()
    self.socket.close()
    try:
      self.irc_connection.close()
    except:
      pass
    sys.exit()

def peerIDToTuple(peerid):
  host, port = peerid.rsplit(':', 1)
  if host.startswith('['):
    host = host[1:len(host)-1]
  return (host, int(port))

def makeID(data):
  m = md5.new()
  m.update(str(time.time()))
  m.update(str(data))
  return base64.encodestring(m.digest())[:-3].replace('/', '$')

if __name__=='__main__':
  p2pclient = P2PClient()
