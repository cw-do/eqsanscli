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
DARK_FILE = MP_DIR + "EQSANS_167516.nxs.h5"
FLUX_FILE = MP_DIR + "bl6_flux_2025B_Aug_rebinned_4m.txt"


#################
def callreduction3():
    start_time = time.time()
    for i in range(0, len(samscatt_1)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt_1)), ' for ', sample_names[i])

        print('...... config 0')
        eq = EQVar()
        eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.1399396
        eq._sampleaperturesize = 10
        eq._maskfilename = ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_4m_148405.nxs"
        eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
        eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"
        eq._numqbins = 50
        eq._qmin = 0.003
        eq._qmax = 0.05
        eq._wavelengthstep = 0.5
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._incohfit_qmin = 0.04
        eq._incohfit_qmax = 0.08
        #eq._incohfit_factor = 4
        #eq._incohfit_intensityweighted = True
        eq._useerrorweighting = True
        eq._qbintype = "log"
        eq._showjson = False
        eq._empty = emptybeam_0
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_0[i])
        eq._bkgtrans = str(bkgtrans_0[i])
        eq._samscatt = str(samscatt_0[i])
        eq._samtrans = str(samtrans_0[i])
        eq._filename = str(sample_names[i])+'_conf0'
        iqname0 = eq._filename
        #reduceNow(eq)

        print('...... config 1')
        eq = EQVar()
        eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.1399396
        eq._sampleaperturesize = 10
        eq._maskfilename = ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_4m_148405.nxs"
        eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
        eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"
        eq._numqbins = 60
        eq._qmin = 0.006
        eq._qmax = 0.1
        eq._wavelengthstep = 0.5
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._incohfit_qmin = 0.04
        eq._incohfit_qmax = 0.08
        #eq._incohfit_factor = 4
        #eq._incohfit_intensityweighted = True
        eq._useerrorweighting = True
        eq._qbintype = "log"
        eq._showjson = False
        eq._empty = emptybeam_1
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_1[i])
        eq._bkgtrans = str(bkgtrans_1[i])
        eq._samscatt = str(samscatt_1[i])
        eq._samtrans = str(samtrans_1[i])
        eq._filename = str(sample_names[i])+'_conf1'
        iqname1 = eq._filename
        #reduceNow(eq)
        
        
        
        print('...... config 2')
        eq = EQVar()
        eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.24733770351586978
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_2o5m_148406.nxs"
        eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
        eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"
        eq._numqbins = 80
        #eq._qmin = 0.022
        #eq._qmax = 0.5
        eq._qbintype = "log"
        eq._showjson = False
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.2
        eq._fitinelasticincoh = True
        eq._selectminincoh = True
        eq._incohfit_qmin = 0.1
        eq._incohfit_qmax = 0.30
        #eq._incohfit_factor = 4
        #eq._incohfit_intensityweighted = True
        eq._outputwavelengthdependentprofile = True
        eq._useerrorweighting = True
        eq._empty = emptybeam_2
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_2[i])
        eq._bkgtrans = str(bkgtrans_2[i])
        eq._samscatt = str(samscatt_2[i])
        eq._samtrans = str(samtrans_2[i])
        eq._filename = str(sample_names[i])+'_conf2_bfit_fullq'
        iqname2 = eq._filename
        reduceNow(eq)
        print('......reduction complete.')
        
        print('......stitching...')
        iq0_fn = output_directory + iqname0 + '_Iq.dat'        
        iq1_fn = output_directory + iqname1 + '_Iq.dat'
        iq2_fn = output_directory + iqname2 + '_Iq.dat'
        iq0 = load_iqmod(iq0_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
        iq1 = load_iqmod(iq1_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']
        iq2 = load_iqmod(iq2_fn, sep='\t', header_type = 'MantidAscii')  
        stitched = stitch_profiles([iq0, iq1, iq2], overlap[0:4], target_profile_index=1)
        merged_fn = output_directory + 'merged3conf_' + str(sample_names[i]) + '_Iq.txt'
        save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
        print('......stitching completed.') 
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))



