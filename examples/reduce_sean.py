#!/usr/bin/env python3
from mantid.simpleapi import *

import os,sys, time
sys.path.append('/SNS/EQSANS/shared/script/eqsanstools')
from eqsans_drtsans_script import *
from eqsans_gpr import process_gpr
from drtsans.dataobjects import load_iqmod, save_iqmod
from drtsans.stitch import stitch_profiles
import h5py

# Note: This script wrapper is not officially supported by SNS
# Instruction:
# To run the script 
#   [prompt]$ drtsans yourscriptname.py
#   [prompt]$ drtsans --dev yourscriptname.py
# Additional help can be found at https://sites.google.com/view/eqsans/home

# Configuration Files
# /SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/Sensitivity_patched_thinPMMA_1o3m_158600.nxs
# /SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/Sensitivity_patched_thinPMMA_2o5m_158599.nxs
# /SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/Sensitivity_patched_thinPMMA_4m_158598.nxs
# eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/EQSANS_158584.nxs.h5"
# eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2025A_flux/bl6_flux_2025A_Jan_rebinned.txt"
# eq._sampleoffset = 314.5 #default
# eq. _detectoroffset = 80 #default
# as of 2/10/2025, [0.97490, 1.03035, 1], sampleoffset = 266.6
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

def callreduction2(conf=0, imin=0, imax=-1):
    start_time = time.time()
    if imax < 0 :
        imax = len(samscatt_1)
    elif imax > len(samscatt_1):
        imax = len(samscatt_1)
    
    print('reducing index min, max : ', imin, imax)
    for i in range(imin, imax):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt_1)), ' for ', sample_names[i])

        print('...... config 1')
        eq = EQVar()
        #eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.3704967534950979*0.698744
        eq._sampleaperturesize = 10
        eq._maskfilename = ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = FLOOD_4m
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._numqbins = 40
        eq._qmin = 0.003
        eq._qmax = 0.1
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._outputwavelengthdependentprofile = True
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._incohfit_qmin = 0.05
        eq._incohfit_qmax = 0.09
        #eq._incohfit_factor = 4
        #eq._incohfit_intensityweighted = True
        eq._useerrorweighting = True
        eq._qbintype = "log"
        eq._showjson = False
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset
        eq._empty = emptybeam_1
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_1[i])
        eq._bkgtrans = str(bkgtrans_1[i])
        eq._samscatt = str(samscatt_1[i])
        eq._samtrans = str(samtrans_1[i])
        eq._filename = str(sample_names[i])+'_conf1'
        #eq._elasticref = eq._samscatt
        #eq._elasticreftrans = eq._samtrans
        #eq._elasticbkg = eq._bkgtrans 
        #eq._elasticbkgtrans = eq._bkgtrans 
        iqname1 = eq._filename        
        if conf ==1 or conf<1:
            reduceNow(eq)

        
        print('...... config 2')
        eq = EQVar()
        #eq._defaultjsonfile = ipts_directory + 'eqsans_reduction.json'
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 0.24733770351586978 *1.078*0.7183
        eq._sampleaperturesize = 10
        eq._maskfilename =  ipts_directory + "mask_4m.nxs"
        eq._sensitivityfilename = FLOOD_2o5m
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._numqbins = 60
        eq._qmin = 0.01
        eq._qmax = 0.7
        eq._qbintype = "log"
        eq._showjson = False
        eq._cuttofmin = 2000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._fitinelasticincoh = True
        eq._selectminincoh = True
        eq._incohfit_qmin = 0.1
        eq._incohfit_qmax = 0.2
        #eq._incohfit_factor = 4
        #eq._incohfit_intensityweighted = True
        eq._outputwavelengthdependentprofile = True
        eq._useerrorweighting = True
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset
        eq._empty = emptybeam_2
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_2[i])
        eq._bkgtrans = str(bkgtrans_2[i])
        eq._samscatt = str(samscatt_2[i])
        eq._samtrans = str(samtrans_2[i])
        eq._filename = str(sample_names[i])+'_conf2_inel'
        iqname2 = eq._filename
        if conf==2 or conf<1:
            reduceNow(eq)
          
        print('......reduction complete.')
        
        if conf==0 or conf==3:
            print('......stitching...')
            iq1_fn = output_directory + iqname1 + '_Iq.dat'
            iq2_fn = output_directory + iqname2 + '_Iq.dat'
            iq1 = load_iqmod(iq1_fn, sep='\t', header_type ='MantidAscii') # header_type = ['MantidAscii' or 'Pandas']
            iq2 = load_iqmod(iq2_fn, sep='\t', header_type = 'MantidAscii')  
            stitched = stitch_profiles([iq1, iq2], overlap[0:2], target_profile_index=0)
            stitched = stitched.extract(slice(1, None)) #remove first 3 points
            merged_fn = output_directory + 'merged_' + str(sample_names[i]) + '_Iq.txt'
            save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
            print('......stitching completed.') 
    end_time = time.time()
    print("Total run time: {}s".format(end_time - start_time))





