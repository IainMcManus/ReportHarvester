#!/usr/bin/python

# Harvest Reports v0.1.1
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

import datetime, os, sys, subprocess, getopt, gzip, time, smtplib, math, csv

import numpy as np
import matplotlib.pyplot as plt

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

class ReportTypes:
    BasicSummary, DetailedSummary = range(2)

class FieldRemapper:
    CountryFromCode = dict()
    CurrencyFromCode = dict()
    ProductTypeFromCode = dict()
    PromoTypeFromCode = dict()
    
    def __init__(self):
        with open('fields_countries.csv', mode='r') as countriesFile:
            reader = csv.reader(countriesFile)
            self.CountryFromCode = {rows[0]:rows[1] for rows in reader}
            
        with open('fields_currencies.csv', mode='r') as currenciesFile:
            reader = csv.reader(currenciesFile)
            self.CurrencyFromCode = {rows[0]:rows[1] for rows in reader}
            
        with open('fields_productTypes.csv', mode='r') as productTypesFile:
            reader = csv.reader(productTypesFile)
            self.ProductTypeFromCode = {rows[0]:rows[1] for rows in reader}
            
        with open('fields_promoCodes.csv', mode='r') as promoCodesFile:
            reader = csv.reader(promoCodesFile)
            self.PromoTypeFromCode = {rows[0]:rows[1] for rows in reader}
            
        if len(self.CountryFromCode) == 0:
            print "Input file fields_countries.csv could not be found. Countries will be listed as their code"
        if len(self.CurrencyFromCode) == 0:
            print "Input file fields_currencies.csv could not be found. Currencies will be listed as their code"
        if len(self.ProductTypeFromCode) == 0:
            print "Input file fields_productTypes.csv could not be found. Product types will be listed as their code"
        if len(self.PromoTypeFromCode) == 0:
            print "Input file fields_promoCodes.csv could not be found. Promo codes will be listed as their code"

class SalesReportFile:
    fields = [
              ["Provider"],
              ["Provider Country"],
              ["SKU"],
              ["Developer"],
              ["Title"],
              ["Version"],
              ["Product Type Identifier"],
              ["Units"],
              ["Developer Proceeds (per item)"],
              ["Begin Date"],
              ["End Date"],
              ["Customer Currency"],
              ["Country Code"],
              ["Currency of Proceeds"],
              ["Apple Identifier"],
              ["Customer Price"],
              ["Promo Code"],
              ["Parent Identifier"],
              ["Subscription"],
              ["Period"],
              ["Category"]
             ]

    def __init__(self, reportFile, isNewFile, fieldRemapper):
        self.data = []
        self.isNewFile = isNewFile
        
        # stream in the downloaded report file
        reportFileHandle = open(reportFile, 'r')
        reportFileContents = reportFileHandle.readlines()
        reportFileHandle.close()
        
        # parse the report data
        firstLine = True
        for reportFileLine in reportFileContents:
            if firstLine:
                firstLine = False
                continue
                
            cleanedLineElements = reportFileLine.strip().split('\t')
         
            # extract and process the fields as required
            extractedLine = dict()
            for fieldIndex in range(0, len(cleanedLineElements)):
                fieldName = self.fields[fieldIndex][0]
                fieldValue = cleanedLineElements[fieldIndex].strip()
                
                # some fields require additional processing to remap to actual values or coerce types
                if len(fieldValue) > 0:
                    if fieldName == "Product Type Identifier" and len(fieldRemapper.ProductTypeFromCode) > 0:
                        fieldValue = fieldRemapper.ProductTypeFromCode[fieldValue]
                    if fieldName == "Provider Country" and len(fieldRemapper.CountryFromCode) > 0:
                        fieldValue = fieldRemapper.CountryFromCode[fieldValue]
                    if fieldName == "Customer Currency" and len(fieldRemapper.CurrencyFromCode) > 0:
                        fieldValue = fieldRemapper.CurrencyFromCode[fieldValue]
                    if fieldName == "Country Code" and len(fieldRemapper.ProductTypeFromCode) > 0:
                        fieldValue = fieldRemapper.CountryFromCode[fieldValue]
                    if fieldName == "Currency of Proceeds" and len(fieldRemapper.CountryFromCode) > 0:
                        fieldValue = fieldRemapper.CurrencyFromCode[fieldValue]
                    if fieldName == "Promo Code" and len(fieldRemapper.PromoTypeFromCode) > 0:
                        fieldValue = fieldRemapper.PromoTypeFromCode[fieldValue]
                        
                    if fieldName == "Developer Proceeds (per item)":
                        fieldValue = float(fieldValue)
                    if fieldName == "Customer Price":
                        fieldValue = float(fieldValue)
                    if fieldName == "Units":
                        fieldValue = int(fieldValue)
                    if fieldName == "Begin Date":
                        fieldValue = (datetime.datetime.strptime(fieldValue, "%m/%d/%Y")).date()
                    if fieldName == "End Date":
                        fieldValue = (datetime.datetime.strptime(fieldValue, "%m/%d/%Y")).date()
                
                extractedLine.update({fieldName : fieldValue})

            # pad out missing fields. sometimes the reports drop off entries for old data
            for fieldIndex in range(0, len(self.fields)):
                fieldName = self.fields[fieldIndex][0]
                
                if not fieldName in extractedLine:
                    extractedLine.update({fieldName : None})
                
            self.data.append(extractedLine)

