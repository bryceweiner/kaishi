#!/usr/bin/env python
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

import tenjin
from tenjin.helpers import *

class P2PClient(object):
  def __init__(self):
    socket.setdefaulttimeout(5)
    self.debug = False
    self.nicks = {}
    self.pings = {}
    self.peers = []
    self.uidlist = []
    self.posts = []
    self.provider = 'http://vector.cluenet.org/~tj9991/provider.php'

    print '----------------------------------------'
    print 'kaishi pre-release alpha'
    print 'If you are unfamiliar with kaishi, please type /help'
    print '----------------------------------------'
    print 'Initializing Peer-to-Peer network interfaces...'

    self.host = urllib.urlopen('http://www.showmyip.com/simple/').read()
    self.port = 44545
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

    data = zlib.compress(data, 9)
    
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
      except:
        self.debugMessage('Failed to establish a connection.')
        pass
      
      if data and uid not in self.uidlist:
        if peerid not in self.peers and identifier != 'JOIN' and identifier != 'DROP':
          self.addPeer(peerid)
          self.debugMessage('Adding ' + peerid + ' from outside message')
          
        if identifier == 'POST':
          self.posts.append(message)
          self.writeBoardPage()
        elif identifier == 'MSG':
          print '\n<' + self.getPeerNickname(peerid) + '> ' + message
        elif identifier == 'ACTION':
          print '\n* ' + self.getPeerNickname(peerid) + ' ' + message
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
            
            self.debugMessage(self.getPeerNickname(peerid) + ' joined network')
        elif identifier == 'PEERS': # list of connected peers
          peers = pickle.loads(message)
          for peer, peer_nick in peers.items():
            self.addPeer(peer)
            self.setPeerNickname(peer, peer_nick)
          self.debugMessage('Got peerlist from ' + peerid)
        elif identifier == 'DROP':
          self.dropPeer(peerid)
        elif identifier == 'PING':
          if peerid in self.pings:
            self.pings.update({peerid: time.time()})
          self.debugMessage('Got PING from ' + peerid)
        elif identifier == 'NICK':
          print '* ' + self.getPeerNickname(peerid) + ' is now known as ' + message
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
            elif data == '/clue':
              print 'Adding Scalar.ClueNet.org:44545 to peer list...'
              if not self.addPeer('67.18.89.26:44545'):
                print 'Unable to connect to ClueNet.'
            elif data == 'provider':
              self.getPeersFromProvider()
            elif data == '/local' or data == '/myid':
              print self.peerid + ' (Displayed as ' + self.getPeerNickname(self.peerid) + ')'
            elif data.startswith('/peers') or data.startswith('/peerlist'):
              print str(len(self.peers)) + ' other peers in current scope.'
              for peerid in self.peers:
                print self.getPeerNickname(peerid)
            elif data.startswith('/add') or data.startswith('/addpeer'):
              command, peerid = data.split(' ')
              if self.addPeer(peerid):
                print 'Successfully added peer.'
              else:
                print 'Unable to establish connection with peer.'
            elif data.startswith('/nick'):
             command, nick = data.split(' ', 1)
             self.setPeerNickname(self.peerid, nick)
             self.sendData('NICK', nick)
            elif data.startswith('/clearpeers'):
              for peerid in self.peers:
                self.dropPeer(peerid)
              print 'Cleared peer list.'
            elif data.startswith('/me') or data.startswith('/action'):
             command, action = data.split(' ', 1)
             self.sendData('ACTION', action)
            elif data.startswith('/debug'):
              self.debug = True
            elif data == '/help':
              print 'Commands: /local /peers /addpeer /clearpeers /nick /clue /help /quit'
            else:
              print 'Unknown command.  Message discarded.'
          else:
            t = datetime.datetime.now()
            date = t.strftime("%y/%m/%d(%a)%H:%M:%S")

            post_filename = None
            post_message = data
            post_filedata = ''
            post_img = ''
            filename = None
            message = data

            if data.startswith('"'):
              end = data.find('"', 1)
              if end != -1:
                filename = data[1:end]
                message = data[end+2:]

            try:
              if os.path.isfile(filename):
                post_filename = filename
                post_message = message
            except:
              pass
            if post_filename:
              f = open(post_filename)
              try:
                post_filedata_io_base64 = StringIO.StringIO()
                base64.encode(f, post_filedata_io_base64)
                post_filedata_base64 = post_filedata_io_base64.getvalue()
                post_filedata = base64.decodestring(post_filedata_base64)
                post_filedata_base64 = base64.urlsafe_b64encode(post_filedata)
              finally:
                f.close()

            if post_filedata:
              content_type, width, height = getImageInfo(post_filedata)
              if content_type in ['image/png', 'image/jpeg', 'image/gif']:
                post_img = 'data:' + content_type + ';base64,' + post_filedata_base64
              else:
                print 'Unknown filetype: ' + content_type + str(width)
            
            self.posts.append(buildPost(post_img, message, date, makeID(message)))
            #self.writeBoardPage()

            self.sendData('MSG', data)
      except KeyboardInterrupt:
        self.gracefulExit()

  def addPeer(self, peerid):
    result = False
    if not peerid in self.peers and peerid != self.peerid:
      self.peers.append(peerid)
      result = self.sendData('JOIN', self.getPeerNickname(self.peerid)) # send our nickname in the message of JOIN
      self.debugMessage('Added peer: ' + self.getPeerNickname(peerid))
      if not result:
        self.dropPeer(peerid)
    return result

  def dropPeer(self, peerid):
    if peerid in self.peers and peerid != self.peerid:
      del self.peers[self.peers.index(peerid)]
      self.debugMessage(self.getPeerNickname(peerid) + ' dropped from network')
        
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
    print 'Found ' + str(added_nodes) + ' nodes on the provider.'
    
  def getPosts(self):
    posts = ''
    for post in reversed(self.posts):
      posts += post + '<hr>'
    return posts
      
  def writeBoardPage(self):
    page_rendered = renderTemplate({'posts': self.getPosts()})
    
    f = open('p2pib.html', 'w')
    try:
      f.write(page_rendered)
    finally:
      f.close()

  def debugMessage(self, message):
    if self.debug:
      print message

  def gracefulExit(self):
    self.sendDropNotice()
    self.socket.close()
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

