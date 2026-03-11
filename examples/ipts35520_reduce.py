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
        eq._scalecomponents = scalecomp
        eq._sampleoffset = samoffset
        eq._detectoroffset = detoffset
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


ipts_number          = 35520
ipts_directory = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/"
print(os.getcwd())
output_directory     = ipts_directory + 'porsil/'
# STANDARDS
samscatt      = [167942]
samtrans      = [167931]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['porsil_1o3m']
sample_names = [v + '_35520' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_1o3m()

output_directory     = ipts_directory + 'porsil/'
samscatt      = [167964]
samtrans      = [167953]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['porsil']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()


# SAMPLES 1-8
output_directory     = ipts_directory + 'output/'
samscatt      = [167943, 167944, 167945, 167946, 167947, 167948, 167949, 167950]
samtrans      = [167932, 167933, 167934, 167935, 167936, 167937, 167938, 167939]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1', 'dpzi-li-10-4', 'dpzi-li-10-2', 'dpzi-li-1-0.1',
                  'patfsi-im-d3', 'paatfsi-li', 'paatfsi-k', 'paatfsi-na']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_1o3m()

# SAMPLES 2.5m 1-8
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(167965, 167973)]
samtrans      = [*range(167954, 167962)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1', 'dpzi-li-10-4', 'dpzi-li-10-2', 'dpzi-li-1-0.1',
                  'patfsi-im-d3', 'paatfsi-li', 'paatfsi-k', 'paatfsi-na']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()
overlap=[0.2, 0.24]
#mergefiles()




# SAMPLES 9-16
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(167986, 167994)]
samtrans      = [*range(167978, 167986)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-na-1-1', 'dpzi-na-10-4', 'dpzi-na-10-2', 'dpzi-na-10-1',
                'dpzi-k-1-1', 'dpzi-k-10-4', 'dpzi-k-10-2', 'dpzi-k-10-1']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_1o3m()

# SAMPLES 2.5m 9-16
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168002, 168010)]
samtrans      = [*range(167994, 168002)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-na-1-1', 'dpzi-na-10-4', 'dpzi-na-10-2', 'dpzi-na-10-1',
                'dpzi-k-1-1', 'dpzi-k-10-4', 'dpzi-k-10-2', 'dpzi-k-10-1']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_2o5m()
#mergefiles()




# SAMPLES 1-16, high-T
# first sample didn't have count due to detector issue

output_directory     = ipts_directory + 'output_100C/'
samscatt      = [*range(168024, 168088, 4)]
samtrans      = [*range(167978, 167986)] + [*range(167994, 168002)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1', 'dpzi-li-10-4', 'dpzi-li-10-2', 'dpzi-li-1-0.1',
                  'patfsi-im-d3', 'paatfsi-li', 'paatfsi-k', 'paatfsi-na']+  ['dpzi-na-1-1', 'dpzi-na-10-4', 'dpzi-na-10-2', 'dpzi-na-10-1',
                'dpzi-k-1-1', 'dpzi-k-10-4', 'dpzi-k-10-2', 'dpzi-k-10-1']
