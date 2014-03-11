import datetime

from .converter import WaypointStyles


class Writer:
    """
    A writer for SeeYou CUP files. Supports waypoints and tasks::

        with open('competition.cup', 'w') as fp:
            writer = Writer(fp)
    """

    HEADER = 'name,code,country,lat,lon,elev,style,rwdir,rwlen,freq,desc'
    DIVIDER = '-----Related Tasks-----'

    DISTANCE_FORMAT_FLOAT = '%.1f%s'
    DISTANCE_FORMAT_INT = '%d%s'
    DISTANCE_FORMAT_OTHER = '%s%s'

    def __init__(self, fp):
        self.fp = fp
        self.wps = set()
        self.in_task_section = False

        self.write_line(self.HEADER)

    def escape(self, field):
        if not field:
            return ''

        return '"%s"' % field.replace('\\', '\\\\').replace('"', '\\"')

    def format_coordinate(self, value, is_latitude=True):
        if is_latitude:
            if not -90 <= value <= 90:
                raise ValueError('Invalid latitude: %s' % value)

            hemisphere = 'S' if value < 0 else 'N'
            format = '%02d%06.3f%s'

        else:
            if not -180 <= value <= 180:
                raise ValueError('Invalid longitude: %s' % value)

            hemisphere = 'W' if value < 0 else 'E'
            format = '%03d%06.3f%s'

        value = abs(value)
        degrees = int(value)
        minutes = (value - degrees) * 60
        return format % (degrees, minutes, hemisphere)

    def format_latitude(self, value):
        return self.format_coordinate(value, is_latitude=True)

    def format_longitude(self, value):
        return self.format_coordinate(value, is_latitude=False)

    def format_distance(self, distance):
        if distance is None or distance == '':
            return ''

        if isinstance(distance, tuple):
            unit = distance[1]
            distance = distance[0]
        else:
            unit = 'm'

        if isinstance(distance, float):
            return self.DISTANCE_FORMAT_FLOAT % (distance, unit)
        elif isinstance(distance, int):
            return self.DISTANCE_FORMAT_INT % (distance, unit)
        else:
            return self.DISTANCE_FORMAT_OTHER % (distance, unit)

    def format_time(self, time):
        if isinstance(time, datetime.datetime):
            time = time.time()

        if isinstance(time, datetime.time):
            time = time.strftime('%H:%M:%S')

        return time

    def format_timedelta(self, timedelta):
        if isinstance(timedelta, datetime.timedelta):
            hours, remainder = divmod(timedelta.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            timedelta = '%02d:%02d:%02d' % (hours, minutes, seconds)

        return timedelta

    def write_line(self, line=''):
        self.fp.write(line + '\r\n')

    def write_fields(self, fields):
        self.write_line(','.join(fields))

    def write_waypoint(
            self, name, shortname, country, latitude, longitude, elevation='',
            style=WaypointStyles.NORMAL, runway_direction='', runway_length='',
            frequency='', description=''):

        """
        Write a waypoint::

            writer.write_waypoint(
                'Meiersberg',
                'MEIER',
                'DE',
                (51 + 7.345 / 60.),
                (6 + 24.765 / 60.),
            )
            # -> "Meiersberg","MEIER",DE,5107.345N,00624.765E,,1,,,,

        :param name: name of the waypoint (must not be empty)
        :param shortname: short name for depending GPS devices
        :param country: IANA top level domain country code (see
            http://www.iana.org/cctld/cctld-whois.htm)
        :param latitude: latitude of the point (between -90 and 90 degrees)
        :param longitude: longitude of the point (between -180 and 180 degrees)
        :param elevation: elevation of the waypoint in meters or as (elevation,
            unit) tuple
        :param style: the waypoint type (see official specification for the
            list of valid styles, defaults to "Normal")
        :param runway_direction: heading of the runway in degrees if the
            waypoint is landable
        :param runway_length: length of the runway in meters or as (length,
            unit) tuple if the waypoint is landable
        :param frequency: radio frequency of the airport
        :param description: optional description of the waypoint (no length
            limit)
        """

        if self.in_task_section:
            raise RuntimeError('Waypoints must be written before any tasks')

        if not name:
            raise ValueError('Waypoint name must not be empty')

        fields = [
            self.escape(name),
            self.escape(shortname),
            country,
            self.format_latitude(latitude),
            self.format_longitude(longitude),
            self.format_distance(elevation),
            str(style),
            str(runway_direction),
            self.format_distance(runway_length),
            self.escape(frequency),
            self.escape(description),
        ]

        self.write_fields(fields)

        self.wps.add(name)

    def write_task(self, description, waypoints):

        """
        Write a task definition::

            writer.write_task('500 km FAI', [
                'MEIER',
                'BRILO',
                'AILER',
                'MEIER',
            ])
            # -> "500 km FAI","MEIER","BRILO","AILER","MEIER"

        Make sure that the referenced waypoints have been written with
        :meth:`~aerofiles.seeyou.Writer.write_waypoint` before writing the
        task. The task section divider will be written to automatically when
        :meth:`~aerofiles.seeyou.Writer.write_task` is called the first time.
        After the first task is written
        :meth:`~aerofiles.seeyou.Writer.write_waypoint` must not be called
        anymore.

        :param description: description of the task (may be blank)
        :param waypoints: list of waypoints in the task (names must match the
            long names of previously written waypoints)
        """

        if not self.in_task_section:
            self.write_line()
            self.write_line(self.DIVIDER)
            self.in_task_section = True

        fields = [self.escape(description)]

        for waypoint in waypoints:
            if waypoint not in self.wps:
                raise ValueError('Waypoint "%s" was not found' % waypoint)

            fields.append(self.escape(waypoint))

        self.write_fields(fields)

    def write_task_options(self, **kw):

        """
        Write an options line for a task definition::

            writer.write_task_options(
                start_time=time(12, 34, 56),
                task_time=timedelta(hours=1, minutes=45, seconds=12),
                waypoint_distance=False,
                distance_tolerance=(0.7, 'km'),
                altitude_tolerance=300.0,
            )
            # -> Options,NoStart=12:34:56,TaskTime=01:45:12,WpDis=False,NearDis=0.7km,NearAlt=300.0m

        :param start_time: opening time of the start line as
            :class:`datetime.time` or string
        :param task_time: designated time for the task as
            :class:`datetime.timedelta` or string
        :param waypoint_distance: task distance calculation (``False``: use
            fixes, ``True``: use waypoints)
        :param distance_tolerance: distance tolerance in meters or as
            (distance, unit) tuple
        :param altitude_tolerance: altitude tolerance in meters or as
            (distance, unit) tuple
        :param min_distance: "uncompleted leg (``False``: calculate maximum
            distance from last observation zone)"
        :param random_order: if ``True``, then Random order of waypoints is
            checked
        :param max_points: maximum number of points
        :param before_points: number of mandatory waypoints at the beginning.
            ``1`` means start line only, ``2`` means start line plus first
            point in task sequence (Task line).
        :param after_points: number of mandatory waypoints at the end. ``1``
            means finish line only, ``2`` means finish line and one point
            before finish in task sequence (Task line).
        :param bonus: bonus for crossing the finish line
        """

        if not self.in_task_section:
            raise RuntimeError(
                'Task options have to be written in task section')

        fields = ['Options']

        if 'start_time' in kw:
            fields.append('NoStart=' + self.format_time(kw['start_time']))

        if 'task_time' in kw:
            fields.append('TaskTime=' + self.format_timedelta(kw['task_time']))

        if 'waypoint_distance' in kw:
            fields.append('WpDis=%s' % kw['waypoint_distance'])

        if 'distance_tolerance' in kw:
            fields.append('NearDis=' +
                self.format_distance(kw['distance_tolerance']))

        if 'altitude_tolerance' in kw:
            fields.append('NearAlt=' +
                self.format_distance(kw['altitude_tolerance']))

        if 'min_distance' in kw:
            fields.append('MinDis=%s' % kw['min_distance'])

        if 'random_order' in kw:
            fields.append('RandomOrder=%s' % kw['random_order'])

        if 'max_points' in kw:
            fields.append('MaxPts=%d' % kw['max_points'])

        if 'before_points' in kw:
            fields.append('BeforePts=%d' % kw['before_points'])

        if 'after_points' in kw:
            fields.append('AfterPts=%d' % kw['after_points'])

        if 'bonus' in kw:
            fields.append('Bonus=%d' % kw['bonus'])

        self.write_fields(fields)
