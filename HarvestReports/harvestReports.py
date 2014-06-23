#!/usr/bin/python

# Harvest Reports v0.1.3
# Copyright (c) 2014 Iain McManus. All rights reserved.
#
# Harvest Reports is a wrapper around Apple's AutoIngestion Java Class.
# Harvest Reports can download all of the recent daily data and will produce
# a summary of the sales, updates and a breakdown of region where sales have occurred.
#
# Information is also generated per version, including a calculation of the number of users
# on the latest version.
#
# Harvest Reports can be run on a regular schedule and be configured to send an email
# with the daily summary when the daily report is out. If no sales/updates have occurred
# it can indicate that as well.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import csv
import datetime
import feedparser
import getopt
import gzip
import math
import os
import smtplib
import socket
import subprocess
import sys
import time

from unidecode import unidecode

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

from SalesReportFile import SalesReportFile
from SKUData import SKUData

from Common import FieldRemapper
from Common import RatingsSummaryFields
from Common import ReportTypes
from Common import RSSFields
                
def processDailiesIn(basePath, downloadedFiles, reportType, fieldRemapper):
    salesReportObjects = []
    
    # build the list of all of the files
    for filename in os.listdir(basePath):
        if filename.endswith('.txt'):
            # check if it's a new file
            isNewFile = False
            if downloadedFiles != None:
                for downloadedFile in downloadedFiles:
                    if filename in downloadedFile:
                        isNewFile = True
                        break
            
            parsedFile = SalesReportFile(os.path.join(basePath, filename), isNewFile, fieldRemapper)
                
            salesReportObjects.append(parsedFile)
            
    skuRelatedReportLines = dict()
    
    # identify all of the SKU names
    for salesReportObject in salesReportObjects:
        for reportEntry in salesReportObject.data:
            skuName = reportEntry["SKU"]
            
            skuRelatedReportLines.setdefault(skuName, []).append([salesReportObject.isNewFile, reportEntry])

    skuData = dict()
                    
    # build up the per sku data
    skuNames = skuRelatedReportLines.keys()
    for skuName in skuNames:
        skuSummary = SKUData(basePath, skuRelatedReportLines[skuName], fieldRemapper)
        
        skuData.update({skuName : skuSummary})
    
    # print out the new data if present
    for skuSummary in skuData.values():
        if skuSummary.hasNewData:
            skuSummary.printNewData()
    
    return skuData
    
