#!/usr/bin/env python

""" feeds2imap 0.2

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

import sys
import os
import time
import string
import optparse

import urllib2
import imaplib
import feedparser
import modutf7
import email

import xml.dom.minidom
from xml.dom.minidom import Node
from xml import xpath


class Feed:
    def __init__(self, url, mailbox):
        self.url = url
        self.mailbox = mailbox
        self.data = None
        
    def has_data(self):
        return self.data is not None


class FeedReader:
    def __init__(self, feeds, verbose, imap_server, imap_ssl, imap_port, imap_user, imap_pwd, msg_limit):
        self.feeds = feeds
        self.verbose = verbose
        self.imap_server = imap_server
        self.imap_ssl = imap_ssl
        self.imap_port = imap_port
        self.imap_user = imap_user
        self.imap_pwd = imap_pwd
        self.msg_limit = msg_limit
    
    def start(self):
        if not self.imap_ssl:
            self.imap_conn = imaplib.IMAP4(self.imap_server, self.imap_port)
        else:
            self.imap_conn = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        self.imap_conn.login(self.imap_user, self.imap_pwd)
        
        for feed in self.feeds:
            self.__check_feed_mailbox(feed.mailbox)
            date = self.__get_newest_message_date(feed.mailbox, feed.url)
            if verbose:
                print 'Fetching %s ...' % feed.url,
            new_articles = 0
            updated_articles = 0
            sys.stdout.flush()
            try:
                f = urllib2.urlopen(feed.url)
                try:
                    feed.data = feedparser.parse(f.read())
                    for entry in feed.data.entries:
                        try:
                            if not entry.has_key('updated_parsed') or entry.updated_parsed is None \
                              or time.mktime(entry.updated_parsed) > time.mktime(date):
                                mid = self.__get_message_id(feed.mailbox, entry.link)
                                if mid is None:
                                    # Create new entry
                                    self.__create_mime_message(feed, entry)
                                    
                                    new_articles += 1
                                elif entry.has_key('updated_parsed') and entry.updated_parsed is not None:
                                    # Entry has been updated, read date of old entry
                                    old_msg = self.__check_imap_result(self.imap_conn.fetch(mid, '(RFC822)'))
                                    old_msg_parsed = email.message_from_string(old_msg[0][1])
                                    created_date = old_msg_parsed['DATE']
                                    last_updated_date = old_msg_parsed.has_key('X-FEED-LASTUPDATED') and old_msg_parsed['X-FEED-LASTUPDATED'] or None
                                    
                                    if last_updated_date is None or \
                                      entry.updated_parsed > time.strptime(last_updated_date+' UTC', "%a, %d %b %Y %H:%M:%S +0000 %Z"):
                                        # Delete old entry
                                        self.__check_imap_result(self.imap_conn.select(feed.mailbox.encode('mod-utf-7')))
                                        self.__check_imap_result(self.imap_conn.store(mid, '+FLAGS', '\\Deleted'))
                                        self.__check_imap_result(self.imap_conn.select(feed.mailbox.encode('mod-utf-7'), True))
                                        
                                        # Create new entry with old date
                                        self.__create_mime_message(feed, entry, created_date)
                                        
                                        updated_articles += 1
                        except Exception, e:
                            if verbose:
                                print 'Error!'
                            print >> sys.stderr, 'Failed to store entry of feed %s to IMAP server:' % feed.url
                            print >> sys.stderr, e
                    try:
                        self.__clean_feed_mailbox(feed.mailbox)
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
                    if new_articles + updated_articles > 0:
                        print "(%s new, %s updated articles)" % (new_articles, updated_articles)
                    else:
                        print "(nothing new)"
        
        self.imap_conn.logout()

    def __check_feed_mailbox(self, mailbox):
        (response, data) = self.imap_conn.select(mailbox.encode('mod-utf-7'), True)
        if response == 'NO':
            self.__check_imap_result(self.imap_conn.create(mailbox.encode('mod-utf-7')))
            self.__check_imap_result(self.imap_conn.subscribe(mailbox.encode('mod-utf-7')))
            self.__check_imap_result(self.imap_conn.select(mailbox.encode('mod-utf-7'), True))
        elif response != 'OK':
            raise Execption('Invalid response from IMAP server: %s' % str(data))

    def __clean_feed_mailbox(self, mailbox):
        # Delete oldest messages if mailbox contains more than the limit
        self.__check_imap_result(self.imap_conn.select(mailbox.encode('mod-utf-7')))
        if self.msg_limit > 0:
            messages = self.__check_imap_result(self.imap_conn.sort('DATE', 'ASCII', 'UNDELETED'))[0].split(' ')
            if len(messages) > self.msg_limit:
                self.__check_imap_result(self.imap_conn.store(','.join(messages[:-self.msg_limit]),
                                       '+FLAGS', '\\Deleted'))
        self.__check_imap_result(self.imap_conn.expunge())
        self.__check_imap_result(self.imap_conn.select(mailbox.encode('mod-utf-7'), True))
    
    def __get_newest_message_date(self, mailbox, feedurl):
        data = self.__check_imap_result(self.imap_conn.sort(
            'REVERSE DATE', 'ASCII', '(HEADER "X-FEED-URL" "%s")' % feedurl))
        mids = string.split(data[0])
        if mids:
            data = self.__check_imap_result(self.imap_conn.fetch(
                mids[0], '(BODY[HEADER.FIELDS (DATE)])'))
            return time.strptime(data[0][1].strip()+' GMT',
                                 "Date: %a, %d %b %Y %H:%M:%S +0000 %Z")
        else:
            return time.gmtime(0)                                                     
    
    def __get_message_id(self, mailbox, entryUrl):
        data = self.__check_imap_result(self.imap_conn.search(
                'ASCII', '(HEADER "MESSAGE-ID" "<%s@localhost.localdomain>")' % entryUrl))
        if data[0] != '':
            return data[0].split(' ')[-1]
        else:
            return None
    
    def __create_mime_message(self, feed, entry, created_date=None):
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
    <iframe id="_mailrssiframe" src="%(link)s"></iframe>
  </body>
</html>
""" % {'date':created_date is not None and created_date or entry_date,
       'link':entry.link,
       'author':(entry.has_key('author') and '%s <void@feeds2imap>' % entry.author
                 or '%s <void@feeds2imap>' % feed.data.feed.title),
       'title':entry.title,
       'summary':entry.has_key('summary') and entry.summary or '',
       'feedurl':feed.url,
       'lastupdated':created_date is not None and "X-Feed-Lastupdated: %s" % entry_date or ''}
        
        # Save message to IMAP server
        self.__check_imap_result(self.imap_conn.append(
                feed.mailbox.encode('mod-utf-7'),
                None, None, message.replace("\n", "\r\n").encode('utf-8')))
    
    def __check_imap_result(self, result, good_response=['OK']):
        if result[0] in good_response:
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

    if os.system('xmllint --noout --valid %s' % configfile):
        print >> sys.stderr, 'The config file "%s" is not valid' % configfile
        sys.exit(1)
    
    try:
        doc = xml.dom.minidom.parse(configfile)
        
        server = unicode(xpath.Evaluate('/feeds2imap/imap/server/child::text()', doc)[0].nodeValue)
        port = int(xpath.Evaluate('/feeds2imap/imap/port/child::text()', doc)[0].nodeValue)
        ssl = bool(xpath.Evaluate('/feeds2imap/imap/ssl', doc))
        username = unicode(xpath.Evaluate('/feeds2imap/imap/username/child::text()', doc)[0].nodeValue)
        password = unicode(xpath.Evaluate('/feeds2imap/imap/password/child::text()', doc)[0].nodeValue)
        messages_per_mailbox = int(xpath.Evaluate('/feeds2imap/imap/messagespermailbox/child::text()', doc)[0].nodeValue)
        
        feeds = []
        for node in xpath.Evaluate('/feeds2imap/feeds/feed', doc):
            url = unicode(xpath.Evaluate('url/child::text()', node)[0].nodeValue)
            mailbox = unicode(xpath.Evaluate('mailbox/child::text()', node)[0].nodeValue)
            feeds.append(Feed(url, mailbox))
    except Exception, e:
        print >> sys.stderr, 'Unable to parse the config file'
        sys.exit(1)
    
    reader = FeedReader(feeds, verbose,
                        server, ssl, port,
                        username, password,
                        messages_per_mailbox)
    reader.start()
