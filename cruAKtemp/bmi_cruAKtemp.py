# -*- coding: utf-8 -*-
"""
bmi_cruAKtemp.py

Provides BMI access to netcdf files containg cruNCEP data for
monthly temperature values for Alaska

For use with Permamodel components

"""

import numpy as np
import os
import cruAKtemp

"""
class FrostnumberMethod( frost_number.BmiFrostnumberMethod ):
    _thisname = 'this name'
"""

class BmiCruAKtempMethod():



    def __init__(self):
        self._model = None
        self._values = {}
        self._var_units = {}
        self._grids = {}
        self._grid_type = {}

        self._name = 'CruAKtemp module'

        self._att_map = {
            'model_name':         'PermaModel_cruAKtemp',
            'version':            '0.1',
            'author_name':        'J. Scott Stewart',
            'grid_type':          'uniform_rectlinear',
            'time_step_type':     'fixed',
            'step_method':        'explicit',
            'comp_name':          'cruAKtemp',
            'model_family':       'PermaModel',
            'cfg_extension':      '_cruAKtemp_model.cfg',
            'time_units':         'days' }

        self._input_var_names = ()

        self._output_var_names = (
            'atmosphere_bottom_air__temperature',
        )

        self._var_name_map = {
            'atmosphere_bottom_air__temperature':        'T_air'
        }

        self._var_units_map = {
            'atmosphere_bottom_air__temperature':        'deg_C',
            'datetime__start':                           'days',
            'datetime__end':                             'days'}


    def initialize(self, cfg_file=None):
        self._model = cruAKtemp.CruAKtempMethod()

        self._model.initialize_from_config_file(cfg_filename=cfg_file)

        self._name = "Permamodel CRU-AK Temperature Component"

        # Verify that all input and output variable names are mapped
        for varname in self._input_var_names:
            assert(varname in self._var_name_map)
            assert(varname in self._var_units_map)
        for varname in self._output_var_names:
            assert(varname in self._var_name_map)
            assert(varname in self._var_units_map)

        # Set a unique grid number for each grid
        gridnumber = 0
        for varname in self._input_var_names:
            self._grids[gridnumber] = varname
            self._grid_type[gridnumber] = 'uniform_rectilinear'
            gridnumber += 1
        for varname in self._output_var_names:
            self._grids[gridnumber] = varname
            self._grid_type[gridnumber] = 'uniform_rectilinear'
            gridnumber += 1

        self._values = _values = {
        # These are the links to the model's variables and
        # should be consistent with _var_name_map
            'atmosphere_bottom_air__temperature': self._model.T_air,
            'datetime__start':                    self._model.first_date,
            'datetime__end':                      self._model.last_date}

        self._model.status = 'initialized'

    def get_attribute(self, att_name):

        try:
            return self._att_map[ att_name.lower() ]
        except:
            print '###################################################'
            print ' ERROR: Could not find attribute: ' + att_name
            print '###################################################'
            print ' '

    def get_input_var_names(self):
        return self._input_var_names

    def get_output_var_names(self):
        return self._output_var_names

    def get_start_time(self):
        # Currently, all models must start from timestep zero
        return np.float64(0)

    def get_var_name(self, long_var_name):
        return self._var_name_map[ long_var_name ]

    def get_var_units(self, long_var_name):
        return self._var_units_map[ long_var_name ]

    def get_current_time(self):
        return self._model.get_current_timestep()

    def get_end_time(self):
        return self._model.get_end_timestep()

    def get_time_units(self):
        return self._model._time_units

    def update(self):
        # Update the time
        self._model.update()

        # Set the bmi temperature to the updated value in the model
        self._values['atmosphere_bottom_air__temperature'] = \
                self._model.T_air

    def update_frac(self, time_fraction):
        """
        Model date is a floating point number of days.  This
        can be updated by fractional day, but update() will
        only be called if the integer value of the day changes
        """
        self._model.increment_date(
            change_amount=time_fraction * self._model._timestep)
        self._model.update_temperature_values()
        self._values['atmosphere_bottom_air__temperature'] = \
                self._model.T_air

    def update_until(self, stop_date):
        if stop_date < self._model.current_date:
            print("Warning: update_until date--%d--is less than current\
                  date--%d" % (stop_date, self._model.current_date))
            print("  no update run")
            return

        if stop_date > self._model._end_date:
            print("Warning: update_until date--%d" % stop_date)
            print("  was greater than end_date--%d." % self._model._end_date)
            print("  Setting stop_date to _end_date")
            stop_date = self._end_date

        # Run update() one timestep at a time until stop_date
        date = self._model.current_date
        while date < stop_date:
            self.update()
            date = self._model.current_date

    def finalize(self):
        SILENT = True

        self._model.status = 'finalizing'

        self._model.close_input_files()
        self._model.write_output_to_file(SILENT=True)
        self._model.close_output_files()

        self._model.status = 'finalized'

        if not SILENT:
            self._model.print_final_report(\
                    comp_name='Permamodel CruAKtemp component')

    def get_grid_type(self, grid_number):
        return self._grid_type[grid_number]

    def get_time_step(self):
        # Model keeps track of timestep as a timedelta
        # Here, find the seconds and divide by seconds/day
        # to get the number of days
        return self._model._timestep.total_seconds()/(24*60*60.0)

    def get_value_ref(self, var_name):
        return self._values[var_name]

    def set_value(self, var_name, new_var_values):
        self._values[var_name] = new_var_values

    def set_value_at_indices(self, var_name, new_var_values, indices):
        self.get_value_ref(var_name).flat[indices] = new_var_values

    def get_var_itemsize(self, var_name):
        return np.asarray(self.get_value_ref(var_name)).flatten()[0].nbytes

    def get_value_at_indices(self, var_name, indices):
        return self.get_value_ref(var_name).take(indices)

    def get_var_nbytes(self, var_name):
        return np.asarray(self.get_value_ref(var_name)).nbytes

    def get_value(self, var_name):
        return np.asarray(self.get_value_ref(var_name))


    def get_var_type(self, var_name):
        return str(self.get_value_ref(var_name).dtype)

    def get_component_name(self):
        return self._name

    def get_var_grid(self, var_name):
        for grid_id, var_name_list in self._grids.items():
            if var_name in var_name_list:
                return grid_id

    def get_grid_shape(self, grid_id):
        """Number of rows and columns of uniform rectilinear grid."""
        var_name = self._grids[grid_id]
        print("shape of {}".format(var_name))
        value = np.array(self.get_value_ref(var_name)).shape
        return value

    def get_grid_size(self, grid_id):
        grid_size = self.get_grid_shape(grid_id)
        if grid_size == ():
            return 1
        else:
            return int(np.prod(grid_size))

    def get_grid_rank(self, var_id):
        return len(self.get_grid_shape(self.get_var_grid(var_id)))
