<?xml version="1.0" encoding="utf-8" ?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:str="http://exslt.org/strings"
                exclude-result-prefixes="str">

  <xsl:output method="xml" version="1.0"
              doctype-system="config.dtd"
              encoding="utf-8" indent="yes" />
  <xsl:strip-space elements="*" />

  <xsl:template match="/opml">
    <feeds2imap>
      <imap>
        <server>mail.example.com</server>
        <port>993</port>
        <ssl />
        <username>user</username>
        <password>123456</password>
        <messagespermailbox>400</messagespermailbox>
      </imap>

      <feeds>
        <xsl:apply-templates select="body"/>
      </feeds>
    </feeds2imap>
  </xsl:template>

  <xsl:template match="outline">
    <xsl:choose>
      <xsl:when test="@title">
        <feed>
          <url><xsl:value-of select="@xmlUrl" /></url>
          <mailbox>
            <xsl:for-each select="ancestor-or-self::*[name()='outline']/@text">
              <xsl:value-of select="str:replace(., '.', ' ')" />
              <xsl:if test="position()!=last()">
                <xsl:text>.</xsl:text>
              </xsl:if>
            </xsl:for-each>
          </mailbox>
        </feed>
      </xsl:when>
    </xsl:choose>
    <xsl:apply-templates />
  </xsl:template>

</xsl:stylesheet>
