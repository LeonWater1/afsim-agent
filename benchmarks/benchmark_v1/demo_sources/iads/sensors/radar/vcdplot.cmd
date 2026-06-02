# ****************************************************************************
# CUI
#
# The Advanced Framework for Simulation, Integration, and Modeling (AFSIM)
#
# The use, dissemination or disclosure of data in this file is subject to
# limitation or restriction. See accompanying README and LICENSE for details.
# ****************************************************************************
# Plot the vcd's. X axis should be in 'nm' and Y axis in 'kft'
#
# load "vcdplot.cmd"

set grid
plot "acq_radar.vcd" using 3:4 with lines title "Acq", \
     "ttr_radar.vcd" using 3:4 with lines title "Trk", \
     35 title "Vehicle"
     