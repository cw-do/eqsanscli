#!/usr/bin/env python3
from mantid.simpleapi import *

import os,sys, time
sys.path.append('/SNS/EQSANS/shared/script/eqsanstools')
from eqsans_drtsans_script import *
from drtsans.dataobjects import load_iqmod, save_iqmod
from drtsans.stitch import stitch_profiles

# Note: This script wrapper is not officially supported by SNS
# Instruction:
# To run the script 
#   [prompt]$ drtsans yourscriptname.py
#   [prompt]$ drtsans --dev yourscriptname.py
# Additional help can be found at https://sites.google.com/view/eqsans/home

# Sensitivity files
# "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_4m_148405.nxs"
# "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_2o5m_148406.nxs"

# eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
# eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"

####################################
# BELOW IS REDUCTION CODE
# CHANGE AFTER CONSULTING WITH LOCAL CONTACT
####################################

MP_DIR = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025B_mp/"
FLOOD_4m = MP_DIR + "Sensitivity_patched_thinPMMA_4m_167517.nxs"
FLOOD_2o5m = MP_DIR + "Sensitivity_patched_thinPMMA_2o5m_167519.nxs"
FLOOD_1o3m = MP_DIR + "Sensitivity_patched_thinPMMA_1o3m_167521.nxs"
FLOOD_1o3m = MP_DIR + "Sensitivity_patched_5mmPMMA_1o3m_167522.nxs"
DARK_FILE = MP_DIR + "EQSANS_167516.nxs.h5"
FLUX_FILE = MP_DIR + "bl6_flux_2025B_Aug_rebinned_4m.txt"


# function to reduce a single file
def callreduction1_9m():
    start_time = time.time()
    for i in range(0, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])

        print('...... single configuration')
        eq = EQVar()
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.1818
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_9m.nxs"
        eq._sensitivityfilename = FLOOD_4m
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._numqbins = 80
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "linear"
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._useerrorweighting = True
        eq._incohfit_qmin = 0.3
        eq._incohfit_qmax = 0.4
        #eq._elasticref = samscatt[i]
        #eq._elasticreftrans = samtrans[i]
        #eq._outputwavelengthdependentprofile = True
        eq._showjson = False
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset        
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) + '_9m'
        iqname = eq._filename
        reduceNow(eq)
        
        print('......reduction complete.')
     
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
    
# function to reduce a single file
def callreduction1_4m():
    start_time = time.time()
    for i in range(0, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])

        print('...... single configuration')
        eq = EQVar()
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.226853 *0.983606#2025B-36228
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m2.nxs"
        eq._sensitivityfilename = FLOOD_4m
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._numqbins = 80
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "linear"
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._useerrorweighting = True
        eq._incohfit_qmin = 0.3
        eq._incohfit_qmax = 0.4
        #eq._elasticref = samscatt[i]
        #eq._elasticreftrans = samtrans[i]
        #eq._outputwavelengthdependentprofile = True
        eq._showjson = False
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset        
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) + '_4m'
        iqname = eq._filename
        reduceNow(eq)
        
        print('......reduction complete.')
     
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
    



# function to reduce a single file
def callreduction1_1o3m(imin=0, imax=100):
    start_time = time.time()
    if imax < len(samscatt):
        range_max = imax
    else:
        range_max = len(samscatt)
                
    for i in range(imin, range_max):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])
        print('...scatt run ', samscatt[i])
        print('...... single configuration')
        eq = EQVar()
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 1
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = FLOOD_1o3m
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._usemaskbacktubes = True
        eq._numqbins = 80
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "log"
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.2
        eq._fitinelasticincoh = True
        eq._selectminincoh = True
        eq._useerrorweighting = True
        eq._incohfit_qmin = 0.6
        eq._incohfit_qmax = 0.8
        #eq._elasticref = samscatt[i]
        #eq._elasticreftrans = samtrans[i]
        eq._outputwavelengthdependentprofile = True
        eq._showjson = False
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) + '_bfit1a_5mmflood'
        iqname = eq._filename
        reduceNow(eq)
        
        print('......reduction complete.')
     
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
    

