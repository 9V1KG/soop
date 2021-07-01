"""
Program using skyfield to predict optimal date and time
for ham radio satellite outdoor operation
"""

import datetime
import time
import re
import sys
from collections import namedtuple
import pytz
from skyfield.api import load, wgs84, Time
from timezonefinder import TimezoneFinder

Col = namedtuple(
    'color',
    ['red', 'green', 'yellow', 'blue', 'purple', 'cyan', 'bold', 'end']
)

COL = Col(red="\033[1;31;48m",
          green="\033[1;32;48m",
          yellow="\033[1;33;48m",
          blue="\033[1;34;48m",
          purple="\033[1;35;48m",
          cyan="\033[1;36;48m",
          bold="\033[1;37;48m",
          end="\033[1;37;0m"
          )

# Constants
EL_MIN = 10  # minimum elevation angle for satellite event
MIN_DUR = 3  # minimum duration for satellite event
QTH_DEF = "OJ11xi"  # default qth locator
SATS_DEF = [44909, 7530, 42759, 42761, 40903, 40906, 40910, 43803, 40908, 25544, 27607]
SATS_FM = [27607, 40931, 43678, 25544]


def get_key(item):
    """
    Needed for sorting sorted() the time list
    :param item:
    :return:
    """
    return item


def f_10_24(j: int) -> float:
    """
    Fractional resolution of latitude
    :param j: index of letter/number pair
    :return: calculated fractional degrees
    """
    return 10 ** (1 - int((j + 1) / 2)) * 24 ** int(-j / 2)


def maiden2latlon(loctr: str) -> tuple:
    """
    Calculates latitude, longitude in decimal degrees,
    centre of the field depending on resolution
    :param loctr: Maidenhead locator 4 up to 10 characters
    :return: lon, lat (dg decimal) or None, None (invalid input)
    """
    lon = lat = -90
    # check validity of input
    if not re.match(r"([A-Ra-r]{2}\d\d)(([A-Za-z]{2})(\d\d)?){0,2}", loctr):
        return None, None
    lets = re.findall(r'([A-Xa-x]{2})', loctr)  # all letter pairs
    nums = re.findall(r'(\d)(\d)', loctr)  # all number pairs
    vals = [(ord(x[0].upper()) - ord("A"),
             ord(x[1].upper()) - ord("A")) for x in lets]
    nums = [(int(x[0]), int(x[1])) for x in nums]
    pairs = [tuple] * (len(vals) + len(nums))  # prepare empty list
    pairs[::2] = vals  # letter value pairs 0, 2, 4 ...
    pairs[1::2] = nums  # number value pairs 1, 3, 5 ...
    for i, (x_1, x_2) in enumerate(pairs):
        lon += f_10_24(i) * x_1
        lat += f_10_24(i) * x_2
    lon *= 2
    lon += f_10_24(len(pairs)-1) / 2  # Centre of the field
    lat += f_10_24(len(pairs)-1) / 2
    return round(lat, 6), round(lon, 6)


def sat_track(geo_pos, dt_start, dt_end, cat_n):
    """
    Find events for a satellite with a specific catalogue number on given date
    Download TLE from celestrack and put results into global list timelist
    :param geo_pos: geo position of earth station
    :param dt_start: earliest datetime to start operation
    :param dt_end: latest datetime to finish operation
    :param cat_n: Norad catalogue number of satellite (int)
    :return: list of events for satellite with cat_n
    """
    ev_list = []
    url = 'https://celestrak.com/satcat/tle.php?CATNR={}'.format(cat_n)
    fname = 'tle-CATNR-{}.txt'.format(cat_n)
    t_aos = None
    time_sc = load.timescale()
    sats = load.tle_file(url, filename=fname)
    by_number = {sat.model.satnum: sat for sat in sats}
    satellite = by_number[cat_n]
    t_start = time_sc.from_datetime(dt_start)
    t_end = time_sc.from_datetime(dt_end)
    t_event, events = satellite.find_events(geo_pos, t_start, t_end, altitude_degrees=10.)
    for t_li, event in zip(t_event, events):
        # Convert time object to timestamp
        time_sc = datetime.datetime.timestamp(Time.utc_datetime(t_li))
        if event == 0:  # AOS
            t_aos = time_sc
        if event == 2 and t_aos is not None:  # LOS
            t_dur = int((time_sc - t_aos)/60)
            if t_dur > MIN_DUR:  # more than 3 minutes
                ev_list.append([t_aos, t_dur, satellite.name])
    return ev_list