sample_names = [v + '_100C_1st' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_1o3m(imin=0)

output_directory     = ipts_directory + 'output_100C/'
samscatt      = [*range(168025, 168089, 4)]
samtrans      = [*range(167978, 167986)] + [*range(167994, 168002)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1', 'dpzi-li-10-4', 'dpzi-li-10-2', 'dpzi-li-1-0.1',
                  'patfsi-im-d3', 'paatfsi-li', 'paatfsi-k', 'paatfsi-na']+  ['dpzi-na-1-1', 'dpzi-na-10-4', 'dpzi-na-10-2', 'dpzi-na-10-1',
                'dpzi-k-1-1', 'dpzi-k-10-4', 'dpzi-k-10-2', 'dpzi-k-10-1']
sample_names = [v + '_100C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
#callreduction1_1o3m(imin=0)


'''
# SAMPLES 1, pos4 repeat.
# first sample didn't have count due to detector issue

output_directory     = ipts_directory + 'output_100C/'
samscatt      = [168152]
samtrans      = [167978] 
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1']
sample_names = [v + '_100C_1st' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m(imin=0)

output_directory     = ipts_directory + 'output_100C/'
samscatt      = [168153]
samtrans      = [167978]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1']
sample_names = [v + '_100C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m(imin=0)




## sample 1-16 high-t
# SAMPLES 2.5m
output_directory     = ipts_directory + 'output_100C/'
samscatt      = [*range(168088, 168088+64, 4)]
samtrans      = [*range(167954, 167962)] + [*range(167994, 168002)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1', 'dpzi-li-10-4', 'dpzi-li-10-2', 'dpzi-li-1-0.1',
                  'patfsi-im-d3', 'paatfsi-li', 'paatfsi-k', 'paatfsi-na']+  ['dpzi-na-1-1', 'dpzi-na-10-4', 'dpzi-na-10-2', 'dpzi-na-10-1',
                'dpzi-k-1-1', 'dpzi-k-10-4', 'dpzi-k-10-2', 'dpzi-k-10-1']
sample_names = [v + '_100C_1st' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()

# SAMPLES 2.5m
output_directory     = ipts_directory + 'output_100C/'
samscatt      = [*range(168089, 168088+64, 4)]
samtrans      = [*range(167954, 167962)] + [*range(167994, 168002)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpzi-li-1-1', 'dpzi-li-10-4', 'dpzi-li-10-2', 'dpzi-li-1-0.1',
                  'patfsi-im-d3', 'paatfsi-li', 'paatfsi-k', 'paatfsi-na']+  ['dpzi-na-1-1', 'dpzi-na-10-4', 'dpzi-na-10-2', 'dpzi-na-10-1',
                'dpzi-k-1-1', 'dpzi-k-10-4', 'dpzi-k-10-2', 'dpzi-k-10-1']
sample_names = [v + '_100C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()

overlap=[0.2, 0.24]
mergefiles()
'''

'''
######
###   pos22-32  20C
######
# 1.3m
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168178, 168200,2 )]
samtrans      = [*range(168156, 168178, 2)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['zil', 'pmtfsi-li', 'pmtfsi-li-2-1', 'pmtfsi-li-1-1', 'pmtfsi-li-1-2',
            'pmtfsi-li-1-4', 'pmtfsi-na', 'pmtfsi-na-1-1', 'pmtfsi-na-1-2', 
            'pmtfsi-na-1-4', 'pmtfsi-k']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

# SAMPLES 2.5m 
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168299, 168321, 2)]
samtrans      = [*range(168277, 168299, 2)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['zil', 'pmtfsi-li', 'pmtfsi-li-2-1', 'pmtfsi-li-1-1', 'pmtfsi-li-1-2',
            'pmtfsi-li-1-4', 'pmtfsi-na', 'pmtfsi-na-1-1', 'pmtfsi-na-1-2', 
            'pmtfsi-na-1-4', 'pmtfsi-k']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()
mergefiles()




######
###   pos 1, 6-9  20C
######
# 1.3m
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168331, 168341, 2)]
samtrans      = [*range(168321, 168331, 2)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpmtfsi-na-2-1', 'dpzi-litfsi-1-1', 'dpzi-litfsi-4-10', 
                  'dpzi-litfsi-2-10', 'dpzi-litfsi-1-10']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

# SAMPLES 2.5m 
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168351, 168361, 2)]
samtrans      = [*range(168341, 168351, 2)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpmtfsi-na-2-1', 'dpzi-litfsi-1-1', 'dpzi-litfsi-4-10', 
                  'dpzi-litfsi-2-10', 'dpzi-litfsi-1-10']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()
overlap=[0.2, 0.24]
mergefiles()


######
###   pos 2-5  20C
######
# 1.3m
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168369, 168377, 2)]
samtrans      = [*range(168361, 168369, 2)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpmtfsi-k-2-1', 'dpmtfsi-k-1-1', 'dpmtfsi-k-1-2', 'dpmtfsi-k-1-4']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

# SAMPLES 2.5m 
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168385, 168393, 2)]
samtrans      = [*range(168377, 168385, 2)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpmtfsi-k-2-1', 'dpmtfsi-k-1-1', 'dpmtfsi-k-1-2', 'dpmtfsi-k-1-4']
sample_names = [v + '_20C' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()
overlap=[0.2, 0.24]
mergefiles()




######
###   pos 1, 6-9  80C
######
# 1.3m
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168394, 168413, 4)]
samtrans      = [*range(168321, 168331, 2)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpmtfsi-na-2-1', 'dpzi-litfsi-1-1', 'dpzi-litfsi-4-10', 
                  'dpzi-litfsi-2-10', 'dpzi-litfsi-1-10']
sample_names = [v + '_80C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m()

# SAMPLES 2.5m 
output_directory     = ipts_directory + 'output/'
samscatt      = [*range(168414, 168433, 4)]
samtrans      = [*range(168341, 168351, 2)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['dpmtfsi-na-2-1', 'dpzi-litfsi-1-1', 'dpzi-litfsi-4-10', 
                  'dpzi-litfsi-2-10', 'dpzi-litfsi-1-10']
sample_names = [v + '_80C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m()
overlap=[0.2, 0.24]
mergefiles()
'''



'''
######
#   pos22-32  80C 2.5m80C is the last set.
#   therefore it may be incomplete. So reduce in the last
######
# 1.3m
output_directory     = ipts_directory + 'output_80C/'
samscatt      = [*range(168232, 168263, 4 )]+[168266, 168270,168274]
samtrans      = [*range(168156, 168178, 2)]
bkgscatt       = [167940] * len(samscatt)
bkgtrans       = [167930] * len(samscatt)
emptybeam      = 167929 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['zil', 'pmtfsi-li', 'pmtfsi-li-2-1', 'pmtfsi-li-1-1', 'pmtfsi-li-1-2',
            'pmtfsi-li-1-4', 'pmtfsi-na', 'pmtfsi-na-1-1', 'pmtfsi-na-1-2', 
            'pmtfsi-na-1-4', 'pmtfsi-k']
sample_names = [v + '_80C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_1o3m(imin=6)

# SAMPLES 2.5m 
output_directory     = ipts_directory + 'output_80C/'
samscatt      = [*range(168434, 168434+45, 4)]
samtrans      = [*range(168277, 168299, 2)]
bkgscatt       = [167963] * len(samscatt)
bkgtrans       = [167952] * len(samscatt)
emptybeam      = 167951 

sample_thick   = [0.1] * len(samscatt)
sample_names   = ['zil', 'pmtfsi-li', 'pmtfsi-li-2-1', 'pmtfsi-li-1-1', 'pmtfsi-li-1-2',
            'pmtfsi-li-1-4', 'pmtfsi-na', 'pmtfsi-na-1-1', 'pmtfsi-na-1-2', 
            'pmtfsi-na-1-4', 'pmtfsi-k']
sample_names = [v + '_80C_2nd' for v in sample_names]
print('Sample number =',len(samscatt))
print('Sample name number =',len(sample_names))
callreduction1_2o5m(imax=3)
mergefiles()
'''






'''
for fn in sample_names:
    mergedfn = output_directory + 'merged_' + fn + '_Iq.txt'
    LoadAscii(Filename=mergedfn, outputworkspace = fn)
'''
reduction_confirm(35520)
