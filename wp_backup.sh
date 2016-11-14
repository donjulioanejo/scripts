#!/bin/bash

#
# Simple shell script for wordpress backups.
# 
# Change WEBROOT and DOCROOT to match your system's configuration (default on Linux systems is /var/www/html)
# Change DB_NAME to match your wordpress database (default is 'wordpress')
# 

# Var definitions
TODAY=$(date +%Y%m%d)
WEBROOT=/var/www
DOCROOT=html
ARCHIVE=/data/backup/${DOCROOT}_${TODAY}.tar.gz
DB_NAME=wp
DB_ARCHIVE=/data/backup/${DB_NAME}_${TODAY}.sql.gz
MYSQLDUMP_ARGS=' --opt --single-transaction --routines --triggers --events --add-drop-database --add-drop-table --complete-insert --hex-blob '
BUCKET_NAME=maplebird-backups
DIR=`pwd`

# Create docroot archive
cd ${WEBROOT}
echo "Archiving wordpress directory at time " `date`
/bin/tar -czf ${ARCHIVE} ${DOCROOT}
cd ${DIR}
echo "Done archiving at time " `date`

# Create database SQL dump
echo "Archiving wordpress database at time " `date`
mysqldump ${MYSQLDUMP_ARGS} ${DB_NAME} | gzip | pv > ${DB_ARCHIVE}
echo "Done archiving at time " `date`

# Upload to S3
aws s3 cp ${ARCHIVE} s3://${BUCKET_NAME}/
aws s3 cp ${DB_ARCHIVE} s3://${BUCKET_NAME}/

# Show S3 bucket contents
aws s3 ls s3://${BUCKET_NAME}
