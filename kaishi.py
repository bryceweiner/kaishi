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
    self.debug = False
    self.nicks = {}
    self.pings = {}
    self.peers = []
    self.uidlist = []
    self.posts = []
    self.serverhost = 'localhost'
    self.serverport = 44545

    print '----------------------------------------'
    print 'kaishi pre-release alpha'
    print 'If you are unfamiliar with kaishi, please type /help'
    print '----------------------------------------'
    print 'Initializing Peer-to-Peer network interfaces...'

    self.hostname = urllib.urlopen('http://www.showmyip.com/simple/').read()
    self.peerid = self.hostname + ':' + str(self.serverport)
    
    if len(sys.argv) > 1:
      self.serverhost, self.serverport = peerIDToTuple(sys.argv[1])
      self.serverport = int(self.serverport)
      self.peers = [self.serverhost + ':' + str(self.serverport)]
      
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.bind(('', self.serverport))

    print 'Entering main network loop...'
    
    thread.start_new_thread(self.receiveData, ())
    thread.start_new_thread(self.pingAllPeers, ())

    print 'Now available for connections on the kaishi network as ' + self.peerid
    print '----------------------------------------'
    
    self.getInput()

  def sendData(self, identifier, message, **kwargs):
    args = {'uid': None,
            'to': None,
            'bounce': True}
    args.update(kwargs)

    if not args['uid']:
      uid = makeID(message)
      if self.debug:
        print 'Making uid for ' + message
    else:
      uid = args['uid']
    self.uidlist.append(uid)
    if args['bounce']:
      bounce = '1'
    else:
      bounce = '0'
    
    data = identifier + ':' + bounce + ':' + uid + ':' + message

    data = zlib.compress(data, 9)
    
    if args['to']:
      #try:
      self.socket.sendto(data, peerIDToTuple(args['to']))
      #except:
      #  self.dropPeer(args['to'])
      #  return False
      #return True
    else:
      for peer in self.peers:
        #try:
        self.socket.sendto(data, peerIDToTuple(peer))
        #except:
        #  self.dropPeer(peer)
        #  return False
      return True

  def receiveData(self):
    while 1:
      data = None
      try:
        data, address = self.socket.recvfrom(65536)
        data = zlib.decompress(data)
        peerid = address[0] + ':' + str(address[1])
        identifier, bounce, uid, message = data.split(':', 3)
      except:
        if self.debug:
          print 'Failed to establish a connection.'
        pass
      
      if data and uid not in self.uidlist:
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
              if self.debug:
                print 'Sent NICK to ' + self.getPeerNickname(peerid)
            elif self.debug:
              print 'Did not send NICK to ' + self.getPeerNickname(peerid)
              
            self.sendData('PEERS', self.makePeerList(), to=peerid, bounce=False)
            
            if self.debug:
              print self.getPeerNickname(peerid) + ' joined network'
        elif identifier == 'PEERS': # list of connected peers
          peers = pickle.loads(message)
          for peer in peers:
            self.addPeer(peer)
          if self.debug:
            'Got peerlist from ' + peerid
        elif identifier == 'DROP':
          self.dropPeer(peerid)
        elif identifier == 'PING':
          if peerid in self.pings:
            self.pings.update({peerid: time.time()})
          if self.debug:
            print 'Got PING from ' + peerid
        elif identifier == 'NICK':
          print '* ' + self.getPeerNickname(peerid) + ' is now known as ' + message
          self.setPeerNickname(peerid, message)
        elif self.debug:
          print 'Unhandled: ' + identifier + ' ' + message

        if bounce == '1':
          self.sendData(identifier, message, uid=uid)
      elif data and self.debug:
        print 'Not rerouting data: ' + data
        
  def getInput(self):
    while 1:
      try:
        data = raw_input('>')
        if data != '':
          if data.startswith('/'):
            if data == '/q' or data == '/quit' or data == '/exit':
              break
            elif data == '/clue':
              print 'Adding Scalar.ClueNet.org:44545 to peer list...'
              if not self.addPeer('67.18.89.26:44545'):
                print 'Unable to connect to ClueNet.'
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
        self.sendDropNotice()
        self.socket.close()
        sys.exit()

  def addPeer(self, peerid):
    result = False
    if not peerid in self.peers and peerid != self.peerid:
      self.peers.append(peerid)
      result = self.sendData('JOIN', self.getPeerNickname(self.peerid)) # send our nickname in the message of JOIN
      if self.debug:
        print 'Added peer: ' + self.getPeerNickname(peerid)
      if not result:
        self.dropPeer(peerid)
    return result

  def dropPeer(self, peerid):
    if peerid in self.peers and peerid != self.peerid:
      del self.peers[self.peers.index(peerid)]
      if self.debug:
        print self.getPeerNickname(peerid) + ' dropped from network'
        
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
    if self.debug:
      print 'Set nickname for ' + peerid + ' to ' + nickname

  def sendDropNotice(self):
    self.sendData('DROP', 'DROP')

  def pingAllPeers(self):
    for peerid in self.peers:
      if peerid in self.pings:
        if time.time() - self.pings[peerid] >= 20:
          self.dropPeer(peerid)
          if self.debug:
            print 'Dropping ' + self.getPeerNickname(peerid) + ' (no ping responses for 20 seconds)'
      else:
        self.pings.update({peerid: time.time()})
      self.sendData('PING', 'PING', to=peerid, bounce=False)
    time.sleep(15)
    thread.start_new_thread(self.pingAllPeers, ())

  def makePeerList(self):
    return pickle.dumps(self.peers)
    
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