# function to reduce a single file
def callreduction1_2o5m(imin=0, imax=100):
    start_time = time.time()
    if imax < len(samscatt):
        range_max = imax    
    else:
        range_max = len(samscatt)
        
    for i in range(imin, range_max):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])
        print('...scatt run ', samscatt[i])
        print('...... single configuration')
        eq = EQVar()
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 1
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = FLOOD_2o5m
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._numqbins = 50
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "linear"
        eq._cuttofmin = 11000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._useerrorweighting = True
        eq._incohfit_qmin = 0.6
        eq._incohfit_qmax = 0.8
        #eq._elasticref = samscatt[i]
        #eq._elasticreftrans = samtrans[i]
        eq._outputwavelengthdependentprofile = False
        eq._showjson = False
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) + '_2o5m'
        iqname = eq._filename
        reduceNow(eq)
        
        print('......reduction complete.')
     
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
        
def mergefiles():
    start_time = time.time()
    for basename in sample_names:
        print('......stitching...')
        iq0_fn = output_directory + basename + '_2o5m_Iq.dat'        
        iq1_fn = output_directory + basename + '_bfit1a_Iq.dat'
        #iq2_fn = output_directory + basename + '_bfit1a_Iq.dat'
        iq0 = load_iqmod(iq0_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
        iq1 = load_iqmod(iq1_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']
        #iq2 = load_iqmod(iq2_fn, sep='\t', header_type = 'MantidAscii')  
        stitched = stitch_profiles([iq0, iq1], overlap[0:2], target_profile_index=1)
        merged_fn = output_directory + 'merged2conf_' + basename + '_Iq.txt'
        save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
        print('......stitching completed.') 
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
    
    
def mergefiles3():
    start_time = time.time()
    for basename in sample_names:
        print('......stitching...')
        iq0_fn = output_directory + basename + '_9m_Iq.dat'        
        iq1_fn = output_directory + basename + '_4m_Iq.dat'
        iq2_fn = output_directory + basename + '_bfit1a_Iq.dat'

        iq0 = load_iqmod(iq0_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
        iq1 = load_iqmod(iq1_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']
        iq2 = load_iqmod(iq2_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
     

        stitched = stitch_profiles([iq0, iq1, iq2], overlap[0:4], target_profile_index=1)
        merged_fn = output_directory + 'merged3conf_' + basename + '_Iq.txt'
        save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
        print('......stitching completed.') 
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
    
    
def mergefiles4():
    start_time = time.time()
    for basename in sample_names:
        print('......stitching...')
        iq0_fn = output_directory + basename + '_9m_Iq.dat'        
        iq1_fn = output_directory + basename + '_4m_Iq.dat'
        iq2_fn = output_directory + basename + '_2o5m_Iq.dat'
        iq3_fn = output_directory + basename + '_bfit1a_Iq.dat'
        iq0 = load_iqmod(iq0_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
        iq1 = load_iqmod(iq1_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']
        iq2 = load_iqmod(iq2_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
        iq3 = load_iqmod(iq3_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        

        stitched = stitch_profiles([iq0, iq1, iq2, iq3], overlap4[0:6], target_profile_index=1)
        merged_fn = output_directory + 'merged4conf_' + basename + '_Iq.txt'
        save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
        print('......stitching completed.') 
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))    
###################################
# USER INPUT BEGINS HERE
# CHANGE THIS TOP FOLDER AS NEEDED
###################################
# 202508 configuration
scale_y = 0.9994188604687534  
scale_all = 1.021
scalecomp = [scale_all , scale_all * scale_y, 1]
samoffset = 290
detoffset = 60.9995821


ipts_number          = 36228
ipts_directory = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/"
print(os.getcwd())
output_directory     = ipts_directory + 'porsil/'
# STANDARDS
samscatt      = [168518]
samtrans      = [168508]
bkgscatt       = [168517] * len(samscatt)
bkgtrans       = [168507] * len(samscatt)
emptybeam      = 168506 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['porsil_36228']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

samscatt      = [168538]
samtrans      = [168528]
bkgscatt       = [168537] * len(samscatt)
bkgtrans       = [168527] * len(samscatt)
emptybeam      = 168526 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['porsil_36228']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()

samscatt      = [168558]
samtrans      = [168548]
bkgscatt       = [168557] * len(samscatt)
bkgtrans       = [168547] * len(samscatt)
emptybeam      = 168546 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['porsil_36228']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_4m()

samscatt      = [168578]
samtrans      = [168568]
bkgscatt       = [168577] * len(samscatt)
bkgtrans       = [168567] * len(samscatt)
emptybeam      = 168566 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['porsil_36228']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_9m()
overlap=[0.015, 0.018, 0.1, 0.12]
mergefiles3()








output_directory     = ipts_directory + 'solutions/'
# SAMPLE
samscatt      = [168519, 168520, 168521, 168522, 168523, 168524, 168525]
samtrans      = [*range(168509, 168516)]
bkgscatt       = [168517] * len(samscatt)
bkgtrans       = [168507] * len(samscatt)
emptybeam      = 168506 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['pSPAN-banjo', 'pSPAN-hTHF', 'pSPAN-dhTHF', 'pSPAN-dTHF', 'pSPAN-hDMSO',
                'pSPAN-dhDMSO', 'pSPAN-dDMSO']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

samscatt      = [*range(168539,168546)]
samtrans      = [*range(168529,168536)]
bkgscatt       = [168537] * len(samscatt)
bkgtrans       = [168527] * len(samscatt)
emptybeam      = 168526 
sample_thick   = [0.1] * len(samscatt)
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()

samscatt      = [*range(168559, 168566)]
samtrans      = [*range(168549, 168556)]
bkgscatt       = [168557] * len(samscatt)
bkgtrans       = [168547] * len(samscatt)
emptybeam      = 168546 
sample_thick   = [0.1] * len(samscatt)
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_4m()

samscatt      = [*range(168579, 168586)]
samtrans      = [*range(168569, 168576)]
bkgscatt       = [168577] * len(samscatt)
bkgtrans       = [168567] * len(samscatt)
emptybeam      = 168566 
sample_thick   = [0.1] * len(samscatt)
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_9m()
overlap=[0.011, 0.013, 0.1, 0.12]
#mergefiles3()
overlap4=[0.011, 0.013, 0.04, 0.045, 0.13,0.14] 
#mergefiles4()

# SAMPLE
samscatt      = [168499]
samtrans      = [168498]
bkgscatt       = [168517] * len(samscatt)
bkgtrans       = [168507] * len(samscatt)
emptybeam      = 168506 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['Li-SPAN-sol']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

samscatt      = [168501]
samtrans      = [168500]
bkgscatt       = [168537] * len(samscatt)
bkgtrans       = [168527] * len(samscatt)
emptybeam      = 168526 
sample_thick   = [0.1] * len(samscatt)
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()

samscatt      = [168503]
samtrans      = [168502]
bkgscatt       = [168557] * len(samscatt)
bkgtrans       = [168547] * len(samscatt)
emptybeam      = 168546 
sample_thick   = [0.1] * len(samscatt)
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_4m()

samscatt      = [168505]
samtrans      = [168504]
bkgscatt       = [168577] * len(samscatt)
bkgtrans       = [168567] * len(samscatt)
emptybeam      = 168566 
sample_thick   = [0.1] * len(samscatt)
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_9m()
overlap=[0.011, 0.013, 0.1, 0.12]
#mergefiles3()
overlap4=[0.011, 0.013, 0.04, 0.045, 0.13,0.14] 
#mergefiles4()




# SAMPLES 
output_directory     = ipts_directory + 'output/'
samscatt      = [168475, 168491]
samtrans      = [168474, 168490]
bkgscatt       = [168483] * len(samscatt)
bkgtrans       = [168482] * len(samscatt)
emptybeam      = 168506 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['Li-SPAN-Al', 'p-SPAN-Al']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

samscatt      = [168477, 168493]
samtrans      = [168476, 168492]
bkgscatt       = [168485] * len(samscatt)
bkgtrans       = [168484] * len(samscatt)
emptybeam      = 168526 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['Li-SPAN-Al', 'p-SPAN-Al']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()

samscatt      = [168479, 168495]
samtrans      = [168478, 168494]
bkgscatt       = [168487] * len(samscatt)
bkgtrans       = [168486] * len(samscatt)
emptybeam      = 168546 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['Li-SPAN-Al', 'p-SPAN-Al']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_4m()

samscatt      = [168481, 168497]
samtrans      = [168480, 168496]
bkgscatt       = [168489] * len(samscatt)
bkgtrans       = [168488] * len(samscatt)
emptybeam      = 168546 
sample_thick   = [0.1] * len(samscatt)
sample_names   = ['Li-SPAN-Al', 'p-SPAN-Al']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_9m()
overlap=[0.011, 0.013, 0.1, 0.12]
#mergefiles3()
overlap4=[0.011, 0.013, 0.04, 0.045, 0.13,0.14] 
#mergefiles4()


'''
for fn in sample_names:
    mergedfn = output_directory + 'merged_' + fn + '_Iq.txt'
    LoadAscii(Filename=mergedfn, outputworkspace = fn)
'''
reduction_confirm(36228)
