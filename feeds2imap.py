#!/usr/bin/env python

""" feeds2imap 0.1

feeds2imap downloads your favourite feeds to your IMAP account. Read them at
home or at work with your desktop mail program or from wherever you are with your
webmail application.

Read README for more information.

Authors: Mathis Hofer <mathis@fsfe.org>
         Simon Hofer <simon@fsfe.org>

Copyright (c) 2008-2009 Mathis & Simon Hofer.

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

import sys, os, time, string, optparse, urllib2, imaplib, feedparser, modutf7, email


class Feed:
    def __init__(self, url, mailbox):
        self.url = url
        self.mailbox = mailbox
        self.data = None
        
    def hasData(self):
        return self.data != None


class FeedReader:
    def __init__(self, feeds, verbose, imapServer, imapSSL, imapPort, imapUser, imapPwd, msgLimit):
        self.feeds = feeds
        self.verbose = verbose
        self.imapServer = imapServer
        self.imapSSL = imapSSL
        self.imapPort = imapPort
        self.imapUser = imapUser
        self.imapPwd = imapPwd
        self.msgLimit = msgLimit
    
    def start(self):
        if not self.imapSSL:
            self.imapConn = imaplib.IMAP4(self.imapServer, self.imapPort)
        else:
            self.imapConn = imaplib.IMAP4_SSL(self.imapServer, self.imapPort)
        self.imapConn.login(self.imapUser, self.imapPwd)
        
        for feed in self.feeds:
            self.__checkFeedMailbox(feed.mailbox)
            date = self.__getNewestMessageDate(feed.mailbox, feed.url)
            if verbose:
                print 'Fetching %s ...' % feed.url,
            newArticles = 0
            updatedArticles = 0
            sys.stdout.flush()
            try:
                f = urllib2.urlopen(feed.url)
                try:
                    feedData = feedparser.parse(f.read())
                    feed.data = feedData
                    for entry in feed.data.entries:
                        try:
                            if (not entry.has_key('updated_parsed') or entry.updated_parsed == None
                                or time.mktime(entry.updated_parsed) > time.mktime(date)):
                                mid = self.__getMessageId(feed.mailbox, entry.link)
                                if mid == None:
                                    # Create new entry
                                    self.__createMimeMessage(feed, entry)
                                    
                                    newArticles += 1
                                elif entry.has_key('updated_parsed') and entry.updated_parsed != None:
                                    # Entry has been updated, read date of old entry
                                    old_msg = self.__checkImapResult(self.imapConn.fetch(mid, '(RFC822)'))
                                    old_msg_parsed = email.message_from_string(old_msg[0][1])
                                    created_date = old_msg_parsed['DATE']
                                    last_updated_date = old_msg_parsed.has_key('X-FEED-LASTUPDATED') and old_msg_parsed['X-FEED-LASTUPDATED'] or None
                                    
                                    if (last_updated_date == None or
                                        entry.updated_parsed > time.strptime(last_updated_date+' UTC', "%a, %d %b %Y %H:%M:%S +0000 %Z")):
                                        # Delete old entry
                                        self.__checkImapResult(self.imapConn.select(feed.mailbox.encode('mod-utf-7')))
                                        self.__checkImapResult(self.imapConn.store(mid, '+FLAGS', '\\Deleted'))
                                        self.__checkImapResult(self.imapConn.select(feed.mailbox.encode('mod-utf-7'), True))
                                        
                                        # Create new entry with old date
                                        self.__createMimeMessage(feed, entry, created_date)
                                        
                                        updatedArticles += 1
                        except Exception, e:
                            if verbose:
                                print 'Error!'
                            print >> sys.stderr, 'Failed to store entry of feed %s to IMAP server:' % feed.url
                            print >> sys.stderr, e
                    try:
                        self.__cleanFeedMailbox(feed.mailbox)
                    except Exception, e:
                        if verbose:
                            print 'Error!'
                        print >> sys.stderr, 'Failed to clean up mailbox of feed %s:' % feed.url
                        print >> sys.stderr, e
                except Exception, e:
                    if verbose:
                        print 'Error!'
                    print >> sys.stderr, 'Parse error for feed %s:' % feed.url
                    print >> sys.stderr, e
                f.close()
            except Exception, e:
                if verbose:
                    print 'Error!'
                print >> sys.stderr, 'Failed to download feed %s:' % feed.url
                print >> sys.stderr, e
            else:
                if verbose:
                    if newArticles + updatedArticles > 0:
                        print "(%s new, %s updated articles)" % (newArticles, updatedArticles)
                    else:
                        print "(nothing new)"
        
        self.imapConn.logout()

    def __checkFeedMailbox(self, mailbox):
        (response, data) = self.imapConn.select(mailbox.encode('mod-utf-7'), True)
        if response == 'NO':
            self.__checkImapResult(self.imapConn.create(mailbox.encode('mod-utf-7')))
            self.__checkImapResult(self.imapConn.subscribe(mailbox.encode('mod-utf-7')))
            self.__checkImapResult(self.imapConn.select(mailbox.encode('mod-utf-7'), True))
        elif response != 'OK':
            raise Execption('Invalid response from IMAP server: %s' % str(data))

    def __cleanFeedMailbox(self, mailbox):
        # Delete oldest messages if mailbox contains more than the limit
        if self.msgLimit > 0:
            messages = self.__checkImapResult(self.imapConn.sort('DATE', 'ASCII', 'UNDELETED'))[0].split(' ')
            if len(messages) > self.msgLimit:
                self.__checkImapResult(self.imapConn.store(','.join(messages[:-self.msgLimit]),
                                       '+FLAGS', '\\Deleted'))
        
        self.__checkImapResult(self.imapConn.select(mailbox.encode('mod-utf-7')))
        self.__checkImapResult(self.imapConn.expunge())
        self.__checkImapResult(self.imapConn.select(mailbox.encode('mod-utf-7'), True))
    
    def __getNewestMessageDate(self, mailbox, feedurl):
        data = self.__checkImapResult(self.imapConn.sort(
            'REVERSE DATE', 'ASCII', '(HEADER "X-FEED-URL" "%s")' % feedurl))
        mids = string.split(data[0])
        if len(mids) > 0:
            data = self.__checkImapResult(self.imapConn.fetch(
                mids[0], '(BODY[HEADER.FIELDS (DATE)])'))
            return time.strptime(data[0][1].strip()+' GMT',
                                 "Date: %a, %d %b %Y %H:%M:%S +0000 %Z")
        else:
            return time.gmtime(0)                                                     
    
    def __getMessageId(self, mailbox, entryUrl):
        data = self.__checkImapResult(self.imapConn.search(
                'ASCII', '(HEADER "MESSAGE-ID" "<%s@localhost.localdomain>")' % entryUrl))
        if data[0] != '':
            return data[0].split(' ')[-1]
        else:
            return None
    
    def __createMimeMessage(self, feed, entry, created_date=None):
        entry_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                                   (entry.has_key('updated_parsed') and entry.updated_parsed
                                    or time.gmtime()))
        # Inspired by Mozilla Thunderbird's "News & Blog" messages format
        message = """Date: %(date)s
