#!/usr/bin/env python3
import sys, time
sys.path.append('/SNS/EQSANS/shared/script/eqsanstools')
from eqsans_drtsans_script import *
from drtsans.dataobjects import load_iqmod, save_iqmod
from drtsans.stitch import stitch_profiles

# Note: This script wrapper is not officially supported by SNS
# Instruction:
# To run the script 
#   [prompt]$ drtsans yourscriptname.py


###################################
# USER INPUT BEGINS HERE
# CHANGE THIS TOP FOLDER AS NEEDED
###################################

ipts_number          = 38681
output_directory     =f"/SNS/EQSANS/IPTS-{ipts_number}/shared/Results/ecSubtract_1_inel_4Q/"

sample_names   =['S1','S2','S3', 'S4', 'S5', 'S6']
   


postfix = '_ecSub_inel'
sample_thick   = [2]*len(sample_names)


#9m 15A
samscatt_0      = [*range(186680,186686)]
samtrans_0      = [*range(186674,186680)]
bkgscatt_0      = [186636] * len(sample_names)
bkgtrans_0      = [186634] * len(sample_names)
emptybeam_0     = 186633


#4m 10A
samscatt_1      = [*range(186668,186674)]
samtrans_1      = [*range(186662,186668)]
bkgscatt_1      = [186631] * len(sample_names)
bkgtrans_1      = [186629] * len(sample_names)
emptybeam_1     = 186628

#2p5m 2p5A
samscatt_2      = [*range(186656,186662)]
samtrans_2      = [*range(186650,186656)]
bkgscatt_2      = [186626] * len(sample_names)
bkgtrans_2      = [186624] * len(sample_names)
emptybeam_2     = 186623

#1.3m 1A
samscatt_3      = [*range(186644,186650)]
samtrans_3      = [*range(186638,186644)]
bkgscatt_3      = [186621] * len(sample_names)
bkgtrans_3      = [186619] * len(sample_names)
emptybeam_3     = 186618


overlap = [0.009, 0.01, 0.035, 0.05, 0.15,0.20]
#overlap = [0.035, 0.05]

print('Sample number =',len(samscatt_1))
print('Sample name number =',len(sample_names))