class SKUData:
    def __init__(self, basePath, reportLines, fieldRemapper):
        self.rawData = reportLines
        
        self.SKU = "Unknown"
        self.Name = "Unknown"
        
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
        
        self.rawData.sort(key = lambda x: x[1]["Begin Date"])
        
        self.Graphs = dict()
        
        # process each report line in order of date and compile the summary
        for [isNewData, reportLine] in self.rawData:
            if self.SKU == "Unknown" and len(reportLine["SKU"].strip()) > 0:
                self.SKU = reportLine["SKU"]
            if self.Name == "Unknown" and len(reportLine["Title"].strip()) > 0:
                self.Name = reportLine["Title"]
            
            version = reportLine["Version"]
            units = reportLine["Units"]
            proceedsPerItem = reportLine["Developer Proceeds (per item)"]
            country = reportLine["Country Code"]
            proceeds = units * proceedsPerItem
            
            self.proceedsTotal += proceeds
            
            # track new profits
            if isNewData:
                self.newProceedsTotal += proceeds
                self.hasNewData = True
            
            # record all versions
            if not version in self.versions:
                self.versions.append(version)
            
            startDate = reportLine["Begin Date"]
            
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
                if version in self.updatesByVersion:
                    newUpdatesByVersion = self.updatesByVersion[version] + units
                    self.updatesByVersion.update({version : newUpdatesByVersion})
                else:
                    self.updatesByVersion.update({version : units})
                
                if startDate in self.updatesByDate:
                    newUpdatesByDate = self.updatesByDate[startDate] + units
                    self.updatesByDate.update({startDate : newUpdatesByDate})
            
                if isNewData:
                    self.newUpdatesTotal += units
            else: # the report line is for sales
                self.allInstallsTotal += units
                
                if version in self.unitsByVersion:
                    newUnitsForVersion = self.unitsByVersion[version] + units
                    self.unitsByVersion.update({version : newUnitsForVersion})
                else:
                    self.unitsByVersion.update({version : units})
                    
                if startDate in self.allInstallsByDate:
                    newInstallsByDate = self.allInstallsByDate[startDate] + units
                    self.allInstallsByDate.update({startDate : newInstallsByDate})
                
                if startDate in self.proceedsByDate:
                    newProceedsByDate = self.proceedsByDate[startDate] + proceeds
                    self.proceedsByDate.update({startDate : newProceedsByDate})
                
                if country in self.allInstallsByCountry:
                    newAllInstallsByCountry = self.allInstallsByCountry[country] + units
                    self.allInstallsByCountry.update({country : newAllInstallsByCountry})
                else:
                    self.allInstallsByCountry.update({country : units})
            
                if isNewData:
                    self.newAllInstallsTotal += units
                
                    if country in self.newAllInstallsByCountry:
                        newNewAllInstallsByCountry = self.newAllInstallsByCountry[country] + units
                        self.newAllInstallsByCountry.update({country : newNewAllInstallsByCountry})
                    else:
                        self.newAllInstallsByCountry.update({country : units})
            
                if version in self.proceedsByVersion:
                    newProceedsForVersion = self.proceedsByVersion[version] + proceeds
                    self.proceedsByVersion.update({version : newProceedsForVersion})
                else:
                    self.proceedsByVersion.update({version : proceeds})
                
                # record the count of promo codes used
                if reportLine["Promo Code"] != None and len(reportLine["Promo Code"]) > 0:
                    self.promoCodesTotal += units
                    
                    if version in self.promoCodesByVersion:
                        newPromoCodesByVersion = self.promoCodesByVersion[version] + units
                        self.promoCodesByVersion.update({version : newPromoCodesByVersion})
                    else:
                        self.promoCodesByVersion.update({version : units})
                        
                    if isNewData:
                        self.newPromoCodesTotal += units
                
                # was this a sale?
                if proceeds > 0:
                    self.paidInstallsTotal += units
                    
                    if startDate in self.paidInstallsByDate:
                        newPaidInstallsByDate = self.paidInstallsByDate[startDate] + units
                        self.paidInstallsByDate.update({startDate : newPaidInstallsByDate})
                
                    if country in self.paidInstallsByCountry:
                        newPaidInstallsByCountry = self.paidInstallsByCountry[country] + units
                        self.paidInstallsByCountry.update({country : newPaidInstallsByCountry})
                    else:
                        self.paidInstallsByCountry.update({country : units})
            
                    if isNewData:
                        self.newPaidInstallsTotal += units
                
                        if country in self.newPaidInstallsByCountry:
                            newNewPaidInstallsByCountry = self.newPaidInstallsByCountry[country] + units
                            self.newPaidInstallsByCountry.update({country : newNewPaidInstallsByCountry})
                        else:
                            self.newPaidInstallsByCountry.update({country : units})
                else: # otherwise it was a free installs
                    self.freeInstallsTotal += units
                    
                    if startDate in self.freeInstallsByDate:
                        newFreeInstallsByDate = self.freeInstallsByDate[startDate] + units
                        self.freeInstallsByDate.update({startDate : newFreeInstallsByDate})
                
                    if country in self.freeInstallsByCountry:
                        newFreeInstallsByCountry = self.freeInstallsByCountry[country] + units
                        self.freeInstallsByCountry.update({country : newFreeInstallsByCountry})
                    else:
                        self.freeInstallsByCountry.update({country : units})
            
                    if isNewData:
                        self.newFreeInstallsTotal += units
                
                        if country in self.newFreeInstallsByCountry:
                            newNewFreeInstallsByCountry = self.newFreeInstallsByCountry[country] + units
                            self.newFreeInstallsByCountry.update({country : newNewFreeInstallsByCountry})
                        else:
                            self.newFreeInstallsByCountry.update({country : units})
                
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
        print "New Data Available for {name}".format(name=self.Name)
        if self.newFreeInstallsTotal > 0:
            print "    Free Installs       : {units:6}".format(units=self.newFreeInstallsTotal)
        if self.newPaidInstallsTotal > 0:
            print "    Sales               : {units:6}".format(units=self.newPaidInstallsTotal)
        if self.newAllInstallsTotal > 0:
            print "    Total Installs      : {units:6}".format(units=self.newAllInstallsTotal)
            
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
                
            report += "</ul>"
        report += "</ul>"
        
        return report
    
    def getEmailSummary_HTML(self):
        summary = ""
        
        summary += "<p><h1>New Data Available for {name}</h1></p>".format(name=self.Name)
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
        if self.promoCodesTotal > 0:
            summary += "<b>Promo Codes Used</b>    : {promoCodes:6}".format(promoCodes=self.newPromoCodesTotal)
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
                
