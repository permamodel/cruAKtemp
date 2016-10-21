# -*- coding: utf-8 -*-
"""
cruAKtemp.py

Reads average monthly temperature in Alaska from an upscaled version of
CRU NCEP data for Alaska
"""

import numpy as np
#from cruAKtemp.tests import examples_directory, data_directory
from .tests import examples_directory, data_directory
import cruAKtemp
import bmi_cruAKtemp
import os
import yaml
from nose.tools import (assert_is_instance, assert_greater_equal,
                        assert_less_equal, assert_almost_equal,
                        assert_greater, assert_in, assert_true,
                        assert_equal)
from scipy.io.netcdf import NetCDFFile as Dataset
import datetime

def assert_between(value, minval, maxval):
    """Fail if value is not between minval and maxval"""
    assert_greater_equal(value, minval)
    assert_less_equal(value, maxval)

class CruAKtempMethod():
    def __init__(self):
        self._cru_temperature_nc_filename = None  # Name of input netcdf file
        self._cru_temperature_nc_filename_default = \
                os.path.join(data_directory, "cruAKtemp.nc")
                                # Default name of input netcdf file
        self._cru_temperature_ncfile = None       # netCDF file handle
        self._cru_temperature = None # This will point to the nc file data
        self._current_date = None # Current num days since _start_date
        self._status = None       # Current state of the model
        self._start_date = None   # Real date of start of model run
        self._end_date = None     # Date on which model run ends
        self._date_at_timestep0 = None  # this could be overwritten with set()
        self._latitude = None # Will point to this model's latitude grid
        self._longitude = None # Will point to this model's longitude grid
        self._temperature = None # Will point to this model's temperature grid
        self.T_air = None        # Temperature grid

    def verify_config_for_uniform_rectilinear_run(self, cfg):
        # Ensure that all necessary variables exist 
        # for uniform_rectilinear grid type

        # Need at least one grid
        assert_greater_equal(len(cfg['grids']), 1)

        # All grids need a valid data type
        # name is a string, type is a type
        for k, v in cfg['grids'].iteritems():
            assert_true(isinstance(k, str))
            # Actually, I don't think this assertion tests the right thing
            assert_true(isinstance(type(v), type))

        # Grid shape can be used to create a numpy array
        assert_true(isinstance(cfg['grid_shape'], tuple))
        try:
            test_array = np.zeros(cfg['grid_shape'], dtype=np.uint8)
        except:
            print("Grid shape can't be used for numpy array: %s" % \
                  str(cfg['grid_shape']))
            raise

    def get_config_from_yaml_file(self, cfg_filename):
        cfg_struct = None
        try:
            with open(cfg_filename, 'r') as cfg_file:
                cfg_struct = yaml.load(cfg_file)
        except:
            print("\nError opening configuration file in\
                  initialize_from_config_file()")
            raise

        return cfg_struct

    def verify_run_type_parameters(self, cfg_struct):
        # There should be a separate verify_config_for_<gridtype>_run()
        # routine for each type of grid
        try:
            exec("self.verify_config_for_%s_run(cfg_struct)" %
                cfg_struct['grid_type'])
        except:
            raise

    def verify_temperature_netcdf_for_region_resolution(self, cfg_struct):
        try:
            if 'lowres' == cfg_struct['run_resolution'] and \
            'Alaska' == cfg_struct['run_region']:
                return os.path.join(data_directory,
                                    'cru_alaska_lowres_temperature.nc')
        except:
            # Likely a KeyError because missing a region or resolution
            raise

        raise ValueError("Combination of run_region '%s' and run_resolution '%s' not recognized" % \
                         (cfg_struct['run_region'],\
                          cfg_struct['run_resolution']))


    def i_nc_from_i(self, i, inverse=False, check_bounds=False):
        """Convert model's i-index to cru file's index
        Input: i  the i-coordinate of the model grid
        Output: i_nc  the coordinate in the netcdf grid
        inverse: if True, reverse the Input and Outpu
        check_bounds: if True, verify that all values are valid
        """
        if not inverse:
            if check_bounds:
                assert_between(i, 0, self._grid_shape[0]-1)
            i_nc = self._nc_i0 + i * self._nc_iskip
            if check_bounds:
                assert_between(i_nc, 0, self._nc_xdim)
            return i_nc
        else:
            i_nc = i
            if check_bounds:
                assert_between(i_nc, 0, self._nc_xdim)
            i = (i_nc - self.nc_i0)/self._nc_iskip
            if check_bounds:
                assert_between(i, 0, self._grid_shape[0]-1)
            return i

    def j_nc_from_j(self, j, inverse=False, check_bounds=False):
        """Convert model's j-index to cru file's index
        Input: j  the j-coordinate of the model grid
        Output: j_nc  the coordinate in the netcdf grid
        inverse: if True, reverse the Input and Outpu
        check_bounds: if True, verify that all values are valid
        """
        if not inverse:
            if check_bounds:
                assert_between(j, 0, self._grid_shape[1]-1)
            j_nc = self._nc_j0 + j * self._nc_jskip
            if check_bounds:
                assert_between(j_nc, 0, self._nc_xdim)
            return j_nc
        else:
            j_nc = j
            if check_bounds:
                assert_between(j_nc, 0, self._nc_ydim)
            j = (j_nc - self.nc_j0)/self._nc_jskip
            if check_bounds:
                assert_between(j, 0, self._grid_shape[1]-1)
            return j

    def initialize_from_config_file(self, cfg_filename=None):
        self.status     = 'initializing'
        cfg_struct = None

        # Set the cfg file if it exists, otherwise, a default
        if not cfg_filename:
           # No config file specified, use a default
           cfg_filename = os.path.join(examples_directory,
                                   'default_temperature.cfg')

        cfg_struct = self.get_config_from_yaml_file(cfg_filename)

        # Verify that the parameters are correct for the grid type
        self.verify_run_type_parameters(cfg_struct)

        # Get the temperature netcdf file name
        self._cru_temperature_nc_filename = \
                self.verify_temperature_netcdf_for_region_resolution(cfg_struct)

        # Initialize the time variables
        try:
            # From config
            self._timestep = cfg_struct['timestep']
            self.first_date = cfg_struct['model_start_date']
            # This could be set externally, eg by WMT
            if self._date_at_timestep0 is None:
                self._date_at_timestep0 = self.first_date
            self.last_date = cfg_struct['model_end_date']
            self._first_valid_date = cfg_struct['dataset_start_date']
            self._last_valid_date = cfg_struct['dataset_end_date']

            # Ensure that model dates are okay
            assert_between(self._date_at_timestep0,
                           self._first_valid_date, self._last_valid_date)
            assert_between(self.first_date,
                           self._first_valid_date, self._last_valid_date)
            assert_between(self.last_date,
                           self._first_valid_date, self._last_valid_date)

            # Initial calculations, assuming units of days
            self._current_date = self._date_at_timestep0
            self._first_timestep = self.timestep_from_date(self.first_date)
            self._last_timestep = self.timestep_from_date(self.last_date)
            self._current_timestep = self._first_timestep
        except:
            raise

        # Allocate the grids
        self._grid_shape = cfg_struct['grid_shape']
        for g in cfg_struct['grids']:
            grid_assignment_string = \
                    "self.%s_grid = np.zeros(%s, dtype=%s)" % \
                    (g, self._grid_shape, cfg_struct['grids'][g])
                    #(g, cfg_struct['grid_shape'], cfg_struct['grids'][g])
            exec(grid_assignment_string)

        # Allocate the lat and lon arrays to what the temperature grid is
        #self._latitude = np.zeros(self._grid_shape, np.float)
        #self._longitude = np.zeros(self._grid_shape, np.float)
        #self._latitude = np.zeros(cfg_struct['grid_shape'], np.float)
        #self._longitude = np.zeros(cfg_struct['grid_shape'], np.float)

        # Open the netcdf files
        self._cru_temperature_ncfile = \
            Dataset(self._cru_temperature_nc_filename, 'r', mmap=True)
        assert_true(self._cru_temperature_ncfile is not None)

        # Set the netcdf offset arrays
        # This should eventually be done non-manually
        self._nc_i0 = cfg_struct['i_ul']
        self._nc_j0 = cfg_struct['j_ul']
        try:
            self._nc_iskip = cfg_struct['i_skip']
        except KeyError:
            self._nc_iskip = 1
        try:
            self._nc_iskip = cfg_struct['j_skip']
        except KeyError:
            self._nc_jskip = 1

        # Calculate the end points
        #self._nc_i1 = self._nc_i0 + self._nc_iskip * self._grid_shape[0]
        #assert_equal(self._nc_i1, self.i_nc_from_i(self._grid_shape[0]))
        self._nc_i1 = self.i_nc_from_i(self._grid_shape[0])
        self._nc_j1 = self.j_nc_from_j(self._grid_shape[1])

        # Read in the latitude and longitude arrays
        nc_latitude = self._cru_temperature_ncfile.variables['lat']
        self._latitude = \
            np.asarray(nc_latitude[self._nc_j0:self._nc_j1:self._nc_jskip,
            self._nc_i0:self._nc_i1:self._nc_iskip]).astype(np.float32)
        nc_longitude = self._cru_temperature_ncfile.variables['lon']
        self._longitude = \
            np.asarray(nc_longitude[self._nc_j0:self._nc_j1:self._nc_jskip,
            self._nc_i0:self._nc_i1:self._nc_iskip]).astype(np.float32)

        # If the variables that point to the netcdfile's variables
        # aren't independently closed, then a RuntimeWarning will be raised
        # when the program ends or thenetcdf file is closed
        nc_latitude = None
        nc_longitude = None

        #self._latitude.tofile("test_latitude.dat")
        #self._longitude.tofile("test_longitude.dat")

        # Read initial data
        # Set the temperature file data to a variable
        # Note: This is probably fine for a small file, but it may not be
        # the best way to read from files that are several GB in size
        nc_temperature = self._cru_temperature_ncfile.variables['temp']
        self._temperature = \
            np.asarray(nc_temperature[:,
            self._nc_j0:self._nc_j1:self._nc_jskip,
            self._nc_i0:self._nc_i1:self._nc_iskip]).astype(np.float32)
        # Deduce the model xdim and ydim from the size of this array
        self._nc_tdim = nc_temperature.shape[0]
        self._nc_ydim = nc_temperature.shape[1]
        self._nc_xdim = nc_temperature.shape[2]

        nc_temperature = None

        # Set the T_air values--which are the "model results--
        # from the _temperature[] grid--which is the full lowres dataset
        self.update_temperature_values()

        # Close the netcdf file
        # Note: this will need to change if reading larger files and
        # accessing data from the files as time goes on
        self._cru_temperature_ncfile.close()
        self._cru_temperature_ncfile = None

    def timestep_from_date(self, this_date):
        """Return the timestep from a date
        Note: assumes that the model's time values have been initialized
        """
        this_timestep  = (this_date - self._date_at_timestep0).days / \
                    self._timestep.days
        return this_timestep

    def increment_date(self, change_amount):
        """Change the current date by a timedelta amount
        and update the timestep to reflect that change
        """
        # Ensure that we've got a timedelta amount
        assert_equal(type(change_amount), type(datetime.timedelta(days=1)))

        self._current_date += change_amount
        self._current_timestep = self.timestep_from_date(self._current_date)

    def update_temperature_values(self):
        """Update the temperature array values based on the current date"""
        # Note: in the future, we may want to do this from an open handle
        # to the netcdf file instead of from the 'fully read-in' 
        # _temperature grid

        # For the cru temperature grid, the first time corresponds to dates
        # in January, 1901
        model_year0 = 1901

        current_year = self._current_date.year
        current_month = self._current_date.month

        this_index = current_month + 12 *(current_year - model_year0) - 1

        self.T_air = self._temperature[this_index, :, :]
        #self.T_air.tofile("test_T_air.dat")

    def read_config_file(self):
        # Open CFG file to read data
        cfg_unit = open( self.cfg_file, 'r' )
        last_var_name = ''

        while (True):
            line  = cfg_unit.readline()
            if (line == ''):
                break                  # (reached end of file)

            # Comments are lines that start with '#'
            COMMENT = (line[0] == '#')

            # Columns are delimited by '|'
            words   = line.split('|')

            # Only process non-comment lines with exactly 4 words
            # Note: the 4th word describes the variable, and is ignored
            if (len(words) == 4) and not(COMMENT):
                var_name = words[0].strip()
                value    = words[1].strip()
                var_type = words[2].strip()

                READ_SCALAR   = False
                READ_FILENAME = False

                # Does var_name end with an array subscript ?
                p1 = var_name.rfind('[')
                p2 = var_name.rfind(']')
                if (p1 > 0) and (p2 > p1):
                    var_base  = var_name[:p1]
                    subscript = var_name[p1:p2+1]
                    var_name_file_str = var_base + '_file' + subscript
                else:
                    var_base = var_name
                    var_name_file_str = var_name + '_file'

                # if the immediately preceding line describes this variables's
                # type, change the type of this variable
                if (last_var_name.startswith(var_base + '_type')):
                    exec( "type_choice = self." + last_var_name )
                    if (type_choice.lower() == 'scalar'):
                        exec( "self." + var_name_file_str + " = ''")
                        READ_SCALAR = True
                    else:
                        exec( "self." + var_name + " = 0.0")
                        READ_FILENAME = True

                #-----------------------------------
                # Read a value of type "var_type"
                #-----------------------------------
                # Convert scalars to numpy scalars
                #-----------------------------------
                if (var_type in ['float64', 'np.float64']):
                    value = np.float64( value )
                    exec( "self." + var_name + " = value" )
                elif (var_type in ['float32', 'np.float32']):
                    value = np.float32( value )
                    exec( "self." + var_name + " = value" )
                elif (var_type in ['long', 'long int', 'np.int64']):
                    value = np.int64( value )
                    exec( "self." + var_name + " = value" )
                elif (var_type in ['int', 'np.int32']):
                    value = np.int32( value )
                    exec( "self." + var_name + " = value" )
                elif (var_type in ['short', 'short int', 'int16', 'np.int16']):
                    value = np.int16( value )
                    exec( "self." + var_name + " = value" )
                elif (var_type == 'string'):
                    # Replace [case_prefix] or [site_prefix] in a string's value
                    # with the appropriate values
                    case_str = '[case_prefix]'
                    site_str = '[site_prefix]'
                    s = value
                    if (s[:13] == case_str):
                        value_str = (self.case_prefix + s[13:])
                    elif (s[:13] == site_str):
                        value_str = (self.site_prefix  + s[13:])
                    else:
                        value_str = s

                    # If var_name starts with "SAVE_" and value is
                    # Yes or No, then convert to Python boolean.
                    if (var_name[:5] == 'SAVE_'):
                        VALUE_SET = True
                        if (s.lower() in ['yes', 'true']):
                            exec( "self." + var_name + " = True" )
                        elif (s.lower() in ['no', 'false']):
                            exec( "self." + var_name + " = False" )
                        else:
                            VALUE_SET = False
                    else:
                        VALUE_SET = False

                    # If string wasn't a SAVE_ variable, set it here
                    if not(VALUE_SET):
                        if (READ_FILENAME):
                            exec( "self." + var_name_file_str + " = value_str" )
                        elif (READ_SCALAR):
                            exec( "self." + var_name + " = np.float64(value_str)")
                        else:
                            exec( "self." + var_name + " = value_str" )
                else:
                    raise ValueError(\
                        "In read_config_file(), unsupported data type: %d" \
                        % var_type)

                last_var_name = var_name
