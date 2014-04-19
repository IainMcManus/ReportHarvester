#!/usr/bin/python

# Harvest Reports v0.1
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
        self.unitsTotal = 0
        self.proceedsByVersion = dict()
        self.proceedsTotal = 0
        self.updatesByVersion = dict()
        self.promoCodesByVersion = dict()
        self.promoCodesTotal = 0
        self.versions = []
        self.salesByDate = dict()
        self.updatesByDate = dict()
        self.proceedsByDate = dict()
        self.salesByCountry = dict()

        self.newSalesTotal = 0
        self.newProceedsTotal = 0
        self.newUpdatesTotal = 0
        self.newPromoCodesTotal = 0
        self.hasNewData = False
        self.newSalesByCountry = dict()
        
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
            if not startDate in self.salesByDate:
                self.salesByDate.update({startDate : 0})
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
                self.unitsTotal += units
                
                if version in self.unitsByVersion:
                    newUnitsForVersion = self.unitsByVersion[version] + units
                    self.unitsByVersion.update({version : newUnitsForVersion})
                else:
                    self.unitsByVersion.update({version : units})
                    
                if startDate in self.salesByDate:
                    newSalesByDate = self.salesByDate[startDate] + units
                    self.salesByDate.update({startDate : newSalesByDate})
                
                if startDate in self.proceedsByDate:
                    newProceedsByDate = self.proceedsByDate[startDate] + proceeds
                    self.proceedsByDate.update({startDate : newProceedsByDate})
                
                if country in self.salesByCountry:
                    newSalesByCountry = self.salesByCountry[country] + units
                    self.salesByCountry.update({country : newSalesByCountry})
                else:
                    self.salesByCountry.update({country : units})
            
                if isNewData:
                    self.newSalesTotal += units
                
                    if country in self.newSalesByCountry:
                        newNewSalesByCountry = self.newSalesByCountry[country] + units
                        self.newSalesByCountry.update({country : newNewSalesByCountry})
                    else:
                        self.newSalesByCountry.update({country : units})
            
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
                
        self.versions.sort()

        # fill in any missing version data
        for version in self.versions:
            if not version in self.unitsByVersion:
                self.unitsByVersion.update({version : 0})
            if not version in self.updatesByVersion:
                self.updatesByVersion.update({version : 0})
            if not version in self.proceedsByVersion:
                self.proceedsByVersion.update({version : 0.0})
            if not version in self.promoCodesByVersion:
                self.promoCodesByVersion.update({version : 0})
        
        # calculate the number on old versions
        self.numOnOldVersions = self.unitsTotal
        self.numOnOldVersions -= self.updatesByVersion[self.versions[len(self.versions) - 1]]
        self.numOnOldVersions -= self.unitsByVersion[self.versions[len(self.versions) - 1]]
        self.legacyUserPercentage = 100.0 * self.numOnOldVersions / self.unitsTotal
        
        self.generateGraphs(basePath)
    
    def printNewData(self):
        print "New Data Available for {name}".format(name=self.Name)
        print "    Units Sold          : {units:6}".format(units=self.newSalesTotal)
        if self.promoCodesTotal > 0:
            print "    Promo Codes Used    : {promoCodes:6}".format(promoCodes=self.newPromoCodesTotal)
        print "    Proceeds            : {proceeds:6.02f}".format(proceeds=self.newProceedsTotal)
        print "    Updates             : {updates:6}".format(updates=self.newUpdatesTotal)
        
    def getReport_HTML(self):
        report = "<p><h1>Sales Report for {name}</h1></p>".format(name=self.Name)
        report += "<p><b>Total Units Sold</b>    : {units:6}</p>".format(units=self.unitsTotal)
        
        if self.promoCodesTotal > 0:
            report += "<p><b>Promo Codes Used</b>    : {promoCodes:6}</p>".format(promoCodes=self.promoCodesTotal)
            
        report += "<p><b>Proceeds</b>            : {proceeds:6.02f}</p>".format(proceeds=self.proceedsTotal)
        report += "<p><b>Users Not on Latest</b> : {legacyUsers:3.01f}%</p>".format(legacyUsers=self.legacyUserPercentage)

        report += "<p><h2>Version Breakdown</h2></p>"
        report += "<ul>"
        for version in reversed(self.versions):
            report += "<li><b>{version}</b>".format(version=version)
            report += "<ul>"
            
            if version in self.unitsByVersion:
                report += "<li>{sold:6} units sold</li>".format(sold=self.unitsByVersion[version])
            if version in self.updatesByVersion:
                report += "<li>{updates:6} installs updated to this version</li>".format(updates=self.updatesByVersion[version])
            if version in self.promoCodesByVersion:
                report += "<li>{promoCodes:6} promo codes used for this version</li>".format(promoCodes=self.promoCodesByVersion[version])
            if version in self.proceedsByVersion:
                report += "<li>{proceeds:6.02f} earned from this version</li>".format(proceeds=self.proceedsByVersion[version])
                
            report += "</ul>"
        report += "</ul>"
        
        return report
    
    def getEmailSummary_HTML(self):
        summary = ""
        
        summary += "<p><h1>New Data Available for {name}</h1></p>".format(name=self.Name)
        summary += "<br>"
        summary += "<b>Units Sold</b>          : {units:6}".format(units=self.newSalesTotal)
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
        summary += "    Units Sold          : {units:6}".format(units=self.newSalesTotal)
        summary += "\r\n"
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
        print "    Units Sold          : {units:6}".format(units=self.unitsTotal)
        if self.promoCodesTotal > 0:
            print "    Promo Codes Used    : {promoCodes:6}".format(promoCodes=self.promoCodesTotal)
        print "    Proceeds            : {proceeds:6.02f}".format(proceeds=self.proceedsTotal)
        print "    Users Not on Latest : {legacyUsers:3.01f}%".format(legacyUsers=self.legacyUserPercentage)
        
        if reportType == ReportTypes.DetailedSummary:
            print "    Version Breakdown"
            for version in reversed(self.versions):
                print "      {version}".format(version=version)
            
                if version in self.unitsByVersion:
                    print "        Sales            : {sold:6} units".format(sold=self.unitsByVersion[version])
                if version in self.updatesByVersion:
                    print "        Updates          : {updates:6} units".format(updates=self.updatesByVersion[version])
                if version in self.promoCodesByVersion:
                    print "        Promo Codes Used : {promoCodes:6}".format(promoCodes=self.promoCodesByVersion[version])
                if version in self.proceedsByVersion:
                    print "        Proceeds         : {proceeds:6.02f}".format(proceeds=self.proceedsByVersion[version])

    def saveUnitsGraph(self, basePath, sales, updates, entryDates):
        barWidth = 0.35
        barIndices = np.arange(len(entryDates))
    
        maxY = max(max(sales), max(updates)) + 1
    
        figure, unitsGraph = plt.subplots()
        salesRects = unitsGraph.bar(barIndices, sales, barWidth, color='g')
        updatesRects = unitsGraph.bar(barIndices+barWidth, updates, barWidth, color='b')
        plt.ylim(ymax=maxY, ymin=0)
    
        unitsGraph.set_ylabel("Units")
        unitsGraph.set_title("Sales Data for {name}".format(name=self.Name))
        unitsGraph.set_xticks(barIndices+barWidth)
        unitsGraph.set_xticklabels(entryDates, rotation=-90)

        unitsGraph.legend((salesRects[0], updatesRects[0]), ('Sales', 'Updates'), bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                if height > 0:
                    unitsGraph.text(rect.get_x()+rect.get_width()/2., 1.05*height, '%d'%int(height), ha='center', va='bottom')

        autolabel(salesRects)
        autolabel(updatesRects)
    
        fileName = os.path.join(basePath, self.SKU + "_SalesAndUpdates.png")
        plt.savefig(fileName,bbox_inches='tight',dpi=100)
        plt.clf()
        plt.cla()
        
        self.Graphs.update({"SalesAndUpdates":fileName})

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
    
    def generateAndSaveCountrySalesChart(self, fileName, title, countries, sales):
        for countryIdx in range(0, len(countries)):
            countries[countryIdx] += " ({sales})".format(sales=sales[countryIdx])
        
        plt.figure(1, figsize=(6,6))
    
        plt.pie(sales, labels=countries, shadow=False)
        plt.title(title)
    
        plt.savefig(fileName, bbox_inches='tight', dpi=100)
        plt.clf()
        plt.cla()

    def saveCountryDistributionGraphs(self, basePath):
        countries = self.salesByCountry.keys()
        sales = self.salesByCountry.values()
    
        fileName = os.path.join(basePath, self.SKU + "_UnitsSoldByCountry.png")
        self.generateAndSaveCountrySalesChart(fileName, "Units Sold by Country", countries, sales)
        self.Graphs.update({"SalesByCountry":fileName})
    
        if self.hasNewData:
            countries = self.newSalesByCountry.keys()
            sales = self.newSalesByCountry.values()
    
            fileName = os.path.join(basePath, self.SKU + "_NewUnitsSoldByCountry.png")
            self.generateAndSaveCountrySalesChart(fileName, "New Units Sold by Country", countries, sales)
            self.Graphs.update({"NewSalesByCountry":fileName})

    def generateGraphs(self, basePath):
        startDate = datetime.date.today()
    
        entryDates = []
    
        reportDates = self.salesByDate.keys()
        reportDates.sort()
    
        sales = []
        updates = []
        proceeds = []
    
        # build up the data for the last 30 days
        for dayOffset in range(30, 0, -1):
            searchDate = startDate - datetime.timedelta(dayOffset)
        
            entryDates.append(searchDate)
        
            if searchDate in reportDates:
                sales.append(self.salesByDate[searchDate])
                updates.append(self.updatesByDate[searchDate])
                proceeds.append(self.proceedsByDate[searchDate])
            else:
                sales.append(0)
                updates.append(0)
                proceeds.append(0)
    
        self.saveUnitsGraph(basePath, sales, updates, entryDates)
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
    
    currentDayReportNotAvailable = False
    
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
            elif "Daily reports are available only for" in autoingestionOutput:
                if dayOffset == 0:
                    currentDayReportNotAvailable = True
                
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
                        print "    No sales are occurred for that date"
                    elif invalidDate:
                        print "    No data exists for that date. Either the day is too far back (Apple only keeps a limited number of dailies) or the report for that day does not yet exist"
                    else:
                       print "    The download failed for an unknown reason"
        else:
            if verbose:
                print "Skipped existing data for {day:02}/{month:02}/{year:04}".format(day=requestedDate.day, month=requestedDate.month, year=requestedDate.year)
    
    return [currentDayReportNotAvailable, downloadedFiles]

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

def emailReportForToday(downloadedFiles, perSKUData):
    summary_PlainText = ""
    summary_HTML = """\
<html>
  <head></head>
  <body>
"""

    attachments = dict()

    if len(downloadedFiles) == 0:
        summary_PlainText = "No sales or updates have occurred today"
        summary_HTML = "<p>No sales or updates have occurred today</p>"
    else:
        for skuSummary in perSKUData.values():
            if skuSummary.hasNewData:
                if len(summary_PlainText) > 0:
                    summary_PlainText += "\r\n"
                    
                summary_PlainText += skuSummary.getEmailSummary_PlainText()
                summary_HTML += skuSummary.getEmailSummary_HTML()
                
                attachments.update({skuSummary.SKU + "NewSalesByCountry.png" : skuSummary.Graphs["NewSalesByCountry"]})
                summary_HTML += '<br><img src="cid:{SKU}NewSalesByCountry.png"><br>'.format(SKU=skuSummary.SKU)
    
    for skuSummary in perSKUData.values():
        summary_HTML += skuSummary.getReport_HTML()
            
        summary_HTML += '<br><img src="cid:{SKU}SalesAndUpdates.png"><br>'.format(SKU=skuSummary.SKU)
        attachments.update({skuSummary.SKU + "SalesAndUpdates.png" : skuSummary.Graphs["SalesAndUpdates"]})
        summary_HTML += '<br><img src="cid:{SKU}SalesByCountry.png"><br>'.format(SKU=skuSummary.SKU)
        attachments.update({skuSummary.SKU + "SalesByCountry.png" : skuSummary.Graphs["SalesByCountry"]})
    
    summary_HTML += """\
  </body>
</html>
"""
    emailConfig = dict()
    
    with open('emailConfig.csv', mode='r') as configFile:
        reader = csv.reader(configFile)
        emailConfig = {rows[0]:rows[1] for rows in reader}
    
    emailMessage = MIMEMultipart("alternative")
    emailMessage["Subject"] = emailConfig["Subject"]
    emailMessage["From"] = emailConfig["From"]
    emailMessage["To"] = emailConfig["To"]
    
    emailMessage.attach(MIMEText(summary_PlainText, "plain"))
    emailMessage.attach(MIMEText(summary_HTML, "html"))
    
    # attach all of the images to the email
    for attachmentName in attachments:
        attachmentHandle = open(attachments[attachmentName], 'rb')
        attachmentImage = MIMEImage(attachmentHandle.read())
        attachmentHandle.close()
        
        attachmentImage.add_header("Content-ID", attachmentName)
        emailMessage.attach(attachmentImage)
    
    try:
        s = smtplib.SMTP(emailConfig["Server"], int(emailConfig["Port"]))
        s.ehlo_or_helo_if_needed()
        if emailConfig["EnableTLS"] == "1":
            s.starttls()  
            s.ehlo()
        s.login(emailConfig["Username"], emailConfig["Password"])  
        s.sendmail(emailMessage["From"], [emailMessage["To"]], emailMessage.as_string())
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
    print "Harvest Reports v0.1"
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

    [currentDayReportNotAvailable, downloadedFiles] = downloadDailies(propertiesFile, vendorId, daysBack, overwriteExistingData, basePath, verbose)
    
    perSKUData = processDailiesIn(basePath, downloadedFiles, reportType)
        
    if saveHTMLReport:
        generateHTMLReport(basePath, perSKUData)

    if (len(downloadedFiles) > 0) and sendEmail:
        emailReportForToday(downloadedFiles, perSKUData)

if __name__ == '__main__':
    main(sys.argv[1:])
