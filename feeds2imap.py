#!/usr/bin/env python

""" feeds2imap 0.1

feeds2imap downloads your favourite feeds to your IMAP account. Read them at
home or at work with your desktop mail program or from wherever you are with your
webmail application.

Consider feeds2imap-sampleconfig.xml for the config file format.

To import your feeds from Thunderbird's "News & Blogs", export them as OPML
file and use the following command (or any other XSLT processor) to generate the
feeds2imap config file:
    xsltproc opml2config.xslt MyFeeds.opml > feeds2imap.xml

Authors: Mathis Hofer <mathis@fsfe.org>
         Simon Hofer <simon@fsfe.org>

Copyright (c) 2008 Mathis & Simon Hofer.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
 
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
 
You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

import xml.dom.minidom
from xml.dom.minidom import Node
from xml import xpath

import sys, os, time, string, optparse, urllib2, imaplib, feedparser, modutf7


class Feed:
    def __init__(self, url, mailbox):
        self.url = url
        self.mailbox = mailbox
        self.data = None
        
    def hasData(self):
        return self.data != None


class FeedReader:
    def __init__(self, feeds, verbose, imapServer, imapSSL, imapPort, imapUser, imapPwd):
        self.feeds = feeds
        self.verbose = verbose
        self.imapServer = imapServer
        self.imapSSL = imapSSL
        self.imapPort = imapPort
        self.imapUser = imapUser
        self.imapPwd = imapPwd
    
    def start(self):
        if not self.imapSSL:
            self.imapConn = imaplib.IMAP4(self.imapServer, self.imapPort)
        else:
            self.imapConn = imaplib.IMAP4_SSL(self.imapServer, self.imapPort)
        self.imapConn.login(self.imapUser, self.imapPwd)
        
        for feed in self.feeds:
            self.__checkFeedMailbox(feed.mailbox)
            date = self.__getNewestMessageDate(feed.mailbox)
            if verbose:
                print 'Fetching %s ...' % feed.url,
            newArticles = 0
            sys.stdout.flush()
            try:
                f = urllib2.urlopen(feed.url)
                try:
                    feedData = feedparser.parse(f.read())
                    feed.data = feedData
                    for entry in feed.data.entries:
                        try:
                            if (entry.has_key('updated_parsed') and entry.updated_parsed != None
                                and time.mktime(entry.updated_parsed) > time.mktime(date)
                                or not entry.has_key('updated_parsed')
                                and not self.__isEntryAvailable(feed.mailbox, entry.link)):
                                message = self.__createMimeMessage(feed, entry)
                                self.__checkImapResult(self.imapConn.append(
                                        feed.mailbox.encode('mod-utf-7'),
                                        None, None, message.encode('utf-8')))
                                newArticles += 1
                        except Exception, e:
                            if verbose:
                                print 'Error!'
                            print >> sys.stderr, 'Failed to store entry of feed %s to IMAP server:' % feed.url
                            print >> sys.stderr, e
                except Exception, e:
                    if verbose:
                        print 'Error!'
                    print >> sys.stderr, 'Parse error for feed %s:' % feed.url
                    print >> sys.stderr, e
                finally:
                    f.close()
            except Exception, e:
                if verbose:
                    print 'Error!'
                print >> sys.stderr, 'Failed to download feed %s:' % feed.url
                print >> sys.stderr, e
            else:
                if verbose:
                    if newArticles == 1:
                        print '(1 new article)'
                    elif newArticles > 1:
                        print '(%i new articles)' % newArticles
                    else:
                        print '(nothing new)'
        
        self.imapConn.logout()

    def __checkFeedMailbox(self, mailbox):
        (response, data) = self.imapConn.select(mailbox.encode('mod-utf-7'), True)
        if response == 'NO':
            self.__checkImapResult(self.imapConn.create(mailbox.encode('mod-utf-7')))
            self.__checkImapResult(self.imapConn.subscribe(mailbox.encode('mod-utf-7')))
        elif response != 'OK':
            raise Execption('Invalid response from IMAP server: %s' % str(data))
    
    def __getNewestMessageDate(self, mailbox):
        self.__checkImapResult(self.imapConn.select(mailbox.encode('mod-utf-7'), True))
        data = self.__checkImapResult(self.imapConn.sort('REVERSE DATE', 'ASCII', 'ALL'))
        mids = string.split(data[0])
        if len(mids) > 0:
            mid = mids[0]
            data = self.__checkImapResult(self.imapConn.fetch(
                    mid, '(BODY[HEADER.FIELDS (DATE)])'))
            date = time.strptime(data[0][1].strip()+' GMT',
                                 "Date: %a, %d %b %Y %H:%M:%S +0000 %Z")
            return date
        else:
            return time.gmtime(0)
    
    def __isEntryAvailable(self, mailbox, entryUrl):
        self.__checkImapResult(self.imapConn.select(mailbox.encode('mod-utf-7'), True))
        data = self.__checkImapResult(self.imapConn.search(
                'ASCII', '(HEADER Message-Id "<%s@localhost.localdomain>")' % entryUrl))
        return data[0] != ''
    
    def __createMimeMessage(self, feed, entry):
        # Taken from Mozilla Thunderbird's "News & Blog" messages
        message = """Date: %(date)s
