import sys
import json
import logging as log
import calendar as calendarLib

try:
    from ortools.sat.python import cp_model
except ImportError as e:
    print('ERROR: Could not find module ortools. Try \'pip install ortools\'')
    sys.exit(1)


PRETTY_PRINT = True

LOG_LEVEL = log.INFO

DOCTORS_FILE = 'doctors.json'
SHIFT_CONF_FILE = 'shiftConfs.json'
CALENDAR_FILE = 'calendar.json'

SHIFT = 's'
CONSULT = 'c'

WEEK_DAY = {
    'Monday': 0,
    'Tuesday': 1,
    'Wednesday': 2,
    'Thursday': 3,
    'Friday': 4,
    'Saturday': 5,
    'Sunday': 6
}

DAY_NUM_TO_WEEK_DAY = {dayNum: weekdayName for weekdayName, dayNum in WEEK_DAY.items()}

# Format will be the function called on objects that are logged
if PRETTY_PRINT:
    from pprint import pformat
    format = lambda obj: pformat(obj)
else:
    format = lambda obj: str(obj)

log.basicConfig(level=LOG_LEVEL)


# First, read the data from the files
with open(DOCTORS_FILE) as f:
    doctors = json.loads(f.read())
    log.debug(f'The doctors dict is: {format(doctors)}')
with open(SHIFT_CONF_FILE) as f:
    shiftConfs = json.loads(f.read())
    log.debug(f'The shiftConfs dict is: {format(shiftConfs)}')
with open(CALENDAR_FILE) as f:
    calendarDict = json.loads(f.read())
    log.debug(f'The calendar dict is: {format(calendarDict)}')

year = calendarDict['year']
month = calendarDict['month']
log.info(f'Generating schedule for {month}/{year}')

# The list of dayConfigurations sorted by day number
dayConfs = sorted(calendarDict['dayConfigurations'], key=lambda day: day['day'])
log.debug(f'dayConfs after being sorted is {dayConfs}')


'''These two lists will contain an entry for each day of the week. 

The first element is a list doctorIds representing the doctors who would
like to have their shifts on Mondays, the second element represent 
doctors who would like to have their shifts of Tuesdays, and so on
'''
shiftsWanted = [[] for i in range(7)]
shiftsNotWanted = [[] for i in range(7)]
for shiftConf in shiftConfs:
    docId = shiftConf['doctorId']
    for wantedShifts in shiftConf['wantedShifts']:
        weekday = WEEK_DAY[wantedShifts['shift']]
        shiftsWanted[weekday].append(docId)
    for unwantedShifts in shiftConf['unwantedShifts']:
        weekday = WEEK_DAY[unwantedShifts['shift']]
        shiftsNotWanted[weekday].append(docId)
log.debug(f'shiftsWanted: {format(shiftsWanted)}')
log.debug(f'shiftsNotWanted: {format(shiftsNotWanted)}')
for i in range(7):
    intersection = set(shiftsWanted[i]) & set(shiftsNotWanted[i])
    if len(intersection) != 0:
        log.warn(f'The doctors with id {intersection} have selected the shifts'
            + f' on {DAY_NUM_TO_WEEK_DAY[i]} as both a wanted and unwanted shift')


# The calendar object will be used to iterate over the days of a month
calendar = calendarLib.Calendar()

# monthrange returns a tuple (dayOfWeek, numDaysInMonth)
numDaysInMonth = calendarLib.monthrange(year, month)[1]

'''requests is a list that will have an entry for each day of the month

The element 0 of the list corresponds to the first day of the month, the
element 1 corresponds to the second day, and so on

Each entry will be a list of exactly two elements:
  - The first element will be a list of doctorIds, representing the 
    doctors who would like to have one of their shifts this day
  - The second element will be another list of doctorIds, representing 
    the doctors who would like to NOT have one of their shifts this day
'''
requests = [[[], []] for i in range(numDaysInMonth)]
# The functin itermonthdates will not only return the dates in the 
# specified month, but also all days before the start of the month or 
# after the end of the month that are required to get a complete week.
daysOfMonth = [day for day in calendar.itermonthdates(year, month) if day.month == month]
for day, dayConf in zip(daysOfMonth, dayConfs):
    log.debug(f'Getting requests information for day {day}')

    weekday = day.weekday()
    log.debug(f'This day is {DAY_NUM_TO_WEEK_DAY[weekday]}')

    highPriorityWantedShifts = [doctor['id'] for doctor in dayConf['wantedShifts']]
    highPriorityUnwantedShifts = [doctor['id'] for doctor in dayConf['unwantedShifts']]
    log.debug(f'highPriorityWantedShifts is: {format(highPriorityWantedShifts)}')
    log.debug(f'highPriorityUnwantedShifts is: {format(highPriorityUnwantedShifts)}')

    intersection = set(highPriorityWantedShifts) & set(highPriorityUnwantedShifts)
    if (len(intersection) != 0):
        log.warn(f'The doctors with id {intersection} have selected shift of '
            + f'the day {day} as both a wanted and unwanted shift')

    # A shift preference specified in the dayConf has higher priority 
    # than a shift preference specified in a doctor's shiftConfiguration
    wantedShiftsAfterPriority = [docId for docId in shiftsWanted[weekday] 
        if docId not in highPriorityUnwantedShifts]
    unwantedShiftsAfterPriority = [docId for docId in shiftsNotWanted[weekday]
        if docId not in highPriorityWantedShifts]
    log.debug(f'wantedShiftsAfterPriority is: {format(wantedShiftsAfterPriority)}')
    log.debug(f'unwantedShiftsAfterPriority is: {format(unwantedShiftsAfterPriority)}')

    log.debug('Combining filtered shift preferences with high priority ones')
    wantedShiftsAfterPriority = list(set(wantedShiftsAfterPriority) 
        | set(highPriorityWantedShifts))
    unwantedShiftsAfterPriority = list(set(unwantedShiftsAfterPriority) 
        | set(highPriorityUnwantedShifts))
    log.debug(f'wantedShiftsAfterPriority is: {format(wantedShiftsAfterPriority)}')
    log.debug(f'unwantedShiftsAfterPriority is: {format(unwantedShiftsAfterPriority)}')

    requests[day.day - 1] = [
        wantedShiftsAfterPriority,
        unwantedShiftsAfterPriority
    ]
log.info(f'Requests for shifts are: {format(requests)}')

model = cp_model.CpModel()

'''shiftVars is a dictionary that will contain the BoolVars used in the 
model.

The keys of the dictionary will be tuples as (doctorId, dayNumber)

The values of the dictionary will be lists of size 1 or 2:
  - The first element of the list will always be a BoolVar that 
    represents whether the doctor with id doctorId has a shift the day
    dayNumber
  - The second element is optinal. It will only be present if the doctor
    doesConsultations. In that case, the element will be another BoolVar
    that will represent whether the doctor has consultations this 
    dayNumber
'''
shiftVars = {}
for shiftConf in shiftConfs:
    for dayConf in dayConfs:
        if dayConf['isWorkingDay']:
            docId = shiftConf['doctorId']
            dayNum = dayConf['day']
            doctorVars = []
            doctorVars.append(
                model.NewBoolVar(f'shift_doc{docId}_day{dayNum}_{SHIFT}')
            )
            if shiftConf['doesConsultations']:
                doctorVars.append(
                    model.NewBoolVar(f'shift_doc{docId}_day{dayNum}_{CONSULT}')
                )
            shiftVars[docId, dayNum] = doctorVars
log.debug(f'The shiftVars are: {format(shiftVars)}')