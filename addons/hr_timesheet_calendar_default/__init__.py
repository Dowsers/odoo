# -*- coding: utf-8 -*-


def uninstall_hook(env):
    """ Restore the hr_timesheet sequence of the "My Timesheets" calendar view
    (see hr_timesheet/views/hr_timesheet_views.xml). """
    calendar_view = env.ref('hr_timesheet.act_hr_timesheet_line_view_calendar', raise_if_not_found=False)
    if calendar_view:
        calendar_view.sequence = 5
