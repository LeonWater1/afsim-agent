# ****************************************************************************
# CUI
#
# The Advanced Framework for Simulation, Integration, and Modeling (AFSIM)
#
# The use, dissemination or disclosure of data in this file is subject to
# limitation or restriction. See accompanying README and LICENSE for details.
# ****************************************************************************
# GNUPLOT plotting commands
# Plot the vcd's. X axis should be in 'nm' and Y axis in 'kft'
# load "vcdplot.cmd"

# lt is for color of the points: -1=black 1=red 2=grn 3=blue 4=purple 5=aqua 6=brn 7=orange 8=light-brn
# pt gives a particular point type: 1=diamond 2=+ 3=square 4=X 5=triangle 6=*
# postscipt: 1=+, 2=X, 3=*, 4=square, 5=filled square, 6=circle,
#            7=filled circle, 8=triangle, 9=filled triangle, etc.


reset
set grid
set size square
set pointsize 0.3
plot "ft_nodetect_data.dat" using 2:1 w p lt 1 pt 5, \
     "ft_detect_data.dat" using 2:1 w p lt 2 pt 5, \
     "ft_track_data.dat" using 2:1 w p lt 3 pt 5 \