####################################
# BELOW IS REDUCTION CODE
# CHANGE AFTER CONSULTING WITH LOCAL CONTACT
####################################
start_time = time.time()
for i in range(0,len(sample_names)):
    print('...reducing data #', str(i+1), ' out of ', str(len(samscatt_1)), ' for ', sample_names[i])

    
    print('...... config 0')
    eq = EQVar()
    eq._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.json'
    eq._outputdir = output_directory
    eq._ipts = ipts_number
    eq._scalecomponents = [1.004251, 1.057915, 1.000000]
    eq._standardabsolutescale = 3.4701 * 0.8835 #1.466 * 0.8382 #1.3843 * 0.8269 #1.3989
    eq._sampleaperturesize = 10
    eq._sampleoffset = 285
    eq._detectoroffset = 66.763
    eq._maskfilename = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/maskWS9m15A.nxs"
    eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/Sensitivity_patched_thinPMMA_4m_186200.nxs"
    eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/EQSANS_186198.nxs.h5"
    eq._beamfluxfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/bl6_flux_2026B_aug_rebinned.txt"
    eq._numqbins = 300
    eq._qbintype = "log"
    #eq._qmin = 0.0023
    #eq._qmax = 0.034
    eq._showjson = False
    eq._cuttofmin = 1000 # custom tof
    eq._cuttofmax = 2000 # custom tof
    eq._empty = emptybeam_0
    eq._thickness = sample_thick[i]
    eq._bkgscatt = str(bkgscatt_0[i])
    eq._bkgtrans = str(bkgtrans_0[i])
    eq._samscatt = str(samscatt_0[i])
    eq._samtrans = str(samtrans_0[i])
    eq._filename = str(sample_names[i]) + postfix + '_conf0'
    eq._fitinelasticincoh = False
    eq._useerrorweighting = False
    eq._selectminincoh = False
    eq._wavelengthstep = 0.2
    eq._incohfit_qmin = 0.015
    eq._incohfit_qmax = 0.042
    #eq._incohfit_intensityweighted = True
    iqname0 = eq._filename
    reduceNow(eq)
        
    print('...... config 1')
    eq = EQVar()
    eq._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.json'
    eq._outputdir = output_directory
    eq._ipts = ipts_number
    eq._scalecomponents = [1.004251, 1.057915, 1.000000]
    eq._standardabsolutescale = 3.4701 #1.466 #1.3843 #1.3989
    eq._sampleaperturesize = 10
    eq._sampleoffset = 285
    eq._detectoroffset = 66.763
    eq._maskfilename = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/maskWS4m10A.nxs"
    eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/Sensitivity_patched_thinPMMA_4m_186200.nxs"
    eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/EQSANS_186198.nxs.h5"
    eq._beamfluxfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/bl6_flux_2026B_aug_rebinned.txt"
    eq._numqbins = 300
    eq._qbintype = "log"
    #eq._qmin = 0.0023
    #eq._qmax = 0.034
    eq._showjson = False
    eq._cuttofmin = 1000 # custom tof
    eq._cuttofmax = 2000 # custom tof
    eq._empty = emptybeam_1
    eq._thickness = sample_thick[i]
    eq._bkgscatt = str(bkgscatt_1[i])
    eq._bkgtrans = str(bkgtrans_1[i])
    eq._samscatt = str(samscatt_1[i])
    eq._samtrans = str(samtrans_1[i])
    eq._filename = str(sample_names[i]) + postfix + '_conf1'
    eq._fitinelasticincoh = True
    eq._useerrorweighting = False
    eq._selectminincoh = True
    eq._wavelengthstep = 0.2
    eq._incohfit_qmin = 0.08
    eq._incohfit_qmax = 0.09
    eq._outputwavelengthdependentprofile = True
    #eq._incohfit_intensityweighted = True
    iqname1 = eq._filename
    reduceNow(eq)
    
    print('...... config 2')
    eq = EQVar()
    eq._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.json'
    eq._outputdir = output_directory
    eq._ipts = ipts_number
    eq._scalecomponents = [1.004251, 1.057915, 1.000000]
    eq._standardabsolutescale = 3.4701 * 1.194  #1.466 * 1.301 #1.3843 * 1.205 #1.3989 * 1.169
    eq._sampleaperturesize = 10
    eq._sampleoffset = 285
    eq._detectoroffset = 66.763
    eq._maskfilename = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/maskWS2p5m2p5A.nxs"
    eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/Sensitivity_patched_thinPMMA_2o5m_186201.nxs"
    eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/EQSANS_186198.nxs.h5"
    eq._beamfluxfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/bl6_flux_2026B_aug_rebinned.txt"
    eq._numqbins = 300
    eq._qbintype = "log"
    #eq._qmin = 0.0023
    #eq._qmax = 0.034
    eq._showjson = False
    eq._cuttofmin = 1000 # custom tof
    eq._cuttofmax = 2000 # custom tof
    eq._empty = emptybeam_2
    eq._thickness = sample_thick[i]
    eq._bkgscatt = str(bkgscatt_2[i])
    eq._bkgtrans = str(bkgtrans_2[i])
    eq._samscatt = str(samscatt_2[i])
    eq._samtrans = str(samtrans_2[i])
    eq._filename = str(sample_names[i]) + postfix + '_conf2'
    eq._fitinelasticincoh = True
    eq._useerrorweighting = False
    eq._selectminincoh = True
    eq._wavelengthstep = 0.2
    eq._incohfit_qmin = 0.15
    eq._incohfit_qmax = 0.3
    eq._outputwavelengthdependentprofile = True
    #eq._incohfit_intensityweighted = True
    iqname2 = eq._filename
    reduceNow(eq)
    
    
    print('...... config 3')
    eq = EQVar()
    eq._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.json'
    eq._outputdir = output_directory
    eq._ipts = ipts_number
    eq._scalecomponents = [1.004251, 1.057915, 1.000000]
    eq._standardabsolutescale = 3.4701 * 1.313 #1.466 * 1.42  #1.3989 * 1.159
    eq._sampleaperturesize = 10
    eq._sampleoffset = 285
    eq._detectoroffset = 66.763
    eq._maskfilename = f"/SNS/EQSANS/IPTS-{ipts_number}/shared/maskWS1p3m1A.nxs"
    eq._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/Sensitivity_patched_thinPMMA_1o3m_186202.nxs"
    eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/EQSANS_186198.nxs.h5"
    eq._beamfluxfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2026B_mp/bl6_flux_2026B_aug_rebinned.txt"
    eq._numqbins = 300
    eq._qbintype = "log"
    eq._showjson = False
    eq._cuttofmin = 1000 # custom tof
    eq._cuttofmax = 2000 # custom tof
    eq._empty = emptybeam_3
    eq._thickness = sample_thick[i]
    eq._bkgscatt = str(bkgscatt_3[i])
    eq._bkgtrans = str(bkgtrans_3[i])
    eq._samscatt = str(samscatt_3[i])
    eq._samtrans = str(samtrans_3[i])
    eq._filename = str(sample_names[i]) + postfix + '_conf3'
    eq._fitinelasticincoh = True
    eq._useerrorweighting = False
    eq._selectminincoh = True
    eq._wavelengthstep = 0.2
    eq._incohfit_qmin = 0.5
    eq._incohfit_qmax = 0.75
    eq._outputwavelengthdependentprofile = True
    #eq._incohfit_intensityweighted = True
    iqname3 = eq._filename
    reduceNow(eq)
    
    
    print('......stitching...')
    iq0_fn = output_directory + iqname0 + '_Iq.dat'
    iq1_fn = output_directory + iqname1 + '_Iq.dat'
    iq2_fn = output_directory + iqname2 + '_Iq.dat'
    iq3_fn = output_directory + iqname3 + '_Iq.dat'
    iq0 = load_iqmod(iq0_fn, sep='\t', header_type = 'MantidAscii')
    iq1 = load_iqmod(iq1_fn, sep='\t', header_type = 'MantidAscii')
    iq2 = load_iqmod(iq2_fn, sep='\t', header_type = 'MantidAscii')
    iq3 = load_iqmod(iq3_fn, sep='\t', header_type = 'MantidAscii')      
    stitched = stitch_profiles([iq0, iq1, iq2, iq3], overlap[0:6], target_profile_index=1)
    merged_fn = output_directory + 'merged_' + str(sample_names[i]) + postfix + '_Iq.dat'
    save_iqmod(stitched, merged_fn, sep=' ', float_format='%.6E')
    print('......stitching completed.') 
    


end_time = time.time()
print("Total run time: {}s".format(end_time - start_time))
