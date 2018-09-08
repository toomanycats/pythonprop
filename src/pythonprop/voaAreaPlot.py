#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# File: voaAreaPlot.py
#
# Copyright (c) 2008 J.Watson
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#

import argparse
import datetime
import gettext
import io
import locale
import math
import os
import re
import sys
import zipfile

import matplotlib
import matplotlib.pyplot as plt

import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import matplotlib.ticker as mticker
from matplotlib.colors import ListedColormap
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
from matplotlib.font_manager import FontProperties
from mpl_toolkits.axes_grid1 import make_axes_locatable


import numpy as np
#import numpy.ma as ma

from .hamlocation import HamLocation
from .voaAreaRect import VOAAreaRect
from .voaFile import VOAFile
from .voaPlotWindow import *
from .vgzArchive import get_base_filename

GETTEXT_DOMAIN = 'voacapgui'
LOCALE_PATH = os.path.join(os.path.realpath(os.path.dirname(sys.argv[0])), 'po')

langs = []
lc, enc = locale.getdefaultlocale()
if lc:
    langs = [lc]
language = os.environ.get('LANGUAGE', None)
if language:
    langs += language.split(':')
gettext.bindtextdomain(GETTEXT_DOMAIN, LOCALE_PATH)
gettext.textdomain(GETTEXT_DOMAIN)
lang = gettext.translation(GETTEXT_DOMAIN, LOCALE_PATH, languages=langs, fallback=True)
lang.install()