# function to reduce a single file
def callreduction1_4m():
    start_time = time.time()
    for i in range(0, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])

        print('...... single configuration')
        eq = EQVar()
        eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 1
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_4m_148405.nxs"
        eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
        eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"
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
    
def callreduction1_2o5m():
    start_time = time.time()
    for i in range(0, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])

        print('...... single configuration')
        eq = EQVar()
        eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 1
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_2o5m_148406.nxs"
        eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
        eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"
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
    
    

def callreduction1():
    start_time = time.time()
    for i in range(0, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])

        print('...... single configuration')
        eq = EQVar()
        eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 1
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/Sensitivity_patched_thinPMMA_2o5m_148406.nxs"
        eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/EQSANS_148385.nxs.h5"
        eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2024B_flux/bl6_flux_2024B_July_rebinned.txt"
        eq._numqbins = 60
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "linear"
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._fitinelasticincoh = True
        eq._selectminincoh = True
        eq._useerrorweighting = True
        eq._incohfit_qmin = 0.3
        eq._incohfit_qmax = 0.4
        #eq._elasticref = samscatt[i]
        #eq._elasticreftrans = samtrans[i]
        eq._outputwavelengthdependentprofile = True
        eq._showjson = False
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) + '_bfit'
        iqname = eq._filename
        reduceNow(eq)
        
        print('......reduction complete.')
     
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))


# function to reduce a single file
def callreduction1_1o3m():
    start_time = time.time()
    for i in range(0, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])

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
        eq._numqbins = 80
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "linear"
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
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) + '_bfit1a'
        iqname = eq._filename
        reduceNow(eq)
        
        print('......reduction complete.')
     
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))
    
    
def mergefiles():
    start_time = time.time()
    for basename in sample_names:
        print('......stitching...')
        iq0_fn = output_directory + basename + '_4m_Iq.dat'        
        iq1_fn = output_directory + basename + '_2o5m_Iq.dat'
        iq2_fn = output_directory + basename + '_bfit1a_Iq.dat'
        iq0 = load_iqmod(iq0_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']        
        iq1 = load_iqmod(iq1_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']
        iq2 = load_iqmod(iq2_fn, sep='\t', header_type = 'MantidAscii')  
        stitched = stitch_profiles([iq0, iq1, iq2], overlap[0:4], target_profile_index=2)
        merged_fn = output_directory + 'merged3conf_' + basename + '_Iq.txt'
        save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
        print('......stitching completed.') 
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))

###################################
# USER INPUT BEGINS HERE
# CHANGE THIS TOP FOLDER AS NEEDED
###################################


# two configuration example
ipts_number          = 33323
ipts_directory = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/"
print(os.getcwd())
output_directory     = ipts_directory + 'output_bfit1a/'

