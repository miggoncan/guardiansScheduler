import json
from pathlib import Path
import logging
import logging.config

import scheduler

# The first parent refest to the src dir
SCHEDULER_DIR = Path(__file__).parent.parent

LOGGING_CONFIG_FILE = SCHEDULER_DIR / 'config/logging.json'

DOCTORS_FILE = SCHEDULER_DIR / 'tmp/doctors.json'
SHIFT_CONF_FILE = SCHEDULER_DIR / 'tmp/shiftConfs.json'
CALENDAR_FILE = SCHEDULER_DIR / 'tmp/calendar.json'

def main():
    with LOGGING_CONFIG_FILE.open() as loggingConfFile:
        loggingConf = json.loads(loggingConfFile.read())
        logging.config.dictConfig(loggingConf)

    log = logging.getLogger('main')

    # First, read the data from the files
    with DOCTORS_FILE.open() as doctorsFile:
        doctors = json.loads(doctorsFile.read())
        log.debug('The doctors dict is: {}'.format(doctors))
    with SHIFT_CONF_FILE.open() as shiftConfsFile:
        shiftConfs = json.loads(shiftConfsFile.read())
        log.debug('The shiftConfs dict is: {}'.format(shiftConfs))
    with CALENDAR_FILE.open() as calendarFile:
        calendarDict = json.loads(calendarFile.read())
        log.debug('The calendar dict is: {}'.format(calendarDict))
    scheduler.schedule(doctors, shiftConfs, calendarDict)


if __name__ == '__main__':
    main()