def downloadDailies(propertiesFile, vendorId, numDaysBack, overwriteExistingData, basePath, verbose):
    downloadedFiles = []
    
    addedPlaceHolderFileForEventlessDay = False
    
    for dayOffset in range(0, numDaysBack):
        requestedDate = datetime.date.today() - datetime.timedelta(dayOffset)
        requestedDateString = "{year:04}{month:02}{day:02}".format(year=requestedDate.year, month=requestedDate.month, day=requestedDate.day)
        
        downloadedFileName = "S_D_{vendorId}_{dateString}.txt".format(vendorId=vendorId, dateString=requestedDateString)
        downloadedFilePath = os.path.join(basePath, downloadedFileName)
        
        if overwriteExistingData or not os.path.exists(downloadedFilePath):
            autoingestionOutput = subprocess.check_output(["java", "-cp", ".", "Autoingestion", propertiesFile, vendorId, "sales", "daily", "summary", requestedDateString])
            
            downloadedSuccessfully = False
            noReportsAvailable = False
            invalidDate = False
            
            if "File Downloaded Successfully" in autoingestionOutput:
                downloadedSuccessfully = True
            elif "There are no reports available to download for this selection." in autoingestionOutput:
                noReportsAvailable = True
                
                placeholderHandle = open(downloadedFilePath, 'wt')
                placeholderHandle.close()
                
                addedPlaceHolderFileForEventlessDay = True
            elif "Daily reports are available only for" in autoingestionOutput:
                invalidDate = True
                    
            if downloadedSuccessfully:
                if verbose:
                    print "Downloaded report for {day:02}/{month:02}/{year:04}".format(day=requestedDate.day, month=requestedDate.month, year=requestedDate.year)
                
                outputLines = autoingestionOutput.split("\n")
                for outputLine in outputLines:
                    if vendorId in outputLine:
                        fileName = outputLine.strip()
                        
                        if ".gz" in outputLine:
                            sourceFileHandle = gzip.GzipFile(fileName)
                            
                            destinationFileHandle = open(downloadedFilePath, 'wb')
                            destinationFileHandle.write(sourceFileHandle.read())
                            destinationFileHandle.close()
                            
                            sourceFileHandle.close()
                            
                            os.remove(fileName)
                        else:
                            shutil.move(fileName, downloadedFilePath)
                            
                        downloadedFiles.append(downloadedFilePath)
            else:
                if verbose:
                    print "Failed to download report for {day:02}/{month:02}/{year:04}".format(day=requestedDate.day, month=requestedDate.month, year=requestedDate.year)
                
                    if noReportsAvailable:
                        print "    No installs have occurred for that date"
                    elif invalidDate:
                        print "    No data exists for that date. Either the day is too far back (Apple only keeps a limited number of dailies) or the report for that day does not yet exist"
                    else:
                       print "    The download failed for an unknown reason"
        else:
            if verbose:
                print "Skipped existing data for {day:02}/{month:02}/{year:04}".format(day=requestedDate.day, month=requestedDate.month, year=requestedDate.year)
    
    return [addedPlaceHolderFileForEventlessDay, downloadedFiles]

def loadFeedFile(filePath):
    feedEntries = dict()
    
    if not os.path.exists(filePath):
        return feedEntries
    
    with open(filePath, mode="rb") as savedFeed:
        reader = csv.reader(savedFeed, delimiter='\t')
        for row in reader:
            entry = {RSSFields.Version:    row[RSSFields.Version], 
                     RSSFields.Title:      row[RSSFields.Title], 
                     RSSFields.Rating:     row[RSSFields.Rating],
                     RSSFields.Summary:    row[RSSFields.Summary],
                     RSSFields.UniqueId:   row[RSSFields.UniqueId]}
            feedEntries.update({row[RSSFields.UniqueId] : entry})
    
    return feedEntries
    
def writeFeedFile(filePath, feedEntries):
    feedFile = open(filePath, "wb")
    feedWriter = csv.writer(feedFile, delimiter="\t", quotechar="\"", quoting=csv.QUOTE_ALL)
    
    for entry in feedEntries.values():
        feedWriter.writerow([entry[RSSFields.Version], 
                             entry[RSSFields.Title],
                             entry[RSSFields.Rating],
                             entry[RSSFields.Summary],
                             entry[RSSFields.UniqueId]])
                             
    feedFile.close()

def identifyNewFeedEntries(previousFeedEntries, feedEntries):
    previousUniqueIds = previousFeedEntries.keys()
    currentUniqueIds = feedEntries.keys()
    
    return [feedEntries[uniqueId] for uniqueId in currentUniqueIds if uniqueId not in previousUniqueIds]
    
