# -*- coding: utf8 -*-
"""Contains the tools to produce a wavelength solution

This module gets the extracted data to produce a wavelength solution, linearize the spectrum and write the solution
to the image's header following the FITS standard.
"""

# TODO Reformat file - It is confusing at the moment
# TODO Reformat _ Re-order imports (first "import ...", then "from ... import ..." alphabetically)
# TODO (simon): Discuss this because there are other rules that will probably conflict with this request.
from __future__ import print_function

import logging
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import scipy.interpolate
from astropy.io import fits
from astropy.stats import sigma_clip
from scipy import signal

import wsbuilder
from linelist import ReferenceData

# FORMAT = '%(levelname)s:%(filename)s:%(module)s: 	%(message)s'
# log.basicConfig(level=log.INFO, format=FORMAT)
log = logging.getLogger('redspec.wavelength')


class WavelengthCalibration(object):
    """Wavelength Calibration Class

    The WavelengthCalibration class is instantiated for each of the science images, which are treated as a "science
    object". In this first release it can find a wavelength solution for a given comparison lamp using an interactive
    GUI based on Matplotlib. Although it works very good, for the next release there is a plan for creating an
    independent GUI based on QT in order to work better in different screen sizes and other topic such as showing
    warnings, messages and help.

    This class takes 1D spectrum with no wavelength calibration and returns fits files with wavelength solutions using
    the FITS standard for linear solutions. Goodman spectra are slightly non-linear therefore they are linearized and
    smoothed before they are returned for the user.

    """

    def __init__(self, sci_pack, science_object, args):
        """Wavelength Calibration Class Initialization

        A WavelengthCalibration class is instantiated for each science target being processed, i.e. every science image.

        Notes:
            This class violates some conventions as for length and number of attributes is concerned. Solving this is
            part of a prioritary plans for next release.

        Args:
            sci_pack (object): Extracted data organized in a Class
            science_object (object): Class with information regarding the science image being processed
            args (objects): Runtime arguments.
        """
        # TODO - Documentation missing
        self.args = args
        self.wsolution = None
        self.rms_error = None
        self.reference_data = ReferenceData(self.args)
        self.science_object = science_object
        self.slit_offset = None
        self.interpolation_size = 200
        self.line_search_method = 'derivative'
        """Instrument configuration and spectral characteristics"""
        self.gratings_dict = {'SYZY_400': 400,
                              'KOSI_600': 600,
                              '930': 930,
                              'RALC_1200-BLUE': 1200,
                              'RALC_1200-RED': 1200}
        self.grating_frequency = None
        self.grating_angle = float(0)
        self.camera_angle = float(0)
        self.binning = 1
        self.pixel_count = None
        self.alpha = None
        self.beta = None
        self.center_wavelength = None
        self.blue_limit = None
        self.red_limit = None
        """Interactive wavelength finding"""
        self.reference_marks_x = []
        self.reference_marks_y = []
        self.raw_data_marks_x = []
        self.raw_data_marks_y = []
        self.click_input_enabled = True
        self.reference_bb = None
        self.raw_data_bb = None
        self.contextual_bb = None
        self.i_fig = None
        self.ax1 = None
        self.ax2 = None
        self.ax3 = None
        self.ax4 = None
        self.ax4_plots = None
        self.ax4_com = None
        self.ax4_rlv = None
        self.legends = None
        self.points_ref = None
        self.points_raw = None
        self.line_raw = None
        self.filling_value = 1000
        self.events = True
        self.first = True
        self.evaluation_comment = None
        # self.binning = self.lamp_header[]
        self.pixelcenter = []
        """this data must come parsed"""
        self.path = self.args.source
        self.science_pack = sci_pack
        self.sci_filename = self.science_object.file_name
        # self.history_of_lamps_solutions = {}
        self.reference_solution = None

    def __call__(self, wsolution_obj=None):
        """Call method for the WavelengthSolution Class

        It takes extracted data and produces wavelength calibrated by means of an interactive mode. The call method
        takes care of the order and logic needed to call the different methods. A wavelength solution can be recycled
        for the next science object. In that case, the wavelength solution is parsed as an argument and then there is no
        need to calculate it again.

        Args:
            wsolution_obj (object): Mathematical model of the wavelength solution if exist. If it doesnt is a None

        Returns:
            wavelength_solution (object): The mathematical model of the wavelength solution. If it fails to create it
                                          will return a None element.

        """
        log.info('Processing Science Target: %s', self.science_pack.headers[0]['OBJECT'])
        if wsolution_obj is None:
            if self.science_object.lamp_count > 0:
                for lamp_index in range(self.science_object.lamp_count):
                    self.calibration_lamp = self.science_object.lamp_file[lamp_index - 1]
                    self.lamp_data = self.science_pack.lamps_data[lamp_index]
                    self.raw_pixel_axis = range(1, len(self.lamp_data) + 1, 1)
                    # self.raw_pixel_axis = range(len(self.lamp_data))
                    self.lamp_header = self.science_pack.lamps_headers[lamp_index]
                    self.lamp_name = self.lamp_header['OBJECT']
                    log.info('Processing Comparison Lamp: %s', self.lamp_name)
                    self.data1 = self.interpolate(self.lamp_data)
                    # self.lines_limits = self.get_line_limits()
                    # self.lines_center = self.get_line_centers(self.lines_limits)
                    self.lines_center = self.get_lines_in_lamp()
                    self.spectral = self.get_spectral_characteristics()
                    if self.args.interactive_ws:
                        self.interactive_wavelength_solution()
                    else:
                        log.warning('Automatic Wavelength Solution is not fully implemented yet')
                        self.automatic_wavelength_solution()
                        # self.wsolution = self.wavelength_solution()
                    if self.wsolution is not None:
                        self.linear_lamp = self.linearize_spectrum(self.lamp_data)
                        self.lamp_header = self.add_wavelength_solution(self.lamp_header,
                                                                        self.linear_lamp,
                                                                        self.science_object.lamp_file[lamp_index - 1])
                        for target_index in range(self.science_object.no_targets):
                            log.debug('Processing target %s', target_index + 1)
                            new_data = self.science_pack.data[target_index]
                            new_header = self.science_pack.headers[target_index]
                            if self.science_object.no_targets > 1:
                                new_index = target_index + 1
                            else:
                                new_index = None
                            self.linearized_sci = self.linearize_spectrum(new_data)
                            self.header = self.add_wavelength_solution(new_header,
                                                                       self.linearized_sci,
                                                                       self.sci_filename,
                                                                       index=new_index)
                        wavelength_solution = WavelengthSolution(solution_type='non_linear',
                                                                 model_name='chebyshev',
                                                                 model_order=3,
                                                                 model=self.wsolution,
                                                                 ref_lamp=self.calibration_lamp,
                                                                 eval_comment=self.evaluation_comment,
                                                                 header=self.header)

                        return wavelength_solution
                    else:
                        log.error('It was not possible to get a wavelength solution from this lamp.')
                        return None

            else:
                log.error('There are no lamps to process')
        else:
            self.wsolution = wsolution_obj.wsolution
            self.calibration_lamp = wsolution_obj.reference_lamp
            self.evaluation_comment = wsolution_obj.evaluation_comment
            # print('wavelengthSolution ', self.wsolution)
            # print('Evaluation Comment', self.evaluation_comment)
            # repeat for all sci
            for target_index in range(self.science_object.no_targets):
                log.debug('Processing target %s', target_index + 1)
                new_data = self.science_pack.data[target_index]
                new_header = self.science_pack.headers[target_index]
                if self.science_object.no_targets > 1:
                    new_index = target_index + 1
                else:
                    new_index = None
                self.linearized_sci = self.linearize_spectrum(new_data)
                self.header = self.add_wavelength_solution(new_header,
                                                           self.linearized_sci,
                                                           self.sci_filename,
                                                           self.evaluation_comment,
                                                           index=new_index)

    def get_wsolution(self):
        """Get the mathematical model of the wavelength solution

        The wavelength solution is a callable mathematical function from astropy.modeling.models
        By obtaining this solution it can be applied to a pixel axis.

        Returns:
            wsolution (callable): A callable mathematical function

        """
        if self.wsolution is not None:
            return self.wsolution
        else:
            log.error("Wavelength Solution doesn't exist!")
            return None

    def get_calibration_lamp(self):
        """Get the name of the calibration lamp used for obtain the solution

        The filename of the lamp used to obtain must go to the header for documentation

        Returns:
            calibration_lamp (str): Filename of calibration lamp used to obtain wavelength solution

        """
        if self.wsolution is not None and self.calibration_lamp is not None:
            return self.calibration_lamp
        else:
            log.error('Wavelength solution has not been calculated yet.')

    def get_lines_in_lamp(self):
        """Identify peaks in a lamp spectrum

        Uses scipy.signal.argrelmax to find peaks in a spectrum i.e emission lines then it calls the recenter_lines
        method that will recenter them using a "center of mass", because, not always the maximum value (peak)
        is the center of the line.

        Returns:
            lines_candidates (list): A common list containing pixel values at approximate location of lines.
        """
        filtered_data = np.where(np.abs(self.lamp_data > self.lamp_data.min() + 0.05 * self.lamp_data.max()),
                                 self.lamp_data,
                                 None)
        peaks = signal.argrelmax(filtered_data, axis=0, order=6)[0]
        lines_center = self.recenter_lines(self.lamp_data, peaks)

        if self.args.plots_enabled:
            fig = plt.figure(1)
            fig.canvas.set_window_title('Lines Detected')
            plt.title('Lines detected in Lamp\n%s' % self.lamp_header['OBJECT'])
            plt.xlabel('Pixel Axis')
            plt.ylabel('Intensity (counts)')
            # Build legends without data
            plt.plot([], color='k', label='Comparison Lamp Data')
            plt.plot([], color='k', linestyle=':', label='Spectral Line Detected')
            for line in peaks:
                plt.axvline(line + 1, color='k', linestyle=':')
            # plt.axhline(median + stddev, color='g')
            plt.plot(self.raw_pixel_axis, self.lamp_data, color='k')
            plt.legend(loc='best')
            plt.show()
        return lines_center

    def recenter_lines(self, data, lines, plots=False):
        """Finds the centroid of an emission line

        For every line center (pixel value) it will scan left first until the data stops decreasing, it assumes it
        is an emission line and then will scan right until it stops decreasing too. Defined those limits it will
        """
        new_center = []
        x_size = data.shape[0]
        median = np.median(data)
        for line in lines:
            # TODO (simon): Check if this definition is valid, so far is not critical
            left_limit = 0
            right_limit = 1
            condition = True
            left_index = int(line)
            while condition and left_index - 2 > 0:
                if (data[left_index - 1] > data[left_index]) and (data[left_index - 2] > data[left_index - 1]):
                    condition = False
                    left_limit = left_index
                elif data[left_index] < median:
                    condition = False
                    left_limit = left_index
                else:
                    left_limit = left_index
                left_index -= 1

            # id right limit
            condition = True
            right_index = int(line)
            while condition and right_index + 2 < x_size - 1:
                if (data[right_index + 1] > data[right_index]) and (data[right_index + 2] > data[right_index + 1]):
                    condition = False
                    right_limit = right_index
                elif data[right_index] < median:
                    condition = False
                    right_limit = right_index
                else:
                    right_limit = right_index
                right_index += 1
            index_diff = [abs(line - left_index), abs(line - right_index)]

            sub_x_axis = range(line - min(index_diff), (line + min(index_diff)) + 1)
            sub_data = data[line - min(index_diff):(line + min(index_diff)) + 1]
            centroid = np.sum(sub_x_axis * sub_data) / np.sum(sub_data)
            # checks for asymmetries
            differences = [abs(data[line] - data[left_limit]), abs(data[line] - data[right_limit])]
            if max(differences) / min(differences) >= 2.:
                if plots:
                    plt.axvspan(line - 1, line + 1, color='g', alpha=0.3)
                new_center.append(line + 1)
            else:
                new_center.append(centroid + 1)
        if plots:
            fig = plt.figure(1)
            fig.canvas.set_window_title('Lines Detected in Lamp')
            plt.axhline(median, color='b')
            plt.plot(self.raw_pixel_axis, data, color='k', label='Lamp Data')
            for line in lines:
                plt.axvline(line + 1, color='k', linestyle=':', label='First Detected Center')
            for center in new_center:
                plt.axvline(center, color='k', linestyle='.-', label='New Center')
            plt.show()
        return new_center

    def get_spectral_characteristics(self):
        """Calculates some Goodman's specific spectroscopic values.

        From the Header value for Grating, Grating Angle and Camera Angle it is possible to estimate what are the limits
        wavelength values and central wavelength. It was necessary to add offsets though, since the formulas provided
        are slightly off. The values are only an estimate.

        Returns:
            spectral_characteristics (dict): Contains the following parameters:
                                            center: Center Wavelength
                                            blue: Blue limit in Angstrom
                                            red: Red limit in Angstrom
                                            alpha: Angle
                                            beta: Angle
                                            pix1: Pixel One
                                            pix2: Pixel Two

        """
        blue_correction_factor = -90
        red_correction_factor = -60
        self.grating_frequency = self.gratings_dict[self.lamp_header['GRATING']]
        self.grating_angle = float(self.lamp_header['GRT_ANG'])
        self.camera_angle = float(self.lamp_header['CAM_ANG'])
        # binning = self.lamp_header[]
        # TODO(simon): Make sure which binning is the important, parallel or serial
        # self.binning = 1
        # PG5_4 parallel
        # PG5_9 serial
        # PARAM18 serial
        # PARAM22 parallel
        try:
            self.binning = self.lamp_header['PG5_4']
            # serial_binning = self.lamp_header['PG5_9']
        except KeyError:
            self.binning = self.lamp_header['PARAM22']
            # serial_binning = self.lamp_header['PARAM18']
        # self.pixel_count = len(self.lamp_data)
        # Calculations
        # TODO (simon): Check whether is necessary to remove the self.slit_offset variable
        self.alpha = self.grating_angle + 0.
        self.beta = self.camera_angle - self.grating_angle
        self.center_wavelength = 10 * (1e6 / self.grating_frequency) * (
            np.sin(self.alpha * np.pi / 180.) + np.sin(self.beta * np.pi / 180.))
        self.blue_limit = 10 * (1e6 / self.grating_frequency) * (
            np.sin(self.alpha * np.pi / 180.) + np.sin((self.beta - 4.656) * np.pi / 180.)) + blue_correction_factor
        self.red_limit = 10 * (1e6 / self.grating_frequency) * (
            np.sin(self.alpha * np.pi / 180.) + np.sin((self.beta + 4.656) * np.pi / 180.)) + red_correction_factor
        pixel_one = self.predicted_wavelength(1)
        pixel_two = self.predicted_wavelength(2)
        log.debug('Center Wavelength : %s Blue Limit : %s Red Limit : %s',
                  self.center_wavelength,
                  self.blue_limit,
                  self.red_limit)
        spectral_characteristics = {'center': self.center_wavelength,
                                    'blue': self.blue_limit,
                                    'red': self.red_limit,
                                    'alpha': self.alpha,
                                    'beta': self.beta,
                                    'pix1': pixel_one,
                                    'pix2': pixel_two}
        return spectral_characteristics

    def interpolate(self, spectrum):
        """Creates an interpolated version of the input spectrum

        This method creates an interpolated version of the input array, it is used mainly for a spectrum but it can
        also be used with any unidimensional array, assuming you are happy with the interpolation_size attribute
        defined for this class. The reason for doing interpolation is that it allows to find the lines and its
        respective center more precisely. The default interpolation size is 200 (two hundred) points.

        Args:
            spectrum (array): an uncalibrated spectrum or any unidimensional array.

        Returns:
            Two dimensional array containing x-axis and interpolated array. The x-axis preserves original pixel values.

        """
        x_axis = range(1, spectrum.size + 1)
        first_x = x_axis[0]
        last_x = x_axis[-1]
        new_x_axis = np.linspace(first_x, last_x, spectrum.size * self.interpolation_size)

        tck = scipy.interpolate.splrep(x_axis, spectrum, s=0)
        new_spectrum = scipy.interpolate.splev(new_x_axis, tck, der=0)
        return [new_x_axis, new_spectrum]

    def recenter_line_by_data(self, data_name, x_data):
        """Finds a better center for a click-selected line

        This method is called by another method that handles click events. An argument is parsed that will tell
        which plot was the clicked and what is the x-value in data coordinates. Then the closest pixel center
        will be found and from there will extract a 20 pixel wide sample of the data (this could be a future improvement
        the width of the extraction should depend on the FWHM of the lines). The sample of the data is used to calculate
        a centroid (center of mass) which is a good approximation but could be influenced by data shape or if the click
        was too far (unquantified yet). That is why for the reference data, a database of laboratory line center will be
        used and for raw data the line centers are calculated earlier in the process, independently of any human input.

        It also will plot the sample, the centroid and the reference line center at the fourth subplot, bottom right
        corner.

        Args:
            data_name (str): 'reference' or 'raw-data' is where the click was done
            x_data (float): click x-axis value in data coordinates

        Returns:
            reference_line_value (float): The value the line center that will be used later to do the wavelength fit

        """
        if data_name == 'reference':
            pseudo_center = np.argmin(abs(self.reference_solution[0] - x_data))
            reference_line_index = np.argmin(abs(self.reference_data.get_line_list_by_name(self.lamp_name) - x_data))
            reference_line_value = self.reference_data.get_line_list_by_name(self.lamp_name)[reference_line_index]
            sub_x = self.reference_solution[0][pseudo_center - 10: pseudo_center + 10]
            sub_y = self.reference_solution[1][pseudo_center - 10: pseudo_center + 10]
            center_of_mass = np.sum(sub_x * sub_y) / np.sum(sub_y)
            # print 'centroid ', center_of_mass
            # plt.figure(3)
            # if self.ax4_plots is not None or self.ax4_com is not None or self.ax4_rlv is not None:
            try:
                self.ax4.cla()
                self.ax4.relim()
            except NameError as err:
                log.error(err)

            self.ax4.set_title('Reference Data Clicked Line')
            self.ax4.set_xlabel('Wavelength (Angstrom)')
            self.ax4.set_ylabel('Intensity (Counts)')
            self.ax4_plots = self.ax4.plot(sub_x, sub_y, color='k', label='Data')
            self.ax4_rlv = self.ax4.axvline(reference_line_value, linestyle='-', color='r', label='Reference Line Value')
            self.ax4_com = self.ax4.axvline(center_of_mass, linestyle='--', color='b', label='Centroid')
            self.ax4.yaxis.set_major_formatter(mtick.FormatStrFormatter('%.1e'))
            self.ax4.legend(loc=3, framealpha=0.5)
            self.i_fig.canvas.draw()
            # return center_of_mass
            return reference_line_value
        elif data_name == 'raw-data':
            pseudo_center = np.argmin(abs(self.raw_pixel_axis - x_data))
            raw_line_index = np.argmin(abs(self.lines_center - x_data))
            raw_line_value = self.lines_center[raw_line_index]
            # print(raw_line_value)
            sub_x = self.raw_pixel_axis[pseudo_center - 10: pseudo_center + 10]
            sub_y = self.lamp_data[pseudo_center - 10: pseudo_center + 10]
            center_of_mass = np.sum(sub_x * sub_y) / np.sum(sub_y)
            # print 'centroid ', center_of_mass
            # plt.figure(3)
            # if self.ax4_plots is not None or self.ax4_com is not None or self.ax4_rlv is not None:
            try:
                self.ax4.cla()
                self.ax4.relim()
            except NameError as err:
                log.error(err)
            self.ax4.set_title('Raw Data Clicked Line')
            self.ax4.set_xlabel('Pixel Axis')
            self.ax4.set_ylabel('Intensity (Counts)')
            self.ax4_plots = self.ax4.plot(sub_x, sub_y, color='k', label='Data')
            self.ax4_rlv = self.ax4.axvline(raw_line_value, linestyle='-', color='r', label='Line Center')
            self.ax4_com = self.ax4.axvline(center_of_mass, linestyle='--', color='b', label='Centroid')
            self.ax4.yaxis.set_major_formatter(mtick.FormatStrFormatter('%.1e'))
            self.ax4.legend(loc=3, framealpha=0.5)
            self.i_fig.canvas.draw()
            # return center_of_mass
            return raw_line_value
        else:
            log.error('Unrecognized data name')

    def predicted_wavelength(self, pixel):
        # TODO (simon): Update with bruno's new calculations
        alpha = self.alpha
        beta = self.beta
        # pixel_count = self.pixel_count
        binning = self.binning
        grating_frequency = self.grating_frequency
        wavelength = 10 * (1e6 / grating_frequency) * (np.sin(alpha * np.pi / 180.)
                                                       + np.sin((beta * np.pi / 180.)
                                                                + np.arctan((pixel * binning - 2048) * 0.015 / 377.2)))
        return wavelength

    def automatic_wavelength_solution(self):
        """Automatic Wavelength Solution NotImplemented

        Raises:
            NotImplemented

        """
        # needs:
        #   - self.sci, self.header
        #   - self.lines_center
        raise NotImplemented

    def interactive_wavelength_solution(self):
        """Find the wavelength solution interactively

        Using matplotlib graphical interface we developed an interactive method to find the wavelength solution. It is
        capable of tracing the slight deviation from linearity of the data. It uses a combination of previously
        wavelength calibrated comparison lamp and laboratory line centers. Those two are combined in a single plot,
        bottom left, to help to visually identify their counterparts in the raw data and viceversa. In the other hand,
        raw data is previously processed to find the lines present. They are stored as a list and used as the correct
        center of the line. Once you select a line, the centroid will be calculated and the closest line will be
        returned.

        This method generates a GUI like plot using matplolib, capable of handling keyboard and click events. The window
        consist of four plots:

        In the top left side will be a wide plot named raw data. This is the uncalibrated comparison lamp associated to
        the science image that is being processed.

        Then in the bottom left, there is the reference plot, where a previously calibrated lamp is displayed along with
        the reference line values.

        In the top right side there is a permanent help text with the basic functions plus a short description.

        And finally in the bottom right side you will find a more dynamic plot. It will show a zoomed line when you mark
        one with a click, a scatter plot when you do a fit to the recorded marks and also will show warnings in case
        something is going wrong.

        For future release there is the plan to put all this method as a new class even with an indepentend QT GUI.

        Notes:
            This method uses the GTK3Agg backend, it will not work with other.





        """
        plt.switch_backend('GTK3Agg')
        reference_file = self.reference_data.get_reference_lamps_by_name(self.lamp_name)
        if reference_file is not None:
            log.info('Using reference file: %s', reference_file)
            reference_plots_enabled = True
            ref_data = fits.getdata(reference_file)
            ref_header = fits.getheader(reference_file)
            fits_ws_reader = wsbuilder.ReadWavelengthSolution(ref_header, ref_data)
            self.reference_solution = fits_ws_reader()
        else:
            reference_plots_enabled = False
            log.error('Please Check the OBJECT Keyword of your reference data')

        # ------- Plots -------
        self.i_fig, ((self.ax1, self.ax2), (self.ax3, self.ax4)) = plt.subplots(2,
                                                                                2,
                                                                                gridspec_kw={'width_ratios': [4, 1]})
        self.i_fig.canvas.set_window_title('Science Target: %s' % self.science_object.name)
        manager = plt.get_current_fig_manager()
        manager.window.maximize()

        self.ax1.set_title('Raw Data - %s' % self.lamp_name)
        self.ax1.set_xlabel('Pixels')
        self.ax1.set_ylabel('Intensity (counts)')
        self.ax1.plot([], linestyle='--', color='r', label='Detected Lines')
        for idline in self.lines_center:
            self.ax1.axvline(idline, linestyle='--', color='r')
        self.ax1.plot(self.raw_pixel_axis, self.lamp_data, color='k', label='Raw Data')
        self.ax1.set_xlim((0, len(self.lamp_data)))
        self.ax1.yaxis.set_major_formatter(mtick.FormatStrFormatter('%.1e'))
        self.ax1.legend(loc=2)

        # Update y limits to have an extra 5% to top and bottom
        ax1_ylim = self.ax1.get_ylim()
        ax1_y_range = ax1_ylim[1] - ax1_ylim[0]
        self.ax1.set_ylim((ax1_ylim[0] - 0.05 * ax1_y_range, ax1_ylim[1] + 0.05 * ax1_y_range))

        self.ax3.set_title('Reference Data')
        self.ax3.set_xlabel('Wavelength (Angstrom)')
        self.ax3.set_ylabel('Intensity (counts)')
        self.ax3.set_xlim((self.blue_limit, self.red_limit))
        self.ax3.yaxis.set_major_formatter(mtick.FormatStrFormatter('%.1e'))
        self.ax3.plot([], linestyle=':', color='r', label='Reference Line Values')

        for rline in self.reference_data.get_line_list_by_name(self.lamp_name):
            self.ax3.axvline(rline, linestyle=':', color='r')
        if reference_plots_enabled:
            self.ax3.plot(self.reference_solution[0],
                          self.reference_solution[1],
                          color='k',
                          label='Reference Lamp Data')
        self.ax3.legend(loc=2)

        # Update y limits to have an extra 5% to top and bottom
        ax3_ylim = self.ax3.get_ylim()
        ax3_y_range = ax3_ylim[1] - ax3_ylim[0]
        self.ax3.set_ylim((ax3_ylim[0] - 0.05 * ax3_y_range, ax3_ylim[1] + 0.05 * ax3_y_range))
        # print(ax3_ylim)

        self.display_help_text()

        # zoomed plot
        self.display_onscreen_message('Use middle button click to select a line')

        plt.subplots_adjust(left=0.05, right=0.99, top=0.97, bottom=0.04, hspace=0.17, wspace=0.11)
        self.raw_data_bb = self.ax1.get_position()
        self.reference_bb = self.ax3.get_position()
        self.contextual_bb = self.ax4.get_position()

        # if self.click_input_enabled:
        self.i_fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.i_fig.canvas.mpl_connect('key_press_event', self.key_pressed)
        # print self.wsolution
        plt.show()

        return True

    def on_click(self, event):
        """Handles Click events for Interactive Mode

        Calls the method register_mark

        Args:
            event (object): Click event
        """
        if event.button == 2:
            self.register_mark(event)
        # else:
            # print(event.button)
        # elif event.button == 3:
        #     if len(self.reference_marks_x) == len(self.raw_data_marks_x):
        #         self.click_input_enabled = False
        #         log.info('Leaving interactive mode')
        #     else:
        #         if len(self.reference_marks_x) < len(self.raw_data_marks_x):
        #             log.info('There is %s click missing in the Reference plot',
        #                      len(self.raw_data_marks_x) - len(self.reference_marks_x))
        #         else:
        #             log.info('There is %s click missing in the New Data plot',
        #                      len(self.reference_marks_x) - len(self.raw_data_marks_x))

    def key_pressed(self, event):
        """Key event handler

        There are several key events that need to be taken care of. See a brief description of each one of them below:

        F1 or ?: Prints a help message
        F2 or f: Fit wavelength solution model.
        F3 or a: Find new lines.
        F4: Evaluate solution
        F6 or l: Linearize data although this is done automatically after the wavelength function is fit
        d: deletes closest point
        ctrl+d: deletes all recorded marks
        ctrl+z: Reverts the action of F3 or a.
        Middle Button Click or m: records data location.
        Enter: Close figure and apply solution if exists.
        Shift+Enter: Close the program with sys.exit(0)

        Notes:
            This method must be simplified

        Args:
            event (object): Key pressed event

        """
        self.events = True
        if event.key == 'f1' or event.key == '?':
            log.info('Print help regarding interactive mode')
            print("F1 or ?: Prints Help.")
            print("F2 or f: Fit wavelength solution model.")
            print("F3 or a: Find new lines.")
            print("F4: Evaluate solution")
            print("F6 or l: Linearize data (for testing not definitive)")
            print("d: deletes closest point")
            # print("l : resample spectrum to a linear dispersion axis")
            print("ctrl+d: deletes all recorded marks")
            print("ctrl+z: Go back to previous solution (deletes automatic added points")
            print('Middle Button Click: records data location.')
            print("Enter: Close figure and apply solution if exists.")
        elif event.key == 'f2' or event.key == 'f':
            log.debug('Calling function to fit wavelength Solution')
            self.fit_pixel_to_wavelength()
            self.plot_raw_over_reference()
        elif event.key == 'f3' or event.key == 'a':
            if self.wsolution is not None:
                self.find_more_lines()
                self.update_marks_plot('reference')
                self.update_marks_plot('raw_data')
        elif event.key == 'f4':
            if self.wsolution is not None and len(self.raw_data_marks_x) > 0:
                self.evaluate_solution(plots=True)
        elif event.key == 'd':
            # TODO (simon): simplify this code.
            figure_x, figure_y = self.i_fig.transFigure.inverted().transform((event.x, event.y))
            if self.raw_data_bb.contains(figure_x, figure_y):
                log.debug('Deleting raw point')
                # print abs(self.raw_data_marks_x - event.xdata) a[:] =
                closer_index = int(np.argmin([abs(list_val - event.xdata) for list_val in self.raw_data_marks_x]))
                # print 'Index ', closer_index
                if len(self.raw_data_marks_x) == len(self.reference_marks_x):
                    self.raw_data_marks_x.pop(closer_index)
                    self.raw_data_marks_y.pop(closer_index)
                    self.reference_marks_x.pop(closer_index)
                    self.reference_marks_y.pop(closer_index)
                    self.update_marks_plot('reference')
                    self.update_marks_plot('raw_data')
                else:
                    if closer_index == len(self.raw_data_marks_x) - 1:
                        self.raw_data_marks_x.pop(closer_index)
                        self.raw_data_marks_y.pop(closer_index)
                        self.update_marks_plot('raw_data')
                    else:
                        self.raw_data_marks_x.pop(closer_index)
                        self.raw_data_marks_y.pop(closer_index)
                        self.reference_marks_x.pop(closer_index)
                        self.reference_marks_y.pop(closer_index)
                        self.update_marks_plot('reference')
                        self.update_marks_plot('raw_data')

            elif self.reference_bb.contains(figure_x, figure_y):
                log.debug('Deleting reference point')
                # print 'reference ', self.reference_marks_x, self.re
                # print self.reference_marks_x
                # print abs(self.reference_marks_x - event.xdata)
                closer_index = int(np.argmin([abs(list_val - event.xdata) for list_val in self.reference_marks_x]))
                if len(self.raw_data_marks_x) == len(self.reference_marks_x):
                    self.raw_data_marks_x.pop(closer_index)
                    self.raw_data_marks_y.pop(closer_index)
                    self.reference_marks_x.pop(closer_index)
                    self.reference_marks_y.pop(closer_index)
                    self.update_marks_plot('reference')
                    self.update_marks_plot('raw_data')
                else:
                    if closer_index == len(self.reference_marks_x) - 1:
                        self.reference_marks_x.pop(closer_index)
                        self.reference_marks_y.pop(closer_index)
                        self.update_marks_plot('reference')
                    else:
                        self.raw_data_marks_x.pop(closer_index)
                        self.raw_data_marks_y.pop(closer_index)
                        self.reference_marks_x.pop(closer_index)
                        self.reference_marks_y.pop(closer_index)
                        self.update_marks_plot('reference')
                        self.update_marks_plot('raw_data')
                    
            elif self.contextual_bb.contains(figure_x, figure_y):
                closer_index_ref = int(np.argmin([abs(list_val - event.ydata) for list_val in self.reference_marks_x]))
                closer_index_raw = int(np.argmin([abs(list_val - event.xdata) for list_val in self.raw_data_marks_x]))
                # print(closer_index_raw, closer_index_ref)
                self.raw_data_marks_x.pop(closer_index_raw)
                self.raw_data_marks_y.pop(closer_index_raw)
                self.reference_marks_x.pop(closer_index_ref)
                self.reference_marks_y.pop(closer_index_ref)
                self.update_marks_plot('reference')
                self.update_marks_plot('raw_data')
                self.update_marks_plot('eval_plots')

        elif event.key == 'f6' or event.key == 'l':
            log.info('Linearize and smoothing spectrum')
            if self.wsolution is not None:
                self.linearize_spectrum(self.lamp_data, plots=True)
        elif event.key == 'ctrl+z':
            log.info('Deleting automatic added points. If exist.')
            if self.raw_data_marks_x is not [] and self.reference_marks_x is not []:
                to_remove = []
                for i in range(len(self.raw_data_marks_x)):
                    # print self.raw_data_marks[i], self.filling_value
                    if self.raw_data_marks_y[i] == self.filling_value:
                        to_remove.append(i)
                        # print to_remove
                to_remove = np.array(sorted(to_remove, reverse=True))
                if len(to_remove) > 0:
                    for index in to_remove:
                        self.raw_data_marks_x.pop(index)
                        self.raw_data_marks_y.pop(index)
                        self.reference_marks_x.pop(index)
                        self.reference_marks_y.pop(index)
                    self.update_marks_plot('reference')
                    self.update_marks_plot('raw_data')
                    # else:
                    # print self.raw_click_plot, self.ref_click_plot, 'mmm'
        elif event.key == 'ctrl+d':
            log.info('Deleting all recording Clicks')
            self.display_onscreen_message(message='Delete all marks? Answer on the terminal.')
            # time.sleep(10)
            answer = raw_input('Are you sure you want to delete all marks? only typing "No" will stop it! : ')
            if answer.lower() != 'no':
                self.reference_marks_x = []
                self.reference_marks_y = []
                self.raw_data_marks_x = []
                self.raw_data_marks_y = []
                self.update_marks_plot('delete')
                self.plot_raw_over_reference(remove=True)
            else:
                log.info('No click was deleted this time!.')
        elif event.key == 'enter':
            if self.wsolution is not None:
                log.info('Closing figure')
                plt.close('all')
            else:
                message = 'There is still no wavelength solution!'
                log.info(message)
                self.display_onscreen_message(message)
        elif event.key == 'm':
            self.register_mark(event)
        elif event.key == 'ctrl+q':
            log.info('Pressed Ctrl+q. Closing the program')
            sys.exit(0)
        else:
            log.debug("Key Pressed: ", event.key)
            pass

    def register_mark(self, event):
        """Marks a line

        Detects where the click was done or m-key was pressed and calls the corresponding method. It handles the middle
        button click and m-key being pressed. There are two regions of interest as for where a click was done.
        The raw and reference data respectively. For any of such regions it will call the method that recenter the line
        and once the desired value is returned it will be appended to the list that contains all the correspondent line
        positions, raw (pixels) and reference (angstrom)

        Args:
            event (object): Click or m-key pressed event
        """
        if event.xdata is not None and event.ydata is not None:
            figure_x, figure_y = self.i_fig.transFigure.inverted().transform((event.x, event.y))
            if self.reference_bb.contains(figure_x, figure_y):
                # self.reference_marks.append([event.xdata, event.ydata])
                self.reference_marks_x.append(self.recenter_line_by_data('reference', event.xdata))
                self.reference_marks_y.append(event.ydata)
                self.update_marks_plot('reference')
            elif self.raw_data_bb.contains(figure_x, figure_y):
                # self.raw_data_marks.append([event.xdata, event.ydata])
                self.raw_data_marks_x.append(self.recenter_line_by_data('raw-data', event.xdata))
                self.raw_data_marks_y.append(event.ydata)
                self.update_marks_plot('raw_data')
            else:
                log.debug(figure_x, figure_y, 'Are not contained')
        else:
            log.error('Clicked Region is out of boundaries')

    def find_more_lines(self):
        """Method to add more lines given that a wavelength solution already exists

        This method is part of the interactive wavelength solution mechanism. If a wavelength solution exist it uses the
        line centers in pixels to estimate their respective wavelength and then search for the closest value in the list
        of reference lines for the elements in the comparison lamp. Then it filters the worst of them by doing sigma
        clipping. Finally it adds them to the class' attributes that contains the list of reference points.

        Better results are obtained if the solution is already decent. Visual inspection also improves final result.
        """
        new_physical = []
        new_wavelength = []
        square_differences = []
        if self.wsolution is not None:
            wlines = self.wsolution(self.lines_center)
            for i in range(len(wlines)):
                # [abs(list_val - wlines[i]) for list_val in self.reference_data.get_line_list_by_name(self.lamp_name)]
                closer_index = np.argmin(abs(self.reference_data.get_line_list_by_name(self.lamp_name) - wlines[i]))
                rline = self.reference_data.get_line_list_by_name(self.lamp_name)[closer_index]
                rw_difference = wlines[i] - rline
                # print('Difference w - r ', rw_difference, rline)
                square_differences.append(rw_difference ** 2)
                new_physical.append(self.lines_center[i])
                new_wavelength.append(rline)
            clipped_differences = sigma_clip(square_differences, sigma=2, iters=3)
            if len(new_wavelength) == len(new_physical) == len(clipped_differences):
                for i in range(len(new_wavelength)):
                    if clipped_differences[i] is not np.ma.masked and new_wavelength[i] not in self.reference_marks_x:
                        self.reference_marks_x.append(new_wavelength[i])
                        self.reference_marks_y.append(self.filling_value)
                        self.raw_data_marks_x.append(new_physical[i])
                        self.raw_data_marks_y.append(self.filling_value)
        return True

    def update_marks_plot(self, action=None):
        """Update the points that represent marks on lamp plots

        When you mark a line a red dot marks the position of the line at the exact y location of the click, for the x
        location it will use the value obtained by means of the recentering method. There are three possible actions:
        Update the reference plot's click, the raw data marks or delete them all.

        Args:
            action (str): A string that could be 'reference', 'raw_data' or 'delete' depending on the action desired
        """
        # print(type(action), type(pixel_axis), type(differences))
        if action == 'reference':
            if self.points_ref is not None:
                try:
                    self.points_ref.remove()
                    self.ax3.relim()
                except:
                    pass
            self.points_ref, = self.ax3.plot(self.reference_marks_x,
                                             self.reference_marks_y,
                                             linestyle='None',
                                             marker='o',
                                             color='r')
            self.i_fig.canvas.draw()
        elif action == 'raw_data':
            # print self.points_raw
            # print dir(self.points_raw)
            if self.points_raw is not None:
                try:
                    self.points_raw.remove()
                    self.ax1.relim()
                except ValueError as err:
                    log.error(err)
            self.points_raw, = self.ax1.plot(self.raw_data_marks_x,
                                             self.raw_data_marks_y,
                                             linestyle='None',
                                             marker='o',
                                             color='r')
            self.i_fig.canvas.draw()
        elif action == 'delete':
            if self.points_raw is not None and self.points_ref is not None:
                self.points_raw.remove()
                self.ax1.relim()
                self.points_ref.remove()
                self.ax3.relim()
                self.i_fig.canvas.draw()

    def plot_raw_over_reference(self, remove=False):
        """Overplot raw data over reference lamp using current wavelength solution model

        Once the wavelength solution is obtained this method is called to apply the already mentioned solution to the
        raw data and then overplot it on the reference lamp plot. This is very useful to have a visual idea of how far
        or close the solution is.

        Args:
            remove (bool): True or False depending whether you want to remove the overplotted lamp or not
        """
        if self.wsolution is not None:
            if self.line_raw is not None:
                try:
                    self.line_raw.remove()
                    self.ax3.relim()
                except:
                    pass
            if not remove:
                # TODO(simon): catch TypeError Exception and correct what is causing it
                self.line_raw, = self.ax3.plot(self.wsolution(self.raw_pixel_axis),
                                               self.lamp_data,
                                               linestyle='-',
                                               color='r',
                                               alpha=0.4,
                                               label='New Wavelength Solution')
            self.ax3.legend(loc=2)
            self.i_fig.canvas.draw()

    def evaluate_solution(self, plots=False):
        """Calculate the Root Mean Square Error of the solution

        Once the wavelength solution is obtained it has to be evaluated. The line centers found for the raw comparison
        lamp will be converted to, according to the new solution, angstrom. Then for each line the closest reference
        line value is obtained. The difference is stored. Then this differences are cleaned by means of a sigma clipping
        method that will rule out any outlier or any line that is not well matched. Then, using the sigma clipped
        differences the Root Mean Square error is calculated.

        It also creates a plot in the bottom right subplot of the interactive window, showing an scatter plot plus some
        information regarding the quality of the fit.

        Args:
            plots (bool): Whether to create the plot or not

        Returns:
            results (list): Contains three elements: rms_error (float), npoints (int), n_rejections (int)

        """
        if self.wsolution is not None:
            differences = np.array([])
            wavelength_line_centers = self.wsolution(self.lines_center)

            for wline in wavelength_line_centers:
                closer_index = np.argmin(abs(self.reference_data.get_line_list_by_name(self.lamp_name) - wline))
                rline = self.reference_data.get_line_list_by_name(self.lamp_name)[closer_index]
                rw_difference = wline - rline
                # print 'Difference w - r ', rw_difference, rline
                differences = np.append(differences, rw_difference)

            clipping_sigma = 2.
            # print(differences)
            clipped_differences = sigma_clip(differences, sigma=clipping_sigma, iters=5, cenfunc=np.ma.median)
            once_clipped_differences = sigma_clip(differences, sigma=clipping_sigma, iters=1, cenfunc=np.ma.median)

            npoints = len(clipped_differences)
            n_rejections = np.ma.count_masked(clipped_differences)
            square_differences = []
            for i in range(len(clipped_differences)):
                if clipped_differences[i] is not np.ma.masked:
                    square_differences.append(clipped_differences[i] ** 2)
            old_rms_error = None
            if self.rms_error is not None:
                old_rms_error = float(self.rms_error)
            self.rms_error = np.sqrt(np.sum(square_differences) / len(square_differences))
            log.info('RMS Error : %s', self.rms_error)
            if plots:
                if self.ax4_plots is not None or self.ax4_com is not None or self.ax4_rlv is not None:
                    try:
                        self.ax4.cla()
                        self.ax4.relim()
                    except NameError as err:
                        log.error(err)

                self.ax4.set_title('RMS Error %.3f \n %d points (%d rejected)' % (self.rms_error,
                                                                                  npoints,
                                                                                  n_rejections))
                self.ax4.set_ylim(once_clipped_differences.min(), once_clipped_differences.max())
                # self.ax4.set_ylim(- rms_error, 2 * rms_error)
                self.ax4.set_xlim(np.min(self.lines_center), np.max(self.lines_center))
                self.ax4_rlv = self.ax4.scatter(self.lines_center,
                                                differences,
                                                marker='x',
                                                color='k',
                                                label='Rejected Points')
                self.ax4_com = self.ax4.axhspan(clipped_differences.min(),
                                                clipped_differences.max(),
                                                color='k',
                                                alpha=0.4,
                                                edgecolor=None,
                                                label='%s Sigma' % clipping_sigma)
                self.ax4_plots = self.ax4.scatter(self.lines_center, clipped_differences, label='Differences')
                if self.rms_error is not None and old_rms_error is not None:
                    # increment_color = 'white'
                    rms_error_difference = self.rms_error - old_rms_error
                    if rms_error_difference > 0.001:
                        increment_color = 'red'
                    elif rms_error_difference < -0.001:
                        increment_color = 'green'
                    else:
                        increment_color = 'white'
                    message = r'$\Delta$ RMSE %+.3f' % rms_error_difference
                    # self.display_onscreen_message(message=message, color=increment_color)
                    self.ax4.text(0.05, 0.95,
                                  message,
                                  verticalalignment='top',
                                  horizontalalignment='left',
                                  transform=self.ax4.transAxes,
                                  color=increment_color,
                                  fontsize=15)

                self.ax4.set_xlabel('Pixel Axis (Pixels)')
                self.ax4.set_ylabel('Difference (Angstroms)')

                self.ax4.legend(loc=3, framealpha=0.5)
                self.i_fig.canvas.draw()

            results = [self.rms_error, npoints, n_rejections]
            return results
        else:
            log.error('Solution is still non-existent!')

    def fit_pixel_to_wavelength(self):
        """Does the fit to find the wavelength solution

        Once you have four data points on each side (raw and reference or pixel and angstrom) it calculates the fit
        usign a Chebyshev model of third degree. This was chosen because it worked better compared to the rest. There is
        a slight deviation from linearity in all Goodman data, therefore a linear model could not be used, also is said
        that a Spline of third degree is "too flexible" which I also experienced and since the deviation from linearity
        is not extreme it seemed that it was not necesary to implement.

        This method checks that the data that will be used as input to calculate the fit have the same dimensions and
        warns the user in case is not.

        Returns:
            None (None): An empty return is created to finish the execution of the method when a fit will not be
                         possible

        """
        if len(self.reference_marks_x) and len(self.raw_data_marks_x) > 0:
            if len(self.reference_marks_x) < 4 or len(self.raw_data_marks_x) < 4:
                message = 'Not enough marks! Minimum 4 each side.'
                self.display_onscreen_message(message)
                return
            if len(self.reference_marks_x) != len(self.raw_data_marks_x):
                if len(self.reference_marks_x) < len(self.raw_data_marks_x):
                    n = len(self.raw_data_marks_x) - len(self.reference_marks_x)
                    if n == 1:
                        message_text = '%s Reference Click is missing!.' % n
                    else:
                        message_text = '%s Reference Clicks are missing!.' % n
                else:
                    n = len(self.reference_marks_x) - len(self.raw_data_marks_x)
                    if n == 1:
                        message_text = '%s Raw Click is missing!.' % n
                    else:
                        message_text = '%s Raw Clicks are missing!.' % n
                self.display_onscreen_message(message_text)
            else:
                pixel = []
                angstrom = []
                for i in range(len(self.reference_marks_x)):
                    pixel.append(self.raw_data_marks_x[i])
                    angstrom.append(self.reference_marks_x[i])
                wavelength_solution = wsbuilder.WavelengthFitter(model='chebyshev', degree=3)
                self.wsolution = wavelength_solution.ws_fit(pixel, angstrom)
                self.evaluate_solution(plots=True)

        else:
            log.error('Clicks record is empty')
            self.display_onscreen_message(message='Clicks record is empty')
            if self.wsolution is not None:
                self.wsolution = None

    def linearize_spectrum(self, data, plots=False):
        """Produces a linearized version of the spectrum

        Storing wavelength solutions in a FITS header is not simple at all for non-linear solutions therefore is easier
        for the final user and for the development code to have the spectrum linearized. It first finds a spline
        representation of the data, then creates a linear wavelength axis (angstrom) and finally it resamples the data
        from the spline representation to the linear wavelength axis.

        It also applies a median filter of kernel size three to smooth the linearized spectrum. Sometimes the splines
        produce funny things when the original data is too steep.

        Args:
            data (Array): The non-linear spectrum
            plots (bool): Whether to show the plots or not

        Returns:
            linear_data (list): Contains two elements: Linear wavelength axis and the smoothed linearized data itself.

        """
        pixel_axis = range(1, len(data) + 1, 1)
        if self.wsolution is not None:
            x_axis = self.wsolution(pixel_axis)
            new_x_axis = np.linspace(x_axis[0], x_axis[-1], len(data))
            tck = scipy.interpolate.splrep(x_axis, data, s=0)
            linearized_data = scipy.interpolate.splev(new_x_axis, tck, der=0)
            smoothed_linearized_data = signal.medfilt(linearized_data)
            if plots:
                fig6 = plt.figure(6)
                plt.xlabel('Wavelength (Angstrom)')
                plt.ylabel('Intensity (Counts)')
                fig6.canvas.set_window_title('Linearized Data')
                plt.plot(x_axis, data, color='k', label='Data')
                plt.plot(new_x_axis, linearized_data, color='r', linestyle=':', label='Linearized Data')
                plt.plot(new_x_axis, smoothed_linearized_data, color='m', alpha=0.5, label='Smoothed Linearized Data')
                plt.tight_layout()
                plt.legend(loc=3)
                plt.show()
                fig7 = plt.figure(7)
                plt.xlabel('Pixels')
                plt.ylabel('Angstroms')
                fig7.canvas.set_window_title('Wavelength Solution')
                plt.plot(x_axis, color='b', label='Non linear wavelength-axis')
                plt.plot(new_x_axis, color='r', label='Linear wavelength-axis')
                plt.tight_layout()
                plt.legend(loc=3)
                plt.show()

            linear_data = [new_x_axis, smoothed_linearized_data]
            return linear_data

    def add_wavelength_solution(self, new_header, spectrum, original_filename, evaluation_comment=None, index=None):
        """Add wavelength solution to the new FITS header

        Defines FITS header keyword values that will represent the wavelength solution in the header so that the image
        can be read in any other astronomical tool. (e.g. IRAF)

        Notes:
            This method also saves the data to a new FITS file, This should be in separated methods to have more control
            on either process.

        Args:
            new_header (object): An Astropy header object
            spectrum (Array): A numpy array that corresponds to the processed data
            original_filename (str): Original Image file name
            evaluation_comment (str): A comment with information regarding the quality of the wavelength solution
            index (int): If in one 2D image there are more than one target the index represents the target number.

        Returns:
            new_header (object): An Astropy header object. Although not necessary since there is no further processing

        """
        if evaluation_comment is None:
            rms_error, n_points, n_rejections = self.evaluate_solution()
            self.evaluation_comment = 'Lamp Solution RMSE = %s Npoints = %s, NRej = %s' % (rms_error,
                                                                                           n_points,
                                                                                           n_rejections)
            new_header['HISTORY'] = self.evaluation_comment
        else:
            new_header['HISTORY'] = evaluation_comment

        new_crpix = 1
        new_crval = spectrum[0][new_crpix - 1]
        new_cdelt = spectrum[0][new_crpix] - spectrum[0][new_crpix - 1]

        new_header['BANDID1'] = 'spectrum - background none, weights none, clean no'
        # new_header['APNUM1'] = '1 1 1452.06 1454.87'
        new_header['WCSDIM'] = 1
        new_header['CTYPE1'] = 'LINEAR  '
        new_header['CRVAL1'] = new_crval
        new_header['CRPIX1'] = new_crpix
        new_header['CDELT1'] = new_cdelt
        new_header['CD1_1'] = new_cdelt
        new_header['LTM1_1'] = 1.
        new_header['WAT0_001'] = 'system=equispec'
        new_header['WAT1_001'] = 'wtype=linear label=Wavelength units=angstroms'
        new_header['DC-FLAG'] = 0
        new_header['DCLOG1'] = 'REFSPEC1 = %s' % self.calibration_lamp

        # print(new_header['APNUM*'])
        if index is None:
            f_end = '.fits'
        else:
            f_end = '_%s.fits' % index
        # idea
        #  remove .fits from original_filename
        # define a base original name
        # modify in to _1, _2 etc in case there are multitargets
        # add .fits

        new_filename = self.args.destiny + self.args.output_prefix + original_filename.replace('.fits', '') + f_end

        fits.writeto(new_filename, spectrum[1], new_header, clobber=True)
        log.info('Created new file: %s', new_filename)
        # print new_header
        return new_header

    def display_onscreen_message(self, message='', color='red'):
        """Uses the fourth subplot to display a message

        Displays a warning message on the bottom right subplot of the interactive window. It is capable to break down
        the message in more than one line if necessary.

        Args:
            message (str): The message to be displayed
            color (str): Color name for the font's color

        """
        full_message = [message]
        if len(message) > 30:
            full_message = []
            split_message = message.split(' ')
            line_length = 0
            # new_line = ''
            e = 0
            for i in range(len(split_message)):
                # print(i, len(split_message))
                line_length += len(split_message[i]) + 1
                if line_length >= 30:
                    new_line = ' '.join(split_message[e:i])
                    # print(new_line, len(new_line))
                    full_message.append(new_line)
                    # new_line = ''
                    line_length = 0
                    e = i
                if i == len(split_message) - 1:
                    new_line = ' '.join(split_message[e:])
                    # print(new_line, len(new_line))
                    full_message.append(new_line)
        try:
            self.ax4.cla()
            self.ax4.relim()
            self.ax4.set_xticks([])
            self.ax4.set_yticks([])
            self.ax4.set_title('Message')
            for i in range(len(full_message)):
                self.ax4.text(0.05, 0.95 - i * 0.05,
                              full_message[i],
                              verticalalignment='top',
                              horizontalalignment='left',
                              transform=self.ax4.transAxes,
                              color=color,
                              fontsize=15)
            self.i_fig.canvas.draw()
        except:
            pass
        return

    def display_help_text(self):
        """Shows static text on the top right subplot

        This will print static help text on the top right subplot of the interactive window.

        Notes:
            This is really hard to format and having a proper GUI should help to have probably richer formatted text
            on the screen.

        """
        self.ax2.set_title('Help')
        self.ax2.set_xticks([])
        self.ax2.set_yticks([])

        self.ax2.text(1, 11, 'F1 or ?:', fontsize=13)
        self.ax2.text(1.46, 11, 'Prints Help.', fontsize=13)
        self.ax2.text(1, 10.5, 'F2 or f:', fontsize=13)
        self.ax2.text(1.46, 10.5, 'Fit Wavelength Solution to points', fontsize=13)
        self.ax2.text(1.46, 10, 'collected', fontsize=13)
        self.ax2.text(1, 9.5, 'F3 or a:', fontsize=13)
        self.ax2.text(1.46, 9.5, 'Find new lines, use when the solution', fontsize=13)
        self.ax2.text(1.46, 9, 'is already decent.', fontsize=13)
        self.ax2.text(1, 8.5, 'F4:', fontsize=13)
        self.ax2.text(1.46, 8.5, 'Evaluate Solution', fontsize=13)
        self.ax2.text(1, 8, 'F6 or l:', fontsize=13)
        self.ax2.text(1.46, 8, 'Linearize Data', fontsize=13)
        self.ax2.text(1, 7.5, 'd :', fontsize=13)
        self.ax2.text(1.46, 7.5, 'Delete Closest Point', fontsize=13)
        self.ax2.text(1, 7, 'Ctrl+d:', fontsize=13)
        self.ax2.text(1.5, 7, 'Delete all recorded marks. Requires', fontsize=13)
        self.ax2.text(1.5, 6.5, 'confirmation on the terminal.', fontsize=13)
        self.ax2.text(1, 6, 'Ctrl+z:', fontsize=13)
        self.ax2.text(1.5, 6, 'Remove all automatic added points.', fontsize=13)
        self.ax2.text(1.5, 5.5, 'Undo what F3 does.', fontsize=13)
        self.ax2.text(1, 5, 'Middle Button Click:', fontsize=13)
        self.ax2.text(1.46, 4.5, 'Finds and records line position', fontsize=13)
        self.ax2.text(1, 4, 'Enter :', fontsize=13)
        self.ax2.text(1.46, 4, 'Close Figure and apply wavelength', fontsize=13)
        self.ax2.text(1.46, 3.5, 'solution', fontsize=13)
        self.ax2.set_ylim((0, 12))
        self.ax2.set_xlim((0.95, 3.5))