def find_best_time(op_h: int, ev_sorted: list):
    """
    Loop through all events to find the optimal operation start time for h hours
    :param op_h: operation period in hours
    :param ev_sorted list of time sorted events for all satellites
    :return: itf, itl first and last index of satellite, best start time in UTC, duration in min
    """
    delta_t = datetime.timedelta(hours=op_h)
    tti = 0  # total time for
    ttd = 0  # total time duration
    itl = 0  # index of last sat to operate
    itf = 0  # index of first sat to operate
    m_sats = len(ev_sorted)
    for i_sat in range(0, m_sats):
        tmax = datetime.datetime.fromtimestamp(ev_sorted[i_sat][0]) + delta_t
        jtl = 0
        for j_sat in range(i_sat, m_sats):
            if datetime.datetime.fromtimestamp(ev_sorted[j_sat][0]) < tmax:
                tti += ev_sorted[j_sat][1]
                jtl += 1
        if tti > ttd:
            itf = i_sat
            itl = itf + jtl - 1
        ttd = max(ttd, tti)
        tti = 0
    return itf, itl, ev_sorted[itf][0], ttd


def check_tle(sat_list):
    """
    Check whether tle files need to be loaded and up-to-date
    Otherwise reload from celestrack
    :param sat_list: list of satellites with Norad catalogue numbers
    :return: void
    """
    for cat_nr in sat_list:
        url = 'https://celestrak.com/satcat/tle.php?CATNR={}'.format(cat_nr)
        fname = 'tle-CATNR-{}.txt'.format(cat_nr)
        sat = load.tle_file(url,reload=False, filename=fname)
        if not sat:
            print(f"{COL.red}Invalid Satellite list, "
                  f"no TLE data for catalogue no {cat_nr}{COL.end}")
            print(f"{COL.red}Please correct your list{COL.end}")
            sys.exit(1)
        tle_days = int(load.days_old(fname))
        if tle_days > 7:
            print("Some TLE data outdated, reloading from celestrack")
            sat = load.tle_file(url, reload=True, filename=fname)

def get_qth():
    """

    :return:
    """
    qthloc = QTH_DEF
    while True:
        line = input(f"QTH locator of operation ( 6 up to 10 alphanum.), default "
                     f"{COL.cyan}OJ11xi{COL.end}: ")
        if line == "":
            break
        if re.match(r"([A-Ra-r]{2}\d\d)(([A-Za-z]{2})(\d\d)?){0,2}", line):
            qthloc = line
            break
        print(f"{COL.red}Invalid input{COL.end}")
    return qthloc


def get_input():
    """
    Get input from user
    :return: qth locator, date of operation, start and end time, duration and days to be forecasted
    """
    valid_date = re.compile(r"[2][0][1-9]{2}-[0-9]{2}-[0-3][0-9]")
    valid_time = re.compile(r"[0-2][0-9]:[0-5][0-9]")
    dt_day = datetime.timedelta(days=1)  # tomorrow

    # defaults
    dte_start = (datetime.datetime.now() + dt_day).strftime("%Y-%m-%d")
    tme_start = "09:00"
    tme_end = "20:00"
    dur_op = 3
    days_fc = 1

    while True:
        line = input(f"1. Earliest date of operation, default "
                     f"{COL.cyan}tomorrow{COL.end} (YYYY-MM-DD): ")
        if line == "":
            break
        if re.match(valid_date, line):
            dte_start = re.match(valid_date, line)[0]
            break
        print(f"{COL.red}Invalid input{COL.end}")
    while True:
        line = input(f"2. Earliest time of operation, default "
                     f"{COL.cyan}09:00{COL.end} (hh:mm): ")
        if line == "":
            break
        if re.match(valid_time, line):
            tme_start = re.match(valid_time, line)[0]
            break
        print(f"{COL.red}Invalid input{COL.end}")
    while True:
        line = input(f"3. Latest time to finish operation, default "
                     f"{COL.cyan}22:00{COL.end} (hh:mm): ")
        if line == "":
            break
        if re.match(valid_time, line):
            tme_end = re.match(valid_time, line)[0]
            break
        print(f"{COL.red}Invalid input{COL.end}")
    while True:
        line = input(f"4. Max. duration of operation in hours, default "
                     f"{COL.cyan}3{COL.end}: ")
        if line == "":
            break
        if 0 < int(line) < 23:
            dur_op = int(line)
            break
        print(f"{COL.red}Invalid input{COL.end}")
    while True:
        line = input(f"5. Number of days to forecast (1-30), default "
                     f"{COL.cyan}1{COL.end}:")
        if line == "":
            break
        if 1 < int(line) < 31:
            days_fc = int(line)
            break
        print(f"{COL.red}Invalid input{COL.end}")
    return dte_start, tme_start, tme_end, dur_op, days_fc