def analyseFeedEntries(feedEntries, newFeedEntries):
    entrySummary = dict()
    
    lifetimeAverageRating = 0
    perVersionAverageRatings = dict()
    perVersionRatingsCount = dict()
    
    # build up the average rating information for all time and per version
    for feedEntry in feedEntries.values():
        appVersion = feedEntry[RSSFields.Version]
        appRating = feedEntry[RSSFields.Rating]
        
        lifetimeAverageRating += appRating
        
        perVersionAverageRatings[appVersion] = perVersionAverageRatings.setdefault(appVersion, 0) + appRating
        perVersionRatingsCount[appVersion] = perVersionRatingsCount.setdefault(appVersion, 0) + 1
        
    # calculate the average rating if possible
    if len(feedEntries) > 0:
        lifetimeAverageRating = float(lifetimeAverageRating) / len(feedEntries)
        
    # calculate the per version averages
    for appVersion in perVersionAverageRatings.keys():
        perVersionAverageRatings[appVersion] = float(perVersionAverageRatings[appVersion]) / perVersionRatingsCount[appVersion]
        
    # add the basic summary info
    entrySummary.update({RatingsSummaryFields.LifetimeAverageRating     : lifetimeAverageRating})
    entrySummary.update({RatingsSummaryFields.LifetimeRatingSamples     : len(feedEntries)})
    entrySummary.update({RatingsSummaryFields.AverageRatingPerVersion   : perVersionAverageRatings})
    entrySummary.update({RatingsSummaryFields.NumberOfRatingsPerVersion : perVersionRatingsCount})
    entrySummary.update({RatingsSummaryFields.NumberOfNewRatings        : len(newFeedEntries)})
    
    return entrySummary
    
def generateRatingsAndReviewsSummaryForApp(ratingsAndReviewsForApp):
    cumulativeAverage = 0.0
    cumulativeAverageSamples = 0
    cumulativeNumberOfNewRatings = 0
    
    cumulativeVersionAverage = dict()
    cumulativeVersionAverageSamples = dict()
    
    # combine the per country data into a single set of statistics for the app as a whole
    for ratingsAndReviews in ratingsAndReviewsForApp.values():
        averageRating = ratingsAndReviews[RatingsSummaryFields.LifetimeAverageRating]
        averageRatingSamples = ratingsAndReviews[RatingsSummaryFields.LifetimeRatingSamples]
        numberOfNewRatings = ratingsAndReviews[RatingsSummaryFields.NumberOfNewRatings]
        
        # update the running totals
        cumulativeAverage += averageRating * averageRatingSamples
        cumulativeAverageSamples += averageRatingSamples
        cumulativeNumberOfNewRatings += numberOfNewRatings
        
        # extract the per version ratings
        perVersionAverageRatings = ratingsAndReviews[RatingsSummaryFields.AverageRatingPerVersion]
        perVersionAverageRatingSamples = ratingsAndReviews[RatingsSummaryFields.NumberOfRatingsPerVersion]
        for version in perVersionAverageRatings.keys():
            versionAverage = perVersionAverageRatings[version]
            versionAverageSamples = perVersionAverageRatingSamples[version]
            
            cumulativeVersionAverage[version] = cumulativeVersionAverage.setdefault(version, 0.0) + (versionAverage * versionAverageSamples)
            cumulativeVersionAverageSamples[version] = cumulativeVersionAverageSamples.setdefault(version, 0) + versionAverageSamples
            
    # calculate the lifetime averages
    if cumulativeAverageSamples > 0:
        cumulativeAverage /= cumulativeAverageSamples
    
    # calculate the per version averages
    for version in cumulativeVersionAverage.keys():
        if cumulativeVersionAverageSamples[version] > 0:
            cumulativeVersionAverage[version] /= cumulativeVersionAverageSamples[version]
            
    # add the calculated data
    ratingsAndReviewsForApp.update({RatingsSummaryFields.LifetimeAverageRating     : cumulativeAverage})
    ratingsAndReviewsForApp.update({RatingsSummaryFields.LifetimeRatingSamples     : cumulativeAverageSamples})
    ratingsAndReviewsForApp.update({RatingsSummaryFields.AverageRatingPerVersion   : cumulativeVersionAverage})
    ratingsAndReviewsForApp.update({RatingsSummaryFields.NumberOfRatingsPerVersion : cumulativeVersionAverageSamples})
    ratingsAndReviewsForApp.update({RatingsSummaryFields.NumberOfNewRatings        : cumulativeNumberOfNewRatings})

