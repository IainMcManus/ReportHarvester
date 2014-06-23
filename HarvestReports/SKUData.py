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

import datetime
import math
import os

import numpy as np
import matplotlib.pyplot as plt

from Common import ReportTypes
                
class SKUData:
    def __init__(self, basePath, reportLines, fieldRemapper):
        self.rawData = reportLines
        
        self.SKU = "Unknown"
        self.Name = "Unknown"
        self.AppId = "Unknown"
        
        self.unitsByVersion = dict()
        self.allInstallsTotal = 0
        self.paidInstallsTotal = 0
        self.freeInstallsTotal = 0
        self.proceedsByVersion = dict()
        self.proceedsTotal = 0
        self.updatesByVersion = dict()
        self.promoCodesByVersion = dict()
        self.promoCodesTotal = 0
        self.versions = []
        self.paidInstallsByDate = dict()
        self.freeInstallsByDate = dict()
        self.allInstallsByDate = dict()
        self.updatesByDate = dict()
        self.proceedsByDate = dict()
        self.paidInstallsByCountry = dict()
        self.freeInstallsByCountry = dict()
        self.allInstallsByCountry = dict()

        self.newPaidInstallsTotal = 0
        self.newFreeInstallsTotal = 0
        self.newAllInstallsTotal = 0
        self.newProceedsTotal = 0
        self.newUpdatesTotal = 0
        self.newPromoCodesTotal = 0
        self.hasNewData = False
        self.newPaidInstallsByCountry = dict()
        self.newFreeInstallsByCountry = dict()
        self.newAllInstallsByCountry = dict()
        self.newDataDates = []

        # these will be populated later        
        self.lifetimeAverageRating = 0
        self.lifetimeRatingSamples = 0
        self.numberOfNewRatings = 0
        self.averageRatingPerVersion = dict()
        self.numberOfRatingsPerVersion = dict()
        
        self.rawData.sort(key = lambda x: x[1]["Begin Date"])
        
        self.Graphs = dict()
        
        # process each report line in order of date and compile the summary
        for [isNewData, reportLine] in self.rawData:
            if self.SKU == "Unknown" and len(reportLine["SKU"].strip()) > 0:
                self.SKU = reportLine["SKU"].strip()
            if self.Name == "Unknown" and len(reportLine["Title"].strip()) > 0:
                self.Name = reportLine["Title"].strip()
            if self.AppId == "Unknown" and len(reportLine["Apple Identifier"].strip()) > 0:
                self.AppId = reportLine["Apple Identifier"].strip()
            
            startDate = reportLine["Begin Date"]
            
            version = reportLine["Version"]
            units = reportLine["Units"]
            proceedsPerItem = reportLine["Developer Proceeds (per item)"]
            country = reportLine["Country Code"]
            proceeds = units * proceedsPerItem
            
            self.proceedsTotal += proceeds
            
            # check if new data is present and setup some basic details
            if isNewData:
                self.newProceedsTotal += proceeds
                self.hasNewData = True
                self.newDataDates.append(startDate)
            
            # record all versions
            if not version in self.versions:
                self.versions.append(version)
            
            # ensure the date is recorded for all arrays
            if not startDate in self.updatesByDate:
                self.updatesByDate.update({startDate : 0})
            if not startDate in self.allInstallsByDate:
                self.allInstallsByDate.update({startDate : 0})
            if not startDate in self.paidInstallsByDate:
                self.paidInstallsByDate.update({startDate : 0})
            if not startDate in self.freeInstallsByDate:
                self.freeInstallsByDate.update({startDate : 0})
            if not startDate in self.proceedsByDate:
                self.proceedsByDate.update({startDate : 0})
            
            # the report line is for updates
            if "Update" in reportLine["Product Type Identifier"]:
                self.updatesByVersion[version] = self.updatesByVersion.setdefault(version, 0) + units
                self.updatesByDate[startDate] = self.updatesByDate.setdefault(startDate, 0) + units
            
                if isNewData:
                    self.newUpdatesTotal += units
            else: # the report line is for sales
                self.allInstallsTotal += units
                
                self.unitsByVersion[version] = self.unitsByVersion.setdefault(version, 0) + units
                self.allInstallsByDate[startDate] = self.allInstallsByDate.setdefault(startDate, 0) + units
                self.allInstallsByCountry[country] = self.allInstallsByCountry.setdefault(country, 0) + units
                self.proceedsByDate[startDate] = self.proceedsByDate.setdefault(startDate, 0) + proceeds
                self.proceedsByVersion[version] = self.proceedsByVersion.setdefault(version, 0) + proceeds
            
                if isNewData:
                    self.newAllInstallsTotal += units
                
                    self.newAllInstallsByCountry[country] = self.newAllInstallsByCountry.setdefault(country, 0) + units
                
                # record the count of promo codes used
                if reportLine["Promo Code"] != None and len(reportLine["Promo Code"]) > 0:
                    self.promoCodesTotal += units
                    
                    self.promoCodesByVersion[version] = self.promoCodesByVersion.setdefault(version, 0) + units
                        
                    if isNewData:
                        self.newPromoCodesTotal += units
                
                # was this a sale?
                if proceeds > 0:
                    self.paidInstallsTotal += units
                    
                    self.paidInstallsByDate[startDate] = self.paidInstallsByDate.setdefault(startDate, 0) + units
                    self.paidInstallsByCountry[country] = self.paidInstallsByCountry.setdefault(country, 0) + units
            
                    if isNewData:
                        self.newPaidInstallsTotal += units
                
                        self.newPaidInstallsByCountry[country] = self.newPaidInstallsByCountry.setdefault(country, 0) + units
                else: # otherwise it was a free installs
                    self.freeInstallsTotal += units
                    
                    self.freeInstallsByDate[startDate] = self.freeInstallsByDate.setdefault(startDate, 0) + units
                    self.freeInstallsByCountry[country] = self.freeInstallsByCountry.setdefault(country, 0) + units
            
                    if isNewData:
                        self.newFreeInstallsTotal += units
                
                        self.newFreeInstallsByCountry[country] = self.newFreeInstallsByCountry.setdefault(country, 0) + units
                
        self.versions.sort()
        
        # fill in any missing version data
        numPreviousVersion = 0
        self.userRetentionByVersion = dict()
        for version in self.versions:
            if not version in self.unitsByVersion:
                self.unitsByVersion.update({version : 0})
            if not version in self.updatesByVersion:
                self.updatesByVersion.update({version : 0})
            if not version in self.proceedsByVersion:
                self.proceedsByVersion.update({version : 0.0})
            if not version in self.promoCodesByVersion:
                self.promoCodesByVersion.update({version : 0})
            
            if not version in self.averageRatingPerVersion:
                self.averageRatingPerVersion.update({version : 0.0})
            if not version in self.numberOfRatingsPerVersion:
                self.numberOfRatingsPerVersion.update({version : 0})
                
            if numPreviousVersion > 0:
                proportionRetained = float(self.updatesByVersion[version]) / float(numPreviousVersion)
                self.userRetentionByVersion.update({version : proportionRetained})
                
            numPreviousVersion += self.unitsByVersion[version]
        
        # calculate the number on old versions
        self.numOnOldVersions = self.allInstallsTotal
        self.numOnOldVersions -= self.updatesByVersion[self.versions[len(self.versions) - 1]]
        self.numOnOldVersions -= self.unitsByVersion[self.versions[len(self.versions) - 1]]
        self.legacyUserPercentage = 100.0 * self.numOnOldVersions / self.allInstallsTotal
        
        self.generateGraphs(basePath)
    
    def printNewData(self):
        startDateString = self.newDataDates[0].strftime("%d %b %Y")
        endDateString = self.newDataDates[-1].strftime("%d %b %Y")
        if startDateString != endDateString:
            print "New Data Available for {name}".format(name=self.Name)
            print "From {startDate} to {endDate}".format(startDate=startDateString, endDate=endDateString)
        else:
            print "New Data Available for {name} for {startDate}".format(name=self.Name, startDate=startDateString)
        
        if self.newFreeInstallsTotal > 0:
            print "    Free Installs       : {units:6}".format(units=self.newFreeInstallsTotal)
        if self.newPaidInstallsTotal > 0:
            print "    Sales               : {units:6}".format(units=self.newPaidInstallsTotal)
        if self.newAllInstallsTotal > 0:
            print "    Total Installs      : {units:6}".format(units=self.newAllInstallsTotal)
        if self.numberOfNewRatings > 0:
            print "    New Ratings         : {newRatings:6}".format(newRatings=self.numberOfNewRatings)
            
        if self.promoCodesTotal > 0:
            print "    Promo Codes Used    : {promoCodes:6}".format(promoCodes=self.newPromoCodesTotal)
        print "    Proceeds            : {proceeds:6.02f}".format(proceeds=self.newProceedsTotal)
        print "    Updates             : {updates:6}".format(updates=self.newUpdatesTotal)
        
    def getReport_HTML(self):
        report = "<p><h1>Sales Report for {name}</h1></p>".format(name=self.Name)
        if self.freeInstallsTotal > 0:
            report += "<p><b>Free Installs</b>       : {units:6}</p>".format(units=self.freeInstallsTotal)
        if self.paidInstallsTotal > 0:
            report += "<p><b>Sales</b>               : {units:6}</p>".format(units=self.paidInstallsTotal)
        if self.allInstallsTotal > 0:
            report += "<p><b>Total Installs</b>      : {units:6}</p>".format(units=self.allInstallsTotal)
        
        if self.promoCodesTotal > 0:
            report += "<p><b>Promo Codes Used</b>    : {promoCodes:6}</p>".format(promoCodes=self.promoCodesTotal)
        if self.lifetimeRatingSamples > 0:
            report += "<b>Lifetime Avg Rating</b>       : {avgRating:6.01f}".format(avgRating=self.lifetimeAverageRating)
            report += "<br>"
            report += "<b>Number of Ratings</b>         : {ratingCount:6}".format(ratingCount=self.lifetimeRatingSamples)
            report += "<br>"
            
        report += "<p><b>Proceeds</b>            : {proceeds:6.02f}</p>".format(proceeds=self.proceedsTotal)
        report += "<p><b>Users Not on Latest</b> : {legacyUsers:3.01f}%</p>".format(legacyUsers=self.legacyUserPercentage)

        report += "<p><h2>Version Breakdown</h2></p>"
        report += "<ul>"
        
        for version in reversed(self.versions):
            report += "<li><b>{version}</b>".format(version=version)
            report += "<ul>"
            
            report += "<li>{installed:6} installs</li>".format(installed=self.unitsByVersion[version])
            report += "<li>{updates:6} installs updated to this version</li>".format(updates=self.updatesByVersion[version])
            if self.promoCodesByVersion[version] > 0:
                report += "<li>{promoCodes:6} promo codes used for this version</li>".format(promoCodes=self.promoCodesByVersion[version])
            report += "<li>{proceeds:6.02f} earned from this version</li>".format(proceeds=self.proceedsByVersion[version])
            
            if version in self.userRetentionByVersion:
                report += "<li>{retainedPct:3.1f}% of users upgraded to this version</li>".format(retainedPct=self.userRetentionByVersion[version]*100.0)
            if self.numberOfRatingsPerVersion[version] > 0:
                report += "<li>{avgRating:4.01f} average rating for this version</li>".format(avgRating=self.averageRatingPerVersion[version])
                report += "<li>{ratingCount:6} ratings for this version</li>".format(ratingCount=self.numberOfRatingsPerVersion[version])
                
            report += "</ul>"
        report += "</ul>"
        
        return report
    
    def getEmailSummary_HTML(self):
        summary = ""
        
        startDateString = self.newDataDates[0].strftime("%d %b %Y")
        endDateString = self.newDataDates[-1].strftime("%d %b %Y")
        if startDateString != endDateString:
            summary += "<p><h1>New Data Available for {name}</h1></p>".format(name=self.Name)
            summary += "<p><h2>Data is from {startDate} to {endDate}</h2></p>".format(startDate=startDateString, endDate=endDateString)
        else:
            summary += "<p><h1>New Data Available for {name} for {startDate}</h1></p>".format(name=self.Name, startDate=startDateString)
        
        summary += "<br>"
        if self.newFreeInstallsTotal > 0:
            summary += "<b>Free Installs</b>             : {units:6}".format(units=self.newFreeInstallsTotal)
            summary += "<br>"
        if self.newPaidInstallsTotal > 0:
            summary += "<b>Sales</b>                     : {units:6}".format(units=self.newPaidInstallsTotal)
            summary += "<br>"
        if self.newAllInstallsTotal > 0:
            summary += "<b>Total Installs</b>            : {units:6}".format(units=self.newAllInstallsTotal)
            summary += "<br>"
        if self.numberOfNewRatings > 0:
            summary += "<b>Number of New Ratings</b>         : {ratingCount:6}".format(ratingCount=self.numberOfNewRatings)
            summary += "<br>"
        if self.promoCodesTotal > 0:
            summary += "<b>Promo Codes Used</b>          : {promoCodes:6}".format(promoCodes=self.newPromoCodesTotal)
            summary += "<br>"
        summary += "<b>Proceeds</b>            : {proceeds:6.02f}".format(proceeds=self.newProceedsTotal)
        summary += "<br>"
        summary += "<b>Updates</b>             : {updates:6}".format(updates=self.newUpdatesTotal)
        summary += "<br>"
        
        return summary
    
    def getEmailSummary_PlainText(self):
        summary = ""
        
        summary += "New Data Available for {name}".format(name=self.Name)
        summary += "\r\n"
        if self.newPaidInstallsTotal > 0:
            summary += "    Free Installs       : {units:6}".format(units=self.newFreeInstallsTotal)
        if self.newFreeInstallsTotal > 0:
            summary += "    Sales               : {units:6}".format(units=self.newPaidInstallsTotal)
        if self.newAllInstallsTotal > 0:
            summary += "    Total Installs      : {units:6}".format(units=self.newAllInstallsTotal)
        if self.promoCodesTotal > 0:
            summary += "    Promo Codes Used    : {promoCodes:6}".format(promoCodes=self.newPromoCodesTotal)
        if self.numberOfNewRatings > 0:
            summary += "    New Ratings         : {newRatings:6}".format(newRatings=self.numberOfNewRatings)
        summary += "\r\n"
        summary += "    Proceeds            : {proceeds:6.02f}".format(proceeds=self.newProceedsTotal)
        summary += "\r\n"
        summary += "    Updates             : {updates:6}".format(updates=self.newUpdatesTotal)
        summary += "\r\n"
        
        return summary
        
    def printSummary(self, reportType):
        print "Summary for {name}".format(name=self.Name)
        if self.freeInstallsTotal > 0:
            print "    Free Installs       : {units:6}".format(units=self.freeInstallsTotal)
        if self.paidInstallsTotal > 0:
            print "    Sales               : {units:6}".format(units=self.paidInstallsTotal)
        if self.allInstallsTotal > 0:
            print "    Total Installs      : {units:6}".format(units=self.allInstallsTotal)
        if self.promoCodesTotal > 0:
            print "    Promo Codes Used    : {promoCodes:6}".format(promoCodes=self.promoCodesTotal)
        if self.lifetimeRatingSamples > 0:
            print "    Lifetime Avg Rating : {avgRating:6.01f}".format(avgRating=self.lifetimeAverageRating)
            print "    Number of Ratings   : {ratingCount:6}".format(ratingCount=self.lifetimeRatingSamples)
        print "    Proceeds            : {proceeds:6.02f}".format(proceeds=self.proceedsTotal)
        print "    Users Not on Latest : {legacyUsers:3.01f}%".format(legacyUsers=self.legacyUserPercentage)
        
        if reportType == ReportTypes.DetailedSummary:
            print "    Version Breakdown"
            
            for version in reversed(self.versions):
                print "      {version}".format(version=version)
            
                print "        Installs         : {installed:6} units".format(installed=self.unitsByVersion[version])
                print "        Updates          : {updates:6} units".format(updates=self.updatesByVersion[version])
                if self.promoCodesByVersion[version] > 0:
                    print "        Promo Codes Used : {promoCodes:6}".format(promoCodes=self.promoCodesByVersion[version])
                print "        Proceeds         : {proceeds:6.02f}".format(proceeds=self.proceedsByVersion[version])
                if version in self.userRetentionByVersion:
                    print "        Users Retained   : {retainedPct:3.1f}% of existing users upgraded to this version".format(retainedPct=self.userRetentionByVersion[version]*100.0)
                if self.numberOfRatingsPerVersion[version] > 0:
                    print "    Average Rating       : {avgRating:6.01f}".format(avgRating=self.averageRatingPerVersion[version])
                    print "    Number of Ratings    : {ratingCount:6}".format(ratingCount=self.numberOfRatingsPerVersion[version])

    def saveUnitsGraph(self, basePath, installs, updates, entryDates):
        barWidth = 0.35
        barIndices = np.arange(len(entryDates))
    
        maxY = max(max(installs), max(updates)) + 1
    
        figure, unitsGraph = plt.subplots()
        installsRects = unitsGraph.bar(barIndices, installs, barWidth, color='g')
        updatesRects = unitsGraph.bar(barIndices+barWidth, updates, barWidth, color='b')
        plt.ylim(ymax=maxY, ymin=0)
    
        unitsGraph.set_ylabel("Units")
        unitsGraph.set_title("Sales Data for {name}".format(name=self.Name))
        unitsGraph.set_xticks(barIndices+barWidth)
        unitsGraph.set_xticklabels(entryDates, rotation=-90)

        unitsGraph.legend((installsRects[0], updatesRects[0]), ('Installs', 'Updates'), bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                if height > 0:
                    unitsGraph.text(rect.get_x()+rect.get_width()/2., 1.05*height, '%d'%int(height), ha='center', va='bottom')

        autolabel(installsRects)
        autolabel(updatesRects)
    
        fileName = os.path.join(basePath, self.SKU + "_AllInstallsAndUpdates.png")
        plt.savefig(fileName,bbox_inches='tight',dpi=100)
        plt.clf()
        plt.cla()
        
        self.Graphs.update({"AllInstallsAndUpdates":fileName})

    def saveProceedsGraph(self, basePath, proceeds, entryDates):
        barWidth = 0.7
        barIndices = np.arange(len(entryDates))
    
        maxY = math.ceil(max(proceeds)) + 1
    
        figure, unitsGraph = plt.subplots()
        proceedsRects = unitsGraph.bar(barIndices, proceeds, barWidth, color='g')
        plt.ylim(ymax=maxY, ymin=0)
    
        unitsGraph.set_ylabel("Amount Earned")
        unitsGraph.set_title("Proceeds for {name}".format(name=self.Name))
        unitsGraph.set_xticks(barIndices+barWidth)
        unitsGraph.set_xticklabels(entryDates, rotation=-90)
    
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                if height > 0:
                    unitsGraph.text(rect.get_x()+rect.get_width()/2., 1.05*height, '%1.2f'%float(height), ha='center', va='bottom', rotation=-90)

        autolabel(proceedsRects)
    
        fileName = os.path.join(basePath, self.SKU + "_Proceeds.png")
        plt.savefig(fileName,bbox_inches='tight',dpi=100)
        plt.clf()
        plt.cla()
        
        self.Graphs.update({"Proceeds":fileName})
    
    def generateAndSaveCountryInstallsChart(self, fileName, title, countries, installs):
        for countryIdx in range(0, len(countries)):
            countries[countryIdx] += " ({installs})".format(installs=installs[countryIdx])
        
        plt.figure(1, figsize=(6,6))
    
        pieWedges = plt.pie(installs, labels=countries, shadow=False)
        
        # make the edges white (From http://nxn.se/post/46440196846/making-nicer-looking-pie-charts-with-matplotlib)
        for wedge in pieWedges[0]:
            wedge.set_edgecolor('white')
            
        plt.title(title)
    
        plt.savefig(fileName, bbox_inches='tight', dpi=100)
        plt.clf()
        plt.cla()

    def saveCountryDistributionGraphs(self, basePath):
        reportList = dict();
        reportList.update({"PaidInstalls" : ["Sales",          self.paidInstallsByCountry, self.newPaidInstallsByCountry]})
        reportList.update({"FreeInstalls" : ["Free Installs",  self.freeInstallsByCountry, self.newFreeInstallsByCountry]})
        reportList.update({"AllInstalls"  : ["Total Installs", self.allInstallsByCountry, self.newAllInstallsByCountry]})
        
        for reportName in reportList:
            [reportTitle, installsByCountry, newInstallsByCountry] = reportList[reportName]
            
            countries = installsByCountry.keys()
            installs = installsByCountry.values()
            
            fileName = os.path.join(basePath, self.SKU + "_{reportName}ByCountry.png".format(reportName=reportName))
            self.generateAndSaveCountryInstallsChart(fileName, "{reportTitle} by Country".format(reportTitle=reportTitle), countries, installs)
            self.Graphs.update({"{reportName}ByCountry".format(reportName=reportName):fileName})
    
            if self.hasNewData and len(newInstallsByCountry) > 0:
                countries = newInstallsByCountry.keys()
                installs = newInstallsByCountry.values()
                
                fileName = os.path.join(basePath, self.SKU + "_New{reportName}ByCountry.png".format(reportName=reportName))
                self.generateAndSaveCountryInstallsChart(fileName, "New {reportTitle} by Country".format(reportTitle=reportTitle), countries, installs)
                self.Graphs.update({"New{reportName}ByCountry".format(reportName=reportName):fileName})

    def generateGraphs(self, basePath):
        startDate = datetime.date.today()
    
        entryDates = []
    
        reportDates = self.allInstallsByDate.keys()
        reportDates.sort()
    
        installs = []
        updates = []
        proceeds = []
    
        # build up the data for the last 30 days
        for dayOffset in range(30, 0, -1):
            searchDate = startDate - datetime.timedelta(dayOffset)
        
            entryDates.append(searchDate)
        
            if searchDate in reportDates:
                installs.append(self.allInstallsByDate[searchDate])
                updates.append(self.updatesByDate[searchDate])
                proceeds.append(self.proceedsByDate[searchDate])
            else:
                installs.append(0)
                updates.append(0)
                proceeds.append(0)
    
        self.saveUnitsGraph(basePath, installs, updates, entryDates)
        self.saveProceedsGraph(basePath, proceeds, entryDates)
        self.saveCountryDistributionGraphs(basePath)
