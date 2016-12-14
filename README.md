# Goodman High Throughput Spectrograph
**WARNING** This code is being developed and is not ready for
scientific use. Always check the branch **other than master**.
 
 If you are interested in this software 

The Goodman High Throughput Spectrograph is an imaging spectrograph
 if you wish to know more about the instrument please check the 
 [SOAR website](http://www.ctio.noao.edu/soar/content/goodman-high-throughput-spectrograph)
 
To see full documentation please go to the GitHub hosted site for [Goodman](https://simontorres.github.io/goodman/)

## What is contained in this package?

This repository contains tools for spectroscopy, but after the data is 
reduced, i.e. bias and flat corrected, for that part please use 
[David Sanmartim's](https://github.com/dsanmartim/goodman_ccdreduction) github repository.

#### redspec.py  
 Spectra extraction and wavelength calibration

## How to use it?

Place the files in your system's **$PATH** variable and then you can call it from anywhere in your system

## Important Notes

Needs python2.7 and a newer version of numpy1.12.0 otherwise there will
be problems with numpy.linspace

# Development Status

The pipeline is organized in three files (this might increase):

## redspec.py
This module basically organizes the data and sort of makes a plan for processing the night.

- [x] Ability to operate Blue and Red camera. (transparent for the user)
- [x] Read and Parse Arguments (uses argparse). Also checks for consistency.
- [x] Define Night Class. Reads header information from and creates a class that contain important _night_ information.
- [ ] Set mode to be used at the telescope (while observing). Is not defined yet if this is really necessary.
- [ ] Organize Full Night. Edits the Night Class by adding SienceObject wich will be defined depending on one of the following modes.
  * [x] Mode 0: One lamp for all targets in the night.
  * [x] Mode 1: One or more lamps per science target.
  * [ ] Mode 2: A text file defines what lamps will be used in what targets.
  * [ ] Mode 3: No lamps, solution will be calculated from skylines.

For every ScienceObject the module Process is called wich will do the actual work.

## process.py
In order to work this needs the source's path and a ScienceObject (class).

- [x] Read target data and header.
- [ ] For any of the modes that use comparison lamps:
  * [x] Read lamps data and header
  * [x] Identify single targets (one target in the slit)
  * [ ] Identify multiple targets (most of the work done but not tested recently)
  * [x] Trace spectrum.
  * [x] Extract data.
    - [x] Normal Extraction
    - [ ] Optimal extraction
- [ ] Nothing done for the case when skylines will be used as wavelength calibrators.

After the extraction of the spectrum it will be packed and then parsed to the next module.

## wavelengthCalibration.py
**TODO**: find a better name

- [x] Interpret science pack (parsed from previous module)
- [ ] Automatic Wavelength Calibration
  - [x] Identify lines
  - [x] Estimate wavelength solution from information in the header
  - [ ] Find wavelength solution (can be tricky and will take some time)
- [ ] Automatic Wavelength Calibration by template (can also be tricky since dispersion is not linear)
- [x] Find wavelength solution interactively.
- [x] Linearize spectrum
- [x] Put wavelength solution in the header and write down files.


# Documentation Status Estimate
In **Bold** are the classes and in _italics_ are their respective methods.
The values presented here are based only on my personal perception and satisfaction about the status of progress
The class percentage doesn't take in account the completeness of 

## redspec.py
- **MainApp** 100%

  - _  __init__ _ 0%
  - _get_args_  100%
  - _set_night_ 100%
  - _organize_full_night_ 100%
  - _convert_time_ 100%
  - _ra_dec_to_deg_ 100%
  - _print_spacers_ 100% - Most likely will be removed
  - _print_progress_ 100% - Most likely will be removed

- **Night** 70%
  - _  __init__ _ 0%
  - _add_sci_ 100%
  - _add_lamp_ 100%
  - _add_sci_object_ 100%
  - _is_telescope_ 100%
  
- **ScienceObject** 100%
  - _  __init__ _ 0%
  - _add_lamp_ 100%
  - _print_all_ 100%
 

## process.py
- **Process** 100%

  - _  __init__ _ 0%
  - _identify_spectra_ 100%
  - _trace_ 100%
  - _mask_ 100%
  - _extract_ 100%

- **IdentifiedTarget** 50%
  - _  __init__ _ 0%
  
  
## wavelength.py
- **WavelengthCalibration** 0%
  
  - _ __init__ _ 0%
  - _ __call__ _ 0%
  - _get_wsolution_ 0%
  - _get_calibration_lamp_ 0%
  - _get_wavelength_solution_ 0%
  - _get_line_limits_ 100%
  - _get_line_centers_ 100%
  - _get_spectral_characteristics_ 0%
  - _interpolate_ 100%
  - _recenter_line_by_model_ 0%
  - _recenter_line_by_data_ 0%
  - _predicted_wavelength_ 0%
  - _automatic_wavelength_solution_ 0%
  - _pixel_axis_cross_correlate_ 0%
  - _interactive_wavelength_solution_ 0%
  - _on_click_ 0%
  - _find_more_lines_ 0%
  - _update_clicks_plot_ 0%
  - _plot_raw_over_reference_ 0%
  - _evaluate_solution_ 0%
  - _fit_pixel_to_wavelength_ 0%
  - _linearize_spectrum_ 0%
  - _add_wavelength_solution_ 0%  
  