def downloadRSSFeed(basePath, appIds, countryCodes):
    ratingsAndReviewsFeed = dict()
    newRatingsAndReviews = False
    
    socket.setdefaulttimeout(120)
    
    # for each app Id and country generate the feed URL and attempt to download the data
    for appId in appIds:
        ratingsAndReviewsForApp = dict()
        
        for countryCode in countryCodes:
            feedURL = "https://itunes.apple.com/{countryCode}/rss/customerreviews/id={appId}/sortBy=mostRecent/xml".format(countryCode=countryCode, appId=appId)
            
            feed = feedparser.parse(feedURL)
            
            # build up the list of feed entries
            feedEntries = dict()
            for entry in feed.entries:
                if "im_version" in entry:
                    feedEntry = {RSSFields.Version:    unidecode(entry["im_version"]), 
                                 RSSFields.Title:      unidecode(entry["title"]), 
                                 RSSFields.Rating:     int(unidecode(entry["im_rating"])),
                                 RSSFields.Summary:    unidecode(entry["summary"]),
                                 RSSFields.UniqueId:   unidecode(entry["id"])}
                    feedEntries.update({unidecode(entry["id"]) : feedEntry})
                                  
            downloadedFeedSummary = os.path.join(basePath, "RatingsAndReviews_{appId}_{countryCode}.csv".format(appId=appId, countryCode=countryCode))
            
            # load the previous set of feed entries
            previousFeedEntries = loadFeedFile(downloadedFeedSummary)
            
            # identify new feed entries
            newFeedEntries = identifyNewFeedEntries(previousFeedEntries, feedEntries)
            
            if len(newFeedEntries) > 0:
                newRatingsAndReviews = True
            
            # save out the list of new entries. no need to merge as the feedEntries is the full set
            writeFeedFile(downloadedFeedSummary, feedEntries)
            
            # analyse the feed data
            feedAnalysis = analyseFeedEntries(feedEntries, newFeedEntries)
            
            # add in the per country data
            ratingsAndReviewsForApp.update({countryCode : feedAnalysis})
        
        # add in the per app data
        ratingsAndReviewsFeed.update({appId : ratingsAndReviewsForApp})
    
    # generate the summary data
    for ratingsAndReviewsForApp in ratingsAndReviewsFeed.values():
        generateRatingsAndReviewsSummaryForApp(ratingsAndReviewsForApp)
    
    return [newRatingsAndReviews, ratingsAndReviewsFeed]

def generateHTMLReport(basePath, perSKUData):
    report_HTML = """\
<html>
  <head></head>
  <body>
"""
    
    for skuSummary in perSKUData.values():
        report_HTML += skuSummary.getReport_HTML()
    
    report_HTML += """\
  </body>
</html>
"""
    
    reportFile = open(os.path.join(basePath, "Report.html"), 'wt')
    
    reportFile.write(report_HTML)
    
    reportFile.close()

