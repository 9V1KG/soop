# Soop
Satellite Operation Outdoor Planning for ham radio by 9V1KG

The program calculates the optimal time slot during a day to work as many as possible ham radio satellites. 
Based on your QTH locator and a list of preferred satellites (Norad catalogue numbers), the program 
calculates a forecast of satellite passes over the coming 1 to 30 days. TLE data are automatically 
loaded or updated from celestrak.
Within the forecasted period the best operation day and timeslot is found, and the maximum possible operation time shown.

# Input
1. QTH locator of the planned operation
2. Earliest date of operation (default: next day)
3. Earliest time of operation (default: 9:00)
4. Latest time to finish operation (default: 22:00)
5. Maximum duration of operation in hours (default: 3 h)
6. Number of days to forecast (1 to 30, default: 1 day)

Based on the QTH locator the geographic position and timezone is found. 
All times entered and displayed refer to this timezone.

# Output
When the number of days to forecast is set to 1, the following information is displayed:
1. Number of total satellite passes during the day
2. Number of satellites which can be worked within the given operation time
3. Start time of operation
4. Total satellites' communication time
This is followed by the list of all satellite names, with the workable satellites within the operation period displayed in green.

# Installation and Dependencies
You need to install pytz, skyfield and timezonefinder

    pip install pytz
    pip install skyfield
    pip install timezonefinder

During the first run, the program will download and save the necessary tle files.
This can take a while, until the process is completed.
