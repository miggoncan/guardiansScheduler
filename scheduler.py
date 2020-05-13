import sys
import json
import logging
import calendar as calendarLib

try:
    from ortools.sat.python import cp_model
except ImportError:
    print('ERROR: Could not find module ortools. Try \'pip install ortools\'')
    sys.exit(1)


# If PRETTY_PRINT is True, the logged objects will be displayed in a 
# more human readable f
PRETTY_PRINT = True

LOG_LEVEL = logging.INFO

DOCTORS_FILE = 'doctors.json'
SHIFT_CONF_FILE = 'shiftConfs.json'
CALENDAR_FILE = 'calendar.json'

# This dict will be used to convert from a day str to its int 
# representation
WEEK_DAY = {
    'Monday': 0,
    'Tuesday': 1,
    'Wednesday': 2,
    'Thursday': 3,
    'Friday': 4,
    'Saturday': 5,
    'Sunday': 6
}

# This dict will be used to convert from the int representation of a
# weekday to its human readable f
DAY_NUM_TO_WEEK_DAY = {dayNum: weekdayName 
                        for weekdayName, dayNum in WEEK_DAY.items()}

# These variables are used to identify the BoolVars used in the CpModel
SHIFT = 's'
CONSULT = 'c'


# Configure the log for this module
# Note no handler is added. If this is the main module, it will be 
# configured in the main function
log = logging.getLogger(__name__)
log.setLevel(LOG_LEVEL)

# f will be the function called on objects that are logged
if PRETTY_PRINT:
    from pprint import pformat
    f = lambda obj: pformat(obj)
else:
    f = lambda obj: str(obj)