class VOAAreaPlot:

    IMG_TYPE_DICT  = { \
        1:{'plot_type':'MUF', 'title':_('Maximum Usable Frequency (MUF)'), 'min':2, 'max':30, 'y_labels':(2, 5, 10, 15, 20, 25, 30), 'formatter':'frequency_format', 'first_char':27, 'last_char':32}, \
        2:{'plot_type':'REL', 'title':_('Circuit Reliability (%)'), 'min':0, 'max':1, 'y_labels':(0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1), 'formatter':'percent_format', 'first_char':98, 'last_char':104}, \
        3:{'plot_type':'SNR', 'title':_('SNR at Receiver (dB)'), 'min':20, 'max':70, 'y_labels':(20, 30, 40, 50, 60, 70), 'formatter':'SNR_format', 'first_char':86, 'last_char':92}, \
        4:{'plot_type':'SNRXX', 'title':_('SNRxx'), 'min':0, 'max':100, 'y_labels':(0, 20, 40, 60, 80, 100), 'formatter':'SNR_format', 'first_char':130, 'last_char':134}, \
        5:{'plot_type':'SDBW', 'title':_('Signal Power'), 'min':-160, 'max':-40, 'y_labels':(-160, -140, -120, -100, -80, -60, -40), 'formatter':'SDBW_format', 'first_char':74, 'last_char':80}, \
        6:{'plot_type':'SMETESNRXXR', 'title':_('S-Meter'), 'min':-151.18, 'max':-43.01, 'y_labels':(-151.18, -139.13, -127.09, -115.05, -103.01, -83.01, -63.01, -43.01), 'formatter':'SMETER_format', 'first_char':74, 'last_char':80} }

    COLOUR_MAPS = [ _('autumn'), _('bone'), _('cool'), _('copper'), _('gray'), \
                _('hot'), _('hsv'), _('jet'), _('pink'), _('spring'), \
                _('summer'), _('winter') ]

    default_font = {'family' : 'sans-serif'}
    show_subplot_frame = True

    def __init__(self, in_file,
                    vg_files = [1],
                    data_type = 1,
                    color_map = 'portland',
                    face_colour = "white",
                    filled_contours = False,
                    plot_contours = False,
                    plot_meridians = True,
                    plot_parallels = True,
                    plot_nightshade = True,
                    resolution = 'c',
                    #points_of_interest = [],
                    save_file = '',
                    run_quietly = False,
                    dpi = 150,
                    parent = None,
                    datadir=None):

        self.run_quietly = run_quietly
        self.dpi=float(dpi)

        self.datadir = datadir

        try:
            plot_parameters = VOAFile((in_file))
            plot_parameters.parse_file()
        except zipfile.BadZipFile as e:
            if parent is None:
                print("Invalid .vgz file")
                sys.exit(1)

        img_grid_size = plot_parameters.get_gridsize()
        self.image_defs = VOAAreaPlot.IMG_TYPE_DICT[int(data_type)]

        """
        if len(points_of_interest) > 0:
            self.points_of_interest.extend(points_of_interest)
        """
        
        imageBuf = np.zeros([img_grid_size, img_grid_size], float)

        area_rect = plot_parameters.get_area_rect()

        # The checks ought to be performed in the area_rect.
        # Do a few basic sanity checks #
        #if ( (area_rect.get_sw_lon() < -180) or (area_rect.get_ne_lon() > 180.0) or (area_rect.get_sw_lat() < -90) or (area_rect.get_ne_lat() > 90.0) ):
        #    print "Input file latitudes/longitudes are out of range"
        #    print "-180 < Latitude < 180.0, -90 < Longitude < 90"
        #    sys.exit(1)
        #if ( (area_rect.get_sw_lon() == area_rect.get_ne_lon()) or (area_rect.get_sw_lat() == area_rect.get_ne_lat()) ):
        #    print "Input file latitudes/longitudes are the same"
        #    print "-180 < Latitude < 180.0, -90 < Longitude < 90"
        #    sys.exit(1)

        #colString = 'matplotlib.cm.'+color_map
        #colMap = eval(colString)
        portland = ListedColormap(["#0C3383", "#0b599b","#0a7fb4","#57a18f","#bec255","#f2c438","#f2a638","#ef8235","#e4502a","#d91e1e"])
        plt.register_cmap(name='portland', cmap=portland)
        colMap = color_map


        self.subplots = []
        number_of_subplots = len(vg_files)

        matplotlib.rcParams['axes.edgecolor'] = 'gray'
        matplotlib.rcParams['axes.facecolor'] = 'white'
        matplotlib.rcParams['figure.facecolor'] = face_colour
        #matplotlib.rcParams['figure.figsize'] = (6, 10)
        matplotlib.rcParams['figure.subplot.hspace'] = 0.45
        matplotlib.rcParams['figure.subplot.wspace'] = 0.35
        #matplotlib.rcParams['figure.subplot.left'] = 0.8
        #matplotlib.rcParams['figure.subplot.right'] = 0.85
        colorbar_fontsize = 12

        if number_of_subplots <= 1:
            num_rows = 1
            self.main_title_fontsize = 24
            matplotlib.rcParams['legend.fontsize'] = 12
            matplotlib.rcParams['axes.labelsize'] = 12
            matplotlib.rcParams['axes.titlesize'] = 10
            matplotlib.rcParams['xtick.labelsize'] = 10
            matplotlib.rcParams['ytick.labelsize'] = 10
            matplotlib.rcParams['figure.subplot.top'] = 0.8 # single figure plots have a larger title so require more space at the top.
        elif ((number_of_subplots >= 2) and (number_of_subplots <= 6 )):
            num_rows = 2
            self.main_title_fontsize = 18
            matplotlib.rcParams['legend.fontsize'] = 10
            matplotlib.rcParams['axes.labelsize'] = 10
            matplotlib.rcParams['axes.titlesize'] = 11
            matplotlib.rcParams['xtick.labelsize'] = 8
            matplotlib.rcParams['ytick.labelsize'] = 8
            #self.x_axes_ticks = P.arange(0,25,4)
        else:
            num_rows = 3
            self.main_title_fontsize = 10
            matplotlib.rcParams['legend.fontsize'] = 8
            matplotlib.rcParams['axes.labelsize'] = 8
            matplotlib.rcParams['axes.titlesize'] = 10
            matplotlib.rcParams['xtick.labelsize'] = 6
            matplotlib.rcParams['ytick.labelsize'] = 6
            #self.x_axes_ticks = P.arange(0,25,4)

        num_cols = int(math.ceil(float(number_of_subplots)/float(num_rows)))

        plt.subplots_adjust(left=0, wspace=0.1)
        
        #https://github.com/SciTools/cartopy/issues/899
        proj=ccrs.PlateCarree()
        fig, axes = plt.subplots(num_rows, num_cols, squeeze=False, subplot_kw=dict(projection=proj))

        self.main_title_label = fig.suptitle(str(self.image_defs['title']), fontsize=self.main_title_fontsize)

        # Hide any unused subplots
        # https://stackoverflow.com/questions/10035446/how-can-i-make-a-blank-subplot-in-matplotlib
        for plot_idx in range(number_of_subplots, (num_rows*num_cols)):
            col_idx = int(plot_idx/num_cols)
            row_idx = plot_idx%num_cols
            axes[col_idx, row_idx].set_visible(False)

        for plot_idx, vg_file in enumerate(vg_files):
            col_idx = int(plot_idx/num_cols)
            row_idx = plot_idx%num_cols

            points = np.zeros([img_grid_size,img_grid_size], float)

            lons = np.arange(area_rect.get_sw_lon(), area_rect.get_ne_lon()+0.001,(area_rect.get_ne_lon()-area_rect.get_sw_lon())/float(img_grid_size-1))
            lons[-1] = min(180.0, lons[-1])
            lats = np.arange(area_rect.get_sw_lat(), area_rect.get_ne_lat()+0.001,(area_rect.get_ne_lat()-area_rect.get_sw_lat())/float(img_grid_size-1))
            lats[-1] = min(90.0, lats[-1])

            axes[col_idx, row_idx].label_outer()
            if in_file.endswith('.vgz'):
                base_filename = get_base_filename(in_file)
                zf = zipfile.ZipFile(in_file)
                vgFile = io.TextIOWrapper(zf.open("{:s}.vg{:d}".format(base_filename, vg_file)), 'utf-8')
            else:
                vgFile = open("{:s}.vg{:d}".format(os.path.splitext(in_file)[0], vg_file))
            pattern = re.compile(r"[a-z]+")

            for line in vgFile:
                match = pattern.search( line )
                if not match:
                    value = float(line[int(self.image_defs['first_char']):int(self.image_defs['last_char'])])
                    # TODO Does this need to be normalised here if it's also being done in the plot?
                    value = max(self.image_defs['min'], value)
                    value = min(self.image_defs['max'], value)
                    points[int(line[3:6])-1][int(line[0:3])-1] = value
            vgFile.close()
            if 'zf' in locals():
                zf.close()
            
            def resize_colorbar(event):
                print('resizing colorbar')
                plt.draw()
                # left, bottom, width, height
                if number_of_subplots == num_cols*num_rows:
                    print('doing 1x1')
                    top_posn = axes[0, num_cols-1].get_position(original=False)
                    print(top_posn)
                    bottom_posn = axes[col_idx, row_idx].get_position(original=False)
                    print(bottom_posn.height)
                    cb_height = top_posn.y0 + top_posn.height - bottom_posn.y0
                    print(cb_height)
                    cbar_ax.set_position([top_posn.x0 + top_posn.width + 0.01, bottom_posn.y0, 0.02, cb_height])
                else:
                    posn = axes[col_idx][row_idx+1].get_position()
                    # fig.subplotpars.hspace, fig.subplotpars.wspace
                    print(fig.subplotpars.hspace)
                    print(fig.subplotpars.wspace)
                    cbar_ax.set_position([posn.x0, posn.y0, 0.02, posn.height])
            
            #fig.canvas.mpl_connect('resize_event', resize_colorbar)

            axes[col_idx, row_idx].coastlines()

            lons, lats  = np.meshgrid(lons, lats)
            points = np.clip(points, self.image_defs['min'], self.image_defs['max'])

            axes[col_idx, row_idx].set_extent([area_rect.get_sw_lon(),
                                                area_rect.get_ne_lon(),
                                                area_rect.get_sw_lat(),
                                                area_rect.get_ne_lat()], ccrs.PlateCarree())

            if (filled_contours):
                im = axes[col_idx, row_idx].contourf(lons, lats, points, self.image_defs['y_labels'],
                    cmap = colMap,
                    transform=ccrs.PlateCarree())
                plot_contours = True
            else:
                im = axes[col_idx, row_idx].pcolormesh(lons, lats, points,
                    vmin = self.image_defs['min'],
                    vmax = self.image_defs['max'],
                    cmap = colMap,
                    transform=ccrs.PlateCarree())

            if plot_contours:
                ct = axes[col_idx, row_idx].contour(lons, lats, points, self.image_defs['y_labels'][1:],
                    linestyles='solid',
                    linewidths=0.5,
                    colors='k',
                    vmin=self.image_defs['min'],
                    vmax=self.image_defs['max'],
                    transform=ccrs.PlateCarree())
            #######################
            # Plot greyline
            #######################
            if plot_nightshade:
                self.fill_dark_side(axes[col_idx, row_idx],
                            time=plot_parameters.get_daynight_datetime(vg_files[plot_idx]-1),
                            color='black',
                            alpha=0.4)

            ##########################
            # Points of interest
            ##########################
            """
            for location in self.points_of_interest:
                if area_rect.contains(location.get_latitude(), location.get_longitude()):
                    xpt,ypt = m(location.get_longitude(),location.get_latitude())
                    ax.plot([xpt],[ypt],'ro')
                    ax.text(xpt+100000,ypt+100000,location.get_name())
            """
            gl = axes[col_idx, row_idx].gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                  linewidth=1, color='black', alpha=0.75)
            gl.xlabels_top = False
            gl.xlabels_bottom = False
            gl.ylabels_left = False
            gl.ylabels_right = False
            gl.xlines = False
            gl.ylines = False
            if plot_meridians:
                if (area_rect.get_lon_delta() <= 90.0):
                    meridians = np.arange(-180, 190.0, 10.0)
                elif (area_rect.get_lon_delta() <= 180.0):
                    meridians = np.arange(-180.0, 210.0, 30.0)
                else:
                    meridians = np.arange(-180, 240.0, 60.0)
                gl.xlines = True
                gl.xlabels_bottom = True
                gl.xformatter = LONGITUDE_FORMATTER
                gl.xlocator = mticker.FixedLocator(meridians)

            if plot_parallels:
                if (area_rect.get_lat_delta() <= 90.0):
                    parallels = np.arange(-90.0, 120.0, 60.0)
                else:
                    parallels = np.arange(-90.0, 120.0, 30.0)
                gl.ylines = True
                gl.ylabels_right = True
                gl.yformatter = LATITUDE_FORMATTER
                gl.ylocator = mticker.FixedLocator(parallels)

            #add a title
            title_str = plot_parameters.get_plot_description_string(vg_files[plot_idx]-1, self.image_defs['plot_type'])
            if number_of_subplots == 1:
                title_str = plot_parameters.get_plot_description_string(vg_files[plot_idx]-1, self.image_defs['plot_type'])
                title_str = title_str + "\n" + plot_parameters.get_detailed_plot_description_string(vg_files[plot_idx]-1)
            else :
                title_str = plot_parameters.get_minimal_plot_description_string(vg_files[plot_idx]-1, self.image_defs['plot_type'])
            self.subplot_title_label = axes[col_idx, row_idx].set_title(title_str)


        #print self.image_defs['y_labels']
        """
        for t in self.cb_ax.get_yticklabels():
            t.set_fontsize(colorbar_fontsize)
        """
        # Add the colorbar axes anywhere in the figure. Its position will be
        # re-calculated at each figure resize.
        #cbar_ax = fig.add_axes([0, 0, 0.1, 0.1])
        divider = make_axes_locatable(axes[col_idx, row_idx])
        cbar_ax = divider.new_horizontal(size="3%", pad=0.1, axes_class=plt.Axes)
        cbar_ax = fig.add_axes(cbar_ax)
        cbar_ax.tick_params(labelsize=10)
        #fig.colorbar(im, cax=cbar_ax)

        #fig.subplots_adjust(hspace=0, wspace=0, top=0.925, left=0.05)

        fig.colorbar(im,
            cax=cbar_ax,
            ticks = self.image_defs['y_labels'],
            format = mticker.FuncFormatter(eval('self.'+self.image_defs['formatter'])))

        gtk_canvas = FigureCanvas(fig)
        gtk_canvas.draw()
        #fig.canvas.mpl_connect('resize_event', resize_colorbar)
        #fig.canvas.show()

        if save_file :
            #resize_colorbar(None)
            plt.savefig(save_file, dpi=self.dpi, facecolor=fig.get_facecolor(), edgecolor='none')
            #plt.savefig(save_file, dpi=self.dpi, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')

        #todo this ought to a command line param
        if not self.run_quietly:
            dia = VOAPlotWindow('pythonProp - ' + self.image_defs['title'], gtk_canvas, parent=parent, datadir=self.datadir)
        return

    """
    The following routine is taken from;
    https://scitools.org.uk/cartopy/docs/latest/gallery/aurora_forecast.html
    """
    def sun_pos(self, dt=None):
        """This function computes a rough estimate of the coordinates for
        the point on the surface of the Earth where the Sun is directly
        overhead at the time dt. Precision is down to a few degrees. This
        means that the equinoxes (when the sign of the latitude changes)
        will be off by a few days.

        The function is intended only for visualization. For more precise
        calculations consider for example the PyEphem package.

        Parameters
        ----------
        dt: datetime
            Defaults to datetime.utcnow()

        Returns
        -------
        lat, lng: tuple of floats
            Approximate coordinates of the point where the sun is
            in zenith at the time dt.

        """
        if dt is None:
            dt = datetime.datetime.utcnow()

        axial_tilt = 23.4
        ref_solstice = datetime.datetime(2016, 6, 21, 22, 22)
        days_per_year = 365.2425
        seconds_per_day = 24*60*60.0

        days_since_ref = (dt - ref_solstice).total_seconds()/seconds_per_day
        lat = axial_tilt*np.cos(2*np.pi*days_since_ref/days_per_year)
        sec_since_midnight = (dt - datetime.datetime(dt.year, dt.month, dt.day)).seconds
        lng = -(sec_since_midnight/seconds_per_day - 0.5)*360
        return lat, lng

    """
    The following routine is taken from;
    https://scitools.org.uk/cartopy/docs/latest/gallery/aurora_forecast.html
    """
    def fill_dark_side(self, ax, time=None, *args, **kwargs):
        """
        Plot a fill on the dark side of the planet (without refraction).

        Parameters
        ----------
            ax : Matplotlib axes
                The axes to plot on.
            time : datetime
                The time to calculate terminator for. Defaults to datetime.utcnow()
            **kwargs :
                Passed on to Matplotlib's ax.fill()

        """
        lat, lng = self.sun_pos(time)
        pole_lng = lng
        if lat > 0:
            pole_lat = -90 + lat
            central_rot_lng = 180
        else:
            pole_lat = 90 + lat
            central_rot_lng = 0

        rotated_pole = ccrs.RotatedPole(pole_latitude=pole_lat,
                                        pole_longitude=pole_lng,
                                        central_rotated_longitude=central_rot_lng)

        x = np.empty(360)
        y = np.empty(360)
        x[:180] = -90
        y[:180] = np.arange(-90, 90.)
        x[180:] = 90
        y[180:] = np.arange(90, -90., -1)

        ax.fill(x, y, transform=rotated_pole, **kwargs)

    def get_cb_axes(self):
        bbox = self.subplots[0].get_window_extent()
        axis_upper_y = bbox.inverse_transformed(fig.transFigure).ymax
        bbox = self.subplots[-1].get_window_extent()
        axis_lower_y = bbox.inverse_transformed(fig.transFigure).ymin
        return [0.87, axis_lower_y, 0.02, axis_upper_y-axis_lower_y]

    def percent_format(self, x, pos):
        return '%(percent)3d%%' % {'percent':x*100}

    def SNR_format(self, x, pos):
        return '%3ddB' % x

    def SDBW_format(self, x, pos):
        return '%3ddBW' % x

    """
    The values below are derived from material
    presented at http://www.voacap.com/s-meter.html
    """
    def SMETER_format(self, x, pos):
        S_DICT = {-151.18:'S1', -145.15:'S2', -139.13:'S3', -133.11:'S4', -127.09:'S5', \
                    -121.07:'S6', -115.05:'S7', -109.03:'S8', -103.01:'S9', -93.01:'S9+10dB', \
                    -83.01:'S9+20dB', -73.01:'S9+30dB', -63.01:'S9+40dB', -53.01:'S9+50dB', -43.01:'S9+60dB'}
        if x in S_DICT:
        	return '%s' % S_DICT[x]
            #return _('%(value)ddBW (%(s_value)s)') %{'value':x, 's_value':S_DICT[x]}
        else : return '%3d' % x


    def frequency_format(self, x, pos):
        return '%2dMHz' % x


    def default_format(self, x, pos):
        return '%d' % x