def processDailiesIn(basePath, downloadedFiles, reportType):
    salesReportObjects = []
    
    fieldRemapper = FieldRemapper()
    
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
            
            if not skuName in skuRelatedReportLines:
                skuRelatedReportLines.update({skuName : [[salesReportObject.isNewFile, reportEntry]]})
            else:
                currentReportLines = skuRelatedReportLines[skuName]
                currentReportLines.append([salesReportObject.isNewFile, reportEntry])
                
                skuRelatedReportLines.update({skuName : currentReportLines})

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
    
    # print out the report
    for skuSummary in skuData.values():
        skuSummary.printSummary(reportType)
    
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
        sys.exit(-1)
    else:
        s.quit()
    
def usage():
    print "Usage:"
    print "      harvestReports -p <Properties File> -v <Vendor Id> [-d <Days Back>] [-rd|-rv] [-e] [-s]"
    print ""
    print "          Properties File  Path to the .properties file with the username/password for iTunes Connect"
    print "          Vendor Id        Your vendor Id"
    print "          Days Back        Number of days worth of data back (from now) to retrieve"
    print "          -o               Overwrites any existing reports"
    print "          -rd              Shows detailed summary report"
    print "          -rv              Shows verbose output"
    print "          -e               Sends an email if there is new data"
    print "          -s               Saves HTML report"

def main(argv):
    print "Harvest Reports v0.1.1"
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
    
    essentialArgumentsFoundCount = 0
    
    try:
        opts, args = getopt.getopt(argv, "hp:v:d:r:oes", ["help", "properties=", "vendorId=", "daysBack=", "report=", "overwrite", "email", "saveHMTL"])
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
            
    if essentialArgumentsFoundCount < 2:
        usage()
        sys.exit(2)

    basePath = "{vendorId}".format(vendorId=vendorId)

    if not os.path.exists(basePath):
        os.makedirs(basePath)

    [addedPlaceHolderFileForEventlessDay, downloadedFiles] = downloadDailies(propertiesFile, vendorId, daysBack, overwriteExistingData, basePath, verbose)
    
    perSKUData = processDailiesIn(basePath, downloadedFiles, reportType)
        
    if saveHTMLReport:
        generateHTMLReport(basePath, perSKUData)

    if (addedPlaceHolderFileForEventlessDay or (len(downloadedFiles) > 0)) and sendEmail:
        emailReportForNewData(downloadedFiles, perSKUData)

if __name__ == '__main__':
    main(sys.argv[1:])