Message-Id: <%(link)s@localhost.localdomain>
From: %(author)s
MIME-Version: 1.0
Subject: %(title)s
Content-Transfer-Encoding: 8bit
Content-Base: %(link)s
Content-Type: text/html; charset=UTF-8
X-Mailer: feeds2imap


<html>
  <head>
    <title>%(title)s</title>
    <base href="%(link)s">
    <style type="text/css">
      
      body {
        margin: 0;
        border: none;
        padding: 0;
      }
      iframe {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%%;
        height: 100%%;
        border: none;
      }

    </style>
  </head>
  <body>
    
    <iframe id ="_mailrssiframe" src="%(link)s">
      %(summary)s
    </iframe>

  </body>
</html>
""" % {'date':time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                            (entry.has_key('updated_parsed') and entry.updated_parsed
                             or time.gmtime())),
       'link':entry.link,
       'author':(entry.has_key('author') and '%s <void@feeds2imap>' % entry.author
                 or '%s <void@feeds2imap>' % feed.data.feed.title),
       'title':entry.title,
       'summary':entry.has_key('summary') and entry.summary or ''}
        return message.replace("\n", "\r\n")
    
    def __checkImapResult(self, result, goodResponse=['OK']):
        if result[0] in goodResponse:
            return result[1]
        else:
            raise Execption('Invalid response from IMAP server: %s' % str(data))
        
    
if __name__=="__main__":
    parser = optparse.OptionParser(usage="%prog [options] configfile", version="%prog 0.1")
    parser.add_option("-v", "--verbose", dest="verbose",
                          action="store_true", default=False,
                          help="enable output")
    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.print_help()
        sys.exit(1)
    
    verbose = options.verbose
    
    configfile = args[0]
    if not os.path.exists(configfile):
        print >> sys.stderr, 'The config file "%s" does not exist' % configfile
        sys.exit(1)
    
    try:
        doc = xml.dom.minidom.parse(configfile)
        
        server = unicode(xpath.Evaluate('/feeds2imap/imap/server/child::text()', doc)[0].nodeValue)
        port = int(xpath.Evaluate('/feeds2imap/imap/port/child::text()', doc)[0].nodeValue)
        useSSL = bool(xpath.Evaluate('/feeds2imap/imap/ssl/child::text()', doc)[0].nodeValue)
        username = unicode(xpath.Evaluate('/feeds2imap/imap/username/child::text()', doc)[0].nodeValue)
        password = unicode(xpath.Evaluate('/feeds2imap/imap/password/child::text()', doc)[0].nodeValue)
        
        feeds = []
        for node in xpath.Evaluate('/feeds2imap/feeds/feed', doc):
            url = unicode(xpath.Evaluate('url/child::text()', node)[0].nodeValue)
            mailbox = unicode(xpath.Evaluate('mailbox/child::text()', node)[0].nodeValue)
            feeds.append(Feed(url, mailbox))
    except Exception, e:
        print >> sys.stderr, 'Unable to parse the config file'
        sys.exit(1)
    
    reader = FeedReader(feeds, verbose, server, useSSL, port, username, password)
    reader.start()