def main(in_file, datadir=None):
    parser = argparse.ArgumentParser(description="Plot voacap area data")
    parser.add_argument("in_file",
        help = _("Path to the .voa file.  This should be in the same directory as the associated .vgx files."))
    
    parser.add_argument("-c", "--contours",
        dest = "plot_contours",
        action = "store_true",
        default = False,
        help = _("Enables contour plotting.") )

    parser.add_argument("-d", "--datatype",
        dest="data_type",
        default=1,
        help=_("DATATYPE - an integer number representing the data to plot. Valid values are 1 (MUF), 2 (REL) and 3 3 (SNR) 4 (SNRxx), 5 (SDBW) and 6 (SDBW - formatted as S-Meter values).  Default value is 1 (MUF).") )

    parser.add_argument("-f", "--filled-contour",
        dest = "plot_filled_contours",
        action = "store_true",
        default = False,
        help = _("Produces a filled contour plot.") )

    parser.add_argument("-i", "--meridian",
        dest="plot_meridians",
        action="store_true",
        default=False,
        help=_("Plot meridians."))
        
    parser.add_argument("-k", "--background",
        dest="face_colour",
        default='white',
        help=_("Specify the colour of the background. Any legal HTML color specification is supported e.g '-k red', '-k #eeefff' (default = white)"))

    parser.add_argument("-l", "--parallels",
        dest="plot_parallels",
        action="store_true",
        default=False,
        help=_("Plot meridians."))

    parser.add_argument("-m", "--cmap",
        dest = "color_map",
        default = 'jet',
        choices = [ 'autumn', 'bone', 'cool', 'copper', 'gray', \
                'hot', 'hsv', 'jet', 'pink', 'spring','summer', 'winter', 'portland' ],
        help=_("COLOURMAP - may be one of 'autumn', 'bone', 'cool', 'copper', 'gray', 'hot', 'hsv', 'jet', 'pink', 'spring', 'summer', 'winter' or 'portland'.  Default = 'jet'"))
    """
    parser.add_argument("-n", "--interest",
        dest = "poi_file",
        default = '',
        help = "poi_file is a text file with points to plot on the map.")
    """
    parser.add_argument("-o", "--outfile",
        dest="save_file",
        help="Save to FILE.",
        metavar="FILE")

    parser.add_argument("-q", "--quiet",
        dest="run_quietly",
        action="store_true",
        default=False,
        help=_("Process quietly (don't display plot on the screen)"))

    parser.add_argument("-r", "--resolution",
        dest="resolution",
        default = 'c',
        choices = ['c', 'l', 'i', 'h', 'f'],
        help=_("RESOLUTION - may be one of 'c' (crude), 'l' (low), 'i' (intermediate), 'h' (high), 'f' (full)"))

    parser.add_argument("-s", "--size",
        dest="dpi",
        default=150,
        help=_("Dots per inch (dpi) of saved file."))

    parser.add_argument("-t", "--terminator",
        dest="plot_nightshade",
        action="store_true",
        default = False,
        help=_("Plot day/night regions on the map"))

    parser.add_argument("-v", "--vg_files",
        dest = "vg_files",
        default = '1',
        help=_("VG_FILES number of plots to process, e.g '-v 1,3,5,6' or use '-v a' to print all plots.") )

    #args = parser.parse_intermixed_args()
    args = parser.parse_args()

    #points_of_interest = []
    vg_files = []
    """
    if args.poi_file:
        try:
            f = open(args.poi_file, 'r')
            for line in f:
                if len(line) > 3:
                    tokens = line.strip().split(',', 2)
                    #lat = float(tokens[1].strip())
                    #lon = float(tokens[0].strip())
                    #name = tokens[2].strip()
                    points_of_interest.append(HamLocation(lat = float(tokens[1].strip()),
                                                lon = float(tokens[0].strip()),
                                                name = tokens[2].strip()))
        except:
            print(_("Error reading points of interest file: %s") % args.poi_file)
            print(sys.exc_info()[0])
            points_of_interest = []
    else:
        points_of_interest = []
    """
    if args.data_type:
        if int(args.data_type) not in VOAAreaPlot.IMG_TYPE_DICT:
            print(_("Unrecognised plot type: Defaulting to MUF"))
            args.dataType = 1

    if args.vg_files:
        args.vg_files.strip()
        if args.vg_files == 'a':
            #'all' option see if the file exists and add it to the list
            for file_num in range (1, 13):
                if os.path.exists(in_file+'.vg'+str(file_num)):
                    print(_("found: "),(in_file+'.vg'+str(file_num)))
                    vg_files.append(file_num)
        else:
            try:
                if args.vg_files.find(','):
                    vg_files = args.vg_files.split(',')
                else:
                    vg_files = [args.vg_files]

                for i in range(0, len(vg_files)):
                    try:
                        vg_files[i] = int(vg_files[i])
                    except:
                        vg_files.pop(i)
                if len(vg_files) == 0:
                    print(_("Error reading vg files (1), resetting to '1'"))
                    vg_files = [1]
            except:
                print(_("Error reading vg files, resetting to '1'"))
                vg_files = [1]
        #print(_("The following %d files have been selected: ") % (len(vg_files)), vg_files)

    VOAAreaPlot(in_file,
                    vg_files = vg_files,
                    data_type = args.data_type,
                    color_map = args.color_map,
                    face_colour = args.face_colour,
                    filled_contours = args.plot_filled_contours,
                    plot_contours = args.plot_contours,
                    plot_meridians = args.plot_meridians,
                    plot_parallels = args.plot_parallels,
                    plot_nightshade = args.plot_nightshade,
                    resolution = args.resolution,
                    #points_of_interest = points_of_interest,
                    save_file = args.save_file,
                    run_quietly = args.run_quietly,
                    dpi = args.dpi,
                    datadir=datadir)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        main(sys.argv[-1])
    else:
        print('voaAreaPlot error: No data file specified')
        print('voaAreaPlot [options] filename')
        sys.exit(1)