def buildPost(image, message, date, uid):
  post = '<table>' + \
  '  <tbody>' + \
  '    <tr>' + \
  '      <td class="doubledash">' + \
  '        &gt;&gt;' + \
  '      </td>' + \
  '      <td class="reply" id="reply' + uid + '">' + \
  '        <a name="' + uid + '"></a>' + \
  '        <label>' + \
  '          <input type="checkbox" name="delete" value="' + uid + '">' + \
  '          ' + date + \
  '        </label>' + \
  '        <span class="reflink">' + \
  '          <a href="#' + uid + '">No.</a>' + \
  '          <a href="#i' + uid + '">' + uid + '</a>' + \
  '        </span>'
  if image:
    post += '        <span id="thumb' + uid + '"><img src="' + image + '" alt="' + uid + '" class="thumb"></span>'
  post += '        <blockquote>' + \
  '          ' + message + \
  '        </blockquote>' + \
  '      </td>' + \
  '    </tr>' + \
  '  </tbody>' + \
  '</table>'

  return post

def getImageInfo(data):
  data = str(data)
  size = len(data)
  height = -1
  width = -1
  content_type = ''

  # handle GIFs
  if (size >= 10) and data[:6] in ('GIF87a', 'GIF89a'):
    # Check to see if content_type is correct
    content_type = 'image/gif'
    w, h = struct.unpack("<HH", data[6:10])
    width = int(w)
    height = int(h)

  # See PNG 2. Edition spec (http://www.w3.org/TR/PNG/)
  # Bytes 0-7 are below, 4-byte chunk length, then 'IHDR'
  # and finally the 4-byte width, height
  elif ((size >= 24) and data.startswith('\211PNG\r\n\032\n')
        and (data[12:16] == 'IHDR')):
    content_type = 'image/png'
    w, h = struct.unpack(">LL", data[16:24])
    width = int(w)
    height = int(h)

  # Maybe this is for an older PNG version.
  elif (size >= 16) and data.startswith('\211PNG\r\n\032\n'):
    # Check to see if we have the right content type
    content_type = 'image/png'
    w, h = struct.unpack(">LL", data[8:16])
    width = int(w)
    height = int(h)

  # handle JPEGs
  elif (size >= 2) and data.startswith('\377\330'):
    content_type = 'image/jpeg'
    jpeg = StringIO.StringIO(data)
    jpeg.read(2)
    b = jpeg.read(1)
    try:
      while (b and ord(b) != 0xDA):
        while (ord(b) != 0xFF): b = jpeg.read
        while (ord(b) == 0xFF): b = jpeg.read(1)
        if (ord(b) >= 0xC0 and ord(b) <= 0xC3):
          jpeg.read(3)
          h, w = struct.unpack(">HH", jpeg.read(4))
          break
        else:
          jpeg.read(int(struct.unpack(">H", jpeg.read(2))[0])-2)
        b = jpeg.read(1)
      try:
        width = int(w)
        height = int(h)
      except:
        pass
    except struct.error:
      pass
    except ValueError:
      pass

  return content_type, width, height

def renderTemplate(template_values={}):
  values = {
    'title': 'P2P Imageboard',
    'board': None,
    'board_name': None,
    'is_page': 'false',
    'replythread': 0,
    'anonymous': None,
    'forced_anonymous': None,
    'disable_subject': None,
    'tripcode_character': None,
    'default_style': 'Futaba',
    'unique_user_posts': None,
    'page_navigator': '',
  }
  
  engine = tenjin.Engine()  
  values.update(template_values)
  
  return engine.render('board.html', values)

if __name__=='__main__':
  p2pclient = P2PClient()
