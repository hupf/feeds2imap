#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of the Infotrope Python Library.
#
# The Infotrope Python Library is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# The Infotrope Python Library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with the Infotrope Python Library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#!/usr/bin/python
import codecs

def decode_mod_utf_7( foo ):
    in_shift = False
    shift_buffer = '+'
    out_buffer = u''

    for c in foo:
        if in_shift:
            if c=='-':
                in_shift = False
                if len(shift_buffer)==0:
                    out_buffer += '&'
                else:
                    shift_buffer += '-'
                    try:
                        out_buffer = out_buffer + shift_buffer.decode( 'utf-7' )
                    except UnicodeDecodeError, e:
                        print e
                        print `e`
                        raise
                    shift_buffer = '+'
            elif c==',':
                shift_buffer += '/'
            else:
                shift_buffer += c
        else:
            if c=='&':
                in_shift = True
            else:
                out_buffer = out_buffer + c
    if in_shift:
        raise UnicodeDecodeError( 'Still in shift at end of string.' )
    return out_buffer

def encode_mod_utf_7( foo, errors = 'strict' ):
    ret = ''
    unibuf = u''
    for c in foo:
        if ord(c)<=0x7f:
            if len(unibuf):
                ret += '&' + unibuf.encode('utf-7').replace( '/', ',' )[1:]
                unibuf = u''
            ret += c.encode('us-ascii')
        else:
            unibuf += c
    if len(unibuf):
        ret += '&' + unibuf.encode('utf-7').replace( '/', ',' )[1:]
    return ret

def decode_mbox_name( foo, errors = 'strict' ):
    try:
        foo8 = foo.decode('us-ascii')
        if len([c for c in foo if c=='&'])==len([c for c in foo if c=='-']):
            return decode_mod_utf_7( foo )
        return foo8
    except UnicodeDecodeError:
        for ch in ['utf-8','iso8859-1']:
            try:
                return foo.decode( ch )
            except UnicodeDecodeError:
                pass
    return foo.decode('us-ascii')

def encoder( foo, errors='strict' ):
    return encode_mod_utf_7( foo ), len(foo)
def decoder( foo, errors='strict' ):
    return decode_mbox_name( foo ), len(foo)

class Codec(codecs.Codec):
    encode = encoder
    decode = decoder

class StreamReader(Codec,codecs.StreamReader):
    pass
class StreamWriter(Codec,codecs.StreamWriter):
    pass

def search_function( encoding ):
    if encoding not in ['modutf7','mod-utf-7','modutf-7','imap-mod-utf-7']:
        return None
    return ( encoder, decoder, StreamReader, StreamWriter )
codecs.register( search_function )

if __name__=='__main__':
    print `decode_mbox_name( '~peter/mail/&U,BTFw-/&ZeVnLIqe-' )`
    print `decode_mbox_name( '&Jjo-!' )`
    print `decode_mbox_name( '&U,BTF2XlZyyKng-' )`

    print ''

    print `'~peter/mail/&U,BTFw-/&ZeVnLIqe-'.decode('modutf7').encode('modutf7')`
    print `'&U,BTF2XIZyyKng-'.decode('modutf7')`
            
    
