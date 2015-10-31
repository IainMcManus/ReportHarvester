#!/usr/bin/python

# Harvest Reports v0.1.5
# Copyright (c) 2014-2015 Iain McManus. All rights reserved.
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

class ReportTypes:
    BasicSummary, DetailedSummary = range(2)
    
class RSSFields:
    Version, Title, Rating, Summary, UniqueId = range(5)
    
class RatingsSummaryFields:
    LifetimeAverageRating, LifetimeRatingSamples, AverageRatingPerVersion, NumberOfRatingsPerVersion, NumberOfNewRatings = range(5)

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