class WavelengthSolution(object):
    """Contains all relevant information of a given wavelength solution


    """
    def __init__(self,
                 solution_type=None,
                 model_name=None,
                 model_order=0,
                 model=None,
                 ref_lamp=None,
                 eval_comment='',
                 header=None):
        self.dtype_dict = {None: -1, 'linear': 0, 'log_linear': 1, 'non_linear': 2}
        # if solution_type == 'non_linear' and model_name is not None:
        self.ftype_dict = {'chebyshev': 1,
                           'legendre': 2,
                           'cubic_spline': 3,
                           'linear_spline': 4,
                           'pixel_coords': 5,
                           'samples_coords': 6,
                           None: None}
        self.solution_type = solution_type
        self.model_name = model_name
        self.model_order = model_order
        self.wsolution = model
        self.reference_lamp = ref_lamp
        self.evaluation_comment = eval_comment
        self.spectral_dict = self.set_spectral_features(header)
        # self.aperture = 1  # aperture number
        # self.beam = 1  # beam
        # self.dtype = self.dtype_dict[solution_type]  # data type
        # self.dispersion_start = 0  # dispersion at start
        # self.dispersion_delta = 0  # dispersion delta average
        # self.pixel_number = 0  # pixel number
        # self.doppler_factor = 0  # doppler factor
        # self.aperture_low = 0  # aperture low (pix)
        # self.aperture_high = 0  # aperture high
        # # funtions parameters
        # self.weight = 1
        # self.zeropoint = 0
        # self.ftype = self.ftype_dict[model_name]  # function type
        # self.forder = model_order  # function order
        # self.pmin = 0  # minimum pixel value
        # self.pmax = 0  # maximum pixel value
        # self.fpar = []  # function parameters

    @staticmethod
    def set_spectral_features(header):
        """Creates dictionary that defines the instrument configuration

        Both Blue and Red Camera produce slightly different FITS headers being the red camera the one that provides
        more precise and better information. This method will recognize the camera and create the dictionary accordingly

        Args:
            header:

        Returns:

        """
        if header is None:
            log.error('Header has not been parsed')
        else:
            try:
                log.debug('Red Camera')
                spectral_dict = {'camera': 'red',
                                 'grating': header['GRATING'],
                                 'roi': header['ROI'],
                                 'filter1': header['FILTER'],
                                 'filter2': header['FILTER2'],
                                 'slit': header['SLIT'],
                                 'instconf': header['INSTCONF'],
                                 'wavmode': header['WAVMODE'],
                                 'cam_ang': header['CAM_ANG'],
                                 'grt_ang': header['GRT_ANG']}

                # for key in dict.keys():
                # print(key, dict[key])
                return spectral_dict
            except KeyError:
                log.debug('Blue Camera')
                spectral_dict = {'camera': 'blue',
                                 'grating': header['GRATING'],
                                 'ccdsum': header['CCDSUM'],
                                 'filter1': header['FILTER'],
                                 'filter2': header['FILTER2'],
                                 'slit': header['SLIT'],
                                 'serial_bin': header['PARAM18'],
                                 'parallel_bin': header['PARAM22'],
                                 'cam_ang': header['CAM_ANG'],
                                 'grt_ang': header['GRT_ANG']}

                # for key in dict.keys():
                # print(key, dict[key])
                return spectral_dict

    def check_compatibility(self, header=None):
        """Checks compatibility of new data

        A wavelength solution is stored as an object (this class). As an attribute of this class there is a dictionary
        that contains critical parameters of the spectrum with which the wavelength solution was found. In order to
        apply the same solution to another spectrum its header has to be parsed and then the parameters are compared
        in a hierarchic way.

        Args:
            header (object): FITS header object from astropy.io.fits

        Returns:
            True or False

        """
        if header is not None:
            new_dict = self.set_spectral_features(header)
            for key in new_dict.keys():
                if self.spectral_dict['camera'] == 'red':
                    if key in ['grating', 'roi', 'instconf', 'wavmode'] and new_dict[key] != self.spectral_dict[key]:
                        log.debug('Keyword: %s does not Match', key.upper())
                        log.info('%s - Solution: %s - New Data: %s', key.upper(), self.spectral_dict[key], new_dict[key])
                        return False
                    elif key in ['cam_ang',  'grt_ang'] and abs(new_dict[key] - self.spectral_dict[key]) > 1:
                        log.debug('Keyword: %s Lamp: %s Data: %s',
                                  key,
                                  self.spectral_dict[key],
                                  new_dict[key])
                        log.info('Solution belong to a different Instrument Configuration.')
                        return False
                    # else:
                    #     return True
                elif self.spectral_dict['camera'] == 'blue':
                    if key in ['grating', 'ccdsum', 'serial_bin', 'parallel_bin']and new_dict[key] != self.spectral_dict[key]:
                        log.debug('Keyword: %s does not Match', key.upper())
                        log.info('%s - Solution: %s - New Data: %s',
                                 key.upper(),
                                 self.spectral_dict[key],
                                 new_dict[key])
                        return False
                    elif key in ['cam_ang',  'grt_ang'] and abs(float(new_dict[key]) - float(self.spectral_dict[key])) > 1:
                        log.debug('Keyword: %s Lamp: %s Data: %s',
                                  key,
                                  self.spectral_dict[key],
                                  new_dict[key])
                        log.info('Solution belong to a different Instrument Configuration.')
                        return False
                    # else:
                    #     return True
            return True
        else:
            log.error('Header has not been parsed')
            return False

    def linear_solution_string(self, header):
        pass


if __name__ == '__main__':
    log.error('This can not be run on its own.')