#low-q
samscatt      = [*range(153964, 153970)]
samtrans      = [*range(153955, 153961)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()



#low-q
samscatt      = [*range(153974, 153978)]
samtrans      = [*range(153970, 153974)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()


#low-q
samscatt      = [*range(154008, 154018)]
samtrans      = [*range(153998, 154008)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_40C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()



#low-q
samscatt      = [*range(154048, 154058)]
samtrans      = [*range(154038, 154048)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_60C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()



#low-q
samscatt      = [*range(154068, 154078)]
samtrans      = [*range(154058, 154068)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_80C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()



#low-q
samscatt      = [*range(154088, 154098)]
samtrans      = [*range(154078, 154088)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_100C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()



#low-q
samscatt      = [*range(154128, 154138)]
samtrans      = [*range(154118, 154128)]
bkgscatt       = [153963] * len(samscatt)
bkgtrans       = [153954] * len(samscatt)
emptybeam      = 153949 


overlap = [0.055, 0.060]
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_120C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1()
###########################








#######################################

ipts_number          = 33323
ipts_directory = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/"
print(os.getcwd())
output_directory     = ipts_directory + 'output_0927/'
'''
####################
# measured at 1.3m 1a
####################
#1.3m 1a
samscatt      = [*range(154108, 154118)]
samtrans      = [*range(154098, 154108)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_120C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()


#1.3m 1a
samscatt      = [*range(154028, 154038)]
samtrans      = [*range(154018, 154028)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_60C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()


#1.3m 1a
samscatt      = [*range(153988, 153998)]
samtrans      = [*range(153978, 153988)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['dmtfsi_li', 'umtfsi_li', 'p2vpps', 'zil0p2', 'zil0p5', 'zil1', 'p2vpps_0p1', 'p2vpps_0p2', 'p2vpps_0p3', 'p2vpps_1']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()


#1.3m 1a
samscatt      = [*range(154147, 154153)]
samtrans      = [*range(154141, 154147)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['zil100', 'pz80p', 'dpeg0p2', 'dpeg1', 'dpeg5', 'dpeg100']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()






##########################################
##### 3 config
#ipts_number          = 33323
#ipts_directory = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/"
#print(os.getcwd())
#output_directory     = ipts_directory + 'output_3conf/'

#1o3m
samscatt      = [*range(154160, 154167)]
samtrans      = [*range(154153, 154160)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1', 'dpeg1', 'dpeg5', 'dpeg100']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

#2.5m 2.5a
samscatt      = [*range(154177, 154184)]
samtrans      = [*range(154169, 154176)]
bkgscatt       = [154176] * len(samscatt)
bkgtrans       = [154168] * len(samscatt)
emptybeam      = 154167 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1', 'dpeg1', 'dpeg5', 'dpeg100']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()
'''


#4m 10a
samscatt      = [*range(154194, 154201)]
samtrans      = [*range(154186, 154193)]
bkgscatt       = [154193] * len(samscatt)
bkgtrans       = [154185] * len(samscatt)
emptybeam      = 154184 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1', 'dpeg1', 'dpeg5', 'dpeg100']
sample_names = [v + '_25C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_4m()
overlap = [0.04, 0.05, 0.24, 0.28]
mergefiles()



##########################################
##### 3 config
#1o3m
samscatt      = [*range(154205, 154209)]
samtrans      = [*range(154201, 154205)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1']
sample_names = [v + '_60C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

#2.5m 2.5a
samscatt      = [*range(154213, 154217)]
samtrans      = [*range(154209, 154213)]
bkgscatt       = [154176] * len(samscatt)
bkgtrans       = [154168] * len(samscatt)
emptybeam      = 154167 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1']
sample_names = [v + '_60C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()

#4m 10a
samscatt      = [*range(154221, 154225)]
samtrans      = [*range(154217, 154221)]
bkgscatt       = [154193] * len(samscatt)
bkgtrans       = [154185] * len(samscatt)
emptybeam      = 154184 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1']
sample_names = [v + '_60C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_4m()
overlap = [0.04, 0.05, 0.24, 0.28]
mergefiles()






##########################################
##### 3 config
#1o3m
samscatt      = [*range(154229, 154233)]
samtrans      = [*range(154225, 154229)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1']
sample_names = [v + '_100C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

#2.5m 2.5a
samscatt      = [*range(154237, 154241)]
samtrans      = [*range(154233, 154237)]
bkgscatt       = [154176] * len(samscatt)
bkgtrans       = [154168] * len(samscatt)
emptybeam      = 154167 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1']
sample_names = [v + '_100C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()

#4m 10a
samscatt      = [*range(154245, 154249)]
samtrans      = [*range(154241, 154245)]
bkgscatt       = [154193] * len(samscatt)
bkgtrans       = [154185] * len(samscatt)
emptybeam      = 154184 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['pz80p_dpm0p2', 'pz80p_dpm1', 'pz80p_dpm5', 'zil1']
sample_names = [v + '_100C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_4m()
overlap = [0.04, 0.05, 0.24, 0.28]
mergefiles()





####################
## last 3
#1o3m
samscatt      = [*range(154259, 154262)]
samtrans      = [*range(154256, 154259)]
bkgscatt       = [154140] * len(samscatt)
bkgtrans       = [154139] * len(samscatt)
emptybeam      = 154138 
sample_thick   = [0.05] * len(samscatt)
sample_names   = ['zil2p8', 'zil5', 'zil6']
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

'''
for fn in sample_names:
    mergedfn = output_directory + 'merged_' + fn + '_Iq.txt'
    LoadAscii(Filename=mergedfn, outputworkspace = fn)
'''
reduction_confirm(33323)