def getShiftPreferences(*, shiftConfs, dayConfs, keys, daysOfMonth):
    '''Obtain the shift preferences indicated by keys

    Day shift preferences indicated by dayConfs have higher preference
    than the ones indicated by shiftConfs

    Keyword Args:
        shiftConfs:
            A list of dicts representing the shift configuration of the 
            doctors. Each dict must have a 'doctorId' key whose value 
            is the id of the corresponding doctor, and both keys 
            indicated by the keyword argument 'keys'. The value of the 
            'keys' must be iterables of dicts, where each dict has to 
            have the key 'shift'. The value of each 'shift' is a day of 
            the week.

            Example: (suppose keys = ['wantedShifts', 'unwantedShifts'])

                [
                    {
                        'doctorId': 1,
                        'wantedShifts': [
                            {'shift': 'Monday'},
                            {'shift': 'Tuesday'}
                        ],
                        'unwantedShifts': [
                            {'shift': 'Friday'}
                        ]
                    },
                    {
                        'doctorId': 3,
                        'wantedShifts': [
                            {'shift': 'Thursday'}
                        ],
                        'unwantedShifts': []
                    },
                    {
                        'doctorId': 5,
                        'wantedShifts': [],
                        'unwantedShifts': [
                            {'shift': 'Wednesday'}
                        ]
                    },
                ]

        dayConfs:
            A list of dicts representing the configuration of each day
            of the month whose schedule is to be generated. Each dict
            must have both keys indicated by the keyword argument 
            'keys'. The value of the 'keys' must be an iterable of dict,
            where each dict has to have a pair 'id': int. The int is 
            the id of a doctor.

            The first element of the list should correspond with the
            configuration of the first day of the daysOfMonth list, the 
            second element with the configuration of the second day, 
            and so on.

            The list is assumed to have the same size as daysOfMonth

            Example: (suppose keys = ['wantedShifts', 'unwantedShifts'])

            [
                {
                    'wantedShifts': [
                        {'id': 1},
                        {'id': 3}
                    ],
                    'unwantedShifts': [
                        {'id': 5}
                    ]
                },
                {
                    'wantedShifts': [],
                    'unwantedShifts': [
                        {'id': 1}
                    ]
                },
                {
                    'wantedShifts': [
                        {'id': 3}
                    ],
                    'unwantedShifts': []
                },
                ...
            ]

        keys:
            A pair of str. Each str must represent a key of both 
            dayConfs and shiftConfs as described above.

            Example: ('wantedShifts', 'unwantedShifts')

        daysOnMonth:
            A list of datetime.date objects. Each date should be a day
            of the month whose shifts are being scheduled. The list 
            should contain one and exactly one date object for each day
            of the month.

            This list can be easily genetared as:
                daysOfMonth = [day 
                        for day in calendar.itermonthdates(year, month) 
                        if day.month == month]

            Where 'calendar' is an instance of calendar.Calendar, and
            year and month are ints. 
            
            Note the call above will return the days of the given month 
            in ascending order. This is, the first element will be a 
            date object represeting the first day of the month, the 
            second element will represent the second day of the month,
            and so on.

    Returns:
        A dictionary that will have an entry for each day of the month

        Each key will be a day of the month. E.g. 1, 2, 3, ...

        Each value will be a list of exactly two elements:
          - The first element will be a list of doctorIds, representing 
            the doctors who would have a keys[0] shift this day
          - The second element will be another list of doctorIds, 
            representing the doctors who would have a keys[1] shift 
            this day

        Example:
            {
                1: [[], [1, 3]],
                2: [[], []],
                3: [[], [5]],
                4: [[3], []],
                ...
             }

             If we supose keys was ('wantedShifts', 'unwantedShifts'),
             then this object means as follows:
                The doctors with id 1 and 3 would not like to have a 
                shift the first day of the month, the doctor with id 5
                would not like to have a shift the third day of the 
                month, and the doctor with id 3 would like to have a 
                shift the fourth day of the month
    '''
    log.info('Requested the shift preferences: {}'.format(keys))
    key1 =  keys[0]
    key2 = keys[1]

    log.debug('Getting shift preferences by week day')
    '''These two lists will contain an entry for each day of the week. 

    The first element of shifts1ByWeekDay is a list doctorIds 
    representing the doctors who would have their key1 shifts on 
    Mondays, the second element represents doctors who would have their 
    key1 shifts of Tuesdays, and so on. 

    (Idem for the corresponding key2 list)
    '''
    shifts1ByWeekDay = [[] for i in range(7)]
    shifts2ByWeekDay = [[] for i in range(7)]
    for shiftConf in shiftConfs:
        docId = shiftConf['doctorId']
        for shift1ByWeekDay in shiftConf[key1]:
            weekday = WEEK_DAY[shift1ByWeekDay['shift']]
            shifts1ByWeekDay[weekday].append(docId)
        for shift2ByWeekDay in shiftConf[key2]:
            weekday = WEEK_DAY[shift2ByWeekDay['shift']]
            shifts2ByWeekDay[weekday].append(docId)
    log.debug(f'{key1} by week day: {f(shifts1ByWeekDay)}')
    log.debug(f'{key2} by week day: {f(shifts2ByWeekDay)}')
    for i in range(7):
        intersection = set(shifts1ByWeekDay[i]) & set(shifts2ByWeekDay[i])
        if len(intersection) != 0:
            log.warn(('The doctors with id {} have selected the shifts on {} '
                + 'as both a {} and {}').format(f(intersection), 
                DAY_NUM_TO_WEEK_DAY[i], key1, key2))

    shiftPreferences = {}
    for day, dayConf in zip(daysOfMonth, dayConfs):
        log.debug('Getting shift preferences information for day {}'
            .format(day))

        weekday = day.weekday()
        log.debug('This day is {}'.format(DAY_NUM_TO_WEEK_DAY[weekday]))

        log.debug('Getting high priority shift preferences')
        shifts1HighPriority = [doctor['id'] for doctor in dayConf[key1]]
        shifts2HighPriority = [doctor['id'] for doctor in dayConf[key2]]
        log.debug('High priority {} are: {}'.format(key1, 
            f(shifts1HighPriority)))
        log.debug('High priority{} are: {}'.format(key2, 
            f(shifts2HighPriority)))

        intersection = set(shifts1HighPriority) & set(shifts2HighPriority)
        if (len(intersection) != 0):
            log.warn(('The doctors with id {intersection} have selected '
                + 'shift of the day {} as both a {} and {}')
                .format(intersection, day, key1, key2))

        log.debug('Filtering week day preferences according to high '
            + 'priority ones')
        shifts1Filtered = [docId for docId in shifts1ByWeekDay[weekday] 
            if docId not in shifts2HighPriority]
        shifts2Filtered = [docId for docId in shifts2ByWeekDay[weekday]
            if docId not in shifts1HighPriority]
        log.debug(f'{key1} after filtering is: {f(shifts1Filtered)}')
        log.debug(f'{key2} after filtering is: {f(shifts2Filtered)}')

        log.debug('Combining filtered shift preferences with high priority '
            + 'ones')
        shifts1Combined = list(set(shifts1Filtered) | set(shifts1HighPriority))
        shifts2Combined = list(set(shifts2Filtered) | set(shifts2HighPriority))
        log.debug(f'{key1} after combining is: {f(shifts1Combined)}')
        log.debug(f'{key2} after combining is: {f(shifts2Combined)}')

        shiftPreferences[day.day] = [
            shifts1Combined,
            shifts2Combined
        ]

    log.debug('The shift preferences are: {}'.format(f(shiftPreferences)))

    return shiftPreferences