def get_pc_timezone():
    """
    Print timezone of computer
    :return:
    """
    print(f"Computer Date and Time are set to UTC {COL.yellow}{time.tzname[0]}{COL.end}")
    return


def main():
    """
    Main program to forecast and find optimal time period for outdoor ham radio satellite operation
    :return: void
    """
    # Norad catalogue numbers
    my_sat_list = SATS_DEF
    #my_sat_list = SATS_FM
    tz_f = TimezoneFinder()  # initialize timezone finder
    get_pc_timezone()
    check_tle(my_sat_list)
    # Header output
    print(f"\n{COL.cyan}SOOP Satellite Outdoor Operation Planning for ham radio by 9V1KG{COL.end}")
    print("For defaults just press enter")

    # Input
    qth_loc = get_qth()
    lat, lon = maiden2latlon(qth_loc)
    tz_qth = tz_f.timezone_at(lng=lon, lat=lat)  # Timezone based on qth locator
    geo_pos = wgs84.latlon(lat, lon)  # Get geo_pos from qth locator
    qth_zone = pytz.timezone(tz_qth)
    ofs = qth_zone.localize(datetime.datetime.now()).utcoffset()
    print(f"Timezone based on QHT locator is {COL.yellow}{qth_zone}{COL.end}.",
          f"\nDate and Time are shown for this timezone, UTC offset is {ofs}\n")

    start_date_str, start_time_str, end_time_str, op_hours, fc_days = get_input()
    print()
    earliest_start_of_op_str = start_date_str + " " + start_time_str
    latest_start_of_op_str = start_date_str + " " + end_time_str
    # Local time (based on qth locator)
    fmt = "%Y-%m-%d %H:%M"
    earliest_start_of_op_loc \
        = qth_zone.localize(datetime.datetime.strptime(earliest_start_of_op_str, fmt))
    latest_start_of_op_loc \
        = qth_zone.localize(datetime.datetime.strptime(latest_start_of_op_str, fmt))
    # UTC
    earliest_start_of_op_utc = earliest_start_of_op_loc.astimezone(pytz.UTC)
    latest_start_of_op_utc = latest_start_of_op_loc.astimezone(pytz.UTC)

    # Loop through all days to be forecasted
    for fc_day in range(0, fc_days):
        fc_date_utc_start = earliest_start_of_op_utc + datetime.timedelta(days=fc_day)
        fc_date_utc_end = latest_start_of_op_utc + datetime.timedelta(days=fc_day)
        fc_date_loc = earliest_start_of_op_loc + datetime.timedelta(days=fc_day)
        # Loop through all satellites
        time_list = []
        for sat_nr in my_sat_list:
            # call function to find events
            evnts = sat_track(geo_pos, fc_date_utc_start, fc_date_utc_end, sat_nr)
            if evnts is not None:
                time_list.extend(evnts)
        # sort by timestamp
        tls_sorted = sorted(time_list, key=get_key)
        # Find optimal operation start time for the day
        res = find_best_time(op_hours, tls_sorted)

        # 0: index first sat 1: index last sat 2: AOS 3: duration 2: Satellite name
        print(f"On{COL.yellow}", str(fc_date_loc).split(" ", maxsplit=1)[0],f"{COL.end}",
              f"{len(tls_sorted)} satellites, "
              f"{COL.yellow}{res[1] - res[0] + 1}{COL.end} can be operated "
              f"within {op_hours} h, "
              f"starting at{COL.yellow} ",
              datetime.datetime.fromtimestamp(res[2]).astimezone(qth_zone).strftime("%H:%M:%S"),
              f"{COL.end},"
              f"total time:{COL.yellow} {res[3]} min{COL.end}")

        # list of satellites when forecast days is set to 1
        if fc_days == 1:
            for i_sl, ops in enumerate(tls_sorted):
                tobs = datetime.datetime.fromtimestamp(ops[0]).astimezone(qth_zone)
                if res[0] <= i_sl <= res[1]:
                    print(f"{COL.green}",
                          tobs.strftime('%H:%M:%S '),
                          tls_sorted[i_sl][2], ops[1], "min", f"{COL.end}")
                else:
                    print(f"{COL.end}",
                          tobs.strftime('%H:%M:%S '),
                          ops[2], ops[1], "min", f"{COL.end}")


if __name__ == '__main__':
    main()