def emailReportForNewData(downloadedFiles, perSKUData):
    summary_PlainText = ""
    summary_HTML = """\
<html>
  <head></head>
  <body>
"""

    attachments = dict()

    if len(downloadedFiles) == 0:
        summary_PlainText = "No installs or updates have occurred today"
        summary_HTML = "<p>No installs or updates have occurred today</p>"
    else:
        for skuSummary in perSKUData.values():
            if skuSummary.hasNewData:
                if len(summary_PlainText) > 0:
                    summary_PlainText += "\r\n"
                    
                summary_PlainText += skuSummary.getEmailSummary_PlainText()
                summary_HTML += skuSummary.getEmailSummary_HTML()
                
                if len(skuSummary.newAllInstallsByCountry) > 0:
                    attachments.update({skuSummary.SKU + "NewAllInstallsByCountry" : skuSummary.Graphs["NewAllInstallsByCountry"]})
                    summary_HTML += '<br><img src="cid:{SKU}NewAllInstallsByCountry"><br>'.format(SKU=skuSummary.SKU)
    
    for skuSummary in perSKUData.values():
        summary_HTML += skuSummary.getReport_HTML()
            
        summary_HTML += '<br><img src="cid:{SKU}AllInstallsAndUpdates"><br>'.format(SKU=skuSummary.SKU)
        attachments.update({skuSummary.SKU + "AllInstallsAndUpdates" : skuSummary.Graphs["AllInstallsAndUpdates"]})
        summary_HTML += '<br><img src="cid:{SKU}AllInstallsByCountry"><br>'.format(SKU=skuSummary.SKU)
        attachments.update({skuSummary.SKU + "AllInstallsByCountry" : skuSummary.Graphs["AllInstallsByCountry"]})
    
    summary_HTML += """\
  </body>
</html>
"""
    emailConfig = dict()
    
    with open('emailConfig.csv', mode='r') as configFile:
        reader = csv.reader(configFile)
        emailConfig = {rows[0]:rows[1] for rows in reader}
    
    emailMessage = MIMEMultipart("related")
    emailMessage["Subject"] = emailConfig["Subject"]
    emailMessage["From"] = emailConfig["From"]
    emailMessage["To"] = emailConfig["To"]
    
    msgContainer = MIMEMultipart("alternative")
    
    emailMessage.attach(msgContainer)
    
    msgContainer.attach(MIMEText(summary_PlainText, "plain"))
    msgContainer.attach(MIMEText(summary_HTML, "html"))
    
    # attach all of the images to the email
    for attachmentName in attachments:
        attachmentHandle = open(attachments[attachmentName], 'rb')
        attachmentImage = MIMEImage(attachmentHandle.read(), "png")
        attachmentHandle.close()
        
        attachmentImage.add_header("Content-ID", attachmentName)
        attachmentImage.add_header("Content-Disposition", "inline", filename=attachmentName+".png")
        emailMessage.attach(attachmentImage)
    
    try:
        s = smtplib.SMTP(emailConfig["Server"], int(emailConfig["Port"]), timeout=30)
        s.ehlo()
        if emailConfig["EnableTLS"] == "1":
            s.starttls()  
        s.login(emailConfig["Username"], emailConfig["Password"])  
        s.sendmail(emailMessage["From"], [emailMessage["To"]], emailMessage.as_string())
    except (smtplib.SMTPServerDisconnected):
        print "Connection unexpectedly closed: [Errno 54] Connection reset by peer"
        
        # we delete the downloaded files on failure to send email so that it will retry
        for downloadedFile in downloadedFiles:
            os.remove(downloadedFile)
        
        sys.exit(-1)
    else:
        s.quit()
    
def usage():
    print "Usage:"
    print "      harvestReports -p <Properties File> -v <Vendor Id> [-d <Days Back>] [-rd|-rv] [-e] [-s] [-f AppId1,AppId2] [-c CountryCode1,CountryCode2]"
    print ""
    print "          Properties File  Path to the .properties file with the username/password for iTunes Connect"
    print "          Vendor Id        Your vendor Id"
    print "          Days Back        Number of days worth of data back (from now) to retrieve"
    print "          -o               Overwrites any existing reports"
    print "          -rd              Shows detailed summary report"
    print "          -rv              Shows verbose output"
    print "          -e               Sends an email if there is new data"
    print "          -s               Saves HTML report"
    print "          -f               Downloads the ratings and reviews RSS feed for the specified app ids"
    print "          -c               List of country codes to download the rating and review data for"

