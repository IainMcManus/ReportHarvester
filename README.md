Introduction
===============

ReportHarvester is a Python based tool for downloading and analysing sales and ratings data from iTunes Connect.

Report Harvester will analyse the downloaded sales and ratings data and provide the following information per each application:
 * Number of installs (total and per version)
 * Number of upgrades (total and per version)
 * Number of promo codes used (total and per version)
 * Proceeds earned (total and per version)
 * Number of users running the latest version
 * Percentage of users retained between versions
 * Average rating of the app and the number of users who have rated it (total and per version)
 * Graph showing geographic distribution of sales for newly downloaded data and for all time
 * Graph showing sales and updates for the last 30 days
 * Graph showing proceeds for the last 30 days

Requirements
===============

You will need the AutoIngestion.Class from Apple. The AutoIngestion.Class cannot be redistributed so you must download it yourself. The two files (AutoIngestion.Class and AutoIngestion.properties) should be placed in the same folder as the HarvestReports.py 

The AutoIngestion tool can be downloaded by following the instructions in the [iTunes Connect Sales and Trends Guide][itunes-guide]
[itunes-guide]: [http://www.apple.com/itunesnews/docs/AppStoreReportingInstructions.pdf]

ReportHarvester uses a number of third party libraries. You will need to install the following:

##Homebrew (Package Manager for OSX)

Install by running the below command in a Terminal window
    ruby -e "$(curl -fsSL https://raw.github.com/Homebrew/homebrew/go/install)"
Alternatively go to the website for more instructions
    http://brew.sh/

## Add the appropriate paths for python to your .profile or .bash_profile file in your home directory. For example:
    export PATH=/usr/local/bin:/usr/local/share/python:$PATH

## Install Python using Homebrew
    brew install python

## Install pip
    easy_install pip

## Install FeedParser
    pip install feedparser

## Install Unidecode
    pip install unidecode

## Install NumPy
    pip install numpy

## Install SciPy
    brew install gfortran
    pip install scipi

## Install Freetype
    brew install freetype

## Install matplotlib
    brew install pkg-config
    pip install matplotlib
    pip install six

Configuration
===============

There are two main areas you must configure:

## Setup autoingestion.properties
    Open autoingestion.properties using a text editor
    Add your iTunes Connect username (userID) and password.

## Setup email options (if being used)
    Open emailConfig.csv
    Fill out the following information
        * Subject   - The subject line for all emails
        * From      - The email address the emails will be sent FROM
        * To        - The email address that emails will be sent TO
        * Server    - The name (or IP address) of the SMTP server
        * Port      - The port on the SMTP server to use
        * EnableTLS - 1 if your SMTP server uses encryption, 0 otherwise
        * Username  - The username to login to the SMTP server
        * Password  - The password to login to the SMTP server

Usage
===============

##python harvestReports -p <Properties File> -v <Vendor Id> [-d <Days Back>] [-rd|-rv] [-e] [-s] [-f AppId1,AppId2] [-c CountryCode1,CountryCode2]
    Properties File  Path to the .properties file with the username/password for iTunes Connect
    Vendor Id        Your vendor Id
    Days Back        Number of days worth of data back (from now) to retrieve
    -o               Overwrites any existing reports
    -rd              Shows detailed summary report
    -rv              Shows verbose output
    -e               Sends an email if there is new data
    -s               Saves HTML report
    -f               Downloads the ratings and reviews RSS feed for the specified app ids
    -c               List of country codes to download the rating and review data for

    # Note - Feeds are ONLY downloaded when a new daily report is downloaded. Or a new filler report is created as no events occurred that day.
    # Multiple app ids can be provided. You can find your app id by logging into iTunes Connect and looking at the page for your app for the Apple Identifier.
    # Multiple country codes can be provided. These are the standard two letter codes, eg. US = United States of America.

Examples
===============

Download the last 5 days of data and generate a report. Download feeds for app with id 697893360 for Australia and the United Kingdom. Send an email if there is new data.
    python harvestReports.py -p autoingestion.properties -v <VendorId> -d 5 -e -s -f 697893360 -c AU,UK

    # Note - Replace <VendorId> with your vendor Id

Download the last 5 days of data and generate a report. Send an email if there is new data.
    python harvestReports.py -p autoingestion.properties -v <VendorId> -d 5 -e -s

    # Note - Replace <VendorId> with your vendor Id

Download the last 5 days of data and generate a report.
    python harvestReports.py -p autoingestion.properties -v <VendorId> -d 5 -s

    # Note - Replace <VendorId> with your vendor Id

Final Remarks
===============

Report Harvester has been tested on OS X 10.9 using Python 2.7.6. The only email provider it has been used with has been Gmail. It has been tested using a Gmail account with two-factor authentication enabled and using application specific passwords.

I have Report Harvester setup to run periodically on a Mac Mini Server with it configured to email me the reports. 