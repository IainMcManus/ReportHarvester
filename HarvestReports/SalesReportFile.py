#!/usr/bin/python

# Harvest Reports v0.1.4
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
        self.fileName = reportFile
        
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
                        extractedLine.update({"Currency Code of Proceeds": fieldValue})
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