Message-Id: <%(link)s@localhost.localdomain>
From: %(author)s
MIME-Version: 1.0
Subject: %(title)s
Content-Transfer-Encoding: 8bit
Content-Base: %(link)s
Content-Type: text/html; charset=UTF-8
X-Mailer: feeds2imap
X-Feed-Url: %(feedurl)s
%(lastupdated)s


<html>
  <head>
    <title>%(title)s</title>
    <base href="%(link)s">
    <style type="text/css">
      
      #msgBody {
        margin: 0;
        border: none;
        padding: 0;
      }
      #msgSummary {
        display: no;
      }
      #msgIframe {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%%;
        height: 100%%;
        border: none;
      }

    </style>
  </head>
  <body id="msgBody" selected="false">
    <div id="msgSummary"><!-- just to make Thunderbird 3 happy --></div>
    <iframe id="msgIframe" selected="false" src="%(link)s">
  </body>
</html>
""" % {'date':created_date != None and created_date or entry_date,
       'link':entry.link,
       'author':(entry.has_key('author') and '%s <void@feeds2imap>' % entry.author
                 or '%s <void@feeds2imap>' % feed.data.feed.title),
       'title':entry.title,
       'summary':entry.has_key('summary') and entry.summary or '',
       'feedurl':feed.url,
       'lastupdated':created_date != None and "X-Feed-Lastupdated: %s" % entry_date or ''}
        
        # Save message to IMAP server
        self.__checkImapResult(self.imapConn.append(
                feed.mailbox.encode('mod-utf-7'),
                None, None, message.replace("\n", "\r\n").encode('utf-8')))
    
    def __checkImapResult(self, result, goodResponse=['OK']):
        if result[0] in goodResponse:
            return result[1]
        else:
            raise Exception('Invalid response from IMAP server: %s' % str(result[1]))
        
    
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
        messagesPerMailbox = int(xpath.Evaluate('/feeds2imap/imap/messagespermailbox/child::text()', doc)[0].nodeValue)
        
        feeds = []
        for node in xpath.Evaluate('/feeds2imap/feeds/feed', doc):
            url = unicode(xpath.Evaluate('url/child::text()', node)[0].nodeValue)
            mailbox = unicode(xpath.Evaluate('mailbox/child::text()', node)[0].nodeValue)
            feeds.append(Feed(url, mailbox))
    except Exception, e:
        print >> sys.stderr, 'Unable to parse the config file'
        sys.exit(1)
    
    reader = FeedReader(feeds, verbose,
                        server, useSSL, port,
                        username, password,
                        messagesPerMailbox)
    reader.start()