# function to reduce a single file
def callreduction1(imin=0, time_int=0):
    start_time = time.time()
    for i in range(imin, len(samscatt)):
        print('...reducing data # ', str(i+1), ' out of ', str(len(samscatt)), ' for ', sample_names[i])
        print('...... single configuration')

        runNum = samscatt[i]
        run_filename = f"/SNS/EQSANS/IPTS-{ipts_number}/nexus/EQSANS_{runNum}.nxs.h5"
        print('...reducing file: ', run_filename)
        hf = h5py.File(run_filename, 'r', swmr=False)
        duration = hf.get('/entry/duration')[0]
        print('... Duration : ', duration, ' seconds')

        eq = EQVar()
        eq._outputdir = output_directory
        eq._ipts = ipts_number
        eq._standardabsolutescale = 1
        eq._sampleaperturesize = 10
        eq._maskfilename = ipts_directory + 'mask_4m.nxs'
        eq._sensitivityfilename =  FLOOD_1o3m
        eq._usemaskbacktubes = True
        eq._darkfilename = DARK_FILE
        eq._beamfluxfilename = FLUX_FILE
        eq._numqbins = 80
        eq._numqxqybins = 100
        #eq._qmin = 0.006
        #eq._qmax = 0.1
        eq._qbintype = "log"
        eq._cuttofmin = 1000 # custom tof
        eq._cuttofmax = 3000 # custom tof
        eq._wavelengthstep = 0.1
        eq._fitinelasticincoh = False
        eq._selectminincoh = True
        eq._incohfit_qmin = 0.2
        eq._incohfit_qmax = 0.3
        eq._useerrorweighting = False
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset
        #eq._filterbytimestart = time_i * 1
        #eq._filterbytimestop = time_f * 1      
        if time_int <0.5 :
            eq._usetimeslice = False            
        else :
            eq._usetimeslice = True
            eq._timesliceinterval = time_int
        eq._showjson = False
        eq._empty = emptybeam
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt[i])
        eq._bkgtrans = str(bkgtrans[i])
        eq._samscatt = str(samscatt[i])
        eq._samtrans = str(samtrans[i])
        eq._filename = str(sample_names[i]) 
        eq._gpr = True
        iqname = eq._filename
        reduceNow(eq)
        #if eq._gpr == True:
        #    run_gpr(output_directory+eq._filename + '_frame_0_Iq.dat')
        #    run_gpr(output_directory+eq._filename + '_frame_1_Iq.dat') 
        print('......reduction complete.')
     
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


# two configuration example
ipts_number          = 35498
# default mask location is ipts_directory.
ipts_directory = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/"

#  
output_directory     = f'/SNS/EQSANS/IPTS-{ipts_number}/shared/Sean/' 
print(os.getcwd()) # Checking current working directory.

#low-q
samscatt_1      = [173063, 173064, 173485]
samtrans_1      = [173059, 173060, 173482]
bkgscatt_1       = ['173062'] * len(samscatt_1)
bkgtrans_1       = ['173058'] * len(samscatt_1)
emptybeam_1      = 173057 

#high-q
samscatt_2     = [173072, 173073, 173491]
samtrans_2      = [173068, 173069, 173488] 
bkgscatt_2       = ['173071'] * len(samscatt_2)
bkgtrans_2       = ['173067'] * len(samscatt_2)
emptybeam_2      = 173066 

overlap = [0.035, 0.045]
sample_thick   = [0.1] * len(samscatt_1)
sample_names   = [ 'porsil', 'H1', 'H11']

print('Sample number =',len(samscatt_1))
print('Sample name number =',len(sample_names))
callreduction2(conf=0, imin=2)









''' 
# Run following to load data to the Mantidworkbench workspaces.
for fn in sample_names:
    mergedfn = output_directory + 'merged_' + fn + '_Iq.txt'
    LoadAscii(Filename=mergedfn, outputworkspace = fn)
'''

reduction_confirm(35498) #update with your ipts number