def schedule():
    # First, read the data from the files
    with open(DOCTORS_FILE) as doctorsFile:
        doctors = json.loads(doctorsFile.read())
        log.debug('The doctors dict is: {}'.format(f(doctors)))
    with open(SHIFT_CONF_FILE) as shiftConfsFile:
        shiftConfs = json.loads(shiftConfsFile.read())
        log.debug('The shiftConfs dict is: {}'.format(f(shiftConfs)))
    with open(CALENDAR_FILE) as calendarFile:
        calendarDict = json.loads(calendarFile.read())
        log.debug('The calendar dict is: {}'.format(f(calendarDict)))

    year = calendarDict['year']
    month = calendarDict['month']
    log.info('Generating schedule for {}-{}'.format(year, month))

    # The list of dayConfigurations sorted by day number
    dayConfs = sorted(calendarDict['dayConfigurations'], 
                        key=lambda day: day['day'])
    log.debug('dayConfs after being sorted is {}'.format(f(dayConfs)))

    # The calendar object will be used to iterate over the days of a month
    calendar = calendarLib.Calendar()

    # The function itermonthdates will not only return the dates in the 
    # specified month, but also all days before the start of the month or 
    # after the end of the month that are required to get a complete week.
    # Each elemnt of daysOfMonth will be a datetime.date object
    daysOfMonth = [day for day in calendar.itermonthdates(year, month) 
                    if day.month == month]
    numDaysInMonth = len(daysOfMonth)
    log.debug('The days in this month are {}'.format(f(daysOfMonth)))

    if numDaysInMonth != len(dayConfs):
        errorMessage = ('The number of expected days for {}-{} is {}, but the '
            + 'number of days given was {}').format(year, month, 
            numDaysInMonth, len(dayConfs))
        log.error(errorMessage)
        log.error('Raising ValueError')
        raise ValueError(errorMessage)

    for day, dayConf in zip(daysOfMonth, dayConfs):
        if day.day != dayConf['day']:
            errorMessage = ('Missing the day {} in the day configurations of '
                + 'the calendar').format(day.day)
            log.error(errorMessage)
            log.error('Raising ValueError')
            raise ValueError(errorMessage)

    requests = getShiftPreferences(shiftConfs=shiftConfs, dayConfs=dayConfs, 
            keys=('wantedShifts', 'unwantedShifts'), daysOfMonth=daysOfMonth)
    log.info('Requested shifts are: {}'.format(f(requests)))

    required = getShiftPreferences(shiftConfs=shiftConfs, dayConfs=dayConfs, 
            keys=('mandatoryShifts', 'unavailableShifts'), 
            daysOfMonth=daysOfMonth)
    log.info('Required shifts are: {}'.format(f(required)))

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
        daynumber
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
    log.debug('The shiftVars are: {}'.format(f(shiftVars)))

def main():
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(name)s in '
        + '%(funcName)s\n\t%(message)s')
    schedule()


if __name__ == '__main__':
    main()