def main(argv):
    print "Harvest Reports v0.1.3"
    print "Written by Iain McManus"
    print ""
    print "Copyright (c) 2014 Iain McManus. All rights reserved"
    print ""
    
    propertiesFile = ""
    vendorId = ""
    daysBack = 1
    overwriteExistingData = False
    verbose = False
    reportType = ReportTypes.BasicSummary
    sendEmail = False
    saveHTMLReport = False
    downloadRatingsAndReviewsFeed = False
    appIds = []
    countryCodes = []
    
    essentialArgumentsFoundCount = 0
    
    try:
        opts, args = getopt.getopt(argv, "hp:v:d:r:oesf:-c:", ["help", "properties=", "vendorId=", "daysBack=", "report=", "overwrite", "email", "saveHMTL", "feed:", "countries:"])
    except getopt.GetoptError, exc:
        print exc.msg
        
        usage()
        sys.exit(2)

    for opt, arg in opts:
        if opt in ("-h"):
            usage()
            sys.exit()
        elif opt in ("-p"):
            propertiesFile = arg
            essentialArgumentsFoundCount += 1
        elif opt in ("-v"):
            vendorId = arg
            essentialArgumentsFoundCount += 1
        elif opt in ("-d"):
            daysBack = int(arg)
        elif opt in ("-r"):
            if arg in ("d"):
                reportType = ReportTypes.DetailedSummary
            elif arg in ("v"):
                verbose = True
        elif opt in ("-o"):
            overwriteExistingData = True
        elif opt in ("-e"):
            sendEmail = True
        elif opt in ("-s"):
            saveHTMLReport = True
        elif opt in ("-f:"):
            downloadRatingsAndReviewsFeed = True
            appIds = arg.strip().split(',')
        elif opt in ("-c:"):
            countryCodes = arg.strip().split(',')
            
    if essentialArgumentsFoundCount < 2:
        usage()
        sys.exit(2)

    basePath = "{vendorId}".format(vendorId=vendorId)

    if not os.path.exists(basePath):
        os.makedirs(basePath)
    
    fieldRemapper = FieldRemapper()

    # download the report data
    [addedPlaceHolderFileForEventlessDay, downloadedFiles] = downloadDailies(propertiesFile, vendorId, daysBack, overwriteExistingData, basePath, verbose)
    
    # parse all the report data and build the per SKU analyses
    perSKUData = processDailiesIn(basePath, downloadedFiles, reportType, fieldRemapper)
    
    # summary email can only send if there was new data or a new placeholder was added
    hasDataForSummaryEmail = (addedPlaceHolderFileForEventlessDay or (len(downloadedFiles) > 0))
    
    # download the RSS feed if enabled and we downloaded new data for the day
    ratingsAndReviewsFeed = None
    if downloadRatingsAndReviewsFeed and hasDataForSummaryEmail:
        [newRatingsAndReviews, ratingsAndReviewsFeed] = downloadRSSFeed(basePath, appIds, countryCodes)
        
        # merge the ratings data in
        for skuData in perSKUData.values():
            # no ratings data present
            if skuData.AppId not in ratingsAndReviewsFeed:
                continue
            
            reviewDataForSKU = ratingsAndReviewsFeed[skuData.AppId]
        
            skuData.lifetimeAverageRating = reviewDataForSKU[RatingsSummaryFields.LifetimeAverageRating]
            skuData.lifetimeRatingSamples = reviewDataForSKU[RatingsSummaryFields.LifetimeRatingSamples]
            skuData.numberOfNewRatings = reviewDataForSKU[RatingsSummaryFields.NumberOfNewRatings]
        
            perVersionAverage = reviewDataForSKU[RatingsSummaryFields.AverageRatingPerVersion]
            perVersionAverageSamples = reviewDataForSKU[RatingsSummaryFields.NumberOfRatingsPerVersion]
        
            for version in perVersionAverage.keys():
                skuData.averageRatingPerVersion[version] = perVersionAverage[version]
                skuData.numberOfRatingsPerVersion[version] = perVersionAverageSamples[version]
    
    # print out the report
    for skuSummary in perSKUData.values():
        skuSummary.printSummary(reportType)
        
    if saveHTMLReport:
        generateHTMLReport(basePath, perSKUData)

    # sales report email will only send if we have a new report downloaded (or a placeholder added due to an eventless day)
    if hasDataForSummaryEmail and sendEmail:
        emailReportForNewData(downloadedFiles, perSKUData)

if __name__ == '__main__':
    main(sys.argv[1:])
